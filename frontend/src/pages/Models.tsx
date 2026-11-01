import { useState, type FormEvent } from "react";
import { BrainCircuit, Check, ChevronRight, FlaskConical, LoaderCircle, Play, RefreshCw, Target, X } from "lucide-react";
import { api, count, dateTime, errorMessage, label, percent, useResource } from "../api";
import { Badge, DataTable, Heading, Metric, Notice, Panel, Status } from "../components";
import type { Algorithm, Model, User } from "../types";

const algorithms: { id: Algorithm; title: string; description: string }[] = [
  { id: "random_forest", title: "Random Forest", description: "Ensemble classification with feature importance" },
  { id: "logistic_regression", title: "Logistic Regression", description: "An interpretable supervised baseline" },
  { id: "isolation_forest", title: "Isolation Forest", description: "Unsupervised anomaly detection" },
];

export function ModelsPage({ user }: { user: User }) {
  const resource = useResource<{ items: Model[] }>("/api/models");
  const [selected, setSelected] = useState("");
  const [showTraining, setShowTraining] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [source, setSource] = useState("database");
  const [chosen, setChosen] = useState<Algorithm[]>(["random_forest"]);
  const [tab, setTab] = useState("Evaluation");
  const items = resource.data?.items || [];
  const model = items.find((item) => item.id === selected) || items[0];
  const canTrain = user.role === "admin" || user.role === "analyst";
  async function train(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<{ items: Model[]; total_samples: number }>("/api/models/train", {
        method: "POST",
        body: JSON.stringify({ algorithms: chosen, source, sample_limit: Number(form.get("sample_limit")) }),
      });
      setSuccess(`${result.items.length} model(s) trained and saved using ${count(result.total_samples)} ${source === "synthetic" ? "synthetic demo" : "labeled database"} transactions. Evaluation only; no production model was changed.`);
      setSelected(result.items[0].id); setShowTraining(false); resource.refresh();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  const importance = model?.feature_importance.map((value, index) => ({
    name: model.feature_names[index] || `Feature ${index + 1}`, value,
  })).sort((a, b) => b.value - a.value).slice(0, 10) || [];
  return <>
    <Heading eyebrow="EXPLAINABLE INTELLIGENCE" title="Model studio" description="Train with intention. Evaluate with evidence. Understand every signal.">
      <button className="button secondary" onClick={resource.refresh}><RefreshCw size={16} />Refresh models</button>{canTrain && <button className="button primary" onClick={() => { setShowTraining(true); setError(""); }} disabled={busy}><Play size={16} />Train a model</button>}
    </Heading>
    {success && <Notice>{success}</Notice>}
    {!canTrain && <Notice>You have read-only model access. An administrator can grant analyst access to enable training.</Notice>}
    <Status {...resource} retry={resource.refresh} />
    {resource.data && !items.length && <div className="card empty-studio"><div className="empty-icon"><BrainCircuit size={36} /></div><div className="eyebrow">YOUR FIRST MODEL STARTS HERE</div><h2>Turn your data into a clearer signal.</h2><p>No trained models yet. Train a fraud detection model to populate evaluation metrics, feature importance, and a persistent model history.</p>{canTrain && <button className="button primary" onClick={() => setShowTraining(true)}><Play size={16} />Train your first model</button>}<div className="empty-steps"><span><i>01</i>Choose your data</span><ChevronRight size={14} /><span><i>02</i>Train an algorithm</span><ChevronRight size={14} /><span><i>03</i>Inspect the evidence</span></div></div>}
    {model && <>
      <div className="model-toolbar"><div className="model-identity"><div className="model-icon"><BrainCircuit size={25} /></div><div><h2>{label(model.name)}</h2><p>Version {model.version} <span className="muted">/ {dateTime(model.training_date)}</span></p></div><Badge value={model.evaluation_only ? "evaluation only" : "saved"} /></div><label>Saved model<select value={model.id} onChange={(event) => setSelected(event.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{label(item.name)} / {dateTime(item.training_date)}</option>)}</select></label></div>
      <div className="model-provenance"><FlaskConical size={17} /><span><strong>{model.data_source === "synthetic" ? "Synthetic demonstration data" : model.data_source === "database" ? "Labeled database data" : "Data source not recorded"}</strong> / {model.dataset_size == null ? "Training samples not recorded" : `${count(model.dataset_size)} training samples`}{model.total_samples != null && ` / ${count(model.total_samples)} total samples`}</span></div>
      {model.data_source === "synthetic" && <Notice>Demo metrics describe generated data, not real-world fraud detection quality. This model cannot be selected automatically for live scoring.</Notice>}
      <div className="tabs" role="tablist" aria-label="Model information">{["Evaluation", "Training history", "Compare models"].map((item) => <button role="tab" aria-selected={tab === item} key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>
      {tab === "Evaluation" && <>
        <div className="metrics-grid">{([["Precision", model.metrics.precision, "Predicted fraud that was correct"], ["Recall", model.metrics.recall, "Labeled fraud successfully detected"], ["F1 score", model.metrics.f1_score, "Balance of precision and recall"], ["ROC-AUC", model.metrics.roc_auc, "Ranking quality on validation data"]] as const).map(([title, value, note]) => <Metric key={title} title={title} value={percent(value)} note={note} icon={<Target size={18} />} />)}</div>
        <div className="two-columns"><Panel title="What drives this model?" description="Top feature importances from the saved model">{importance.length ? <div className="feature-list">{importance.map((item) => <div className="feature" key={item.name}><div><span>{label(item.name)}</span><strong>{percent(item.value)}</strong></div><div className="feature-track"><span style={{ width: `${Math.min(100, item.value * 100)}%` }} /></div></div>)}</div> : <div className="state">Feature importance was not recorded for this algorithm.</div>}</Panel>
          <Panel title="Validation breakdown" description="Recorded outcomes on the chronological validation split">{model.metrics.confusion_matrix ? <div className="confusion-grid">{Object.entries(model.metrics.confusion_matrix).map(([key, value]) => <div key={key} className={key.startsWith("true") ? "correct" : ""}><span>{label(key)}</span><strong>{count(value)}</strong></div>)}</div> : <div className="state">Confusion matrix was not recorded.</div>}<div className="evaluation-summary"><div><span>Accuracy</span><strong>{percent(model.metrics.accuracy)}</strong></div><div><span>Cross-validation F1</span><strong>{percent(model.cv_mean)}</strong></div><div><span>Artifact status</span><strong><Check size={15} />Saved to disk</strong></div></div></Panel></div>
        <Notice>These are exploratory evaluation metrics from the existing feature pipeline. Review temporal feature leakage and validate against independent real-world data before any production deployment. Training does not deploy a model.</Notice>
      </>}
      {tab === "Training history" && <Panel title="Saved training runs" description="Metadata persists across application restarts"><DataTable rows={items} rowKey={(item) => item.id} columns={[{ title: "Model", cell: (item) => <button className="text-button" onClick={() => { setSelected(item.id); setTab("Evaluation"); }}>{label(item.name)}</button> }, { title: "Trained", cell: (item) => dateTime(item.training_date) }, { title: "Source", cell: (item) => <Badge value={item.data_source} /> }, { title: "Samples", cell: (item) => item.dataset_size == null ? "Not recorded" : count(item.dataset_size) }, { title: "F1 score", cell: (item) => percent(item.metrics.f1_score) }]} /></Panel>}
      {tab === "Compare models" && <Panel title="Model comparison" description="Compare validation scores; different datasets are not directly comparable."><DataTable rows={items} rowKey={(item) => item.id} columns={[{ title: "Model", cell: (item) => <div className="cell-stack"><strong>{label(item.name)}</strong><small>{dateTime(item.training_date)}</small></div> }, { title: "Source", cell: (item) => item.data_source }, ...(["precision", "recall", "f1_score", "roc_auc"] as const).map((key) => ({ title: label(key), cell: (item: Model) => percent(item.metrics[key]) }))]} /></Panel>}
    </>}
    {showTraining && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="training-title" className="modal"><header><div><div className="eyebrow">BUILD AN EVALUATION MODEL</div><h2 id="training-title">Configure training</h2></div><button className="icon-button" disabled={busy} onClick={() => setShowTraining(false)} aria-label="Close training"><X /></button></header><p>Artifacts and metadata are saved on the API server. No live scoring model is replaced.</p><form onSubmit={train}><label>Data source<select value={source} disabled={busy} onChange={(event) => setSource(event.target.value)}><option value="database">Labeled database transactions</option><option value="synthetic">Synthetic demo data</option></select></label>{source === "synthetic" && <Notice>For demonstration only. Generates data in memory without adding transactions to the database. Metrics are not production evidence.</Notice>}<label>Maximum samples<input name="sample_limit" type="number" defaultValue={1000} min={100} max={5000} step={100} required disabled={busy} /></label><small className="muted">100-5,000 samples. Both labels must appear in each chronological split; at least five of each class are required in training.</small><fieldset disabled={busy}><legend>Algorithms</legend>{algorithms.map((algorithm) => <label className={`algorithm-option ${chosen.includes(algorithm.id) ? "chosen" : ""}`} key={algorithm.id}><input type="checkbox" checked={chosen.includes(algorithm.id)} onChange={(event) => setChosen(event.target.checked ? [...chosen, algorithm.id] : chosen.filter((id) => id !== algorithm.id))} /><span><strong>{algorithm.title}</strong><small>{algorithm.description}</small></span></label>)}</fieldset>{error && <Notice error>{error}</Notice>}{busy && <Notice>Training in progress. Keep this page open. This may take a few minutes. If the connection is lost, refresh the registry before retrying.</Notice>}<div className="modal-actions"><button type="button" className="button secondary" onClick={() => setShowTraining(false)} disabled={busy}>Cancel</button><button className="button primary" disabled={busy || !chosen.length}>{busy ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}{busy ? "Training models..." : "Start training"}</button></div></form></section></div>}
  </>;
}

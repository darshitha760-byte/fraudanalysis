import { useState, type FormEvent } from "react";
import { Check, Plus, RefreshCw, ShieldCheck, X } from "lucide-react";
import { api, dateTime, errorMessage, label, useResource } from "../api";
import { Badge, DataTable, ExportButton, Heading, Notice, Pagination, Panel, Status } from "../components";
import type { Alert, AlertDetail, AuditEvent, Paginated, Role, Rule, User } from "../types";

function useAction(refresh: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function run(path: string, method: string, body: object, success: string) {
    setBusy(true); setError(""); setMessage("");
    try {
      await api(path, { method, body: JSON.stringify(body) });
      setMessage(success); refresh(); return true;
    } catch (failure) { setError(errorMessage(failure)); return false; }
    finally { setBusy(false); }
  }
  return { busy, error, message, run };
}

export function AlertsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("PENDING");
  const [selected, setSelected] = useState<number>();
  const resource = useResource<{ alerts: Alert[]; total: number }>(`/api/alerts/status/${status}?limit=20&offset=${(page - 1) * 20}`);
  const detail = useResource<AlertDetail>(selected ? `/api/alerts/${selected}` : null);
  const action = useAction(() => { resource.refresh(); detail.refresh(); });
  async function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (await action.run(`/api/alerts/${selected}/decide`, "PUT", {
      decision: form.get("decision"), justification: form.get("justification"),
    }, "Your review decision has been saved.")) setSelected(undefined);
  }
  return <>
    <Heading eyebrow="ACT ON WHAT MATTERS" title="Fraud review queue" description="Investigate signals, document your reasoning, and close the loop."><button className="button secondary" onClick={resource.refresh}><RefreshCw size={16} />Refresh queue</button></Heading>
    {action.message && <Notice>{action.message}</Notice>}{action.error && !selected && <Notice error>{action.error}</Notice>}
    <Panel title="Alert worklist" description="Select an alert to inspect its evidence and record a decision" action={<label className="inline-label">Status<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>{["PENDING", "UNDER_REVIEW", "RESOLVED", "DISMISSED"].map((value) => <option key={value} value={value}>{label(value.toLowerCase())}</option>)}</select></label>}>
      <Status {...resource} retry={resource.refresh} />{resource.data && <><DataTable rows={resource.data.alerts} rowKey={(row) => row.alert_id} columns={[
        { title: "Alert", cell: (row) => <button className="text-button" onClick={() => setSelected(row.alert_id)}>ALT-{row.alert_id}</button> },
        { title: "Transaction", cell: (row) => `#${row.transaction_id}` },
        { title: "Risk score", cell: (row) => <strong>{row.risk_score.toFixed(0)} / 100</strong> },
        { title: "Risk level", cell: (row) => <Badge value={row.risk_level} /> },
        { title: "Severity", cell: (row) => <Badge value={row.alert_severity} /> },
        { title: "Status", cell: (row) => <Badge value={row.alert_status} /> },
        { title: "Created", cell: (row) => dateTime(row.created_at) },
      ]} /><Pagination page={page} total={resource.data.total} onChange={setPage} /></>}
    </Panel>
    {selected && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="alert-title" className="modal"><header><div><div className="eyebrow">INVESTIGATE & DECIDE</div><h2 id="alert-title">Alert ALT-{selected}</h2></div><button aria-label="Close alert" className="icon-button" disabled={action.busy} onClick={() => setSelected(undefined)}><X /></button></header><Status {...detail} retry={detail.refresh} />{detail.data && <><div className="detail-grid"><div><span>Customer</span><strong>#{detail.data.customer_id}</strong></div><div><span>Risk score</span><strong>{detail.data.risk_score} / 100</strong></div><div><span>Triggered rules</span><strong>{detail.data.triggered_rules.join(", ") || "None recorded"}</strong></div><div><span>Analyst notes</span><strong>{detail.data.analyst_notes || "No notes yet"}</strong></div></div><form onSubmit={decide}><label>Review decision<select name="decision"><option value="REJECTED">Not fraud / false positive</option><option value="APPROVED">Confirm fraud</option><option value="NEEDS_REVIEW">Needs further review</option></select></label><label>Justification<textarea name="justification" minLength={10} required rows={4} placeholder="Document the evidence behind your decision (at least 10 characters)." /></label>{action.error && <Notice error>{action.error}</Notice>}<button className="button primary" disabled={action.busy}><ShieldCheck size={16} />{action.busy ? "Saving..." : "Save review decision"}</button></form></>}</section></div>}
  </>;
}

export function RulesPage({ user }: { user: User }) {
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Rule>();
  const resource = useResource<Paginated<Rule>>(`/fraud/rules?page=${page}&limit=20`);
  const action = useAction(resource.refresh);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (await action.run(`/fraud/rules/${editing?.rule_id}`, "PATCH", {
      name: form.get("name"), description: form.get("description"),
      threshold_value: form.get("threshold_value") ? Number(form.get("threshold_value")) : null,
      risk_weight: Number(form.get("risk_weight")), severity: form.get("severity"),
    }, "Detection rule updated.")) setEditing(undefined);
  }
  const isAdmin = user.role === "admin";
  return <>
    <Heading eyebrow="YOUR DETECTION FRAMEWORK" title="Detection rules" description="Manage the explainable signals in your hybrid fraud engine." />
    {action.message && <Notice>{action.message}</Notice>}{action.error && !editing && <Notice error>{action.error}</Notice>}
    <Panel title="Rule registry" description="Enable, disable, and tune existing rules. Changes affect future assessments.">
      <Status {...resource} retry={resource.refresh} />{resource.data && <><DataTable rows={resource.data.data} rowKey={(row) => row.id} columns={[
        { title: "Rule", cell: (row) => <div className="cell-stack"><button className="text-button" onClick={() => isAdmin && setEditing(row)}>{row.name}</button><small>{row.rule_id} / {label(row.rule_type)}</small></div> },
        { title: "Description", cell: (row) => <span className="description-cell">{row.description}</span> },
        { title: "Severity", cell: (row) => <Badge value={row.severity} /> },
        { title: "Weight", cell: (row) => row.risk_weight },
        { title: "Threshold", cell: (row) => row.threshold_value ?? "Not set" },
        { title: "Enabled", cell: (row) => <button role="switch" aria-checked={row.is_enabled} aria-label={`${row.name} enabled`} className={`toggle ${row.is_enabled ? "on" : ""}`} disabled={action.busy || !isAdmin} onClick={() => isAdmin && void action.run(`/fraud/rules/${row.rule_id}`, "PATCH", { is_enabled: !row.is_enabled }, `${row.name} ${row.is_enabled ? "disabled" : "enabled"}.`)}><span /></button> },
      ]} /><Pagination page={page} total={resource.data.pagination.total} onChange={setPage} /></>}
    </Panel>
    {editing && isAdmin && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="rule-title" className="modal"><header><h2 id="rule-title">Edit {editing.rule_id}</h2><button className="icon-button" aria-label="Close rule" disabled={action.busy} onClick={() => setEditing(undefined)}><X /></button></header><form onSubmit={save}><label>Rule name<input name="name" defaultValue={editing.name} required /></label><label>Description<textarea name="description" defaultValue={editing.description} required rows={3} /></label><div className="two-columns"><label>Risk weight<input name="risk_weight" type="number" min={0} max={100} step="any" defaultValue={editing.risk_weight} required /></label><label>Threshold<input name="threshold_value" type="number" step="any" defaultValue={editing.threshold_value ?? ""} /></label></div><label>Severity<select name="severity" defaultValue={editing.severity}>{["low", "medium", "high", "critical"].map((value) => <option key={value}>{value}</option>)}</select></label>{action.error && <Notice error>{action.error}</Notice>}<button disabled={action.busy} className="button primary"><Check size={16} />Save rule</button></form></section></div>}
  </>;
}

export function UsersPage({ user }: { user: User }) {
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const resource = useResource<User[]>(`/api/users?skip=${(page - 1) * 20}&limit=21`);
  const action = useAction(resource.refresh);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (await action.run("/api/users", "POST", Object.fromEntries(form), "Team member created.")) setAdding(false);
  }
  const isAdmin = user.role === "admin";
  return <>
    <Heading eyebrow="BUILT FOR YOUR TEAM" title="Team members" description="Manage access and assign the right permissions to every operator.">{isAdmin && <button className="button primary" onClick={() => setAdding(true)}><Plus size={16} />Add team member</button>}</Heading>
    {action.message && <Notice>{action.message}</Notice>}{action.error && !adding && <Notice error>{action.error}</Notice>}
    <Panel title="Workspace access" description="Viewers can inspect data. Analysts can review alerts and train models. Admins manage access."><Status {...resource} retry={resource.refresh} />{resource.data && <><DataTable rows={resource.data.slice(0, 20)} rowKey={(row) => row.id} columns={[
      { title: "Team member", cell: (row) => <div className="cell-stack"><strong>{row.full_name}{row.id === user.id ? " (you)" : ""}</strong><small>{row.email}</small></div> },
      { title: "Role", cell: (row) => <select aria-label={`Role for ${row.email}`} value={row.role} disabled={action.busy || row.id === user.id || !isAdmin} onChange={(event) => void action.run(`/api/users/${row.id}`, "PUT", { role: event.target.value as Role }, "Role updated.")}>{["viewer", "analyst", "admin"].map((role) => <option key={role}>{role}</option>)}</select> },
      { title: "Account status", cell: (row) => <Badge value={row.is_active ? "active" : "inactive"} /> },
      { title: "Access", cell: (row) => isAdmin ? <button className="button secondary" disabled={action.busy || row.id === user.id} onClick={() => void action.run(`/api/users/${row.id}`, "PATCH", { is_active: !row.is_active }, "Account access updated.")}>{row.is_active ? "Deactivate" : "Activate"}</button> : <span className="text-muted">-</span> },
    ]} /><div className="pagination"><span>Page {page}</span><div><button className="button secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><button className="button secondary" disabled={resource.data.length <= 20} onClick={() => setPage(page + 1)}>Next</button></div></div></>}</Panel>
    {adding && isAdmin && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="user-title" className="modal"><header><h2 id="user-title">Add team member</h2><button className="icon-button" aria-label="Close team member form" disabled={action.busy} onClick={() => setAdding(false)}><X /></button></header><form onSubmit={create}><label>Full name<input name="full_name" required maxLength={255} /></label><label>Email address<input name="email" type="email" required /></label><label>Initial password<input name="password" type="password" minLength={8} required autoComplete="new-password" /></label><label>Role<select name="role" defaultValue="viewer"><option>viewer</option><option>analyst</option><option>admin</option></select></label>{action.error && <Notice error>{action.error}</Notice>}<button className="button primary" disabled={action.busy}>Create team member</button></form></section></div>}
  </>;
}

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState("");
  const resource = useResource<{ items: AuditEvent[]; total: number }>(`/api/audit-logs?skip=${(page - 1) * 20}&limit=20${filters}`);
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    new FormData(event.currentTarget).forEach((value, key) => { if (value) params.set(key, String(value)); });
    setPage(1); setFilters(params.size ? `&${params}` : "");
  }
  return <>
    <Heading eyebrow="ACCOUNTABILITY AT EVERY STEP" title="Audit trail" description="A persisted record of access, changes, and operational decisions."><ExportButton rows={(resource.data?.items || []).map((row) => ({ ...row }))} filename="audit-events" /></Heading>
    <Panel title="Workspace events" description="Search the persisted audit log"><form className="filter-bar" onSubmit={search}><label>Actor email<input name="actor" type="email" placeholder="All team members" /></label><label>Action<input name="action" placeholder="e.g. login, update" /></label><label>From<input name="start_date" type="date" /></label><label>To<input name="end_date" type="date" /></label><button className="button primary">Apply filters</button></form><Status {...resource} retry={resource.refresh} />{resource.data && <><DataTable rows={resource.data.items} rowKey={(row) => row.id} columns={[
      { title: "Timestamp", cell: (row) => dateTime(row.timestamp) },
      { title: "Actor", cell: (row) => row.actor },
      { title: "Action", cell: (row) => label(row.action) },
      { title: "Target", cell: (row) => `${row.target_type} ${row.target_id || ""}` },
      { title: "Status", cell: (row) => <Badge value={row.status} /> },
      { title: "Details", cell: (row) => row.details || "-" },
    ]} /><Pagination page={page} total={resource.data.total} onChange={setPage} /></>}</Panel>
  </>;
}

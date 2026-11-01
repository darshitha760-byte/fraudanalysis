"""Inspect metrics and history from saved model training artifacts."""

import pandas as pd
import streamlit as st

from components import AuthHandler, create_bar_chart, display_chart_with_error_handling
from utils import show_error_message


def format_score(value):
    """Evaluation metrics are fractions, not percentages."""
    return f"{value:.2%}" if value is not None else "Not recorded"


def main():
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return
    if not AuthHandler.has_permission("view_models"):
        st.error("You don't have permission to view this page")
        return

    st.markdown("## 🤖 Model Performance")
    client = AuthHandler.get_api_client()
    if AuthHandler.has_permission("train_models"):
        with st.expander("Train a model"):
            st.caption("Evaluation training only. Saved models are not automatically deployed.")
            with st.form("model_training"):
                algorithms = st.multiselect(
                    "Algorithms", ["random_forest", "logistic_regression", "isolation_forest"],
                    default=["random_forest"],
                )
                source = st.selectbox("Training data", ["database", "synthetic"])
                sample_limit = st.number_input("Maximum samples", min_value=100, max_value=5000, value=1000, step=100)
                st.caption("Synthetic data is for demonstration only and is never inserted into your database.")
                submitted = st.form_submit_button("Start training")
            if submitted:
                if not algorithms:
                    st.error("Select at least one algorithm.")
                else:
                    with st.spinner("Training and saving model artifacts..."):
                        result = client.train_models(algorithms, source, int(sample_limit))
                    if "error" in result:
                        show_error_message("Unable to train models", result["error"])
                    else:
                        st.success(f"Saved {len(result['items'])} model(s). Select one below to inspect its metrics.")
                        st.session_state.pop("current_model", None)
    response = client.get_models()
    if "error" in response:
        show_error_message("Unable to load models", response["error"])
        return

    models = response["items"]
    if not models:
        st.info(
            "No trained models are available in the API's models directory yet. "
            "Train a model and save its model artifact and JSON training metadata "
            "before loading performance metrics."
        )
        return

    by_id = {model["id"]: model for model in models}
    selected_id = st.selectbox(
        "Saved model",
        list(by_id),
        format_func=lambda model_id: (
            f"{by_id[model_id]['name']} · {by_id[model_id]['version']}"
        ),
    )
    current, history, comparison = st.tabs(
        ["Selected Model", "Training History", "Model Comparison"]
    )
    with current:
        if st.button("🔄 Load Model Metrics", use_container_width=True):
            st.session_state.pop("current_model", None)
            result = client.get_model_metrics(selected_id)
            if "error" in result:
                show_error_message("Unable to load metrics", result["error"])
            else:
                st.session_state.current_model = result

        model = st.session_state.get("current_model")
        if model and model["id"] == selected_id:
            st.caption(
                f"Trained: {model.get('training_date') or 'Not recorded'} | "
                f"Training samples: {model.get('dataset_size') or 'Not recorded'} | "
                f"Data source: {model.get('data_source', 'Not recorded')}"
            )
            metrics = model["metrics"]
            if metrics:
                for column, (label, key) in zip(
                    st.columns(4),
                    [("Accuracy", "accuracy"), ("Precision", "precision"),
                     ("Recall", "recall"), ("F1 Score", "f1_score")],
                ):
                    column.metric(label, format_score(metrics.get(key)))
                auc = metrics.get("roc_auc")
                st.metric("ROC-AUC", f"{auc:.3f}" if auc is not None else "Not recorded")
                confusion = metrics.get("confusion_matrix")
                if confusion:
                    st.subheader("Confusion matrix")
                    st.json(confusion)
            else:
                st.info("Validation metrics were not recorded for this model.")
            if model.get("cv_mean") is not None:
                st.metric("Cross-validation F1 (mean)", format_score(model["cv_mean"]))

            features = model.get("feature_importance", [])
            names = model.get("feature_names", [])
            if features:
                feature_data = [
                    {"feature_name": names[i] if i < len(names) else f"Feature {i + 1}",
                     "importance": value}
                    for i, value in enumerate(features)
                ]
                display_chart_with_error_handling(
                    create_bar_chart,
                    sorted(feature_data, key=lambda item: item["importance"], reverse=True)[:10],
                    "Feature importance", "feature_name", "importance",
                    "Feature", "Importance", horizontal=True,
                )
        else:
            st.caption("Choose a saved model and select Load Model Metrics.")

    with history:
        st.dataframe(
            pd.DataFrame([
                {"Model": model["name"], "Version": model["version"],
                 "Trained": model["training_date"],
                 "Training samples": model["dataset_size"],
                 "F1 Score": format_score(model["metrics"].get("f1_score"))}
                for model in models
            ]),
            use_container_width=True,
            hide_index=True,
        )
    with comparison:
        if len(models) < 2:
            st.info("At least two saved models are needed for comparison.")
        else:
            selected = st.multiselect(
                "Models to compare", list(by_id), default=list(by_id)[:2]
            )
            if len(selected) >= 2:
                st.dataframe(pd.DataFrame({
                    model_id: {
                        key: format_score(by_id[model_id]["metrics"].get(key))
                        for key in ("accuracy", "precision", "recall", "f1_score", "roc_auc")
                    }
                    for model_id in selected
                }), use_container_width=True)


if __name__ == "__main__":
    main()

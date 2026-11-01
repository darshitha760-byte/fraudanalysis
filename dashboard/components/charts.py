"""
Chart components for the dashboard
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
from config import CHART_HEIGHT, CHART_COLOR_SCHEME, CHART_CONFIG
from utils import get_risk_color, format_currency, format_percentage


def create_kpi_card(title: str, value: str, subtext: str = "", icon: str = ""):
    """Create a KPI card with title and value."""
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {icon} {title}")
            st.markdown(f"## {value}")
            if subtext:
                st.markdown(f"*{subtext}*")
        with col2:
            st.empty()


def create_metric_row(
    col1_title: str,
    col1_value: str,
    col2_title: str,
    col2_value: str,
    col3_title: str = None,
    col3_value: str = None,
):
    """Create a row of metric cards."""
    if col3_title:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(col1_title, col1_value)
        with col2:
            st.metric(col2_title, col2_value)
        with col3:
            st.metric(col3_title, col3_value)
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric(col1_title, col1_value)
        with col2:
            st.metric(col2_title, col2_value)


def create_pie_chart(
    data: List[Dict[str, Any]],
    title: str,
    labels_key: str = "name",
    values_key: str = "count",
) -> go.Figure:
    """Create pie chart."""
    if not data or len(data) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No data available")
        return fig

    labels = [item.get(labels_key, "Unknown") for item in data]
    values = [item.get(values_key, 0) for item in data]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                marker=dict(colors=px.colors.qualitative.Set3),
                textposition="inside",
                textinfo="label+percent",
            )
        ]
    )

    fig.update_layout(
        title=title,
        height=CHART_HEIGHT,
        showlegend=True,
        hovermode="closest",
    )

    return fig


def create_line_chart(
    data: List[Dict[str, Any]],
    title: str,
    x_key: str = "date",
    y_key: str = "count",
    x_label: str = "Date",
    y_label: str = "Count",
) -> go.Figure:
    """Create line chart."""
    if not data or len(data) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No data available")
        return fig

    x_values = [item.get(x_key) for item in data]
    y_values = [item.get(y_key, 0) for item in data]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="lines+markers",
            name="Trend",
            line=dict(color=CHART_COLOR_SCHEME["primary"], width=2),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor=f"rgba(0, 102, 204, 0.2)",
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        height=CHART_HEIGHT,
        hovermode="x unified",
        showlegend=False,
    )

    return fig


def create_bar_chart(
    data: List[Dict[str, Any]],
    title: str,
    x_key: str = "name",
    y_key: str = "count",
    x_label: str = "Category",
    y_label: str = "Count",
    horizontal: bool = False,
) -> go.Figure:
    """Create bar chart."""
    if not data or len(data) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No data available")
        return fig

    x_values = [item.get(x_key, "Unknown") for item in data]
    y_values = [item.get(y_key, 0) for item in data]

    if horizontal:
        fig = go.Figure(
            data=[
                go.Bar(
                    y=x_values,
                    x=y_values,
                    orientation="h",
                    marker=dict(color=CHART_COLOR_SCHEME["primary"]),
                    text=y_values,
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(
            title=title,
            xaxis_title=y_label,
            yaxis_title=x_label,
            height=CHART_HEIGHT,
            yaxis=dict(autorange="reversed"),
        )
    else:
        fig = go.Figure(
            data=[
                go.Bar(
                    x=x_values,
                    y=y_values,
                    marker=dict(color=CHART_COLOR_SCHEME["primary"]),
                    text=y_values,
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(
            title=title,
            xaxis_title=x_label,
            yaxis_title=y_label,
            height=CHART_HEIGHT,
        )

    return fig


def create_histogram(
    data: List[Dict[str, Any]],
    title: str,
    value_key: str = "amount",
    nbins: int = 20,
    x_label: str = "Amount",
) -> go.Figure:
    """Create histogram."""
    if not data or len(data) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No data available")
        return fig

    values = [item.get(value_key, 0) for item in data]

    fig = go.Figure(
        data=[
            go.Histogram(
                x=values,
                nbinsx=nbins,
                marker=dict(color=CHART_COLOR_SCHEME["info"]),
            )
        ]
    )

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title="Frequency",
        height=CHART_HEIGHT,
        showlegend=False,
    )

    return fig


def create_risk_distribution_chart(risk_data: Dict[str, int]) -> go.Figure:
    """Create risk level distribution pie chart."""
    levels = list(risk_data.keys())
    counts = list(risk_data.values())
    colors = [
        CHART_COLOR_SCHEME["risk_low"] if level == "low" else
        CHART_COLOR_SCHEME["risk_low"] if level == "LOW" else
        CHART_COLOR_SCHEME["risk_medium"] if level in ["medium", "MEDIUM"] else
        CHART_COLOR_SCHEME["risk_high"] if level in ["high", "HIGH"] else
        CHART_COLOR_SCHEME["risk_high"]
        for level in levels
    ]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=levels,
                values=counts,
                marker=dict(colors=colors),
                textposition="inside",
                textinfo="label+value",
            )
        ]
    )

    fig.update_layout(
        title="Risk Distribution",
        height=CHART_HEIGHT,
        showlegend=True,
    )

    return fig


def create_heatmap(
    data: pd.DataFrame,
    title: str,
    x_col: str = None,
    y_col: str = None,
    z_col: str = None,
) -> go.Figure:
    """Create heatmap chart."""
    if data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available")
        return fig

    fig = go.Figure(
        data=go.Heatmap(
            z=data[z_col],
            x=data[x_col],
            y=data[y_col],
            colorscale="RdYlGn_r",
            colorbar=dict(title="Intensity"),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title=x_col,
        yaxis_title=y_col,
        height=CHART_HEIGHT,
    )

    return fig


def create_scatter_chart(
    data: List[Dict[str, Any]],
    title: str,
    x_key: str = "x",
    y_key: str = "y",
    color_key: str = None,
    size_key: str = None,
    x_label: str = "X",
    y_label: str = "Y",
) -> go.Figure:
    """Create scatter plot."""
    if not data or len(data) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No data available")
        return fig

    x_values = [item.get(x_key, 0) for item in data]
    y_values = [item.get(y_key, 0) for item in data]

    kwargs = {
        "x": x_values,
        "y": y_values,
        "mode": "markers",
        "marker": dict(size=8, color=CHART_COLOR_SCHEME["primary"]),
    }

    if color_key:
        color_values = [item.get(color_key, 0) for item in data]
        kwargs["marker"]["color"] = color_values
        kwargs["marker"]["colorscale"] = "Viridis"
        kwargs["marker"]["showscale"] = True

    if size_key:
        size_values = [max(5, item.get(size_key, 1)) for item in data]
        kwargs["marker"]["size"] = size_values

    fig = go.Figure(data=[go.Scatter(**kwargs)])

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        height=CHART_HEIGHT,
        hovermode="closest",
    )

    return fig


def display_chart_with_error_handling(chart_func, *args, **kwargs):
    """Display chart with error handling."""
    try:
        fig = chart_func(*args, **kwargs)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    except Exception as e:
        st.error(f"Error creating chart: {str(e)}")

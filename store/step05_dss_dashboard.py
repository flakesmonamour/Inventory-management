"""
============================================================
MARK WAMBUGU  |  DDA-01-0142/2025
LSTM & SVR Stock-Level Prediction — Perishable Goods

WORKFLOW STEP 05: DSS Dashboard Deploy
  Streamlit · Plotly · MySQL · Reorder alerts · Expiry risk
============================================================
Run with:  streamlit run step05_dss_dashboard.py
============================================================
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "raw")

def p(path):
    return os.path.join(BASE_DIR, path)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import pickle
import re
import warnings
import xmlrpc.client
warnings.filterwarnings('ignore')

THEMES = {
    "Light": {
        "app_bg": "#f5f1e8",
        "sidebar_bg": "#ece4d5",
        "card_bg": "#fffdf8",
        "paper_bg": "#fffdf8",
        "plot_bg": "#f7f3eb",
        "text": "#18212b",
        "muted_text": "#5f6b76",
        "grid": "#d9d0c3",
        "border": "#d6ccbf",
        "primary": "#223a5e",
        "secondary": "#bb5a3c",
        "accent": "#64866f",
        "success": "#2c7a4b",
        "warning": "#bf7f1f",
        "danger": "#b14545",
        "info": "#4d6f95",
    },
    "Dark": {
        "app_bg": "#11161b",
        "sidebar_bg": "#17202a",
        "card_bg": "#1b2630",
        "paper_bg": "#182028",
        "plot_bg": "#121820",
        "text": "#edf2f7",
        "muted_text": "#a5b2bf",
        "grid": "#30414f",
        "border": "#2a3946",
        "primary": "#9fc0ff",
        "secondary": "#ff9b71",
        "accent": "#8fc4a6",
        "success": "#78d39b",
        "warning": "#ffd166",
        "danger": "#ff7b72",
        "info": "#7db6ff",
    },
}

DEBUG_DASHBOARD = os.getenv("DSS_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}

try:
    import mysql.connector as mysql_connector
    MYSQL_CONNECTOR_IMPORT_ERROR = None
except Exception as exc:
    mysql_connector = None
    MYSQL_CONNECTOR_IMPORT_ERROR = exc

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Stock-Level DSS | Mark Wambugu DDA-01-0142/2025",
    layout="wide",
    initial_sidebar_state="expanded"
)


def _get_app_theme_name():
    configured = os.getenv("DSS_THEME", "").strip().title()
    if configured in THEMES:
        return configured

    try:
        active_theme = (st.context.theme or {}).get("type", "")
        active_theme = str(active_theme).strip().title()
        if active_theme in THEMES:
            return active_theme
    except Exception:
        pass

    try:
        base_theme = (st.get_option("theme.base") or "").strip().title()
    except Exception:
        base_theme = ""

    return "Dark" if base_theme == "Dark" else "Light"


theme_name = _get_app_theme_name()
theme = THEMES[theme_name]


def _hex_to_rgba(hex_color, alpha):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _apply_plotly_theme(fig, height=None, horizontal_legend=False):
    legend = dict(font=dict(color=theme["text"]), bgcolor="rgba(0,0,0,0)")
    if horizontal_legend:
        legend.update(dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

    fig.update_layout(
        height=height,
        plot_bgcolor=theme["plot_bg"],
        paper_bgcolor=theme["paper_bg"],
        font=dict(color=theme["text"]),
        legend=legend,
        hoverlabel=dict(bgcolor=theme["card_bg"], font_color=theme["text"]),
    )
    fig.update_xaxes(gridcolor=theme["grid"], linecolor=theme["border"], zerolinecolor=theme["grid"])
    fig.update_yaxes(gridcolor=theme["grid"], linecolor=theme["border"], zerolinecolor=theme["grid"])


def _apply_matplotlib_theme():
    sns.set_theme(
        style="whitegrid" if theme_name == "Light" else "darkgrid",
        rc={
            "figure.facecolor": theme["paper_bg"],
            "axes.facecolor": theme["paper_bg"],
            "axes.edgecolor": theme["border"],
            "axes.labelcolor": theme["text"],
            "axes.titlecolor": theme["text"],
            "xtick.color": theme["text"],
            "ytick.color": theme["text"],
            "grid.color": theme["grid"],
            "text.color": theme["text"],
        },
    )


def _build_chart_frame(frame, resolution):
    chart_frame = frame.sort_values("Date").copy()
    multiple_rows_per_day = chart_frame.groupby("Date").size().max() > 1
    if multiple_rows_per_day:
        chart_frame = (
            chart_frame.groupby("Date", as_index=False)
            .agg({
                "Actual": "mean",
                "LSTM_Predicted": "mean",
                "SVR_Predicted": "mean",
                "Inventory_Level": "mean",
            })
            .sort_values("Date")
        )

    if resolution != "Daily":
        resample_rule = "W" if resolution == "Weekly" else "MS"
        chart_frame = (
            chart_frame.set_index("Date")
            .resample(resample_rule)
            .mean(numeric_only=True)
            .reset_index()
        )
    return chart_frame, multiple_rows_per_day


def _status_box(message, tone):
    st.markdown(f'<div class="status-box status-box--{tone}">{message}</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
    :root {{
        --theme-app-bg: {theme['app_bg']};
        --theme-sidebar-bg: {theme['sidebar_bg']};
        --theme-card-bg: {theme['card_bg']};
        --theme-paper-bg: {theme['paper_bg']};
        --theme-plot-bg: {theme['plot_bg']};
        --theme-text: {theme['text']};
        --theme-muted: {theme['muted_text']};
        --theme-grid: {theme['grid']};
        --theme-border: {theme['border']};
        --theme-primary: {theme['primary']};
    }}
    .stApp {{ background: {theme['app_bg']}; color: {theme['text']}; }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] {{ background: {theme['sidebar_bg']}; }}
    [data-testid="stSidebar"] > div {{ background: {theme['sidebar_bg']}; }}
    [data-testid="stSidebar"] * {{ color: {theme['text']}; }}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ color: {theme['text']}; }}
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {{ color: {theme['text']} !important; }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="base-input"] > div,
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea {{
        background: {theme['card_bg']} !important;
        color: {theme['text']} !important;
        border-color: {theme['border']} !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] svg,
    [data-testid="stSidebar"] [data-baseweb="popover"] svg,
    [data-testid="stSidebar"] [role="radiogroup"] svg {{
        fill: {theme['text']} !important;
        color: {theme['text']} !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div > div,
    [data-testid="stSidebar"] [data-baseweb="base-input"] > div > div {{
        color: {theme['text']} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stDateInputField"] {{
        background: {theme['card_bg']} !important;
    }}
    [data-testid="stSidebar"] hr {{ border-color: {theme['border']}; }}
    [data-testid="stSidebar"] .stAlert {{
        background: {_hex_to_rgba(theme['info'], 0.12)};
        color: {theme['text']};
        border: 1px solid {theme['border']};
    }}
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p,
    .stTabs [data-baseweb="tab-list"] button {{ color: {theme['text']} !important; }}
    .stSelectbox label,
    .stRadio label,
    .stDateInput label,
    .stTextInput label,
    .stNumberInput label,
    .stCaption,
    .stMarkdown,
    .stText,
    .stSubheader,
    .stHeader {{ color: {theme['text']}; }}
    [data-testid="stMetricValue"] {{ font-size: 2rem; font-weight: 700; }}
    div[data-testid="stMetric"] {{
        background: {theme['card_bg']};
        border: 1px solid {theme['border']};
        border-radius: 12px;
        padding: 0.8rem;
    }}
    .status-box {{
        padding: 10px 16px;
        border-radius: 10px;
        margin: 6px 0;
        border-left: 5px solid transparent;
        color: {theme['text']};
    }}
    .status-box--success {{
        background: {_hex_to_rgba(theme['success'], 0.14)};
        border-left-color: {theme['success']};
    }}
    .status-box--warning {{
        background: {_hex_to_rgba(theme['warning'], 0.14)};
        border-left-color: {theme['warning']};
    }}
    .status-box--danger {{
        background: {_hex_to_rgba(theme['danger'], 0.14)};
        border-left-color: {theme['danger']};
    }}
    .stDataFrame, .stTable {{
        background: {theme['card_bg']};
        color: {theme['text']};
    }}
    h1, h2, h3, h4, h5, h6 {{ color: {theme['text']}; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.title("Stock-Level Prediction DSS")
st.markdown("**LSTM & SVR Forecasting System** · Mark Wambugu · DDA-01-0142/2025")
st.markdown("---")


# ─────────────────────────────────────────────
# HELPERS — flexible CSV / XLS reader
# ─────────────────────────────────────────────
def _read_flexible(path, **kwargs):
    """
    Read a file that may be a true CSV or an .xls/.csv file saved with the
    wrong extension (Step 04 saves .xls files that are actually CSVs).
    Falls back through pd.read_csv → pd.read_excel automatically.
    """
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return pd.read_excel(path, **kwargs)


def _load_history_file(language="Python"):
    history = None
    candidates = (
        [os.path.join(RAW_DIR, "lstm_training_history_R.csv"), p("lstm_training_history_R.csv")]
        if language == "R"
        else [os.path.join(RAW_DIR, "lstm_training_history.xls"), p("lstm_training_history.csv")]
    )
    for h in candidates:
        if os.path.exists(h):
            try:
                history = _read_flexible(h)
            except Exception:
                pass
            break
    return history


def _get_secret_section(name):
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:
        return {}


def _debug_log(*args):
    if DEBUG_DASHBOARD:
        print(*args)


def _get_db_defaults():
    secret_db = _get_secret_section("mysql")
    return {
        "host": os.getenv("MYSQL_HOST", secret_db.get("host", "localhost")),
        "port": int(os.getenv("MYSQL_PORT", secret_db.get("port", 3306))),
        "user": os.getenv("MYSQL_USER", secret_db.get("user", "root")),
        "password": os.getenv("MYSQL_PASSWORD", secret_db.get("password", "")),
        "database": os.getenv("MYSQL_DATABASE", secret_db.get("database", "mini_market_dss")),
    }


def _get_odoo_defaults():
    secret_db = _get_secret_section("odoo")
    return {
        "base_url": os.getenv("ODOO_BASE_URL", secret_db.get("base_url", secret_db.get("url", ""))),
        "database": os.getenv("ODOO_DATABASE", secret_db.get("database", "")),
        "username": os.getenv("ODOO_USERNAME", secret_db.get("username", "")),
        "password": os.getenv("ODOO_PASSWORD", secret_db.get("password", "")),
        "api_key": os.getenv("ODOO_API_KEY", secret_db.get("api_key", "")),
    }


def _extract_store_id(location_name):
    match = re.search(r"Store\s+(S\d+)", str(location_name))
    return match.group(1) if match else None


def _normalize_inventory_levels(series):
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    max_value = numeric.max()
    if pd.isna(max_value) or max_value <= 0:
        return pd.Series(np.zeros(len(numeric)), index=series.index, dtype=float)
    return (numeric / max_value).clip(0, 1)


def _latest_forecast_snapshot(pred):
    latest_date = pred["Date"].max()
    snapshot = pred[pred["Date"] == latest_date].copy()
    snapshot = snapshot.sort_values(["Store ID", "Product ID"]).reset_index(drop=True)
    snapshot.attrs["forecast_snapshot_date"] = latest_date
    return snapshot


def _init_saved_config(key, defaults):
    if key not in st.session_state:
        st.session_state[key] = dict(defaults)
    else:
        merged = dict(defaults)
        merged.update(st.session_state[key])
        st.session_state[key] = merged
    return dict(st.session_state[key])


def _save_config(key, config):
    st.session_state[key] = dict(config)


def _database_config_ready(config):
    return bool(config and config.get("host") and config.get("user") and config.get("database"))


def _odoo_config_ready(config):
    return bool(
        config
        and config.get("base_url")
        and config.get("database")
        and config.get("username")
        and (config.get("password") or config.get("api_key"))
    )


def _normalize_prediction_df(pred):
    pred = pred.copy()
    pred.rename(columns={
        "forecast_date": "Date",
        "store_id": "Store ID",
        "product_id": "Product ID",
        "actual_sold": "Actual",
        "lstm_predicted": "LSTM_Predicted",
        "svr_predicted": "SVR_Predicted",
        "inventory_level": "Inventory_Level",
        "reorder_alert": "Reorder_Alert",
        "expiry_risk": "Expiry_Risk",
    }, inplace=True)

    expected_columns = [
        "Date", "Store ID", "Product ID", "Actual", "LSTM_Predicted",
        "SVR_Predicted", "Inventory_Level", "Reorder_Alert", "Expiry_Risk"
    ]
    for column in expected_columns:
        if column not in pred.columns:
            pred[column] = np.nan

    pred["Date"] = pd.to_datetime(pred["Date"], errors="coerce")
    pred = pred.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return pred[expected_columns]


def _normalize_metrics_df(metrics):
    metrics = metrics.copy()
    metrics.rename(columns={
        "model_name": "Model",
        "smape_pct": "sMAPE (%)",
        "mape_pct": "MAPE (%)",
        "accuracy_pct": "Accuracy (%)",
        "run_date": "Run Date",
        "created_at": "Created At",
        "rmse": "RMSE",
    }, inplace=True)

    if "Created At" in metrics.columns:
        metrics["Created At"] = pd.to_datetime(metrics["Created At"], errors="coerce")
    if "Run Date" in metrics.columns:
        metrics["Run Date"] = pd.to_datetime(metrics["Run Date"], errors="coerce")

    if "Model" in metrics.columns:
        sort_columns = [column for column in ["Run Date", "Created At"] if column in metrics.columns]
        if sort_columns:
            metrics = metrics.sort_values(sort_columns, ascending=False)
        metrics = metrics.drop_duplicates(subset=["Model"], keep="first")

    return metrics.reset_index(drop=True)


def _ensure_prediction_columns(pred, cleaned=None):
    """
    Guarantee that pred has every column the dashboard tabs rely on:
    Date, Store ID, Product ID, Actual, LSTM_Predicted, SVR_Predicted,
    Inventory_Level, Reorder_Alert, Expiry_Risk.

    This is a safety net so the dashboard never crashes with a KeyError just
    because a particular pipeline (Python, R, a future one) used slightly
    different column names or forgot to compute a derived column. It repairs
    what it can from common alternate names, then computes anything still
    missing from what IS available, rather than assuming the source file is
    exactly right.
    """
    pred = pred.copy()

    # 1. Normalize column names: strip whitespace, and map common variants
    #    (e.g. "LSTM_Pred" from an earlier pipeline version) onto the
    #    canonical names the rest of the dashboard expects.
    pred.columns = [str(c).strip() for c in pred.columns]
    rename_map = {
        "LSTM_Pred": "LSTM_Predicted",
        "LSTM Predicted": "LSTM_Predicted",
        "SVR_Pred": "SVR_Predicted",
        "SVR Predicted": "SVR_Predicted",
        "Inventory Level": "Inventory_Level",
        "Reorder Alert": "Reorder_Alert",
        "Expiry Risk": "Expiry_Risk",
    }
    pred.rename(columns={k: v for k, v in rename_map.items() if k in pred.columns}, inplace=True)

    required_ids = ["Date", "Store ID", "Product ID", "Actual"]
    missing_ids = [c for c in required_ids if c not in pred.columns]
    if missing_ids:
        # These can't be safely fabricated — fail loudly and specifically
        # instead of letting a downstream tab crash with a cryptic KeyError.
        raise KeyError(
            f"Prediction data is missing required column(s) {missing_ids}. "
            "Check that the pipeline that generated this file writes these columns."
        )

    # 2. Inventory_Level: derive from the cleaned dataset if not present.
    if "Inventory_Level" not in pred.columns or pred["Inventory_Level"].isna().all():
        derived = None
        if cleaned is not None:
            inv_col = next((c for c in ["Inventory_Level", "Inventory Level", "Inventory.Level"] if c in cleaned.columns), None)
            if inv_col is not None:
                key_cols = [c for c in ["Date", "Store ID", "Product ID"] if c in cleaned.columns]
                if len(key_cols) == 3:
                    lookup = cleaned[key_cols + [inv_col]].rename(columns={inv_col: "Inventory_Level"})
                    pred = pred.drop(columns=["Inventory_Level"], errors="ignore").merge(
                        lookup, on=key_cols, how="left"
                    )
                    derived = True
        if derived is None:
            pred["Inventory_Level"] = 0.0

    # 3. LSTM_Predicted / SVR_Predicted: if genuinely absent, fall back to
    #    whichever prediction column IS available rather than crashing charts.
    if "LSTM_Predicted" not in pred.columns:
        pred["LSTM_Predicted"] = pred["SVR_Predicted"] if "SVR_Predicted" in pred.columns else np.nan
    if "SVR_Predicted" not in pred.columns:
        pred["SVR_Predicted"] = pred["LSTM_Predicted"]

    pred["Inventory_Level"] = pd.to_numeric(pred["Inventory_Level"], errors="coerce").fillna(0.0)
    pred["LSTM_Predicted"] = pd.to_numeric(pred["LSTM_Predicted"], errors="coerce")
    pred["SVR_Predicted"] = pd.to_numeric(pred["SVR_Predicted"], errors="coerce")

    # 4. Reorder_Alert / Expiry_Risk: compute from the same rule used
    #    everywhere else in the dashboard if the pipeline didn't provide them.
    demand_signal = pred["LSTM_Predicted"].fillna(pred["SVR_Predicted"]).fillna(0.0)
    if "Reorder_Alert" not in pred.columns or pred["Reorder_Alert"].isna().all():
        pred["Reorder_Alert"] = (demand_signal > (pred["Inventory_Level"] * 0.70)).astype(int)
    if "Expiry_Risk" not in pred.columns or pred["Expiry_Risk"].isna().all():
        pred["Expiry_Risk"] = ((pred["Inventory_Level"] > 0.60) & (demand_signal < 0.30)).astype(int)

    pred["Reorder_Alert"] = pd.to_numeric(pred["Reorder_Alert"], errors="coerce").fillna(0).astype(int)
    pred["Expiry_Risk"] = pd.to_numeric(pred["Expiry_Risk"], errors="coerce").fillna(0).astype(int)

    pred["Date"] = pd.to_datetime(pred["Date"], errors="coerce")
    pred["Store ID"] = pred["Store ID"].astype(str)
    pred["Product ID"] = pred["Product ID"].astype(str)
    pred = pred.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

    return pred


def _ensure_metrics_columns(metrics):
    """
    Guarantee metrics_df has the columns the Model Metrics tab relies on:
    Model, sMAPE (%) or MAPE (%), RMSE, Accuracy (%).

    Same rationale as _ensure_prediction_columns: different pipelines
    (Python, R, future ones) may write "sMAPE" instead of "sMAPE (%)", etc.
    Normalize known variants and derive anything still missing rather than
    trusting the source file to match exactly.
    """
    metrics = metrics.copy()
    metrics.columns = [str(c).strip() for c in metrics.columns]

    rename_map = {
        "sMAPE": "sMAPE (%)",
        "SMAPE": "sMAPE (%)",
        "smape": "sMAPE (%)",
        "MAPE": "MAPE (%)",
        "mape": "MAPE (%)",
        "Accuracy": "Accuracy (%)",
        "accuracy": "Accuracy (%)",
        "model": "Model",
        "rmse": "RMSE",
    }
    metrics.rename(columns={k: v for k, v in rename_map.items() if k in metrics.columns}, inplace=True)

    if "Model" not in metrics.columns:
        raise KeyError("Metrics data is missing required column 'Model'.")

    if "RMSE" not in metrics.columns:
        metrics["RMSE"] = np.nan

    smape_col = "sMAPE (%)" if "sMAPE (%)" in metrics.columns else ("MAPE (%)" if "MAPE (%)" in metrics.columns else None)
    if smape_col is None:
        metrics["sMAPE (%)"] = np.nan
        smape_col = "sMAPE (%)"

    if "Accuracy (%)" not in metrics.columns:
        metrics["Accuracy (%)"] = (100 - pd.to_numeric(metrics[smape_col], errors="coerce")).clip(lower=0)

    return metrics


def _query_mysql(connection, query):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(query)
        return pd.DataFrame(cursor.fetchall())
    finally:
        cursor.close()


@st.cache_data
def load_file_data(language="Python"):
    if language == "R":
        pred_path = os.path.join(RAW_DIR, "validation_predictions_R.csv")
        metrics_path = os.path.join(RAW_DIR, "validation_metrics_R.csv")
        cleaned_path = os.path.join(RAW_DIR, "cleaned_grocery_inventory_R.csv")
        if not (os.path.exists(pred_path) and os.path.exists(metrics_path) and os.path.exists(cleaned_path)):
            raise FileNotFoundError(
                "R outputs not found in store/raw/. Run train_pipeline.R and copy "
                "validation_predictions_R.csv, validation_metrics_R.csv, "
                "cleaned_grocery_inventory_R.csv and lstm_training_history_R.csv into store/raw/."
            )
        pred = _read_flexible(pred_path, parse_dates=["Date"])
        metrics = _read_flexible(metrics_path)
        cleaned = _read_flexible(cleaned_path, parse_dates=["Date"])
        history = _load_history_file(language="R")
        return pred, metrics, history, cleaned

    pred = _read_flexible(os.path.join(RAW_DIR, "validation_predictions.xls"), parse_dates=["Date"])
    metrics = _read_flexible(os.path.join(RAW_DIR, "validation_metrics.xls"))
    cleaned = _read_flexible(os.path.join(RAW_DIR, "cleaned_grocery_inventory.xls"), parse_dates=["Date"])
    history = _load_history_file(language="Python")
    return pred, metrics, history, cleaned


@st.cache_data(ttl=60)
def load_mysql_data(host, port, user, password, database):
    if mysql_connector is None:
        raise RuntimeError(f"mysql-connector-python is unavailable: {MYSQL_CONNECTOR_IMPORT_ERROR}")

    connection = mysql_connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connection_timeout=5,
    )
    try:
        pred = _query_mysql(connection, """
            SELECT
                forecast_date,
                store_id,
                product_id,
                actual_sold,
                lstm_predicted,
                svr_predicted,
                inventory_level,
                reorder_alert,
                expiry_risk
            FROM forecast_outputs
            ORDER BY forecast_date, store_id, product_id
        """)
        metrics = _query_mysql(connection, """
            SELECT
                model_name,
                smape_pct,
                rmse,
                accuracy_pct,
                run_date,
                created_at
            FROM model_metrics
            ORDER BY COALESCE(run_date, DATE(created_at)) DESC, created_at DESC, id DESC
        """)
    finally:
        connection.close()

    pred = _normalize_prediction_df(pred)
    metrics = _normalize_metrics_df(metrics)

    if pred.empty:
        raise ValueError(
            "Connected to MySQL, but no rows were found in forecast_outputs. "
            "Load forecast data into the database first."
        )
    if metrics.empty:
        raise ValueError(
            "Connected to MySQL, but no rows were found in model_metrics. "
            "Load validation metrics into the database first."
        )

    cleaned = _read_flexible(os.path.join(RAW_DIR, "cleaned_grocery_inventory.xls"), parse_dates=["Date"])
    history = _load_history_file()
    return pred, metrics, history, cleaned


@st.cache_data(ttl=60)
def load_odoo_data(base_url, database, username, password, api_key):
    if not base_url or not database or not username:
        raise ValueError("Provide Odoo base URL, database, and username.")
    if not (password or api_key):
        raise ValueError("Provide either an Odoo password or an API key.")

    pred, metrics, history, cleaned = load_file_data()
    pred = pred.copy()
    latest_snapshot = _latest_forecast_snapshot(pred)
    credential = api_key or password
    common = xmlrpc.client.ServerProxy(f"{base_url.rstrip('/')}/xmlrpc/2/common", allow_none=True)

    try:
        uid = common.authenticate(database, username, credential, {})
    except OSError as exc:
        raise RuntimeError(f"Could not reach Odoo at {base_url}: {exc}") from exc

    if not uid:
        raise RuntimeError("Odoo authentication failed. Check the database name, username, and password/API key.")

    models = xmlrpc.client.ServerProxy(f"{base_url.rstrip('/')}/xmlrpc/2/object", allow_none=True)
    lot_count = 0
    for lot_model in ["stock.lot", "stock.production.lot"]:
        try:
            lot_count = models.execute_kw(database, uid, credential, lot_model, "search_count", [[]])
            break
        except xmlrpc.client.Fault:
            continue

    locations = models.execute_kw(
        database,
        uid,
        credential,
        "stock.location",
        "search_read",
        [[["name", "like", "Store S%"], ["usage", "=", "internal"]]],
        {"fields": ["id", "name", "complete_name"], "limit": 500, "order": "complete_name"},
    )
    if not locations:
        raise ValueError("No internal Odoo store locations named 'Store S...' were found.")

    location_ids = [row["id"] for row in locations]
    location_names = {row["id"]: row.get("complete_name") or row.get("name") for row in locations}

    quants = models.execute_kw(
        database,
        uid,
        credential,
        "stock.quant",
        "search_read",
        [[["location_id", "in", location_ids], ["quantity", ">", 0]]],
        {"fields": ["product_id", "location_id", "quantity", "reserved_quantity", "write_date"], "limit": 5000, "order": "write_date desc"},
    )
    if not quants:
        raise ValueError("Connected to Odoo, but no stock quants were found for the configured store locations.")

    product_ids = sorted({
        row["product_id"][0]
        for row in quants
        if isinstance(row.get("product_id"), list) and row.get("product_id")
    })
    products = models.execute_kw(
        database,
        uid,
        credential,
        "product.product",
        "search_read",
        [[["id", "in", product_ids]]],
        {"fields": ["id", "default_code", "display_name"], "limit": max(1, len(product_ids))},
    )
    product_codes = {
        row["id"]: row.get("default_code") or row.get("display_name")
        for row in products
    }

    quant_rows = []
    for row in quants:
        product_ref = row.get("product_id")
        location_ref = row.get("location_id")
        if not isinstance(product_ref, list) or not isinstance(location_ref, list):
            continue

        product_id = product_codes.get(product_ref[0])
        store_id = _extract_store_id(location_names.get(location_ref[0], location_ref[1]))
        if not product_id or not store_id:
            continue

        quant_rows.append({
            "Store ID": store_id,
            "Product ID": str(product_id),
            "Inventory_Units": float(row.get("quantity") or 0.0),
            "Odoo Snapshot": pd.to_datetime(row.get("write_date"), errors="coerce"),
        })

    quant_frame = pd.DataFrame(quant_rows)
    if quant_frame.empty:
        raise ValueError("Odoo stock rows were found, but none could be mapped to Store ID/Product ID pairs.")

    quant_summary = (
        quant_frame.groupby(["Store ID", "Product ID"], as_index=False)
        .agg({
            "Inventory_Units": "sum",
            "Odoo Snapshot": "max",
        })
    )
    quant_summary["Odoo_Inventory_Level"] = _normalize_inventory_levels(quant_summary["Inventory_Units"])

    pred = pred.copy()
    pred["Store ID"] = pred["Store ID"].astype(str)
    pred["Product ID"] = pred["Product ID"].astype(str)
    quant_summary["Store ID"] = quant_summary["Store ID"].astype(str)
    quant_summary["Product ID"] = quant_summary["Product ID"].astype(str)

    merged = latest_snapshot.merge(
        quant_summary[["Store ID", "Product ID", "Odoo_Inventory_Level", "Inventory_Units", "Odoo Snapshot"]],
        on=["Store ID", "Product ID"],
        how="left",
    )
    if merged["Odoo_Inventory_Level"].notna().sum() == 0:
        raise ValueError(
            "Connected to Odoo, but none of the live Store ID/Product ID pairs overlap with the dashboard forecast artifacts."
        )

    merged["Inventory_Level"] = merged["Odoo_Inventory_Level"].fillna(merged["Inventory_Level"]).astype(float)
    demand_signal = merged["LSTM_Predicted"].fillna(merged["SVR_Predicted"]).fillna(0.0)
    merged["Reorder_Alert"] = (demand_signal > (merged["Inventory_Level"] * 0.70)).astype(int)
    merged["Expiry_Risk"] = ((merged["Inventory_Level"] > 0.60) & (demand_signal < 0.30)).astype(int)
    merged["Live_Odoo_Inventory"] = merged["Odoo_Inventory_Level"].notna().astype(int)

    history_rows = pred[pred["Date"] < latest_snapshot.attrs.get("forecast_snapshot_date")].copy()
    history_rows["Inventory_Units"] = np.nan
    history_rows["Odoo Snapshot"] = pd.NaT
    history_rows["Odoo_Inventory_Level"] = np.nan
    history_rows["Live_Odoo_Inventory"] = 0

    combined = pd.concat([history_rows, merged], ignore_index=True, sort=False)
    combined = combined.sort_values(["Date", "Store ID", "Product ID"]).reset_index(drop=True)
    combined.attrs["odoo_lot_count"] = lot_count
    combined.attrs["forecast_snapshot_date"] = latest_snapshot.attrs.get("forecast_snapshot_date")
    return combined, metrics, history, cleaned


# ─────────────────────────────────────────────
# DATA LOADER
# ─────────────────────────────────────────────
def load_data(source, db_config=None, language="Python"):
    if source == "Database":
        pred, metrics, history, cleaned = load_mysql_data(
            db_config["host"],
            db_config["port"],
            db_config["user"],
            db_config["password"],
            db_config["database"],
        )
    elif source == "Odoo":
        pred, metrics, history, cleaned = load_odoo_data(
            db_config["base_url"],
            db_config["database"],
            db_config["username"],
            db_config["password"],
            db_config["api_key"],
        )
    else:
        pred, metrics, history, cleaned = load_file_data(language=language)

    # Safety net: guarantee pred and metrics have every column the tabs need,
    # regardless of which pipeline/language/source produced them.
    # See _ensure_prediction_columns and _ensure_metrics_columns.
    original_attrs = pred.attrs
    pred = _ensure_prediction_columns(pred, cleaned=cleaned)
    pred.attrs.update(original_attrs)
    metrics = _ensure_metrics_columns(metrics)

    return pred, metrics, history, cleaned


# ─────────────────────────────────────────────
# SIDEBAR — DATA SOURCE
# ─────────────────────────────────────────────
st.sidebar.header("Data Source")
db_defaults = _get_db_defaults()
odoo_defaults = _get_odoo_defaults()
saved_db_config = _init_saved_config("saved_database_config", db_defaults)
saved_odoo_config = _init_saved_config("saved_odoo_config", odoo_defaults)
data_source = st.sidebar.radio(
    "Load dashboard data from",
    ["Local files", "Odoo", "Database"],
    help="Use local artifacts, live Odoo stock, or a MySQL/MariaDB-compatible database.",
)

language = "Python"
if data_source == "Local files":
    language = st.sidebar.radio(
        "Language",
        ["Python", "R"],
        help=(
            "Python reads the LSTM/SVR outputs from the Python pipeline (store/raw/validation_*.xls). "
            "R reads the equivalent outputs from train_pipeline.R "
            "(store/raw/validation_*_R.csv) — run that script and copy its outputs into store/raw/ first."
        ),
    )

db_config = None
if data_source == "Database":
    with st.sidebar.expander("Database connection", expanded=True):
        st.caption("Defaults come from MYSQL_* environment variables or Streamlit secrets under [mysql]. Changes apply only after you click Save connection.")
        with st.form("database_connection_form", clear_on_submit=False):
            db_host = st.text_input("Host", value=saved_db_config["host"], key="db_host")
            db_port = st.number_input("Port", min_value=1, max_value=65535, value=int(saved_db_config["port"]), key="db_port")
            db_user = st.text_input("User", value=saved_db_config["user"], key="db_user")
            db_password = st.text_input("Password", value=saved_db_config["password"], type="password", key="db_password")
            db_database = st.text_input("Database", value=saved_db_config["database"], key="db_database")
            save_database = st.form_submit_button("Save connection", use_container_width=True)

        if save_database:
            saved_db_config = {
                "host": db_host.strip(),
                "port": int(db_port),
                "user": db_user.strip(),
                "password": db_password,
                "database": db_database.strip(),
            }
            _save_config("saved_database_config", saved_db_config)
            st.sidebar.success("Saved database connection settings for this session.")

        db_config = dict(st.session_state["saved_database_config"])

        if mysql_connector is None:
            st.error("mysql-connector-python is not available in this environment.")
elif data_source == "Odoo":
    with st.sidebar.expander("Odoo connection", expanded=True):
        st.caption("Defaults come from ODOO_* environment variables or Streamlit secrets under [odoo]. Changes apply only after you click Save connection.")
        with st.form("odoo_connection_form", clear_on_submit=False):
            odoo_base_url = st.text_input("Base URL", value=saved_odoo_config["base_url"], key="odoo_base_url")
            odoo_database = st.text_input("Database", value=saved_odoo_config["database"], key="odoo_database")
            odoo_username = st.text_input("Username", value=saved_odoo_config["username"], key="odoo_username")
            odoo_password = st.text_input("Password", value=saved_odoo_config["password"], type="password", key="odoo_password")
            odoo_api_key = st.text_input("API key", value=saved_odoo_config["api_key"], type="password", key="odoo_api_key")
            save_odoo = st.form_submit_button("Save connection", use_container_width=True)

        if save_odoo:
            saved_odoo_config = {
                "base_url": odoo_base_url.strip(),
                "database": odoo_database.strip(),
                "username": odoo_username.strip(),
                "password": odoo_password,
                "api_key": odoo_api_key,
            }
            _save_config("saved_odoo_config", saved_odoo_config)
            st.sidebar.success("Saved Odoo connection settings for this session.")

        db_config = dict(st.session_state["saved_odoo_config"])
        st.caption("Odoo mode keeps the forecast and metrics artifacts locally, then overlays live stock from Odoo onto matching Store ID/Product ID pairs.")

st.sidebar.markdown("---")

connection_prompt = None
if data_source == "Database" and not _database_config_ready(db_config):
    connection_prompt = "Enter the database settings and click Save connection before loading the dashboard."
elif data_source == "Odoo" and not _odoo_config_ready(db_config):
    connection_prompt = "Enter the Odoo settings and click Save connection before loading the dashboard."

if connection_prompt:
    st.info(connection_prompt)
    st.stop()


try:
    pred_df, metrics_df, history_df, cleaned_df = load_data(data_source, db_config, language)

    _debug_log(f"✔ data loaded from {data_source}")
    _debug_log(pred_df.head())
    _debug_log("✔ validation_metrics loaded")
    _debug_log(metrics_df.head())
    _debug_log("✔ cleaned_grocery_inventory loaded")
    _debug_log(cleaned_df.head())

    SMAPE_COL = "sMAPE (%)" if "sMAPE (%)" in metrics_df.columns else "MAPE (%)"

    data_ok = True

except Exception as e:
    st.error(f"ERROR LOADING DATA: {e}")
    _debug_log("FULL ERROR:", e)
    data_ok = False

if not data_ok:
    st.stop()


# ─────────────────────────────────────────────
# SIDEBAR — FILTERS
# ─────────────────────────────────────────────
st.sidebar.header("Filters")
st.sidebar.markdown("---")

source_caption = {
    "Local files": f"local {language}-trained validation artifacts",
    "Odoo": "live Odoo stock over local forecast artifacts",
    "Database": "MySQL/MariaDB database",
}[data_source]
st.sidebar.caption(f"Currently reading from {source_caption}.")
if data_source == "Odoo" and pred_df.attrs.get("forecast_snapshot_date") is not None:
    snapshot_date = pd.to_datetime(pred_df.attrs["forecast_snapshot_date"]).date()
    st.sidebar.caption(f"Odoo mode keeps the full forecast history and applies current live Odoo inventory on the latest forecast snapshot: {snapshot_date}.")

stores = ["All"] + sorted(pred_df["Store ID"].unique().tolist())
selected_store = st.sidebar.selectbox("Store", stores)

products = ["All"] + sorted(pred_df["Product ID"].unique().tolist())
selected_product = st.sidebar.selectbox("Product (SKU)", products)

date_min = pred_df["Date"].min().date()
date_max = pred_df["Date"].max().date()
date_range = st.sidebar.date_input(
    "Date Range",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max
)

st.sidebar.markdown("---")
model_choice = st.sidebar.radio("Forecast Model", ["LSTM", "SVR", "Both"])
chart_resolution = st.sidebar.selectbox("Chart Resolution", ["Daily", "Weekly", "Monthly"], index=1)
st.sidebar.markdown("---")
st.sidebar.markdown("**About**")
st.sidebar.info("Perishable goods DSS — predicts stock levels to reduce waste & stockouts.")

# Apply filters
df = pred_df.copy()
if selected_store != "All":
    df = df[df["Store ID"] == selected_store]
if selected_product != "All":
    df = df[df["Product ID"] == selected_product]
if len(date_range) == 2:
    df = df[(df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])]


# ─────────────────────────────────────────────
# TAB LAYOUT
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Forecast Charts",
    "Reorder Alerts",
    "Expiry Risk",
    "Model Metrics",
    "Data Visualisation",
    "Connections"
])


# ════════════════════════════════════════════
# TAB 1 — FORECAST CHARTS
# ════════════════════════════════════════════
with tab1:
    st.subheader("Actual vs Predicted — Units Sold")

    if df.empty:
        st.warning("No data for current filter selection.")
    else:
        chart_df, aggregated_view = _build_chart_frame(df, chart_resolution)
        if aggregated_view:
            st.caption("Showing daily averages because the current filters include multiple records on the same date.")
        if chart_resolution != "Daily":
            st.caption(f"Chart resolution is set to {chart_resolution.lower()} for readability.")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=chart_df["Date"], y=chart_df["Actual"],
            name="Actual Units Sold",
            line=dict(color=theme["primary"], width=2),
            mode="lines"
        ))

        if model_choice in ["LSTM", "Both"]:
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=chart_df["LSTM_Predicted"],
                name="LSTM Forecast",
                line=dict(color=theme["secondary"], width=2, dash="dash"),
                mode="lines"
            ))

        if model_choice in ["SVR", "Both"]:
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=chart_df["SVR_Predicted"],
                name="SVR Forecast",
                line=dict(color=theme["accent"], width=2, dash="dot"),
                mode="lines"
            ))

        fig.update_layout(xaxis_title="Date", yaxis_title="Units Sold (Scaled 0–1)", hovermode="x unified")
        _apply_plotly_theme(fig, height=420, horizontal_legend=True)
        st.plotly_chart(fig, width='stretch')

    # Inventory level over time
    st.subheader("Inventory Level Over Time")
    if not df.empty:
        inventory_df, _ = _build_chart_frame(df, chart_resolution)
        fig2 = px.area(
            inventory_df, x="Date", y="Inventory_Level",
            color_discrete_sequence=[theme["primary"]],
            labels={"Inventory_Level": "Inventory Level (Scaled 0–1)"},
        )
        _apply_plotly_theme(fig2, height=300)
        st.plotly_chart(fig2, width='stretch')


# ════════════════════════════════════════════
# TAB 2 — REORDER ALERTS
# ════════════════════════════════════════════
with tab2:
    st.subheader("Reorder Alerts")
    st.markdown("Triggered when **predicted demand > 70% of current inventory** — restock before stockout.")

    alerts = df[df["Reorder_Alert"] == 1].copy()
    total  = len(df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Records",    f"{total:,}")
    col2.metric("Reorder Alerts",   f"{len(alerts):,}", delta=f"{len(alerts)/total*100:.1f}% of records" if total else "—")
    col3.metric("Safe Stock Days",  f"{total - len(alerts):,}")

    if alerts.empty:
        _status_box("No reorder alerts for the current selection.", "success")
    else:
        _status_box(f"<b>{len(alerts)} reorder alerts</b> — these SKUs need restocking soon.", "warning")

        # Alert timeline
        alert_daily = alerts.groupby("Date").size().reset_index(name="Alert Count")
        fig3 = px.bar(
            alert_daily, x="Date", y="Alert Count",
            color_discrete_sequence=[theme["warning"]],
            title="Reorder Alerts Over Time"
        )
        _apply_plotly_theme(fig3, height=300)
        st.plotly_chart(fig3, width='stretch')

        st.markdown("**Alert Detail Table**")
        st.dataframe(
            alerts[["Date", "Store ID", "Product ID",
                    "Inventory_Level", "LSTM_Predicted", "Actual"]].rename(columns={
                "Inventory_Level":  "Inv. Level",
                "LSTM_Predicted":   "LSTM Forecast",
                "Actual":           "Actual Sold"
            }).sort_values("Date", ascending=False).reset_index(drop=True),
            width='stretch'
        )

        # Per-product breakdown
        st.markdown("**Alerts by Product**")
        prod_alerts = alerts.groupby("Product ID").size().reset_index(name="Alert Count").sort_values("Alert Count", ascending=False)
        fig4 = px.bar(prod_alerts, x="Product ID", y="Alert Count",
                      color_discrete_sequence=[theme["secondary"]], title="Reorder Alerts by SKU")
        _apply_plotly_theme(fig4, height=280)
        st.plotly_chart(fig4, width='stretch')


# ════════════════════════════════════════════
# TAB 3 — EXPIRY RISK
# ════════════════════════════════════════════
with tab3:
    st.subheader("Expiry Risk")
    st.markdown("Triggered when **inventory is high (>60%)** but **predicted demand is low (<30%)** — goods at risk of expiring.")

    at_risk = df[df["Expiry_Risk"] == 1].copy()

    col1, col2 = st.columns(2)
    col1.metric("Expiry Risk Records", f"{len(at_risk):,}")
    col2.metric("Expiry Risk Rate",    f"{len(at_risk)/len(df)*100:.1f}%" if len(df) > 0 else "—")

    if at_risk.empty:
        _status_box("No expiry risk detected for the current selection.", "success")
    else:
        _status_box(f"<b>{len(at_risk)} records</b> show high inventory and low demand — risk of spoilage.", "danger")

        # Scatter: inventory vs predicted demand
        fig5 = px.scatter(
            df, x="Inventory_Level", y="LSTM_Predicted",
            color=df["Expiry_Risk"].map({0: "Safe", 1: "At Risk"}),
            color_discrete_map={"Safe": theme["success"], "At Risk": theme["danger"]},
            labels={"Inventory_Level": "Inventory Level", "LSTM_Predicted": "LSTM Forecast"},
            title="Inventory Level vs Predicted Demand (Expiry Risk View)",
            opacity=0.6
        )
        fig5.add_vline(x=0.60, line_dash="dash", line_color=theme["muted_text"], annotation_text="Inv. threshold (0.60)")
        fig5.add_hline(y=0.30, line_dash="dash", line_color=theme["muted_text"], annotation_text="Demand threshold (0.30)")
        _apply_plotly_theme(fig5, height=380)
        st.plotly_chart(fig5, width='stretch')

        st.markdown("**Expiry Risk Detail Table**")
        st.dataframe(
        at_risk[["Date", "Store ID", "Product ID",
             "Inventory_Level", "LSTM_Predicted", "Actual"]].rename(columns={
        "Inventory_Level": "Inv. Level",
        "LSTM_Predicted":  "LSTM Forecast",
        "Actual":          "Actual Sold"
    }).sort_values("Inv. Level", ascending=False).reset_index(drop=True),
    width='stretch'
)


# ════════════════════════════════════════════
# TAB 4 — MODEL METRICS
# ════════════════════════════════════════════
with tab4:
    st.subheader("Model Validation Metrics")
    st.markdown("Performance on **real held-out test data** (20% of Groceries dataset).")

    # KPI cards
    # FIX 4 (applied): use SMAPE_COL which resolves to the correct column name
    for _, row in metrics_df.iterrows():
        model_name = row["Model"]
        mape = row[SMAPE_COL]        # was hardcoded "MAPE (%)" — now resolved dynamically
        rmse = row["RMSE"]
        acc  = row["Accuracy (%)"]

        st.markdown(f"#### {model_name} Model")
        c1, c2, c3 = st.columns(3)
        c1.metric("sMAPE (%)",    f"{mape:.4f}%",  help="Symmetric MAPE — lower is better")
        c2.metric("RMSE",         f"{rmse:.6f}",   help="Root Mean Square Error (scaled 0–1) — lower is better")
        c3.metric("Accuracy (%)", f"{acc:.2f}%",   help="= 100% − sMAPE")
        st.markdown("---")

    # FIX 3: lstm_training_history.csv may not exist — guard with a clear notice
    st.subheader("LSTM Training History")
    if history_df is not None and "loss" in history_df.columns and "val_loss" in history_df.columns:
        fig6 = go.Figure()
        fig6.add_trace(go.Scatter(y=history_df["loss"],     name="Train Loss", line=dict(color=theme["secondary"])))
        fig6.add_trace(go.Scatter(y=history_df["val_loss"], name="Val Loss",   line=dict(color=theme["accent"], dash="dash")))
        fig6.update_layout(xaxis_title="Epoch", yaxis_title="MSE Loss")
        _apply_plotly_theme(fig6, height=320, horizontal_legend=True)
        st.plotly_chart(fig6, width='stretch')
    else:
        st.info(
            "`lstm_training_history.csv` was not found. "
            "To generate it, add `history_df = pd.DataFrame(history.history)` "
            "and `history_df.to_csv('lstm_training_history.csv', index=False)` "
            "at the end of Step 03 model training."
        )

    # Actual vs predicted scatter
    # FIX 5: trendline="ols" requires statsmodels which may not be installed.
    #         Use a manual OLS regression line with numpy instead.
    st.subheader("Actual vs Predicted (LSTM) — Scatter")
    filtered_for_scatter = df if not df.empty else pred_df
    fig7 = px.scatter(
        filtered_for_scatter, x="Actual", y="LSTM_Predicted",
        opacity=0.4,
        color_discrete_sequence=[theme["secondary"]],
        labels={"Actual": "Actual Units Sold", "LSTM_Predicted": "LSTM Predicted"},
        # trendline="ols"  ← REMOVED: requires statsmodels; replaced with manual line below
    )
    # Manual OLS trendline using numpy (no extra dependency)
    _x = filtered_for_scatter["Actual"].dropna().values
    _y = filtered_for_scatter["LSTM_Predicted"].dropna().values
    if len(_x) > 1:
        _m, _b = np.polyfit(_x, _y, 1)
        _xr = np.linspace(_x.min(), _x.max(), 100)
        fig7.add_trace(go.Scatter(
            x=_xr, y=_m * _xr + _b,
            mode="lines", name="OLS trend",
            line=dict(color=theme["accent"], width=2, dash="dash")
        ))
    # Perfect-fit reference line
    fig7.add_shape(type="line", x0=0, y0=0, x1=1, y1=1,
                   line=dict(color=theme["primary"], dash="dash"), name="Perfect Fit")
    _apply_plotly_theme(fig7, height=350)
    st.plotly_chart(fig7, width='stretch')


# ════════════════════════════════════════════
# TAB 5 — DATA VISUALISATION (Matplotlib + Seaborn)
# ════════════════════════════════════════════
with tab5:
    st.subheader("Analytical Data Visualisation")
    st.markdown("Static analytical charts using **Matplotlib** and **Seaborn** — demand distributions, prediction error analysis, inventory heatmaps, and store-level reporting.")

    plot_df = df if not df.empty else pred_df
    _apply_matplotlib_theme()
    
    TITLE_FS = 11
    LABEL_FS = 9

    # ── Row 1: Demand distribution + Prediction error distribution ──
    st.markdown("#### Demand & Error Distributions")
    col_a, col_b = st.columns(2)

    with col_a:
        fig_dist, ax = plt.subplots(figsize=(5, 3.2))
        sns.histplot(plot_df["Actual"],         bins=30, color=theme["primary"], alpha=0.7, label="Actual", ax=ax, kde=True)
        sns.histplot(plot_df["LSTM_Predicted"], bins=30, color=theme["secondary"], alpha=0.5, label="LSTM",   ax=ax, kde=True)
        sns.histplot(plot_df["SVR_Predicted"],  bins=30, color=theme["accent"], alpha=0.4, label="SVR",    ax=ax, kde=True)
        ax.set_title("Units Sold — Distribution Comparison", fontsize=TITLE_FS)
        ax.set_xlabel("Scaled Value (0–1)", fontsize=LABEL_FS)
        ax.set_ylabel("Frequency", fontsize=LABEL_FS)
        ax.legend(fontsize=LABEL_FS)
        plt.tight_layout()
        st.pyplot(fig_dist)
        plt.close(fig_dist)

    with col_b:
        lstm_err = plot_df["LSTM_Predicted"] - plot_df["Actual"]
        svr_err  = plot_df["SVR_Predicted"]  - plot_df["Actual"]
        fig_err, ax = plt.subplots(figsize=(5, 3.2))
        sns.kdeplot(lstm_err, color=theme["secondary"], fill=True, alpha=0.4, label="LSTM Error", ax=ax)
        sns.kdeplot(svr_err,  color=theme["accent"], fill=True, alpha=0.4, label="SVR Error",  ax=ax)
        ax.axvline(0, color=theme["text"], linewidth=1, linestyle="--", label="Zero error")
        ax.set_title("Prediction Error Distribution (Predicted − Actual)", fontsize=TITLE_FS)
        ax.set_xlabel("Error (Scaled)", fontsize=LABEL_FS)
        ax.set_ylabel("Density", fontsize=LABEL_FS)
        ax.legend(fontsize=LABEL_FS)
        plt.tight_layout()
        st.pyplot(fig_err)
        plt.close(fig_err)

    # ── Row 2: Box plots ──
    st.markdown("#### Box Plots — Spread & Outliers")
    col_c, col_d = st.columns(2)

    with col_c:
        box_data = pd.DataFrame({
            "Actual":         plot_df["Actual"].values,
            "LSTM Predicted": plot_df["LSTM_Predicted"].values,
            "SVR Predicted":  plot_df["SVR_Predicted"].values,
        })
        fig_box, ax = plt.subplots(figsize=(5, 3.2))
        sns.boxplot(data=box_data, palette=[theme["primary"], theme["secondary"], theme["accent"]], ax=ax)
        ax.set_title("Units Sold — Box Plot Comparison", fontsize=TITLE_FS)
        ax.set_ylabel("Scaled Value (0–1)", fontsize=LABEL_FS)
        ax.tick_params(axis='x', labelsize=LABEL_FS)
        plt.tight_layout()
        st.pyplot(fig_box)
        plt.close(fig_box)

    with col_d:
        inv_box_data = pred_df.copy()
        inv_box_data["Status"] = inv_box_data["Reorder_Alert"].map({0: "Safe", 1: "Reorder Alert"})
        fig_inv_box, ax = plt.subplots(figsize=(5, 3.2))
        sns.boxplot(data=inv_box_data, x="Status", y="Inventory_Level",
                    palette={"Safe": theme["success"], "Reorder Alert": theme["warning"]}, ax=ax)
        ax.set_title("Inventory Level by Reorder Alert Status", fontsize=TITLE_FS)
        ax.set_xlabel("", fontsize=LABEL_FS)
        ax.set_ylabel("Inventory Level (Scaled 0–1)", fontsize=LABEL_FS)
        plt.tight_layout()
        st.pyplot(fig_inv_box)
        plt.close(fig_inv_box)

    # ── Row 3: Seaborn heatmap — avg demand by Store × Product ──
    st.markdown("#### Demand Heatmap — Store × Product SKU")
    try:
        pivot = (
            pred_df.groupby(["Store ID", "Product ID"])["Actual"]
            .mean().unstack(fill_value=0)
        )
        if pivot.shape[1] > 15:
            pivot = pivot.iloc[:, :15]
        fig_heat, ax = plt.subplots(figsize=(10, max(3, len(pivot) * 0.55)))
        heat_cmap = "YlOrBr" if theme_name == "Light" else "rocket"
        sns.heatmap(pivot, annot=True, fmt=".2f", cmap=heat_cmap,
                    linewidths=0.4, linecolor=theme["border"],
                    cbar_kws={"label": "Avg Units Sold (Scaled 0–1)"}, ax=ax)
        ax.set_title("Average Demand Heatmap — Store vs Product SKU", fontsize=TITLE_FS)
        ax.set_xlabel("Product ID", fontsize=LABEL_FS)
        ax.set_ylabel("Store ID", fontsize=LABEL_FS)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.tick_params(axis='y', rotation=0,  labelsize=8)
        plt.tight_layout()
        st.pyplot(fig_heat)
        plt.close(fig_heat)
    except Exception as e:
        st.warning(f"Heatmap could not be rendered: {e}")

    # ── Row 4: Matplotlib grouped bar — alerts per store ──
    st.markdown("#### Alert Summary by Store — Matplotlib Report Chart")
    try:
        store_summary = pred_df.groupby("Store ID").agg(
            Reorder_Alerts=("Reorder_Alert", "sum"),
            Expiry_Risks=("Expiry_Risk",     "sum")
        ).reset_index()
        x = np.arange(len(store_summary))
        width = 0.38
        fig_bar, ax = plt.subplots(figsize=(max(6, len(store_summary) * 0.9), 3.5))
        ax.bar(x - width/2, store_summary["Reorder_Alerts"], width, label="Reorder Alerts", color=theme["warning"], edgecolor=theme["paper_bg"])
        ax.bar(x + width/2, store_summary["Expiry_Risks"],   width, label="Expiry Risks",   color=theme["danger"], edgecolor=theme["paper_bg"])
        ax.set_xticks(x)
        ax.set_xticklabels(store_summary["Store ID"], rotation=45, ha="right", fontsize=LABEL_FS)
        ax.set_title("Reorder Alerts & Expiry Risks per Store", fontsize=TITLE_FS)
        ax.set_ylabel("Count", fontsize=LABEL_FS)
        ax.legend(fontsize=LABEL_FS)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        sns.despine(ax=ax)
        plt.tight_layout()
        st.pyplot(fig_bar)
        plt.close(fig_bar)
    except Exception as e:
        st.warning(f"Store alert chart could not be rendered: {e}")

    # ── Row 5: Seaborn pair plot on a sample ──
    st.markdown("#### Feature Relationships — Seaborn Pair Plot")
    try:
        sample = pred_df[["Actual", "LSTM_Predicted", "SVR_Predicted", "Inventory_Level"]].dropna().sample(
            n=min(500, len(pred_df)), random_state=42
        )
        pair_fig = sns.pairplot(sample, plot_kws={"alpha": 0.3, "s": 10, "color": theme["primary"]},
                                diag_kws={"color": theme["secondary"]})
        pair_fig.figure.suptitle("Pair Plot: Actual, LSTM, SVR, Inventory Level", y=1.02, fontsize=TITLE_FS)
        st.pyplot(pair_fig.figure)
        plt.close(pair_fig.figure)
    except Exception as e:
        st.warning(f"Pair plot could not be rendered: {e}")


# ════════════════════════════════════════════
# TAB 6 — CONNECTIONS
# ════════════════════════════════════════════
with tab6:
    st.subheader("Data Connections")
    if data_source == "Database":
        st.success(
            f"Connected mode is active. The dashboard is currently loading forecast data from "
            f"`{db_config['database']}` on `{db_config['host']}:{db_config['port']}`."
        )
    elif data_source == "Odoo":
        st.success(
            f"Odoo mode is active. The dashboard is pulling live stock from `{db_config['database']}` at "
            f"`{db_config['base_url']}` and overlaying it onto the local forecast artifacts."
        )
        if pred_df.attrs.get("odoo_lot_count", 0) == 0:
            st.info(
                "No Odoo lot or expiration records were found on the current tenant, so the Expiry Risk tab is still using the forecast-vs-inventory heuristic rather than true lot expiry dates."
            )
        st.markdown("""
#### Odoo live stock mode

When Odoo is selected, the dashboard connects directly over XML-RPC using the
sidebar credentials or `ODOO_*` environment variables. It reads internal store
locations named `Store S...`, maps product codes such as `P0001`, and refreshes
inventory, reorder alerts, and expiry-risk calculations from live Odoo stock.

The forecast curves and validation metrics still come from the local model
artifacts, because Odoo holds operational stock data rather than trained model
outputs.
""")
    else:
        st.info(
            "The dashboard is currently reading local files. Switch the sidebar data source to Odoo "
            "for live stock, or to Database for MySQL/MariaDB forecast tables."
        )

    st.markdown("""
This tab also keeps the SQL schema and Python connection code used by the
MySQL/MariaDB database path.

---
#### Step 1 — Create the Database & Tables
""")

    st.code("""
-- Run this in MySQL Workbench or your MySQL CLI
CREATE DATABASE IF NOT EXISTS mini_market_dss;
USE mini_market_dss;

-- Stores POS transaction & inventory records (Step 01 data)
CREATE TABLE IF NOT EXISTS inventory_records (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    record_date   DATE         NOT NULL,
    store_id      VARCHAR(10)  NOT NULL,
    product_id    VARCHAR(10)  NOT NULL,
    category      VARCHAR(50),
    inventory_lvl FLOAT,
    units_sold    INT,
    units_ordered INT,
    price         FLOAT,
    discount      FLOAT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stores daily forecast outputs from LSTM & SVR
CREATE TABLE IF NOT EXISTS forecast_outputs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    forecast_date   DATE        NOT NULL,
    store_id        VARCHAR(10) NOT NULL,
    product_id      VARCHAR(10) NOT NULL,
    actual_sold     FLOAT,
    lstm_predicted  FLOAT,
    svr_predicted   FLOAT,
    inventory_level FLOAT,
    reorder_alert   TINYINT(1)  DEFAULT 0,
    expiry_risk     TINYINT(1)  DEFAULT 0,
    created_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

-- Stores model performance metrics
CREATE TABLE IF NOT EXISTS model_metrics (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    model_name   VARCHAR(20),
    smape_pct    FLOAT,
    rmse         FLOAT,
    accuracy_pct FLOAT,
    run_date     DATE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""", language="sql")

    st.markdown("#### Step 2 — Python: Write Forecast Outputs to MySQL/MariaDB")
    st.code("""
import mysql.connector
import pandas as pd

def read_flexible(path, **kwargs):
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return pd.read_excel(path, **kwargs)

# ── Connection (update credentials) ──────────────────────
conn = mysql.connector.connect(
    host     = "localhost",
    port     = 3306,
    user     = "root",          # your MySQL username
    password = "your_password", # your MySQL password
    database = "mini_market_dss"
)
cursor = conn.cursor()

# ── Load predictions ──────────────────────────────────────
pred_df = read_flexible("store/raw/validation_predictions.xls", parse_dates=["Date"])
metrics_df = read_flexible("store/raw/validation_metrics.xls")

# ── Insert rows ───────────────────────────────────────────
forecast_sql = '''
    INSERT INTO forecast_outputs
        (forecast_date, store_id, product_id, actual_sold,
         lstm_predicted, svr_predicted, inventory_level,
         reorder_alert, expiry_risk)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
'''

forecast_rows = [
    (
        row["Date"].date(),
        row["Store ID"],
        row["Product ID"],
        float(row["Actual"]),
        float(row["LSTM_Predicted"]),
        float(row["SVR_Predicted"]),
        float(row["Inventory_Level"]),
        int(row["Reorder_Alert"]),
        int(row["Expiry_Risk"])
    )
    for _, row in pred_df.iterrows()
]

metric_sql = '''
    INSERT INTO model_metrics
        (model_name, smape_pct, rmse, accuracy_pct, run_date)
    VALUES (%s, %s, %s, %s, CURDATE())
'''

metric_rows = [
    (
        row["Model"],
        float(row["sMAPE (%)"]),
        float(row["RMSE"]),
        float(row["Accuracy (%)"])
    )
    for _, row in metrics_df.iterrows()
]

cursor.executemany(forecast_sql, forecast_rows)
cursor.executemany(metric_sql, metric_rows)
conn.commit()
print(f"✔ {len(forecast_rows)} forecast rows written to MySQL")
print(f"✔ {len(metric_rows)} metric rows written to MySQL")
cursor.close()
conn.close()
""", language="python")

    st.success("Once configured and populated, the dashboard can query a MySQL/MariaDB database live instead of reading only local files.")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "**Mark Wambugu** · DDA-01-0142/2025 · "
    "LSTM & SVR Stock-Level Prediction Pipeline · "
    "Workflow Steps 01–05 Complete"
)
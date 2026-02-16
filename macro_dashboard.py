# ------------------------------------------------------------
# Macro Dashboard — CPI (YoY), Unemployment, 10Y Real Yield
# Source: FRED (St. Louis Fed)
#   CPI index: CPIAUCSL (we compute YoY %)
#   Unemployment rate: UNRATE (%)
#   Real 10Y yield: DFII10 (daily -> monthly mean)
#
# Runs on Streamlit Cloud. Requires FRED_API_KEY in secrets.
# ------------------------------------------------------------

import io
import os
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------- Page setup ----------
st.set_page_config(
    page_title="Macro Dashboard (CPI, Unemployment, Real Rates)",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Macro Dashboard — CPI (YoY), Unemployment, Real Rates")
st.caption("Source: Federal Reserve Economic Data (FRED).")

# ---------- Config / Secrets ----------
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
api_key = st.secrets.get("FRED_API_KEY", "")  # Streamlit Cloud secrets

if not api_key:
    st.warning(
        "Your app is running, but no FRED API key is set. "
        "Go to Streamlit → Settings → Secrets and add FRED_API_KEY.\n\n"
        "See the README for instructions."
    )
    st.stop()

# ---------- Sidebar ----------
st.sidebar.header("Settings")
start_date = st.sidebar.date_input("Start date", pd.to_datetime("2000-01-01")).strftime("%Y-%m-%d")
smooth_ma = st.sidebar.checkbox("Apply 3‑month moving average (display only)", value=False)
st.sidebar.caption("Series: CPIAUCSL (CPI index), UNRATE (U‑3), DFII10 (10‑year TIPS real yield).")

# ---------- Helpers ----------
def fetch_fred(series_id: str, start: str) -> pd.DataFrame:
    """Fetch a FRED series as a DateTime-indexed DataFrame with column 'value' (float)."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
    }
    r = requests.get(FRED_API, params=params, timeout=30)
    r.raise_for_status()
    js = r.json()
    obs = js.get("observations", [])
    if not obs:
        return pd.DataFrame(columns=["value"]).astype({"value": "float64"})
    df = pd.DataFrame(obs)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("date").sort_index()
    return df[["value"]]


def monthlyize(df: pd.DataFrame, how: str = "last") -> pd.DataFrame:
    if df.empty:
        return df
    if how == "mean":
        return df.resample("M").mean()
    return df.resample("M").last()


def cpi_yoy_from_index(cpi_idx: pd.DataFrame) -> pd.Series:
    if cpi_idx.empty:
        return pd.Series(dtype="float64", name="CPI_YoY")
    if pd.infer_freq(cpi_idx.index) not in ("M", "MS"):
        cpi_idx = cpi_idx.resample("M").last()
    yoy = cpi_idx["value"].pct_change(12) * 100
    yoy.name = "CPI_YoY"
    return yoy


def metric_card(label: str, value: float, suffix: str = ""):
    st.metric(
        label=label,
        value=("-" if pd.isna(value) else f"{value:,.2f}{suffix}")
    )


def line_chart(df: pd.DataFrame, y: str, title: str, yaxis_title: str):
    if df.empty or y not in df.columns:
        st.info(f"No data to display for **{title}**.")
        return
    fig = px.line(df.reset_index().rename(columns={"index": "date"}), x="date", y=y, title=title)
    fig.update_layout(xaxis_title="", yaxis_title=yaxis_title, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# ---------- Fetch Data ----------
with st.spinner("Fetching data from FRED…"):
    # CPI index (SA) -> CPI YoY
    cpi_idx = fetch_fred("CPIAUCSL", start=start_date)  # CPI index (1982-84=100)
    cpi_m = monthlyize(cpi_idx, how="last").rename(columns={"value": "CPI"})
    cpi_yoy = cpi_yoy_from_index(cpi_idx)

    # Unemployment rate (monthly, %)
    unrate = fetch_fred("UNRATE", start=start_date)
    unrate_m = monthlyize(unrate, how="last").rename(columns={"value": "Unemployment"})

    # 10Y real yield (daily %) -> monthly mean
    real10_daily = fetch_fred("DFII10", start=start_date)
    real10_m = monthlyize(real10_daily, how="mean").rename(columns={"value": "Real10Y"})

# Combine (monthly)
panel = pd.concat([cpi_m["CPI"], cpi_yoy, unrate_m["Unemployment"], real10_m["Real10Y"]], axis=1)
panel = panel.dropna(how="all")

# Optional smoothing for display
display_df = panel.copy()
if smooth_ma:
    for col in display_df.columns:
        display_df[col] = display_df[col].rolling(3).mean()

# ---------- KPI Row ----------
latest = panel.dropna()
if latest.empty:
    st.info("No data available yet for the selected period.")
else:
    last = latest.iloc[-1]
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("CPI YoY", last.get("CPI_YoY", np.nan), suffix=" %")
    with c2:
        metric_card("Unemployment", last.get("Unemployment", np.nan), suffix=" %")
    with c3:
        metric_card("Real 10Y Yield", last.get("Real10Y", np.nan), suffix=" %")

# ---------- Charts ----------
st.subheader("CPI — Year‑over‑Year (%)")
line_chart(display_df[["CPI_YoY"]].dropna(), "CPI_YoY", "CPI YoY (computed from CPIAUCSL)", "%")

st.subheader("Unemployment Rate (%)")
line_chart(display_df[["Unemployment"]].dropna(), "Unemployment", "Unemployment Rate (UNRATE)", "%")

st.subheader("Real Rates — 10Y TIPS Real Yield (%)")
line_chart(display_df[["Real10Y"]].dropna(), "Real10Y", "10‑Year Real Yield (DFII10 monthly average)", "%")

# ---------- Download ----------
st.markdown("### Download data")
st.caption("Monthly series; CPI YoY computed; Real10Y is monthly mean of DFII10.")
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xl:
    panel.to_excel(xl, sheet_name="macro_panel")
    cpi_m.to_excel(xl, sheet_name="cpi_index")
    unrate_m.to_excel(xl, sheet_name="unemployment")
    real10_m.to_excel(xl, sheet_name="real10y")
st.download_button(
    label="⬇️ Export to Excel",
    data=buf.getvalue(),
    file_name="macro_dashboard_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

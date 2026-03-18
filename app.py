# app.py — NHS Maternity Outcomes Dashboard
# Compares hospital-level maternity outcomes across NHS trusts in England.
# Primary focus: Birmingham Women's and Children's NHS Foundation Trust (RQ3)
#
# Data sources:
#   MSDS Monthly (NHS Digital) — provider-level experimental data format
#   MBRRACE-UK — trust-level perinatal mortality (auto-loaded from data/)
#
# Run:  streamlit run app.py

from __future__ import annotations
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")

from data_loaders import (
    BWC_NAME,
    BWC_ODS,
    BWC_SEARCH,
    COMPARATOR_PRESETS,
    MONTH_ORDER,
    MSDS_METRICS,
    MSDS_CQIMS,
    MSDS_URLS,
    get_cqim_annual,
    get_cqim_trend,
    get_msds_coverage,
    get_best_annual_year,
    get_latest_year,
    get_msds_trust_list,
    load_mbrrace_local,
)

# ---------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="NHS Maternity Outcomes Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; }
    .metric-box {
        background: #f8f9fa; border-radius: 6px; padding: 12px 16px;
        border-left: 4px solid #dee2e6; margin-bottom: 8px;
    }
    .metric-box.red   { border-left-color: #c0392b; }
    .metric-box.amber { border-left-color: #e67e22; }
    .metric-box.green { border-left-color: #27ae60; }
    .metric-box.grey  { border-left-color: #95a5a6; }
    .data-note {
        font-size: 0.78em; color: #6c757d; margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# CACHED DATA LOADING  (all @st.cache_data wrappers live here, not in data_loaders)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading MSDS data (downloading missing months from NHS Digital — this may take up to 60 s on first run)…")
def _load_cqims(year: int) -> pd.DataFrame:
    return get_cqim_annual(year)


@st.cache_data(show_spinner="Loading monthly trend data…")
def _load_trend(year: int, metric_key: str) -> pd.DataFrame:
    return get_cqim_trend(year, metric_key)


@st.cache_data(show_spinner=False)
def _load_trust_list(year: int) -> list[str]:
    return get_msds_trust_list(year)


@st.cache_data(show_spinner=False)
def _load_mbrrace() -> pd.DataFrame:
    return load_mbrrace_local()


# ---------------------------------------------------------------------------
# YEAR SELECTION (automatic — no user selector)
# Funnel charts use the year with the most months (most complete annual data).
# Trend charts use the latest year with any data.
# ---------------------------------------------------------------------------

annual_year  = get_best_annual_year()   # e.g. 2024 — most complete annual data
trend_year   = get_latest_year()        # e.g. 2025 — most recent data
annual_label = get_msds_coverage(annual_year)
trend_label  = get_msds_coverage(trend_year)

# ---------------------------------------------------------------------------
# FUNNEL CHART HELPERS
# ---------------------------------------------------------------------------

def _funnel_limits(p: float, n_arr: np.ndarray, is_rate: bool) -> dict:
    """Poisson (p<0.10) or binomial funnel control limits."""
    n = n_arr.astype(float)
    z95, z998 = 1.96, 3.09
    se = (np.sqrt(p / np.maximum(n, 1)) if is_rate
          else np.sqrt(p * (1 - p) / np.maximum(n, 1)))
    scale = 1000 if is_rate else 100
    return {
        "mean": p * scale,
        "u95":  (p + z95  * se) * scale,
        "l95":  np.maximum(0, (p - z95  * se)) * scale,
        "u998": (p + z998 * se) * scale,
        "l998": np.maximum(0, (p - z998 * se)) * scale,
    }


def _trust_status(value: float, p: float, n: float, is_rate: bool,
                  higher_is_worse: bool) -> tuple[str, str]:
    """Return (label, css_class) for one trust relative to control limits."""
    lims = _funnel_limits(p, np.array([n]), is_rate)
    if higher_is_worse:
        if value > lims["u998"][0]: return "Above 99.8% control limit (high outlier)", "red"
        if value > lims["u95"][0]:  return "Above 95% control limit", "amber"
        if value < lims["l95"][0]:  return "Below 95% control limit (better than average)", "green"
    else:
        if value < lims["l998"][0]: return "Below 99.8% control limit (low outlier)", "red"
        if value < lims["l95"][0]:  return "Below 95% control limit", "amber"
        if value > lims["u95"][0]:  return "Above 95% control limit (better than average)", "green"
    return "Within control limits", "grey"


def make_funnel_chart(
    df: pd.DataFrame,
    value_col: str,
    denom_col: str,
    name_col: str,
    focus_fragment: str,
    title: str,
    unit: str,
    higher_is_worse: bool = True,
    min_denom: int = 20,
    comparators: list[str] | None = None,
) -> go.Figure | None:
    """
    Funnel (control) chart comparing all trusts.
    X-axis bounded by maximum denominator. Focus trust shown as a diamond.
    Comparator trusts shown as squares.
    """
    df = df.dropna(subset=[value_col, denom_col]).copy()
    df = df[df[denom_col] >= min_denom]
    if len(df) < 3:
        return None

    is_rate = unit.startswith("per 1,")
    scale = 1000 if is_rate else 100

    total_events = (df[value_col] * df[denom_col] / scale).sum()
    total_denom  = df[denom_col].sum()
    p = total_events / total_denom if total_denom > 0 else 0.0

    x_max   = df[denom_col].max()
    n_smooth = np.linspace(df[denom_col].min(), x_max, 400)
    lims = _funnel_limits(p, n_smooth, is_rate)

    fig = go.Figure()

    # 99.8% band
    fig.add_trace(go.Scatter(
        x=np.concatenate([n_smooth, n_smooth[::-1]]),
        y=np.concatenate([lims["u998"], lims["l998"][::-1]]),
        fill="toself", fillcolor="rgba(255,165,0,0.10)",
        line=dict(color="rgba(255,165,0,0.45)", width=1),
        name="99.8% control limits", hoverinfo="skip",
    ))
    # 95% band
    fig.add_trace(go.Scatter(
        x=np.concatenate([n_smooth, n_smooth[::-1]]),
        y=np.concatenate([lims["u95"], lims["l95"][::-1]]),
        fill="toself", fillcolor="rgba(30,120,255,0.08)",
        line=dict(color="rgba(30,120,255,0.30)", width=1),
        name="95% control limits", hoverinfo="skip",
    ))
    # National mean line
    fig.add_hline(
        y=lims["mean"],
        line_dash="dash", line_color="rgba(100,100,100,0.7)", line_width=1.5,
        annotation_text=f"National mean: {lims['mean']:.2f} {unit}",
        annotation_position="top right", annotation_font_size=11,
    )

    focus_mask = df[name_col].str.upper().str.contains(focus_fragment.upper(), na=False)
    other_df   = df[~focus_mask]
    focus_df   = df[focus_mask]

    def _dot_colour(row) -> str:
        val = row[value_col]; n = row[denom_col]
        pt = _funnel_limits(p, np.array([n]), is_rate)
        if higher_is_worse:
            if val > pt["u998"][0]: return "#c0392b"
            if val > pt["u95"][0]:  return "#e67e22"
            if val < pt["l95"][0]:  return "#27ae60"
        else:
            if val < pt["l998"][0]: return "#c0392b"
            if val < pt["l95"][0]:  return "#e67e22"
            if val > pt["u95"][0]:  return "#27ae60"
        return "#95a5a6"

    if not other_df.empty:
        colours = [_dot_colour(r) for _, r in other_df.iterrows()]
        fig.add_trace(go.Scatter(
            x=other_df[denom_col], y=other_df[value_col],
            mode="markers",
            marker=dict(color=colours, size=7, opacity=0.65,
                        line=dict(width=0.4, color="white")),
            text=other_df[name_col],
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"Rate: %{{y:.2f}} {unit}<br>"
                "N: %{x:,.0f}<extra></extra>"
            ),
            name="Other NHS trusts",
        ))

    _comp_palette = ["#3498db", "#9b59b6", "#1abc9c", "#f39c12", "#34495e"]
    if comparators:
        for ci, comp in enumerate(comparators[:5]):
            comp_mask = df[name_col].str.upper().str.contains(comp[:30].upper(), na=False)
            comp_df   = df[comp_mask & ~focus_mask]
            if not comp_df.empty:
                colour = _comp_palette[ci % len(_comp_palette)]
                fig.add_trace(go.Scatter(
                    x=comp_df[denom_col], y=comp_df[value_col],
                    mode="markers",
                    marker=dict(color=colour, size=12, symbol="square",
                                opacity=0.9, line=dict(width=1.5, color="white")),
                    text=comp_df[name_col],
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        f"Rate: %{{y:.2f}} {unit}<br>"
                        "N: %{x:,.0f}<extra></extra>"
                    ),
                    name=comp_df[name_col].iloc[0][:45],
                ))

    if not focus_df.empty:
        row   = focus_df.iloc[0]
        val   = row[value_col]; n = row[denom_col]
        label, css = _trust_status(val, p, n, is_rate, higher_is_worse)
        colour_map = {"red": "#8b0000", "amber": "#c0392b",
                      "green": "#1a7a4a", "grey": "#2c3e50"}
        fig.add_trace(go.Scatter(
            x=focus_df[denom_col], y=focus_df[value_col],
            mode="markers",
            marker=dict(color=colour_map[css], size=16, symbol="diamond",
                        line=dict(width=2, color="white")),
            text=focus_df[name_col],
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"Rate: %{{y:.2f}} {unit}<br>"
                "N: %{x:,.0f}<br>"
                f"{label}<extra></extra>"
            ),
            name=f"Focus trust — {label}",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#2c3e50")),
        xaxis_title="Number of deliveries (denominator)",
        yaxis_title=f"Rate ({unit})",
        height=450,
        hovermode="closest",
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="top", y=-0.22,
                    xanchor="left", x=0, font=dict(size=10)),
        margin=dict(t=50, b=110, l=65, r=50),
        xaxis=dict(showgrid=True, gridcolor="#ebebeb", zeroline=False,
                   range=[0, x_max * 1.05]),
        yaxis=dict(showgrid=True, gridcolor="#ebebeb", rangemode="tozero"),
    )
    return fig


def make_trend_chart(
    trend_df: pd.DataFrame,
    focus_fragment: str,
    title: str,
    unit: str,
    comparators: list[str] | None = None,
) -> go.Figure | None:
    """Monthly trend chart for an MSDS metric."""
    if trend_df.empty or "Org_Name" not in trend_df.columns:
        return None

    fig = go.Figure()

    # National mean per month
    nat_rows = []
    for month, grp in trend_df.groupby("_month"):
        d = grp["Denominator"].sum()
        nat_rows.append({
            "_month": month,
            "Rate": grp["Numerator"].sum() / d * 1000 if d > 0 else np.nan,
        })
    nat = pd.DataFrame(nat_rows)
    month_idx = {m: i for i, m in enumerate(MONTH_ORDER)}
    nat["_ord"] = nat["_month"].map(month_idx)
    nat = nat.sort_values("_ord")

    fig.add_trace(go.Scatter(
        x=nat["_month"], y=nat["Rate"],
        mode="lines",
        line=dict(color="rgba(150,150,150,0.6)", dash="dash", width=1.8),
        name="National mean",
        hovertemplate="National mean<br>%{x}: %{y:.2f}<extra></extra>",
    ))

    if comparators:
        palette = ["#3498db", "#9b59b6", "#1abc9c", "#f39c12", "#34495e"]
        for i, comp in enumerate(comparators[:5]):
            comp_data = trend_df[
                trend_df["Org_Name"].str.upper().str.contains(comp[:30].upper(), na=False)
            ].copy()
            if not comp_data.empty:
                comp_data["_ord"] = comp_data["_month"].map(month_idx)
                comp_data = comp_data.sort_values("_ord")
                fig.add_trace(go.Scatter(
                    x=comp_data["_month"], y=comp_data["Rate"],
                    mode="lines+markers",
                    line=dict(color=palette[i % len(palette)], width=1.8),
                    marker=dict(size=5),
                    name=comp_data["Org_Name"].iloc[0][:45],
                    opacity=0.75,
                ))

    focus_data = trend_df[
        trend_df["Org_Name"].str.upper().str.contains(focus_fragment.upper(), na=False)
    ].copy()
    if not focus_data.empty:
        focus_data["_ord"] = focus_data["_month"].map(month_idx)
        focus_data = focus_data.sort_values("_ord")
        fig.add_trace(go.Scatter(
            x=focus_data["_month"], y=focus_data["Rate"],
            mode="lines+markers",
            line=dict(color="#c0392b", width=3),
            marker=dict(size=9, color="#c0392b"),
            name=focus_data["Org_Name"].iloc[0][:50],
            hovertemplate="%{fullData.name}<br>%{x}: %{y:.2f} " + unit + "<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#2c3e50")),
        xaxis_title="Month",
        yaxis_title=f"Rate ({unit})",
        height=360,
        hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#ebebeb",
                   categoryorder="array", categoryarray=MONTH_ORDER),
        yaxis=dict(showgrid=True, gridcolor="#ebebeb", rangemode="tozero"),
        legend=dict(orientation="h", yanchor="top", y=-0.22,
                    xanchor="left", x=0, font=dict(size=10)),
        margin=dict(t=45, b=100, l=60, r=40),
    )
    return fig


# ---------------------------------------------------------------------------
# STATUS BADGE
# ---------------------------------------------------------------------------

def status_badge(label: str, css_class: str) -> str:
    colours = {
        "red":   ("#c0392b", "#fdf0ee"),
        "amber": ("#e67e22", "#fef9f0"),
        "green": ("#1a7a4a", "#edf7f2"),
        "grey":  ("#636e72", "#f5f5f5"),
    }
    fg, bg = colours.get(css_class, colours["grey"])
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 9px;'
        f'border-radius:4px;font-size:0.82em;font-weight:600;">{label}</span>'
    )


def data_note(source: str, coverage: str, n_trusts: int | None = None) -> str:
    """Standardised data source caption."""
    parts = [f"Source: {source}", f"Period: {coverage}"]
    if n_trusts:
        parts.append(f"{n_trusts:,} NHS trusts")
    return " &nbsp;|&nbsp; ".join(parts)


def _val_col(meta: dict) -> str:
    return "Rate" if meta["unit"].startswith("per") else "Rate_pct"


def _metric_label(data: pd.DataFrame) -> str:
    """Return a coverage label like 'Jan–Dec 2024 (12 months)' from metric data rows."""
    if data.empty:
        return annual_label
    year = data["_data_year"].iloc[0] if "_data_year" in data.columns else None
    months = data["_data_months"].iloc[0] if "_data_months" in data.columns else None
    if year is None:
        return annual_label
    return get_msds_coverage(int(year)) if months is None else f"{get_msds_coverage(int(year))}"


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Dashboard Settings")
    st.markdown("---")

    # Trust selector
    st.markdown("**Focus Trust**")
    with st.spinner("Loading trust list…"):
        trust_list = _load_trust_list(annual_year)

    if trust_list:
        default_idx = next(
            (i for i, t in enumerate(trust_list) if BWC_SEARCH in t.upper()), 0
        )
        focus_trust = st.selectbox("Select focus trust", trust_list, index=default_idx,
                                   label_visibility="collapsed")
    else:
        focus_trust = st.text_input("Focus trust name", value=BWC_NAME)

    focus_fragment = focus_trust[:30]

    st.markdown("---")
    st.markdown("**Comparator Trusts**")
    preset_name = st.selectbox(
        "Preset group",
        list(COMPARATOR_PRESETS.keys()),
        index=0,
    )

    comparators: list[str] = list(COMPARATOR_PRESETS.get(preset_name, []))

    manual = st.multiselect(
        "Additional trusts",
        [t for t in trust_list if t != focus_trust and t not in comparators],
        max_selections=4,
        placeholder="Search trusts…",
    ) if trust_list else []
    comparators = comparators + manual

    if comparators:
        st.caption("Active: " + " · ".join(
            t.split()[0] + " " + t.split()[1] for t in comparators[:4]
            if len(t.split()) >= 2
        ))

    st.markdown("---")
    st.markdown(
        f"**Data coverage**  \n"
        f"Funnel charts: {annual_label}  \n"
        f"Trend charts: {trend_label}"
    )
    st.markdown("---")
    st.caption(
        "MSDS Monthly, NHS Digital · "
        "MBRRACE-UK (Trust-level perinatal mortality)  \n"
        "Funnel plots show 95% and 99.8% Poisson / binomial control limits."
    )
    if st.button("Clear cached data"):
        st.cache_data.clear()
        st.rerun()


# ---------------------------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------------------------

st.markdown("## NHS Maternity Outcomes Dashboard")
st.markdown(
    f"**Focus trust:** {focus_trust} &nbsp;|&nbsp; "
    f"**Annual data:** {annual_label} &nbsp;|&nbsp; "
    f"**Trend data:** {trend_label}"
)
st.markdown("---")


# ---------------------------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------------------------

with st.spinner(f"Loading MSDS {annual_year} data…"):
    cqim_df = _load_cqims(annual_year)

mbrrace_df = _load_mbrrace()


def cqim_for_dim(dim_name: str) -> pd.DataFrame:
    if cqim_df.empty:
        return pd.DataFrame()
    return cqim_df[cqim_df["Dimension"] == dim_name].copy()


def _n_trusts(data: pd.DataFrame) -> int:
    if "Org_Name" in data.columns:
        return data["Org_Name"].nunique()
    return 0


# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------

tabs = st.tabs([
    "Overview",
    "Perinatal Mortality",
    "Birth Outcomes",
    "Delivery Mode",
    "Maternal Morbidity",
    "Monthly Trends",
    "Risk Factors",
    "MBRRACE Data",
])

(tab_overview, tab_perinatal, tab_birth, tab_delivery,
 tab_morbidity, tab_trends, tab_risk, tab_mbrrace) = tabs


# ── TAB 1: OVERVIEW ────────────────────────────────────────────────────────

with tab_overview:
    st.subheader(f"Summary — {focus_trust}")
    st.markdown(
        "Status of the focus trust relative to national funnel control limits. "
        "Red = statistically high (worse), green = statistically low (better), "
        "grey = within expected range."
    )
    st.caption(
        f"Perinatal mortality: MBRRACE-UK 2023 · "
        f"All other indicators: MSDS Provider Level Experimental Data, NHS Digital · "
        f"Period: {annual_label}"
    )

    _OVERVIEW_EXCLUDE_DOMAINS = {"Risk Factors", "Infant Health", "Access"}

    rows = []

    # MBRRACE perinatal mortality rows (shown first, domain = "Perinatal Mortality")
    if not mbrrace_df.empty and "OrganisationName" in mbrrace_df.columns:
        mb_eng = mbrrace_df.copy()
        if "CountryName" in mb_eng.columns:
            eng_rows = mb_eng[mb_eng["CountryName"].str.upper() == "ENGLAND"]
            if not eng_rows.empty:
                mb_eng = eng_rows

        focus_mb = mb_eng[
            mb_eng["OrganisationName"].str.upper().str.contains(
                focus_fragment.upper(), na=False)
        ]

        for mb_label, mb_rcol, mb_dcol, mb_unit in [
            ("Stillbirth rate",                "CrudeStillbirthRate",    "TotalBirths",     "per 1,000 births"),
            ("Neonatal mortality rate",         "CrudeNeonatalDeathRate", "TotalLiveBirths", "per 1,000 live births"),
            ("Extended perinatal mortality rate","CrudePerinatalDeathRate","TotalBirths",    "per 1,000 births"),
        ]:
            if mb_rcol not in mb_eng.columns or mb_dcol not in mb_eng.columns:
                continue
            valid = mb_eng.dropna(subset=[mb_rcol, mb_dcol])
            if valid.empty or focus_mb.empty:
                continue
            total_d = valid[mb_dcol].sum()
            total_e = (valid[mb_rcol] * valid[mb_dcol] / 1000).sum()
            p_mb    = total_e / total_d if total_d > 0 else 0.0
            mb_r    = focus_mb.iloc[0]
            if pd.isna(mb_r.get(mb_rcol)) or pd.isna(mb_r.get(mb_dcol)):
                continue
            trust_val = float(mb_r[mb_rcol])
            trust_n   = float(mb_r[mb_dcol])
            nat_mean  = p_mb * 1000
            lstr, css = _trust_status(trust_val, p_mb, trust_n, True, True)
            rows.append({
                "Indicator": mb_label,
                "Domain": "Perinatal Mortality",
                "Trust value": round(trust_val, 2),
                "National mean": round(nat_mean, 2),
                "Unit": mb_unit,
                "N (trust)": int(trust_n) if not np.isnan(trust_n) else None,
                "_css": css,
                "_status": lstr,
                "_source": "MBRRACE-UK 2023",
            })

    # MSDS rows (excluding filtered domains)
    if not cqim_df.empty:
        for label, meta in MSDS_METRICS.items():
            if meta["domain"] in _OVERVIEW_EXCLUDE_DOMAINS:
                continue
            dim_data = cqim_for_dim(meta["dim"])
            if dim_data.empty:
                continue
            is_rate = meta["unit"].startswith("per")
            scale   = meta["scale"]
            vc      = _val_col(meta)

            total_n = dim_data["Denominator"].sum()
            total_e = (dim_data[vc] * dim_data["Denominator"] / scale).sum()
            p       = total_e / total_n if total_n > 0 else 0.0

            focus_row = dim_data[
                dim_data["Org_Name"].str.upper().str.contains(
                    focus_fragment.upper(), na=False)
            ]
            if focus_row.empty:
                continue

            trust_val = focus_row[vc].iloc[0]
            trust_n   = focus_row["Denominator"].iloc[0]
            nat_mean  = p * scale
            lstr, css = _trust_status(trust_val, p, trust_n, is_rate,
                                      meta["higher_is_worse"])
            rows.append({
                "Indicator": label,
                "Domain": meta["domain"],
                "Trust value": round(trust_val, 2),
                "National mean": round(nat_mean, 2),
                "Unit": meta["unit"],
                "N (trust)": int(trust_n) if not np.isnan(trust_n) else None,
                "_css": css,
                "_status": lstr,
                "_source": f"MSDS {annual_label}",
            })

    if rows:
        summary_df = pd.DataFrame(rows)
        for domain in summary_df["Domain"].unique():
            st.markdown(f"#### {domain}")
            for _, r in summary_df[summary_df["Domain"] == domain].iterrows():
                cols = st.columns([3, 1.5, 1.5, 1.2, 3.5])
                cols[0].markdown(
                    f"**{r['Indicator']}**<br>"
                    f"<span style='color:#9e9e9e;font-size:0.82em;font-weight:400;'>"
                    f"{r['Unit']}</span>",
                    unsafe_allow_html=True,
                )
                cols[1].metric("Trust", f"{r['Trust value']:.2f}")
                cols[2].metric("National mean", f"{r['National mean']:.2f}")
                cols[3].caption(
                    f"N={r['N (trust)']:,}" if r["N (trust)"] else "N/A"
                )
                cols[4].markdown(
                    status_badge(r["_status"], r["_css"]),
                    unsafe_allow_html=True,
                )
    else:
        st.info(
            "No overview data available. The MSDS data may still be loading — "
            "please wait and then click 'Clear cached data' in the sidebar."
        )


# ── TAB 2: PERINATAL MORTALITY ─────────────────────────────────────────────

with tab_perinatal:
    st.subheader("Perinatal Mortality")

    # MBRRACE-UK — primary source for trust-level mortality rates
    if not mbrrace_df.empty:
        st.markdown("### MBRRACE-UK Trust-Level Perinatal Mortality")
        st.caption(
            "Source: MBRRACE-UK Perinatal Mortality Data Viewer (timms.le.ac.uk) · "
            "Period: 2023 · Organisation type: NHS Trust (England) · "
            "Crude rates per 1,000 births"
        )

        _mbrrace_configs = [
            ("Stillbirth",              "TotalBirths",     "CrudeStillbirthRate",
             "OrganisationName", "per 1,000 births"),
            ("Neonatal death",          "TotalLiveBirths", "CrudeNeonatalDeathRate",
             "OrganisationName", "per 1,000 live births"),
            ("Extended perinatal death","TotalBirths",     "CrudePerinatalDeathRate",
             "OrganisationName", "per 1,000 births"),
        ]
        for label, dcol, rcol, ncol, unit in _mbrrace_configs:
            if rcol not in mbrrace_df.columns:
                continue
            plot_df = mbrrace_df.dropna(subset=[rcol, dcol]).copy()
            if "CountryName" in plot_df.columns:
                eng = plot_df[plot_df["CountryName"].str.upper() == "ENGLAND"]
                if not eng.empty:
                    plot_df = eng
            fig = make_funnel_chart(
                plot_df, rcol, dcol, ncol, focus_fragment,
                f"{label} rate — MBRRACE-UK 2023",
                unit, higher_is_worse=True, comparators=comparators or None,
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    data_note("MBRRACE-UK", "2023", _n_trusts(plot_df))
                    + " &nbsp;|&nbsp; England NHS trusts only",
                    unsafe_allow_html=True,
                )

        # Focus trust summary
        focus_mb = mbrrace_df[
            mbrrace_df["OrganisationName"]
            .str.upper().str.contains(focus_fragment.upper(), na=False)
        ] if "OrganisationName" in mbrrace_df.columns else pd.DataFrame()

        if not focus_mb.empty:
            mb_row = focus_mb.iloc[0]
            st.markdown(f"**{mb_row['OrganisationName']}**")
            mc = st.columns(3)
            for ci, (lbl, col) in enumerate([
                ("Stillbirth rate",                "CrudeStillbirthRate"),
                ("Neonatal mortality rate",         "CrudeNeonatalDeathRate"),
                ("Extended perinatal mortality rate","CrudePerinatalDeathRate"),
            ]):
                if col in mb_row.index and not pd.isna(mb_row[col]):
                    mc[ci].metric(lbl, f"{mb_row[col]:.2f} per 1,000")
    else:
        st.info(
            "MBRRACE trust-level data not found. "
            "Place `perinatal-mortality-rates-2023-trusthealth-board.csv` in the "
            "data/ folder, or upload via the MBRRACE Data tab."
        )

    st.markdown("---")
    st.subheader("Low Apgar Score at 5 Minutes (MSDS)")
    st.caption(
        "Proportion of term singleton births with Apgar score 0–6 at 5 minutes. "
        "A proxy indicator for acute perinatal compromise."
    )
    apgar_meta = MSDS_METRICS["Low Apgar at 5 min (term singleton)"]
    apgar_data = cqim_for_dim(apgar_meta["dim"])
    if not apgar_data.empty:
        fig = make_funnel_chart(
            apgar_data, "Rate", "Denominator", "Org_Name", focus_fragment,
            f"Low Apgar at 5 min (term singleton) — {_metric_label(apgar_data)}",
            apgar_meta["unit"], higher_is_worse=True, comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          annual_label, _n_trusts(apgar_data)),
                unsafe_allow_html=True,
            )
    else:
        st.caption("Low Apgar data not available for this period.")


# ── TAB 3: BIRTH OUTCOMES ──────────────────────────────────────────────────

with tab_birth:
    st.subheader("Birth Outcomes")
    st.caption(
        f"Source: MSDS Provider Level Experimental Data, NHS Digital · "
        f"Period: {annual_label}"
    )

    col1, col2 = st.columns(2)

    for col_w, metric_key in [(col1, "Preterm birth (<37 weeks)"),
                               (col2, "Low birth weight term (<2,500g)")]:
        meta = MSDS_METRICS[metric_key]
        data = cqim_for_dim(meta["dim"])
        vc   = _val_col(meta)
        if not data.empty:
            mlabel = _metric_label(data)
            fig = make_funnel_chart(
                data, vc, "Denominator", "Org_Name", focus_fragment,
                f"{metric_key} — {mlabel}",
                meta["unit"], meta["higher_is_worse"], comparators=comparators or None,
            )
            if fig:
                col_w.plotly_chart(fig, use_container_width=True)
        else:
            col_w.caption(f"{metric_key}: data not available.")

    st.markdown("---")
    st.subheader("Skin-to-Skin Contact at 1 Hour (Term)")
    meta = MSDS_METRICS["Skin-to-skin contact (1 hour, term)"]
    data = cqim_for_dim(meta["dim"])
    if not data.empty:
        fig = make_funnel_chart(
            data, "Rate_pct", "Denominator", "Org_Name", focus_fragment,
            f"Skin-to-skin contact at 1 hour (term) — {_metric_label(data)}",
            meta["unit"], meta["higher_is_worse"], comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          annual_label, _n_trusts(data)),
                unsafe_allow_html=True,
            )


# ── TAB 4: DELIVERY MODE ──────────────────────────────────────────────────

with tab_delivery:
    st.subheader("Delivery Mode and Caesarean Sections")
    st.caption(
        f"Source: MSDS Provider Level Experimental Data, NHS Digital · "
        f"Period: {annual_label} · "
        "Denominator: all recorded deliveries (excluding 'Other' and missing)"
    )

    cs_keys = [
        "Emergency caesarean section",
        "Elective caesarean section",
        "Spontaneous vaginal delivery",
        "Instrumental delivery",
    ]
    cs_cols = st.columns(2)
    for i, key in enumerate(cs_keys):
        meta = MSDS_METRICS[key]
        data = cqim_for_dim(meta["dim"])
        if not data.empty:
            fig = make_funnel_chart(
                data, "Rate_pct", "Denominator", "Org_Name", focus_fragment,
                f"{key} — {_metric_label(data)}",
                meta["unit"], meta["higher_is_worse"], comparators=comparators or None,
            )
            if fig:
                cs_cols[i % 2].plotly_chart(fig, use_container_width=True)
        else:
            cs_cols[i % 2].caption(f"{key}: data not available.")

    st.caption(
        "Note: Robson classification and VBAC rate are not available in the current "
        "MSDS experimental data format. Delivery mode is derived from "
        "DeliveryMethodBabyGroup."
    )


# ── TAB 5: MATERNAL MORBIDITY ──────────────────────────────────────────────

with tab_morbidity:
    st.subheader("Maternal Morbidity")

    st.markdown("#### 3rd and 4th Degree Perineal Tears")
    st.caption(
        "Rate of severe perineal injury (3rd or 4th degree tear) requiring "
        "surgical repair. Denominator: vaginal deliveries with a recorded "
        "genital tract trauma outcome (caesarean section deliveries are excluded). "
        "Where 2025 data has limited monthly coverage for this dimension, "
        "2024 annual data is used automatically."
    )
    tears_meta = MSDS_METRICS["3rd/4th degree perineal tears"]
    tears_data = cqim_for_dim(tears_meta["dim"])
    if not tears_data.empty:
        tears_label = _metric_label(tears_data)
        fig = make_funnel_chart(
            tears_data, "Rate", "Denominator", "Org_Name", focus_fragment,
            f"3rd/4th degree perineal tears — {tears_label}",
            tears_meta["unit"], higher_is_worse=True, comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          tears_label, _n_trusts(tears_data)),
                unsafe_allow_html=True,
            )
    else:
        st.caption("Perineal trauma data not available for this period.")

    st.markdown("---")
    st.markdown("#### Breastfeeding Initiation")
    st.caption("Proportion of babies receiving maternal or donor breast milk at first feed.")
    bf_meta = MSDS_METRICS["Breastfeeding initiation"]
    bf_data = cqim_for_dim(bf_meta["dim"])
    if not bf_data.empty:
        fig = make_funnel_chart(
            bf_data, "Rate_pct", "Denominator", "Org_Name", focus_fragment,
            f"Breastfeeding initiation — {_metric_label(bf_data)}",
            bf_meta["unit"], higher_is_worse=False, comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          _metric_label(bf_data), _n_trusts(bf_data)),
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.caption(
        "Postpartum haemorrhage (≥1,500 ml) and VBAC rate are not available "
        "in the MSDS experimental data format (2024 onwards). These were "
        "reported under the previous CQIM publication format."
    )


# ── TAB 6: MONTHLY TRENDS ─────────────────────────────────────────────────

with tab_trends:
    st.subheader("Monthly Trends")
    st.caption(
        f"Source: MSDS Provider Level Experimental Data, NHS Digital · "
        f"Period: {trend_label} · "
        "National mean shown as dashed line. Comparators selected from sidebar."
    )

    selected_metric = st.selectbox("Select indicator", list(MSDS_METRICS.keys()))
    meta_t = MSDS_METRICS[selected_metric]

    with st.spinner("Loading monthly data…"):
        trend_data = _load_trend(trend_year, selected_metric)

    if not trend_data.empty:
        fig = make_trend_chart(
            trend_data, focus_fragment,
            title=f"{selected_metric} — monthly trend {trend_label}",
            unit=meta_t["unit"],
            comparators=comparators if comparators else None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        focus_trend = trend_data[
            trend_data["Org_Name"].str.upper().str.contains(
                focus_fragment.upper(), na=False)
        ]
        if not focus_trend.empty:
            st.markdown(f"##### {focus_trust} — monthly data")
            show_cols = ["_month", "Numerator", "Denominator", "Rate"]
            show_cols = [c for c in show_cols if c in focus_trend.columns]
            st.dataframe(
                focus_trend[show_cols]
                .rename(columns={"_month": "Month",
                                  "Rate": f"Rate ({meta_t['unit']})"})
                .set_index("Month"),
                use_container_width=True,
            )
    else:
        st.info(
            f"No monthly trend data for '{selected_metric}' in {trend_year}. "
            "The indicator may not be present in the downloaded months."
        )


# ── TAB 7: RISK FACTORS ────────────────────────────────────────────────────

with tab_risk:
    st.subheader("Risk Factors")
    st.caption(
        f"Source: MSDS Provider Level Experimental Data, NHS Digital · "
        f"Period: {annual_label}"
    )

    st.markdown("### Smoking")

    smk_bk_meta = MSDS_METRICS["Smoking at booking"]
    smk_bk = cqim_for_dim(smk_bk_meta["dim"])
    if not smk_bk.empty:
        fig = make_funnel_chart(
            smk_bk, "Rate_pct", "Denominator", "Org_Name", focus_fragment,
            f"Smoking status at booking — {_metric_label(smk_bk)}",
            smk_bk_meta["unit"], higher_is_worse=True, comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          _metric_label(smk_bk), _n_trusts(smk_bk))
                + " &nbsp;|&nbsp; Denominator: women with a known smoking status",
                unsafe_allow_html=True,
            )

    smk_del_meta = MSDS_METRICS["Smoking at delivery (CO ≥4 ppm)"]
    smk_del = cqim_for_dim(smk_del_meta["dim"])
    if not smk_del.empty:
        fig = make_funnel_chart(
            smk_del, "Rate_pct", "Denominator", "Org_Name", focus_fragment,
            f"Smoking at delivery (CO ≥4 ppm) — {_metric_label(smk_del)}",
            smk_del_meta["unit"], higher_is_worse=True, comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          _metric_label(smk_del), _n_trusts(smk_del))
                + " &nbsp;|&nbsp; CO ≥4 ppm is a proxy for active smoking at delivery",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("### Early Antenatal Booking")
    eb_meta = MSDS_METRICS["Early antenatal booking (<10 weeks)"]
    eb_data = cqim_for_dim(eb_meta["dim"])
    if not eb_data.empty:
        fig = make_funnel_chart(
            eb_data, "Rate_pct", "Denominator", "Org_Name", focus_fragment,
            f"Antenatal booking before 10 weeks gestation — {_metric_label(eb_data)}",
            eb_meta["unit"], higher_is_worse=False, comparators=comparators or None,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                data_note("MSDS Provider Level, NHS Digital",
                          _metric_label(eb_data), _n_trusts(eb_data)),
                unsafe_allow_html=True,
            )


# ── TAB 8: MBRRACE DATA ────────────────────────────────────────────────────

with tab_mbrrace:
    st.subheader("MBRRACE-UK Perinatal Mortality Data")

    if not mbrrace_df.empty:
        st.markdown(
            f"Data loaded from `data/` folder — **{len(mbrrace_df):,} organisations**, "
            "reporting year 2023."
        )
        st.caption(
            "Source: MBRRACE-UK Perinatal Mortality Data Viewer "
            "(timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer/) · "
            "Crude rates are unadjusted; stabilised rates are case-mix adjusted."
        )

        # Key metrics for focus trust
        if "OrganisationName" in mbrrace_df.columns:
            focus_mb = mbrrace_df[
                mbrrace_df["OrganisationName"]
                .str.upper().str.contains(focus_fragment.upper(), na=False)
            ]
            if not focus_mb.empty:
                mb = focus_mb.iloc[0]
                st.markdown(f"**{mb['OrganisationName']} — 2023**")
                kc = st.columns(4)
                for ci, (lbl, col) in enumerate([
                    ("Total births",              "TotalBirths"),
                    ("Stillbirth rate",            "CrudeStillbirthRate"),
                    ("Neonatal mortality rate",    "CrudeNeonatalDeathRate"),
                    ("Extended perinatal mortality","CrudePerinatalDeathRate"),
                ]):
                    if col in mb.index and not pd.isna(mb[col]):
                        suffix = " per 1,000" if "rate" in col.lower() or "mortality" in col.lower() else ""
                        kc[ci].metric(lbl, f"{mb[col]:,.0f}{suffix}")

                # Comparator group
                if "ComparatorGroupName" in mb.index:
                    st.caption(
                        f"MBRRACE comparator group: **{mb['ComparatorGroupName']}** "
                        f"(group mean: {mb.get('GroupAveragePerinatalDeathRate', 'N/A'):.2f} "
                        f"per 1,000)" if not pd.isna(mb.get("GroupAveragePerinatalDeathRate", np.nan)) else
                        f"MBRRACE comparator group: **{mb['ComparatorGroupName']}**"
                    )

        st.markdown("---")
        st.markdown("### Funnel charts — all NHS trusts (England)")

        for label, dcol, rcol, unit in [
            ("Crude stillbirth rate",             "TotalBirths",
             "CrudeStillbirthRate",     "per 1,000 births"),
            ("Crude neonatal mortality rate",      "TotalLiveBirths",
             "CrudeNeonatalDeathRate",  "per 1,000 live births"),
            ("Crude extended perinatal mortality", "TotalBirths",
             "CrudePerinatalDeathRate", "per 1,000 births"),
            ("Stabilised extended perinatal mortality","TotalBirths",
             "StabilisedPerinatalDeathRate","per 1,000 births"),
        ]:
            if rcol not in mbrrace_df.columns:
                continue
            plot_df = mbrrace_df.dropna(subset=[rcol, dcol]).copy()
            if "CountryName" in plot_df.columns:
                eng = plot_df[plot_df["CountryName"].str.upper() == "ENGLAND"]
                if not eng.empty:
                    plot_df = eng
            fig = make_funnel_chart(
                plot_df, rcol, dcol, "OrganisationName", focus_fragment,
                f"{label} — MBRRACE-UK 2023",
                unit, higher_is_worse=True, comparators=comparators or None,
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        with st.expander("View full data table"):
            cols_show = [c for c in [
                "OrganisationName", "TotalBirths",
                "CrudeStillbirthRate", "StabilisedStillbirthRate",
                "CrudeNeonatalDeathRate", "StabilisedNeonatalDeathRate",
                "CrudePerinatalDeathRate", "StabilisedPerinatalDeathRate",
                "ComparatorGroupName",
            ] if c in mbrrace_df.columns]
            st.dataframe(mbrrace_df[cols_show], use_container_width=True)

    else:
        st.warning(
            "No MBRRACE file found in the data/ folder. "
            "Please place `perinatal-mortality-rates-2023-trusthealth-board.csv` "
            "in the data/ folder, or upload a file below."
        )

    st.markdown("---")
    st.markdown("### Upload updated or additional MBRRACE data")
    st.markdown("""
To download the latest data:
1. Visit [timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer](https://timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer/)
2. Select **Organisation type = Provider**, **Indicator = Extended perinatal mortality**
3. Download as CSV and save to the `data/` folder as `perinatal-mortality-rates-{year}-trusthealth-board.csv`
""")

    uploaded = st.file_uploader(
        "Upload MBRRACE trust-level CSV (optional)", type=["csv", "xlsx"]
    )
    if uploaded:
        try:
            mb_up = (pd.read_excel(uploaded) if uploaded.name.endswith(".xlsx")
                     else pd.read_csv(uploaded))
            st.success(f"Uploaded: {len(mb_up):,} rows, {len(mb_up.columns)} columns.")
            st.dataframe(mb_up.head(5), use_container_width=True)

            num_cols = mb_up.select_dtypes(include="number").columns.tolist()
            str_cols = mb_up.select_dtypes(include="object").columns.tolist()

            if len(str_cols) >= 1 and len(num_cols) >= 2:
                nc = st.selectbox("Trust name column", str_cols, index=0)
                vc = st.selectbox(
                    "Rate column", num_cols,
                    index=next((i for i, c in enumerate(num_cols)
                                if "rate" in c.lower() or "mortality" in c.lower()), 0)
                )
                dc = st.selectbox("Denominator column", num_cols,
                                  index=min(1, len(num_cols) - 1))
                us = st.selectbox("Unit", ["per 1,000 births", "%"], index=0)

                if st.button("Draw funnel chart"):
                    mb_clean = mb_up.dropna(subset=[vc, dc])
                    mb_clean = mb_clean[mb_clean[dc] > 0]
                    fig = make_funnel_chart(
                        mb_clean, vc, dc, nc, focus_fragment,
                        f"MBRRACE-UK — {uploaded.name}", us, True,
                        comparators=comparators or None,
                    )
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Insufficient data for funnel chart.")
        except Exception as e:
            st.error(f"Could not read file: {e}")

    st.markdown("---")
    st.markdown(
        "**Reference Tables** (cause of death, deprivation, ethnicity sub-groups): "
        "available from the MBRRACE-UK website as an Excel reference tables file."
    )

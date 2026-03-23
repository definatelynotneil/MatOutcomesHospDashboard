# data_loaders.py
# Data loading and caching for the Maternity Outcomes Dashboard.
from __future__ import annotations
# Sources: MSDS Monthly (NHS Digital), MBRRACE-UK (auto-loaded from disk).
# NOTE: No Streamlit imports here — all @st.cache_data wrappers live in app.py.

import io
import pathlib
import warnings

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# MSDS Clinical Quality Improvement Metrics derived from the exp-data format.
# msds_dim             = Dimension column value in the raw MSDS CSV
# numerator_measures   = list of Measure values that sum to the numerator
# denominator_exclude  = Measure values excluded from the denominator total
# scale                = 1000 → per 1,000 rate;  100 → percentage
MSDS_METRICS: dict[str, dict] = {
    "Low Apgar at 5 min (term singleton)": {
        "msds_dim": "ApgarScore5TermGroup7",
        "numerator_measures": ["0 to 6"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "per 1,000 term births",
        "scale": 1000,
        "domain": "Perinatal Outcome",
        "higher_is_worse": True,
    },
    "Preterm birth (<37 weeks)": {
        "msds_dim": "GestationLengthBirthGroup37",
        "numerator_measures": ["<37 weeks"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "per 1,000 births",
        "scale": 1000,
        "domain": "Birth Outcomes",
        "higher_is_worse": True,
    },
    "3rd/4th degree perineal tears": {
        "msds_dim": "GenitalTractTraumaticLesion",
        "numerator_measures": [
            "Perineal tear - third degree",
            "Perineal tear - fourth degree",
        ],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "per 1,000 vaginal deliveries",
        "scale": 1000,
        "domain": "Maternal Morbidity",
        "higher_is_worse": True,
    },
    "Low birth weight term (<2,500g)": {
        "msds_dim": "BirthweightTermGroup2500",
        "numerator_measures": ["Under 2500g"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "%",
        "scale": 100,
        "domain": "Birth Outcomes",
        "higher_is_worse": True,
    },
    "Emergency caesarean section": {
        "msds_dim": "DeliveryMethodBabyGroup",
        "numerator_measures": ["Emergency caesarean section"],
        "denominator_exclude": [
            "Missing Value / Value outside reporting parameters",
            "Other",
        ],
        "unit": "%",
        "scale": 100,
        "domain": "Delivery Mode",
        "higher_is_worse": True,
    },
    "Elective caesarean section": {
        "msds_dim": "DeliveryMethodBabyGroup",
        "numerator_measures": ["Elective caesarean section"],
        "denominator_exclude": [
            "Missing Value / Value outside reporting parameters",
            "Other",
        ],
        "unit": "%",
        "scale": 100,
        "domain": "Delivery Mode",
        "higher_is_worse": False,
    },
    "Spontaneous vaginal delivery": {
        "msds_dim": "DeliveryMethodBabyGroup",
        "numerator_measures": ["Spontaneous"],
        "denominator_exclude": [
            "Missing Value / Value outside reporting parameters",
            "Other",
        ],
        "unit": "%",
        "scale": 100,
        "domain": "Delivery Mode",
        "higher_is_worse": False,
    },
    "Instrumental delivery": {
        "msds_dim": "DeliveryMethodBabyGroup",
        "numerator_measures": ["Instrumental"],
        "denominator_exclude": [
            "Missing Value / Value outside reporting parameters",
            "Other",
        ],
        "unit": "%",
        "scale": 100,
        "domain": "Delivery Mode",
        "higher_is_worse": False,
    },
    "Smoking at booking": {
        "msds_dim": "SmokingStatusGroupBooking",
        "numerator_measures": ["Smoker"],
        "denominator_exclude": [
            "Missing Value / Value outside reporting parameters",
            "Unknown",
        ],
        "unit": "%",
        "scale": 100,
        "domain": "Risk Factors",
        "higher_is_worse": True,
    },
    "Smoking at delivery (CO ≥4 ppm)": {
        "msds_dim": "CO_Concentration_Delivery",
        "numerator_measures": ["4 and over ppm"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "%",
        "scale": 100,
        "domain": "Risk Factors",
        "higher_is_worse": True,
    },
    "Breastfeeding initiation": {
        "msds_dim": "BabyFirstFeedBreastMilkStatus",
        "numerator_measures": ["Maternal or Donor Breast Milk"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "%",
        "scale": 100,
        "domain": "Infant Health",
        "higher_is_worse": False,
    },
    "Early antenatal booking (<10 weeks)": {
        "msds_dim": "GestAgeFormalAntenatalBookingGroup",
        "numerator_measures": ["0 to 70 days"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "%",
        "scale": 100,
        "domain": "Access",
        "higher_is_worse": False,
    },
    "Skin-to-skin contact (1 hour, term)": {
        "msds_dim": "SkinToSkinContact1HourTerm",
        "numerator_measures": ["Y"],
        "denominator_exclude": ["Missing Value / Value outside reporting parameters"],
        "unit": "%",
        "scale": 100,
        "domain": "Infant Health",
        "higher_is_worse": False,
    },
}

# Inject "dim" = metric key into each entry (used in app.py for filtering)
for _k, _v in MSDS_METRICS.items():
    _v["dim"] = _k

# Backward-compat alias
MSDS_CQIMS = MSDS_METRICS

MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Preset comparator groups shown in the sidebar
COMPARATOR_PRESETS: dict[str, list[str]] = {
    "None": [],
    "Specialist women's hospitals": [
        "LIVERPOOL WOMEN'S NHS FOUNDATION TRUST",
        "CHELSEA AND WESTMINSTER HOSPITAL NHS FOUNDATION TRUST",
        "NOTTINGHAM UNIVERSITY HOSPITALS NHS TRUST",
    ],
    "West Midlands hospitals": [
        "SANDWELL AND WEST BIRMINGHAM HOSPITALS NHS TRUST",
        "UNIVERSITY HOSPITALS BIRMINGHAM NHS FOUNDATION TRUST",
        "THE ROYAL WOLVERHAMPTON NHS TRUST",
        "UNIVERSITY HOSPITALS COVENTRY AND WARWICKSHIRE NHS TRUST",
    ],
}

# MSDS monthly provider-level data URLs (exp-data format)
MSDS_URLS: dict[int, dict[str, str]] = {
    2024: {
        "Jan": "https://files.digital.nhs.uk/B9/B48FFB/msds-jan2024-exp-data.csv",
        "Feb": "https://files.digital.nhs.uk/60/D1D5F8/msds-feb2024-exp-data.csv",
        "Mar": "https://files.digital.nhs.uk/B2/24691F/msds-mar2024-exp-data.csv",
        "Apr": "https://files.digital.nhs.uk/B7/9D3FA9/msds-apr2024-exp-data.csv",
        "May": "https://files.digital.nhs.uk/9F/7F5835/msds-may2024-exp-data.csv",
        "Jun": "https://files.digital.nhs.uk/9C/6F6B1B/msds-jun2024-exp-data.csv",
        "Jul": "https://files.digital.nhs.uk/30/B19CDD/msds-jul2024-exp-data.csv",
        "Aug": "https://files.digital.nhs.uk/9D/AAAA86/msds-aug2024-exp-data.csv",
        "Sep": "https://files.digital.nhs.uk/D8/DCBAB8/msds-sep2024-exp-data.csv",
        "Oct": "https://files.digital.nhs.uk/D2/EC1099/msds-oct2024-exp-data.csv",
        "Nov": "https://files.digital.nhs.uk/F4/CF7A0B/msds-nov2024-exp-data.csv",
        "Dec": "https://files.digital.nhs.uk/6E/CC3FC4/msds-dec2024-exp-data.csv",
    },
    2025: {
        "Jan": "https://files.digital.nhs.uk/BE/E47BBB/msds-jan2025-exp-data.csv",
        "Feb": "https://files.digital.nhs.uk/E1/2CA6EC/msds-feb2025-exp-data.csv",
        "Mar": "https://files.digital.nhs.uk/2F/B1EC9C/msds-mar2025-exp-data.csv",
        "Apr": "https://files.digital.nhs.uk/50/A42CCF/msds-apr2025-exp-data.csv",
        "May": "https://files.digital.nhs.uk/E9/BDE3F8/msds-may2025-exp-data.csv",
        "Jun": "https://files.digital.nhs.uk/21/3CEC86/msds-jun2025-exp-data.csv",
        "Jul": "https://files.digital.nhs.uk/2E/0AF065/msds-jul2025-exp-data.csv",
        "Aug": "https://files.digital.nhs.uk/C4/21C1A8/msds-aug2025-exp-data.csv",
        "Sep": "https://files.digital.nhs.uk/58/567CCE/msds-sep2025-exp-data.csv",
        "Oct": "https://files.digital.nhs.uk/63/8A87FC/msds-oct2025-exp-data.csv",
        "Nov": "https://files.digital.nhs.uk/38/A6A4D2/msds-nov2025-exp-data.csv",
        "Dec": "https://files.digital.nhs.uk/FA/125DC2/msds-dec2025Provisional-exp-data.csv",
    },
}

BWC_ODS = "RQ3"
BWC_NAME = "BIRMINGHAM WOMEN'S AND CHILDREN'S NHS FOUNDATION TRUST"
BWC_SEARCH = "BIRMINGHAM WOMEN"


# ---------------------------------------------------------------------------
# LOCAL DISK CACHE
# ---------------------------------------------------------------------------

DATA_DIR = pathlib.Path(__file__).parent / "data"


def _parquet_path(name: str) -> pathlib.Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{name}.parquet"


def _load_parquet(name: str) -> pd.DataFrame:
    p = _parquet_path(name)
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            pass
    return pd.DataFrame()


def _save_parquet(df: pd.DataFrame, name: str) -> None:
    if df.empty:
        return
    try:
        df.to_parquet(_parquet_path(name), index=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# MSDS MONTHLY DATA
# ---------------------------------------------------------------------------

def _normalise_msds_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Rename 2023-format MSDS columns to the 2024+ standard."""
    rename = {
        "OrgCode": "Org_Code",
        "OrgName": "Org_Name",
        "OrgLevel": "Org_Level",
        "RPStartDate": "ReportingPeriodStartDate",
        "RPEndDate": "ReportingPeriodEndDate",
        "Indicator": "Dimension",
        "IndicatorFamily": "Count_Of",
        "Value": "Final_value",
        "Currency": "Measure",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


def _download_month(year: int, month: str, url: str) -> pd.DataFrame | None:
    """Download one monthly MSDS CSV. Returns None on failure."""
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
        df = _normalise_msds_cols(df)
        df["_month"] = month
        df["_year"] = year
        if "Org_Level" in df.columns:
            df = df[df["Org_Level"].str.strip().str.lower() == "provider"]
        if "Final_value" in df.columns:
            df["Final_value"] = pd.to_numeric(df["Final_value"], errors="coerce")
        return df if not df.empty else None
    except Exception:
        return None


def load_msds_year(year: int) -> pd.DataFrame:
    """
    Load MSDS provider-level data for *year*.

    On first call downloads all monthly CSVs from NHS Digital and caches to
    data/msds_{year}.parquet.  On subsequent calls loads from the parquet, then
    checks whether any months listed in MSDS_URLS are absent from the cache and
    downloads only those, updating the parquet in place.  This means the cache
    is incrementally kept up to date as new months are published.
    """
    if year not in MSDS_URLS:
        return pd.DataFrame()

    cache_name = f"msds_{year}"
    cached = _load_parquet(cache_name)

    # Determine which months are already cached
    cached_months: set[str] = (
        set(cached["_month"].dropna().unique())
        if not cached.empty and "_month" in cached.columns
        else set()
    )

    # Find months that are in MSDS_URLS but not yet in the cache
    missing_months = {
        m: u for m, u in MSDS_URLS[year].items() if m not in cached_months
    }

    if not missing_months:
        return cached  # Cache is complete — nothing to download

    # Download only the missing months
    new_dfs = []
    for month, url in missing_months.items():
        df = _download_month(year, month, url)
        if df is not None:
            new_dfs.append(df)

    if not new_dfs:
        # Nothing new downloaded — return whatever we have
        return cached

    new_data = pd.concat(new_dfs, ignore_index=True)

    # Merge with existing cache and save
    combined = (
        pd.concat([cached, new_data], ignore_index=True)
        if not cached.empty
        else new_data
    )
    _save_parquet(combined, cache_name)
    return combined


def get_msds_coverage(year: int) -> str:
    """Return a short string describing available months, e.g. 'Jan–Sep 2025 (5 months)'."""
    df = _load_parquet(f"msds_{year}")
    if df.empty or "_month" not in df.columns:
        return f"{year}"
    months = sorted(
        df["_month"].dropna().unique(),
        key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99,
    )
    if not months:
        return f"{year}"
    n = len(months)
    return f"{months[0]}–{months[-1]} {year} ({n} months)"


def get_best_annual_year() -> int:
    """Return the year with the most months of data available on disk."""
    best_year = max(MSDS_URLS.keys())
    best_n = 0
    for year in MSDS_URLS:
        df = _load_parquet(f"msds_{year}")
        if "_month" in df.columns:
            n = df["_month"].nunique()
            if n > best_n:
                best_n = n
                best_year = year
    return best_year


def get_latest_year() -> int:
    """Return the highest year that has data on disk."""
    for year in sorted(MSDS_URLS.keys(), reverse=True):
        df = _load_parquet(f"msds_{year}")
        if not df.empty:
            return year
    return max(MSDS_URLS.keys())


def _compute_metric_rows(df: pd.DataFrame, metric_key: str, meta: dict,
                         data_year: int | None = None) -> list[dict]:
    """Compute per-trust rows for one MSDS metric from a loaded year dataframe."""
    msds_dim = meta["msds_dim"]
    dim_data = df[df["Dimension"] == msds_dim]
    if dim_data.empty:
        return []

    # Derive year from data if not supplied
    if data_year is None and "_year" in df.columns:
        years = df["_year"].dropna().unique()
        data_year = int(years[0]) if len(years) == 1 else None

    num_measures  = set(meta["numerator_measures"])
    excl_measures = set(meta.get("denominator_exclude", []))

    # How many months are covered for this metric
    n_months = dim_data["_month"].nunique() if "_month" in dim_data.columns else None

    by_trust_measure = (
        dim_data
        .groupby(["Org_Name", "Measure"], as_index=False)["Final_value"]
        .sum()
    )

    rows = []
    for org_name, grp in by_trust_measure.groupby("Org_Name"):
        measure_counts: dict[str, float] = dict(zip(grp["Measure"], grp["Final_value"]))
        numerator   = sum(measure_counts.get(m, 0.0) for m in num_measures)
        denominator = sum(v for m, v in measure_counts.items() if m not in excl_measures)
        if denominator > 0:
            rows.append({
                "Org_Name": org_name,
                "Dimension": metric_key,
                "Numerator": numerator,
                "Denominator": denominator,
                "Rate": numerator / denominator * 1000,
                "Rate_pct": numerator / denominator * 100,
                "_data_year": data_year,
                "_data_months": n_months,
            })
    return rows


def _month_count_for_dim(df: pd.DataFrame, msds_dim: str) -> int:
    """Return number of distinct months present for a dimension in a dataframe."""
    if df.empty or "_month" not in df.columns:
        return 0
    sub = df[df["Dimension"] == msds_dim]
    return sub["_month"].nunique() if not sub.empty else 0


def get_cqim_annual(year: int) -> pd.DataFrame:
    """
    Compute annual MSDS metrics per trust from raw breakdown data.

    For each metric, uses the year with the most months of data for that
    specific dimension — falling back to (year-1) if the primary year has
    sparse coverage.  This handles cases where certain dimensions (e.g.
    GenitalTractTraumaticLesion) are only published for a subset of months
    in the most recent year.

    Returns columns:
        Org_Name, Dimension (= metric key name), Numerator, Denominator,
        Rate (per 1,000), Rate_pct (%)
    """
    df_primary  = load_msds_year(year)
    fallback_year = year - 1
    df_fallback = load_msds_year(fallback_year) if fallback_year in MSDS_URLS else pd.DataFrame()

    required = {"Dimension", "Measure", "Final_value", "Org_Name"}
    if not required.issubset(df_primary.columns if not df_primary.empty else set()):
        if df_primary.empty:
            return pd.DataFrame()

    results = []

    for metric_key, meta in MSDS_METRICS.items():
        msds_dim = meta["msds_dim"]

        primary_months  = _month_count_for_dim(df_primary,  msds_dim)
        fallback_months = _month_count_for_dim(df_fallback, msds_dim)

        # Use fallback year if it has meaningfully more months for this metric
        if fallback_months > primary_months and not df_fallback.empty:
            df_use    = df_fallback
            year_used = fallback_year
        else:
            df_use    = df_primary
            year_used = year

        rows = _compute_metric_rows(df_use, metric_key, meta, data_year=year_used)
        results.extend(rows)

    return pd.DataFrame(results) if results else pd.DataFrame()


def get_cqim_trend(year: int, metric_key: str) -> pd.DataFrame:
    """
    Monthly trend for one MSDS metric across all trusts.

    Uses the year with the most months for the given metric, falling back
    to (year-1) if that has better coverage.

    Returns columns: Org_Name, _month, Numerator, Denominator, Rate (per 1,000).
    Sorted by MONTH_ORDER.
    """
    if metric_key not in MSDS_METRICS:
        return pd.DataFrame()

    meta     = MSDS_METRICS[metric_key]
    msds_dim = meta["msds_dim"]

    df_primary  = load_msds_year(year)
    fallback_year = year - 1
    df_fallback = load_msds_year(fallback_year) if fallback_year in MSDS_URLS else pd.DataFrame()

    primary_months  = _month_count_for_dim(df_primary,  msds_dim)
    fallback_months = _month_count_for_dim(df_fallback, msds_dim)
    df = df_fallback if fallback_months > primary_months and not df_fallback.empty else df_primary

    if df.empty:
        return pd.DataFrame()

    dim_data = df[df["Dimension"] == msds_dim]
    if dim_data.empty:
        return pd.DataFrame()

    num_measures = set(meta["numerator_measures"])
    excl_measures = set(meta.get("denominator_exclude", []))

    by_trust_month_measure = (
        dim_data
        .groupby(["Org_Name", "_month", "Measure"], as_index=False)["Final_value"]
        .sum()
    )

    results = []
    for (org_name, month), grp in by_trust_month_measure.groupby(["Org_Name", "_month"]):
        measure_counts: dict[str, float] = dict(
            zip(grp["Measure"], grp["Final_value"])
        )
        numerator = sum(measure_counts.get(m, 0.0) for m in num_measures)
        denominator = sum(
            v for m, v in measure_counts.items() if m not in excl_measures
        )
        if denominator > 0:
            results.append({
                "Org_Name": org_name,
                "_month": month,
                "Numerator": numerator,
                "Denominator": denominator,
                "Rate": numerator / denominator * 1000,
            })

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    month_idx = {m: i for i, m in enumerate(MONTH_ORDER)}
    result_df["_month_order"] = result_df["_month"].map(month_idx)
    return (
        result_df
        .sort_values(["Org_Name", "_month_order"])
        .drop(columns="_month_order")
        .reset_index(drop=True)
    )


def get_msds_trust_list(year: int) -> list[str]:
    """Return sorted list of provider trust names from MSDS data."""
    df = load_msds_year(year)
    if df.empty or "Org_Name" not in df.columns:
        return []
    return sorted(df["Org_Name"].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# MBRRACE-UK AUTO-LOAD
# ---------------------------------------------------------------------------

def load_nmpa_pph() -> pd.DataFrame:
    """
    Auto-load NMPA 2023 trust-level PPH data from data/nmpa_pph_2023.csv.

    Accepts the NMPA export format with columns:
        Country, Organisation name, Organisation code,
        Numerator, Denominator, Unadjusted rate, Adjusted rate, GB mean

    Rates in the source file are percentages (e.g. "2.70%"); these are
    converted to per-1,000 maternities (multiply by 10).  Rate is also
    computed directly from Numerator/Denominator * 1000 for trusts that
    submitted counts.

    Only England rows are returned.  Rows without a valid Denominator are
    dropped (trusts that did not submit data to NMPA).

    Source: National Maternity and Perinatal Audit (NMPA) 2023 Clinical Report,
    RCOG / RCM / RCPCH / HQIP.  Available from https://www.npeu.ox.ac.uk/nmpa
    """
    candidates = sorted(DATA_DIR.glob("nmpa_pph*.csv"))
    if not candidates:
        return pd.DataFrame()
    try:
        # Strip lines whose text (ignoring an opening quote) starts with '#'
        with open(candidates[0], encoding="utf-8-sig", errors="replace") as f:
            lines = [
                ln for ln in f
                if not ln.lstrip('"').lstrip("'").startswith("#")
            ]
        if not lines:
            return pd.DataFrame()

        df = pd.read_csv(io.StringIO("".join(lines)))

        # Normalise column names to dashboard standard
        df = df.rename(columns={
            "Organisation name": "Org_Name",
            "Organisation code": "Org_Code",
        })

        # Keep England rows only
        if "Country" in df.columns:
            df = df[df["Country"].str.strip() == "England"].copy()

        # Parse numeric columns
        df["Numerator"]   = pd.to_numeric(df.get("Numerator"),   errors="coerce")
        df["Denominator"] = pd.to_numeric(df.get("Denominator"), errors="coerce")

        # Convert %-formatted rate columns to per 1,000
        for col in ["Unadjusted rate", "Adjusted rate", "GB mean"]:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(
                        df[col].astype(str).str.rstrip("%"), errors="coerce"
                    ) * 10  # percent → per 1,000
                )

        # Compute Rate per 1,000 from raw counts (preferred over reported %)
        valid = df["Denominator"] > 0
        df.loc[valid, "Rate"] = (
            df.loc[valid, "Numerator"] / df.loc[valid, "Denominator"] * 1000
        )

        # Drop rows with no denominator (trust did not submit data)
        df = df.dropna(subset=["Denominator", "Rate"])
        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def load_mbrrace_local() -> pd.DataFrame:
    """
    Auto-load MBRRACE trust-level perinatal mortality CSV from the data/ folder.
    Looks for files matching perinatal-mortality-*.csv or mbrrace-*.csv.
    """
    candidates = (
        sorted(DATA_DIR.glob("perinatal-mortality-*.csv"))
        + sorted(DATA_DIR.glob("mbrrace-*.csv"))
    )
    if not candidates:
        return pd.DataFrame()
    try:
        df = pd.read_csv(candidates[0])
        for col in df.columns:
            if any(k in col.lower() for k in ("rate", "births", "deaths", "total")):
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()

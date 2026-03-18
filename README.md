# NHS Maternity Outcomes Dashboard

An interactive Streamlit dashboard for comparing hospital-level maternity outcomes across NHS trusts in England. Designed to support clinical governance and quality improvement work.

**Primary focus trust:** Birmingham Women's and Children's NHS Foundation Trust (ODS: RQ3)
**Comparator:** All NHS acute trusts in England

---

## Features

- **Funnel (control) charts** — statistically compare each trust against national rates using 95% and 99.8% Poisson/binomial control limits
- **Focus trust highlighting** — selected trust shown as a diamond marker; comparator trusts shown as squares
- **Comparator presets** — quickly select specialist women's hospitals or West Midlands NHS trusts
- **Monthly trend charts** — track changes over time with national mean and comparator overlays
- **MBRRACE-UK perinatal mortality** — auto-loaded from the `data/` folder (stillbirth, neonatal, extended perinatal mortality rates)
- **Overview summary** — at-a-glance status across key domains with traffic-light badges

### Dashboard Tabs

| Tab | Content | Data source |
|---|---|---|
| Overview | Summary status for focus trust across all domains | MSDS + MBRRACE-UK |
| Perinatal Mortality | MBRRACE funnel charts + Low Apgar score | MBRRACE-UK + MSDS |
| Birth Outcomes | Preterm birth, low birth weight, skin-to-skin contact | MSDS |
| Delivery Mode | Emergency/elective CS, spontaneous vaginal, instrumental | MSDS |
| Maternal Morbidity | 3rd/4th degree perineal tears, breastfeeding initiation | MSDS |
| Monthly Trends | Any indicator over time, with comparators | MSDS |
| Risk Factors | Smoking at booking/delivery, early antenatal booking | MSDS |
| MBRRACE Data | Full MBRRACE funnel charts and data table | MBRRACE-UK |

---

## Quickstart

### Prerequisites

- Python 3.10+
- Internet access for first run (MSDS data downloaded from NHS Digital)

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/MatOutcomesHospDashboard.git
cd MatOutcomesHospDashboard
pip install -r requirements.txt
```

### Running the dashboard

```bash
streamlit run app.py
```

On first run the app downloads approximately 12 months of MSDS experimental data from NHS Digital (~30 s) and saves it to `data/` as Parquet files. Subsequent runs load from disk.

### Changing the focus trust

Use the **Focus Trust** selector in the left sidebar to switch to any NHS trust in the MSDS dataset. The default is Birmingham Women's and Children's NHS Foundation Trust.

---

## Data Sources

Full column-level documentation is in [`data/DATA_DICTIONARY.md`](data/DATA_DICTIONARY.md).

| Source | Indicators | Access |
|---|---|---|
| **MSDS Monthly Experimental Data** (NHS Digital) | Preterm birth, low birth weight, delivery mode, perineal tears, Apgar score, smoking, breastfeeding, skin-to-skin, antenatal booking | Auto-downloaded on first run |
| **MBRRACE-UK** (NPEU / University of Leicester) | Stillbirth rate, neonatal mortality rate, extended perinatal mortality rate (crude and stabilised) | Manual download required — see below |

All data are published aggregate statistics. No individual-level or patient-identifiable data are used.

### MBRRACE-UK data (manual step)

Trust-level perinatal mortality data must be downloaded from the MBRRACE-UK interactive data viewer:

1. Visit [timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer](https://timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer/)
2. Select **Organisation type = Provider**, choose the year and indicator
3. Download as CSV
4. Save to the `data/` folder as `perinatal-mortality-rates-{year}-trusthealth-board.csv`

The dashboard auto-loads any file matching this pattern on startup.

---

## Project Structure

```
app.py                     Main Streamlit dashboard
data_loaders.py            Data loading, caching, and metric computation
msds_exploration.py        Original Colab exploration script (reference only)
requirements.txt
data/
  DATA_DICTIONARY.md       Full documentation of all data sources and columns
  msds_{year}.parquet      Cached MSDS data (auto-generated, gitignored)
  perinatal-mortality-rates-{year}-trusthealth-board.csv   MBRRACE data (manual download)
```

---

## Technical Notes

### Funnel chart methodology

- **Poisson limits** used for rare-event rates reported per 1,000 (e.g. stillbirth, Apgar)
- **Binomial limits** used for proportions reported as percentages (e.g. caesarean section rate)
- Control limits are set at 95% (two-sigma equivalent) and 99.8% (three-sigma equivalent)
- National mean is computed as the weighted aggregate across all trusts with a denominator ≥ 20

### MSDS data format

The dashboard uses the NHS Digital **Experimental Provider Level** data format (2024 onwards). This format differs from the earlier CQIM publication:

- Metrics are computed by summing raw category counts across monthly files, then dividing numerator by denominator
- Each monthly file covers one calendar month; the app detects and back-fills any months not yet cached locally
- The year with the most complete month coverage is used for funnel charts; the most recent year is used for trend charts

### Caching

All `@st.cache_data` wrappers live in `app.py`. `data_loaders.py` is a plain Python module that uses only Parquet-based disk caching. This prevents stale in-memory results persisting across code changes.

---

## Licence

Data sources are published under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
Dashboard code is released under the [MIT Licence](LICENSE).

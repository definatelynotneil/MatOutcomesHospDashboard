# Data Dictionary – Maternity Outcomes Dashboard

All datasets used in the dashboard are documented here.
Files downloaded by the app are cached in this `data/` folder as Parquet files.

---

## 1. MSDS Monthly Experimental Data (NHS Digital)

| Property | Value |
|---|---|
| **Cached as** | `data/msds_{year}.parquet` |
| **Source** | NHS Digital – Maternity Services Monthly Statistics |
| **Publication page** | https://digital.nhs.uk/data-and-information/publications/statistical/maternity-services-monthly-statistics |
| **Coverage** | Monthly, 2024–present (2023 format differs — see note) |
| **Granularity** | Provider (NHS Trust) level |
| **Update frequency** | Monthly |
| **License** | Open Government Licence v3.0 |

### Column Reference (2024+ format)

| Column | Description |
|---|---|
| `Org_Code` | NHS ODS organisation code (e.g. `RQ3`) |
| `Org_Name` | Full trust name (UPPER CASE) |
| `Org_Level` | `Provider`, `National`, or `LMNS` |
| `ReportingPeriodStartDate` | First day of the reporting month |
| `ReportingPeriodEndDate` | Last day of the reporting month |
| `Dimension` | Metric name — CQIMs start with `CQIM`; demographic/volume measures use descriptive names |
| `Measure` | `Numerator`, `Denominator`, or `Rate` |
| `Final_value` | Numeric value |
| `Count_Of` | Population subgroup (e.g. ethnicity category) — blank for aggregate |
| `_month` | Added by loader: abbreviated month (`Jan`–`Dec`) |
| `_year` | Added by loader: calendar year |

### CQIM Dimensions

| Dimension value | Metric | Denominator |
|---|---|---|
| `CQIMPPH` | Postpartum haemorrhage ≥1,500ml | per 1,000 maternities |
| `CQIMTears` | 3rd or 4th degree perineal tear | per 1,000 vaginal term deliveries |
| `CQIMPreterm` | Singleton birth 22–36+6 weeks gestation | per 1,000 singleton deliveries |
| `CQIMApgar` | Apgar score 0–6 at 5 min, term singleton | per 1,000 term singleton births |
| `CQIMVBAC` | Vaginal birth after caesarean (VBAC) | % of eligible women |
| `CQIMRobson01` | Caesarean section rate, Robson Group 1 (nulliparous, term, singleton, cephalic, spontaneous labour) | % |
| `CQIMRobson02` | Caesarean section rate, Robson Group 2 (nulliparous, term, singleton, cephalic, induced or pre-labour CS) | % |
| `CQIMRobson05` | Caesarean section rate, Robson Group 5 (previous uterine scar, singleton, cephalic) | % |
| `CQIMSmokingBooking` | Smoking status recorded at booking | % |
| `CQIMSmokingDelivery` | Smoking at time of delivery | % |
| `CQIMBreastfeeding` | Initial feed was breastmilk | % |

### 2023 vs 2024+ Column Differences

The 2023 monthly files used older column names. The loader applies this rename dict automatically:

```
RPStartDate       → ReportingPeriodStartDate
RPEndDate         → ReportingPeriodEndDate
Indicator         → Dimension
Value             → Final_value
Currency          → Measure
IndicatorFamily   → Count_Of
OrgCode           → Org_Code
OrgName           → Org_Name
OrgLevel          → Org_Level
```

### URL Pattern

```
2024: https://files.digital.nhs.uk/{hash}/msds-{mon}2024-exp-data.csv
2025: https://files.digital.nhs.uk/{hash}/msds-{mon}2025-exp-data.csv
```

Full URL list is in `data_loaders.py → MSDS_URLS`.

---

## 2. NHS Fingertips / OHID (API)

| Property | Value |
|---|---|
| **Cached as** | `data/fingertips_area14.parquet` |
| **Source** | Office for Health Inequalities and Disparities (OHID) |
| **API base** | https://fingertips.phe.org.uk/api |
| **Coverage** | Annual, up to ~2023 |
| **Granularity** | NHS Acute Trust (area_type_id = 14) |
| **Update frequency** | Annual (profile-dependent) |
| **License** | Open Government Licence v3.0 |

### Indicator IDs Used

| Indicator | ID | Unit | Note |
|---|---|---|---|
| Stillbirth rate | 92530 | per 1,000 births | Based on birth registrations |
| Neonatal mortality rate | 92705 | per 1,000 live births | Under 28 days |
| Preterm births (<37 weeks) | 91743 | % | All births |
| Low birth weight – term babies | 20101 | % | Term babies only |
| Low birth weight – all babies | 92531 | % | All gestations |
| Caesarean section rate | 92244 | % | Elective + emergency combined |
| Smoking status at delivery | 93085 | % | Women smoking at delivery |
| Obesity in early pregnancy | 94131 | % | BMI ≥30 at booking |
| Early access to maternity care | 94121 | % | Booking by 12+6 weeks |

### Column Reference (Fingertips CSV format)

| Column | Description |
|---|---|
| `Indicator ID` | Numeric indicator ID |
| `Indicator Name` | Full indicator name |
| `Area Code` | ODS/ONS area code (e.g. `RQ3` for NHS Trust) |
| `Area Name` | Trust name (mixed case) |
| `Area Type` | Area type label |
| `Time period` | e.g. `2022/23` |
| `Time period Sortable` | Numeric sortable form of Time period |
| `Value` | Rate or percentage |
| `Count` | Numerator (events) |
| `Denominator` | Population denominator |
| `Lower CI 95.0 limit` | Pre-computed lower 95% CI |
| `Upper CI 95.0 limit` | Pre-computed upper 95% CI |
| `Lower CI 99.8 limit` | Pre-computed lower 99.8% CI |
| `Upper CI 99.8 limit` | Pre-computed upper 99.8% CI |
| `Compared to England value or percentiles` | Fingertips comparison label |

### API Endpoints

```
All data for indicator at area type:
  GET /all_data/csv/by_indicator_id?indicator_ids={id}&area_type_id={at}

Indicator metadata:
  GET /indicator_metadata/csv/by_indicator_id?indicator_ids={id}

Area types:
  GET /area_types
```

---

## 3. NHS Annual Maternity Statistics – HES Provider Level (NHS Digital)

| Property | Value |
|---|---|
| **Cached as** | `data/hes_provider_{year_label}.parquet` (if successfully parsed) |
| **Source** | NHS Digital – NHS Maternity Statistics |
| **Publication page** | https://digital.nhs.uk/data-and-information/publications/statistical/nhs-maternity-statistics |
| **Coverage** | Annual financial years; 2024–25 is latest |
| **Granularity** | NHS Trust (provider) level |
| **Update frequency** | Annual |
| **License** | Open Government Licence v3.0 |
| **Format** | Excel workbook, multiple sheets |

### Download URLs

| Year | URL |
|---|---|
| 2024–25 | https://files.digital.nhs.uk/90/9B8B43/hosp-epis-stat-mat-pla-2425_v2.xlsx |
| 2023–24 | https://files.digital.nhs.uk/3F/228AD4/hosp-epis-stat-mat-pla-2023-24.xlsx |

### Key Content (sheets vary by year)

- Delivery method by trust (spontaneous vaginal, instrumental, elective CS, emergency CS)
- Onset of labour (spontaneous, induced, no labour)
- Gestation at delivery
- Age of mother
- Ethnicity of mother
- Deprivation quintile (IMD)
- Birth weight categories

---

## 4. MBRRACE-UK Perinatal Mortality (NPEU / University of Leicester)

| Property | Value |
|---|---|
| **Cached as** | Manual upload only — `data/mbrrace_upload.parquet` if saved |
| **Source** | MBRRACE-UK, hosted at TIMMS (University of Leicester) |
| **Interactive viewer** | https://timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer/ |
| **Reference tables** | https://timms.le.ac.uk/mbrrace-uk-perinatal-mortality/files/MBRRACE_Reference_Tables_2023.xlsx |
| **Coverage** | Births 2013–2023 (2023 data published May 2025) |
| **Granularity** | NHS Provider Trust level |
| **Update frequency** | Annual |
| **Note** | Trust-level rates are in the interactive data viewer only. Reference tables contain CODAC cause-of-death classifications and sub-group analyses (ethnicity, deprivation). |

### Indicators Available (interactive viewer)

| Indicator | Definition |
|---|---|
| Crude stillbirth rate | Stillbirths per 1,000 births (≥24 weeks) |
| Crude neonatal mortality rate | Neonatal deaths per 1,000 live births |
| Extended perinatal mortality rate | (Stillbirths + neonatal deaths) per 1,000 births |
| Stabilised rates | Funnel-adjusted rates using indirect standardisation |
| Ethnicity sub-group rates | Available in reference tables |
| Deprivation sub-group rates | Available in reference tables (IMD quintiles) |

### How to Download Trust-Level Data

1. Visit https://timms.le.ac.uk/mbrrace-uk-perinatal-mortality/data-viewer/
2. Select Year, Organisation type = **Provider**, Indicator
3. Click **Download CSV**
4. Upload to the dashboard's MBRRACE tab

---

## 5. NMPA 2023 — Postpartum Haemorrhage (RCOG / RCM / RCPCH / HQIP)

| Property | Value |
|---|---|
| **Cached as** | Manual — `data/nmpa_pph_2023.csv` |
| **Source** | National Maternity and Perinatal Audit (NMPA) 2023 Clinical Report |
| **Publisher** | RCOG / RCM / RCPCH / HQIP |
| **Report URL** | https://www.npeu.ox.ac.uk/nmpa/reports |
| **Coverage** | NHS trust deliveries in England, 2021–22 |
| **Granularity** | NHS Trust (provider) level |
| **Update frequency** | Annual |
| **Definition** | Major obstetric haemorrhage: estimated blood loss ≥1,500 ml at or after delivery |
| **Unit** | Rate per 1,000 maternities |

### CSV Column Reference (NMPA export format)

| Column | Description |
|---|---|
| `Country` | `England`, `Scotland`, or `Wales` — loader filters to England only |
| `Organisation name` | Full trust name (mixed case) — mapped to `Org_Name` |
| `Organisation code` | NHS ODS code (e.g. `RQ3`) — mapped to `Org_Code` |
| `Numerator` | PPH cases (blood loss ≥1,500 ml); blank = trust did not submit |
| `Denominator` | Total maternities; blank = trust did not submit |
| `Unadjusted rate` | Raw rate as a percentage (e.g. `2.70%`); converted to per 1,000 by loader |
| `Adjusted rate` | Case-mix adjusted rate (maternal age, deprivation, BMI, complications); `%` → per 1,000 |
| `GB mean` | Great Britain mean rate; `%` → per 1,000 |

The loader computes `Rate` per 1,000 directly from `Numerator / Denominator * 1000`.
Rows with no valid `Denominator` (non-submitting trusts) are dropped.
Lines beginning with `#` (or `"#`) are treated as comments and ignored.

### Why not MSDS?

PPH (blood loss ≥1,500 ml) was reported in the previous MSDS CQIM publication format
under dimension `CQIMPPH`. It is not included in the MSDS experimental data format
used from 2024 onwards.

---

## 6. CQC Inspection Ratings (Care Quality Commission)

| Property | Value |
|---|---|
| **Cached as** | Not currently integrated — download separately |
| **Source** | Care Quality Commission |
| **Bulk download** | https://www.cqc.org.uk/sites/default/files/2026-03/01_March_2026_Latest_ratings.ods |
| **Coverage** | All CQC-registered services, updated monthly |
| **Format** | ODS spreadsheet |
| **Filter for maternity** | Column `Service type` = "Maternity and midwifery services" |

### Key Columns

| Column | Description |
|---|---|
| `Provider ID` | CQC provider ID |
| `Provider name` | Trust name |
| `Location name` | Hospital site name |
| `Service type` | e.g. "Maternity and midwifery services" |
| `Overall rating` | Outstanding / Good / Requires Improvement / Inadequate |
| `Safe rating` | Safe domain rating |
| `Effective rating` | Effective domain rating |
| `Caring rating` | Caring domain rating |
| `Responsive rating` | Responsive domain rating |
| `Well-led rating` | Well-led domain rating |
| `Report publication date` | Date of most recent inspection report |

---

## Focus Trust Reference

| Property | Value |
|---|---|
| **Trust name** | Birmingham Women's and Children's NHS Foundation Trust |
| **ODS code** | RQ3 |
| **Search fragment used in code** | `BIRMINGHAM WOMEN` |
| **MSDS Org_Name value** | `BIRMINGHAM WOMEN'S AND CHILDREN'S NHS FOUNDATION TRUST` |
| **Fingertips Area Code** | RQ3 |
| **Fingertips Area Name** | Birmingham Women's and Children's NHS Foundation Trust |
| **CQC Provider ID** | 1-5893777591 |

---

## Notes on Rates and Denominators

- **MSDS CQIMs**: Numerator and Denominator are summed across all months in a year to produce an annual rate. Monthly rates can be volatile for smaller trusts.
- **Fingertips**: Values and confidence intervals are pre-computed by OHID; denominators may reflect the birth registration population (resident-based), not delivery-site.
- **MBRRACE**: Stabilised rates use indirect standardisation to adjust for case-mix. Use crude rates for direct comparison; use stabilised rates for benchmarking.
- **Funnel plots**: The dashboard uses Poisson limits for rates <10% (per 1,000 measures) and binomial limits for proportions ≥10%.

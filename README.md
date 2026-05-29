<div align="center">

# 🌿 Green Chemistry Dashboard

### Suzuki-Miyaura Cross-Coupling Reaction Analysis

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.52.1-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![ORD](https://img.shields.io/badge/Dataset-ORD-4CAF50?style=for-the-badge)](https://open-reaction-database.org/dataset/ord_dataset-3b5db90e337942ea886b8f5bc5e3aa72)

> **An interactive sustainability analytics platform for evaluating Suzuki-Miyaura cross-coupling reactions from the Open Reaction Database — computing green chemistry metrics, environmental impact and catalyst performance with AI-powered recommendations.**

[🔗 Dataset](https://open-reaction-database.org/dataset/ord_dataset-3b5db90e337942ea886b8f5bc5e3aa72) · [📊 Dashboard](#-dashboard-tabs) · [🚀 Quick Start](#-quick-start)

</div>

---

## 📌 What This Project Does

Suzuki-Miyaura cross-coupling is one of the most widely used reactions in pharmaceutical and fine chemical synthesis. However, evaluating its **sustainability** — waste generated, atom efficiency, carbon footprint — requires complex multi-metric analysis.

This dashboard pulls reaction data directly from the **Open Reaction Database (ORD)** and computes seven green chemistry metrics per reaction, enabling chemists to:

- Compare catalysts by yield, E-Factor and environmental impact
- Identify the greenest reaction conditions statistically
- Get AI expert system recommendations for sustainable synthesis
- Export full sustainability reports as PDF or DOCX

---

## 📊 Dashboard Tabs

| # | Tab | What It Shows |
|---|---|---|
| 1 | **Dashboard Overview** | Average yield, RME, E-Factor, CO₂ — key KPIs at a glance |
| 2 | **Green Chemistry Metrics** | Metrics comparison charts + correlation heatmap |
| 3 | **Catalyst Performance** | Side-by-side catalyst statistics and ranking |
| 4 | **Environmental Impact** | CO₂ emissions distribution + E-Factor analysis |
| 5 | **Advanced Statistics** | ANOVA + pairwise comparisons + confidence intervals |
| 6 | **Expert System** | AI-generated recommendations + learned synthesis rules |
| 7 | **Sensitivity Analysis** | Factor impact on yield — which variables matter most |
| 8 | **Data & Export** | Full filtered data table + PDF/DOCX report download |
| 9 | **Custom Reaction Evaluation** | Enter your own reaction conditions and get instant metrics |

---

## 🧪 Green Chemistry Metrics Computed

| Metric | Formula | Meaning |
|---|---|---|
| **E-Factor** | Waste (kg) / Product (kg) | Lower = greener. Industry gold standard |
| **RME** | AE × Yield / 100 | Reaction Mass Efficiency — overall efficiency |
| **Atom Economy (AE)** | MW(product) / ΣMW(reactants) × 100 | % atoms that end up in product |
| **PMI** | E-Factor + 1 | Process Mass Intensity — total material used |
| **Carbon Efficiency** | f(yield) | % carbon atoms incorporated into product |
| **Solvent Score** | 1–10 scale | Greenness of solvent choice |
| **CO₂ Footprint** | f(energy, solvent) | Estimated kg CO₂ per reaction |

---

## 🗂️ Project Structure

```
green-chemistry-dashboard/
│
├── data/
     └── ord_search_results.pb
├── images/
     └── logo.png
├── app.py                    # Main Streamlit application (9-tab dashboard)
├── data_parser.py            # ORD protobuf parser → pandas DataFrame
├── metrics_calculator.py     # All 7 green chemistry metric computations
├── visualizations.py         # Plotly charts — yield, heatmap, scatter, bar
├── advanced_analytics.py     # ANOVA, expert system, sensitivity analysis
├── pdf_generator.py          # PDF and DOCX report generator (ReportLab)
└──requirements.txt          # All dependencies pinned
```

---

## ⚙️ How It Works

```
ORD Database (protobuf)
        │
        ▼
┌─────────────────────────┐
│    data_parser.py       │  Parses .pb files → extracts reactants,
│    ORDDataParser        │  products, catalysts, solvents, yields
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  metrics_calculator.py  │  Computes E-Factor, RME, AE, PMI,
│  GreenMetricsCalculator │  Carbon Efficiency, Solvent Score, CO₂
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  advanced_analytics.py  │  ANOVA catalyst comparison
│  StatisticalAnalyzer    │  Expert rules · Sensitivity analysis
│  ExpertSystem           │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   visualizations.py     │  Plotly interactive charts
│   app.py (Streamlit)    │  9-tab dashboard with sidebar filters
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   pdf_generator.py      │  PDF / DOCX sustainability reports
│   PDFReportGenerator    │  with all metrics and charts
└─────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Manoj8541/ord-green-chemistry-dashboard.git
cd ord-green-chemistry-dashboard
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Add the ORD dataset
Download the dataset protobuf file from:
```
https://open-reaction-database.org/dataset/ord_dataset-3b5db90e337942ea886b8f5bc5e3aa72
```
Place it at:
```
data/ord_search_results.pb
```

### 4. Run the app
```bash
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`

---

## 🔬 Dataset

| Field | Details |
|---|---|
| **Source** | Open Reaction Database (ORD) |
| **Dataset ID** | `ord_dataset-3b5db90e337942ea886b8f5bc5e3aa72` |
| **Reaction Type** | Suzuki-Miyaura Cross-Coupling |
| **Link** | [View on ORD](https://open-reaction-database.org/dataset/ord_dataset-3b5db90e337942ea886b8f5bc5e3aa72) |

---

## 🛠️ Tech Stack

| Category | Tools |
|---|---|
| Web Framework | Streamlit 1.52.1 |
| Chemistry |        ord-schema 0.3.99      |
| Data | Pandas, NumPy, PyArrow |
| Visualisation | Plotly 6.5.0, Matplotlib |
| Statistics | SciPy, Statsmodels |
| Report Generation | ReportLab (PDF), Pandas (Excel), python-docx (docx) |

---

<div align="center">
<i>Built with Streamlit · RDKit · Open Reaction Database</i>
</div>

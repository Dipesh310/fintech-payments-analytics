# PayPulse — Digital Payments & Risk Analytics

An end-to-end **Fintech Data Analytics** project featuring a deterministic transaction generator, a SQLite analytical warehouse with a **Data Quality Quarantine** layer, modular ANSI SQL analytics queries, automated unit tests, GitHub Actions CI, and a live **interactive dashboard** ready for **GitHub Pages**.

## Architecture

```text
data/generate_data.py  ──▶  data/raw_transactions.csv (15,120 rows)
                                  │
                                  ▼
src/pipeline.py        ──▶  SQLite Warehouse (clean_transactions + quarantine_transactions)
                                  │
                                  ├──▶ sql/analytics_queries.sql
                                  ├──▶ outputs/*.csv (analyst exports)
                                  └──▶ docs/data/dashboard_data.json ──▶ docs/index.html (GitHub Pages)
```

## Key Analytical Modules

- **Executive Payments Performance:** Monthly GMV, net take-rate fee revenue (bps), approval rates, and settlement latency across 5 payment rails (`UPI / Instant`, `Credit Card`, `Debit Card`, `Digital Wallet`, `Bank Transfer`).
- **Risk & Fraud Intelligence:** 24-hour nocturnal risk spike profiling, merchant-category risk exposure matrix, interactive risk-score cutoff simulator, and inspectable high-risk transaction alerts.
- **Cohort Retention:** Monthly customer retention heatmap (M0–M5) and cohort decay curves.
- **Data Quality & Quarantine:** Captures malformed timestamps, missing/duplicate transaction IDs, negative amounts, and invalid statuses into `quarantine_transactions` before analytical aggregation.

## Quickstart (Zero External Dependencies)

The pipeline and test suite run on standard Python 3.11+ with no third-party packages required:

```bash
# 1. Generate synthetic fintech dataset (15,000 valid + 120 malformed records)
python3 data/generate_data.py

# 2. Run ETL, SQLite warehouse load, SQL analytics & dashboard JSON export
python3 src/pipeline.py

# 3. Run automated data quality & KPI reconciliation tests
python3 -m unittest discover -s tests -v
```

## Hosting Live on GitHub Pages

1. Create a new repository on GitHub (e.g., `https://github.com/Dipesh310/fintech-payments-analytics`).
2. Initialize Git in this folder and push to `main`:
   ```bash
   git init -b main
   git add .
   git commit -m "Initial commit: PayPulse fintech analytics pipeline and dashboard"
   git remote add origin https://github.com/Dipesh310/fintech-payments-analytics.git
   git push -u origin main
   ```
3. In your GitHub repository, go to **Settings → Pages**.
4. Under **Build and deployment**, set **Source** to **Deploy from a branch**, select **`main`** and folder **`/docs`**, then click **Save**.
5. Your interactive dashboard will go live at:
   `https://<your-username>.github.io/fintech-payments-analytics/`

## Project Structure

| Path | Purpose |
| :--- | :--- |
| `data/generate_data.py` | Deterministic fintech payments & fraud pattern generator (`seed=42`) |
| `sql/analytics_queries.sql` | Named SQL queries for KPIs, rails, merchant risk, cohorts, and cube |
| `src/pipeline.py` | ETL runner, schema validation, quarantine loader, and JSON/CSV exporter |
| `tests/test_pipeline.py` | Automated reconciliation & data-quality verification suite |
| `docs/index.html` | Self-contained interactive dashboard deployed via GitHub Pages |
| `docs/data/dashboard_data.json` | Pre-aggregated analytics payload consumed by the dashboard |
| `.github/workflows/ci.yml` | GitHub Actions workflow running the pipeline and tests on every push |

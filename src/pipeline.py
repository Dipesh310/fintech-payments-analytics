"""PayPulse Fintech Analytics — End-to-End ETL & Analytical Pipeline.

Stages:
1. Ensure raw CSV exists (runs deterministic generator if absent).
2. Validate & load into SQLite warehouse (`clean_transactions` + `quarantine_transactions`).
3. Execute named SQL queries from `sql/analytics_queries.sql`.
4. Export CSV reports to `outputs/` and consolidated JSON to `docs/data/dashboard_data.json`.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

VALID_STATUSES = {"APPROVED", "DECLINED", "CHARGEBACK", "FRAUD_FLAGGED"}


def parse_named_sql(sql_path: Path) -> dict[str, str]:
    """Parse `-- name: <query_name>` blocks from a SQL file."""
    queries: dict[str, str] = {}
    current_name: str | None = None
    buffer: list[str] = []

    for line in sql_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("-- name:"):
            if current_name and buffer:
                queries[current_name] = "\n".join(buffer).strip()
            current_name = stripped.split(":", 1)[1].strip()
            buffer = []
        elif current_name is not None:
            buffer.append(line)

    if current_name and buffer:
        queries[current_name] = "\n".join(buffer).strip()

    return queries


def init_warehouse(conn: sqlite3.Connection) -> None:
    """Create analytical warehouse and quarantine tables."""
    conn.executescript(
        """
        DROP TABLE IF EXISTS clean_transactions;
        DROP TABLE IF EXISTS quarantine_transactions;

        CREATE TABLE clean_transactions (
            transaction_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            cohort_month TEXT NOT NULL,
            payment_rail TEXT NOT NULL,
            merchant_category TEXT NOT NULL,
            region TEXT NOT NULL,
            amount_usd REAL NOT NULL CHECK (amount_usd > 0),
            fee_usd REAL NOT NULL CHECK (fee_usd >= 0),
            status TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            is_international INTEGER NOT NULL,
            risk_score REAL NOT NULL
        );

        CREATE INDEX idx_clean_month ON clean_transactions(SUBSTR(timestamp, 1, 7));
        CREATE INDEX idx_clean_rail ON clean_transactions(payment_rail);
        CREATE INDEX idx_clean_category ON clean_transactions(merchant_category);
        CREATE INDEX idx_clean_status ON clean_transactions(status);

        CREATE TABLE quarantine_transactions (
            row_number INTEGER NOT NULL,
            transaction_id TEXT,
            raw_payload TEXT NOT NULL,
            quarantine_reason TEXT NOT NULL
        );
        """
    )


def validate_and_load(conn: sqlite3.Connection, csv_path: Path) -> dict[str, int]:
    """Validate raw CSV rows, routing invalid records to quarantine_transactions."""
    seen_ids: set[str] = set()
    clean_batch: list[tuple] = []
    quarantine_batch: list[tuple] = []

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row_num, row in enumerate(reader, start=2):
            txn_id = (row.get("transaction_id") or "").strip()
            ts = (row.get("timestamp") or "").strip()
            status = (row.get("status") or "").strip()

            reason = None
            if not txn_id:
                reason = "Missing transaction_id"
            elif txn_id in seen_ids:
                reason = "Duplicate transaction_id"
            elif status not in VALID_STATUSES:
                reason = f"Invalid status ({status})"
            else:
                try:
                    datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    reason = "Malformed timestamp"

            amount = 0.0
            fee = 0.0
            latency = 0
            is_intl = 0
            risk_score = 0.0
            if reason is None:
                try:
                    amount = float(row["amount_usd"])
                    fee = float(row["fee_usd"])
                    latency = int(row["latency_ms"])
                    is_intl = int(row["is_international"])
                    risk_score = float(row["risk_score"])
                    if amount <= 0:
                        reason = "Non-positive amount_usd"
                except (ValueError, KeyError):
                    reason = "Numeric parse error"

            if reason is not None:
                quarantine_batch.append(
                    (row_num, txn_id, json.dumps(row), reason)
                )
            else:
                seen_ids.add(txn_id)
                clean_batch.append(
                    (
                        txn_id,
                        ts,
                        row["customer_id"].strip(),
                        row["cohort_month"].strip(),
                        row["payment_rail"].strip(),
                        row["merchant_category"].strip(),
                        row["region"].strip(),
                        amount,
                        fee,
                        status,
                        latency,
                        is_intl,
                        risk_score,
                    )
                )

    conn.executemany(
        """
        INSERT INTO clean_transactions (
            transaction_id, timestamp, customer_id, cohort_month,
            payment_rail, merchant_category, region, amount_usd,
            fee_usd, status, latency_ms, is_international, risk_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        clean_batch,
    )
    conn.executemany(
        """
        INSERT INTO quarantine_transactions (
            row_number, transaction_id, raw_payload, quarantine_reason
        ) VALUES (?, ?, ?, ?)
        """,
        quarantine_batch,
    )
    conn.commit()

    return {
        "clean_rows": len(clean_batch),
        "quarantined_rows": len(quarantine_batch),
        "total_processed": len(clean_batch) + len(quarantine_batch),
    }


def query_as_dicts(conn: sqlite3.Connection, sql: str) -> list[dict]:
    """Execute a SELECT query and return a list of dictionaries."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql)
    return [dict(row) for row in cur.fetchall()]


def write_csv(rows: list[dict], out_path: Path) -> None:
    """Write a list of dicts to a CSV file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(project_root: Path | None = None) -> dict:
    """Run the full ETL and analytics export pipeline."""
    root = project_root or Path(__file__).resolve().parents[1]
    raw_csv = root / "data" / "raw_transactions.csv"
    db_path = root / "data" / "fintech_warehouse.db"
    sql_path = root / "sql" / "analytics_queries.sql"
    outputs_dir = root / "outputs"
    dashboard_json = root / "docs" / "data" / "dashboard_data.json"

    if not raw_csv.exists():
        sys.path.insert(0, str(root))
        from data.generate_data import generate_dataset

        generate_dataset(raw_csv)

    queries = parse_named_sql(sql_path)

    with sqlite3.connect(db_path) as conn:
        init_warehouse(conn)
        dq_counts = validate_and_load(conn, raw_csv)

        results = {name: query_as_dicts(conn, sql) for name, sql in queries.items()}

    # Export analyst-ready CSV tables
    write_csv(results["monthly_trends"], outputs_dir / "monthly_kpis.csv")
    write_csv(results["rail_performance"], outputs_dir / "rail_performance.csv")
    write_csv(results["merchant_risk_matrix"], outputs_dir / "merchant_risk.csv")
    write_csv(results["top_risk_alerts"], outputs_dir / "flagged_anomalies.csv")

    # Assemble dashboard payload
    payload = {
        "metadata": {
            "project": "PayPulse Digital Payments & Risk Analytics",
            "generated_at": "2026-11-24",
            "date_range": "2025-12 to 2026-11",
            "usd_to_inr_rate": 84.0,
            "dq_counts": dq_counts,
        },
        "executive_kpis": results["executive_kpis"][0],
        "monthly_trends": results["monthly_trends"],
        "rail_performance": results["rail_performance"],
        "merchant_risk_matrix": results["merchant_risk_matrix"],
        "regional_breakdown": results["regional_breakdown"],
        "hourly_risk_profile": results["hourly_risk_profile"],
        "cohort_retention": results["cohort_retention"],
        "top_risk_alerts": results["top_risk_alerts"],
        "dq_summary": results["dq_summary"],
        "filter_cube": results["filter_cube"],
    }

    dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    dashboard_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    summary = run_pipeline()
    kpis = summary["executive_kpis"]
    dq = summary["metadata"]["dq_counts"]
    print(
        f"Pipeline complete: {dq['clean_rows']} clean, {dq['quarantined_rows']} quarantined | "
        f"Approved GMV: ${kpis['approved_gmv_usd']:,.2f} | Approval Rate: {kpis['approval_rate_pct']}%"
    )

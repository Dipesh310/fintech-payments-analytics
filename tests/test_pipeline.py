"""Automated data quality, SQL reconciliation, and export tests for PayPulse."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from src.pipeline import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestPayPulsePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = run_pipeline(PROJECT_ROOT)
        cls.db_path = PROJECT_ROOT / "data" / "fintech_warehouse.db"
        cls.json_path = PROJECT_ROOT / "docs" / "data" / "dashboard_data.json"

    def test_dq_quarantine_counts(self) -> None:
        dq = self.payload["metadata"]["dq_counts"]
        self.assertEqual(dq["clean_rows"], 15_000)
        self.assertEqual(dq["quarantined_rows"], 120)
        self.assertEqual(dq["total_processed"], 15_120)

    def test_rail_gmv_reconciles_with_executive_kpis(self) -> None:
        exec_gmv = self.payload["executive_kpis"]["approved_gmv_usd"]
        rail_gmv = round(sum(r["approved_gmv_usd"] for r in self.payload["rail_performance"]), 2)
        self.assertAlmostEqual(exec_gmv, rail_gmv, places=1)

    def test_cube_reconciles_with_total_transactions(self) -> None:
        cube_txns = sum(r["n"] for r in self.payload["filter_cube"])
        self.assertEqual(cube_txns, self.payload["executive_kpis"]["total_transactions"])

    def test_approval_and_risk_rates_within_realistic_bounds(self) -> None:
        kpis = self.payload["executive_kpis"]
        self.assertGreater(kpis["approval_rate_pct"], 85.0)
        self.assertLess(kpis["approval_rate_pct"], 99.0)
        self.assertGreater(kpis["risk_incident_rate_pct"], 0.5)
        self.assertLess(kpis["risk_incident_rate_pct"], 10.0)

    def test_no_non_positive_amounts_in_clean_table(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            bad_count = conn.execute(
                "SELECT COUNT(*) FROM clean_transactions WHERE amount_usd <= 0"
            ).fetchone()[0]
        self.assertEqual(bad_count, 0)

    def test_dashboard_json_and_csv_exports_exist(self) -> None:
        self.assertTrue(self.json_path.exists())
        loaded = json.loads(self.json_path.read_text(encoding="utf-8"))
        for key in (
            "metadata",
            "executive_kpis",
            "monthly_trends",
            "rail_performance",
            "merchant_risk_matrix",
            "hourly_risk_profile",
            "cohort_retention",
            "top_risk_alerts",
            "filter_cube",
        ):
            self.assertIn(key, loaded)

        outputs_dir = PROJECT_ROOT / "outputs"
        for fname in (
            "monthly_kpis.csv",
            "rail_performance.csv",
            "merchant_risk.csv",
            "flagged_anomalies.csv",
        ):
            self.assertTrue((outputs_dir / fname).exists(), f"Missing {fname}")


if __name__ == "__main__":
    unittest.main()

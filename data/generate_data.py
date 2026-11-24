"""Deterministic synthetic fintech payments dataset generator.

Generates 15,000 realistic digital payment transactions across 12 months
(2025-12 through 2026-11) plus 120 intentionally malformed records to exercise
the ETL pipeline's data-quality quarantine layer.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
NUM_VALID_TXNS = 15_000
NUM_MALFORMED_TXNS = 120
NUM_CUSTOMERS = 2_400

START_DATE = datetime(2025, 12, 1, 0, 0, 0)
END_DATE = datetime(2026, 11, 24, 23, 59, 59)

PAYMENT_RAILS = [
    # (name, weight, mean_log_amt, sigma_log_amt, fee_bps, base_decline, base_fraud, base_latency_ms)
    ("UPI / Instant", 0.38, 3.35, 0.72, 18, 0.022, 0.004, 420),
    ("Credit Card", 0.27, 4.75, 0.85, 215, 0.048, 0.024, 890),
    ("Debit Card", 0.16, 4.10, 0.78, 95, 0.041, 0.011, 760),
    ("Digital Wallet", 0.12, 3.60, 0.68, 125, 0.029, 0.008, 510),
    ("Bank Transfer", 0.07, 5.45, 0.90, 45, 0.055, 0.006, 1650),
]

MERCHANT_CATEGORIES = [
    # (name, weight, risk_multiplier, amount_multiplier)
    ("E-Commerce", 0.28, 1.15, 1.10),
    ("Food & Dining", 0.19, 0.55, 0.45),
    ("SaaS & Cloud", 0.15, 0.70, 1.35),
    ("Travel & Mobility", 0.13, 1.25, 1.55),
    ("Utilities & Bills", 0.11, 0.35, 0.75),
    ("Gaming & Digital", 0.08, 2.35, 0.85),
    ("Cross-Border FX", 0.06, 2.95, 2.20),
]

REGIONS = [
    ("Mumbai", 0.22),
    ("Bengaluru", 0.21),
    ("Delhi NCR", 0.17),
    ("Hyderabad", 0.12),
    ("Pune", 0.09),
    ("Chennai", 0.08),
    ("Singapore", 0.06),
    ("London", 0.05),
]

FIELDNAMES = [
    "transaction_id",
    "timestamp",
    "customer_id",
    "cohort_month",
    "payment_rail",
    "merchant_category",
    "region",
    "amount_usd",
    "fee_usd",
    "status",
    "latency_ms",
    "is_international",
    "risk_score",
]


def _weighted_choice(rng: random.Random, items: list[tuple], weight_idx: int = 1):
    weights = [item[weight_idx] for item in items]
    return rng.choices(items, weights=weights, k=1)[0]


def generate_dataset(output_path: Path) -> dict[str, int]:
    """Generate raw_transactions.csv deterministically and return generation stats."""
    rng = random.Random(SEED)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Pre-assign customers to signup cohorts across the 12-month window
    months = [
        "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
        "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11",
    ]
    customer_cohorts: dict[str, str] = {}
    customer_ids = [f"CUST-{i:05d}" for i in range(1, NUM_CUSTOMERS + 1)]
    for cid in customer_ids:
        # Weight earlier cohorts slightly higher so retention curves have depth
        cohort = rng.choices(
            months,
            weights=[14, 12, 11, 10, 10, 9, 8, 8, 6, 5, 4, 3],
            k=1,
        )[0]
        customer_cohorts[cid] = cohort

    total_seconds = int((END_DATE - START_DATE).total_seconds())
    rows: list[dict[str, str]] = []

    for idx in range(1, NUM_VALID_TXNS + 1):
        cid = rng.choice(customer_ids)
        cohort_month = customer_cohorts[cid]
        cohort_start = datetime.strptime(cohort_month + "-01", "%Y-%m-%d")

        # Transaction occurs on or after customer cohort start with slight growth trend
        min_offset = max(0, int((cohort_start - START_DATE).total_seconds()))
        span = max(1, total_seconds - min_offset)
        # Mild upward growth bias toward more recent months
        u = rng.random() ** 0.86
        ts = START_DATE + timedelta(seconds=min_offset + int(u * span))

        # Adjust hour-of-day distribution (busier daytime, quieter late night)
        hour = ts.hour
        if 1 <= hour <= 5 and rng.random() < 0.62:
            ts = ts.replace(hour=rng.randint(9, 21))
            hour = ts.hour

        rail_name, _, mu, sigma, fee_bps, base_decline, base_fraud, base_lat = _weighted_choice(
            rng, PAYMENT_RAILS
        )
        cat_name, _, risk_mult, amt_mult = _weighted_choice(rng, MERCHANT_CATEGORIES)
        region_name, _ = _weighted_choice(rng, REGIONS)

        is_intl = 1 if (region_name in ("Singapore", "London") or cat_name == "Cross-Border FX") else 0

        # Log-normal realistic amount
        raw_amt = math.exp(rng.gauss(mu, sigma)) * amt_mult
        amount = round(min(max(raw_amt, 2.50), 9500.00), 2)

        # Seasonal Q3 Bank Transfer latency / decline degradation (2026-07 to 2026-08)
        month_str = ts.strftime("%Y-%m")
        lat_mult = 1.0
        decline_adj = base_decline
        if rail_name == "Bank Transfer" and month_str in ("2026-07", "2026-08"):
            lat_mult = 1.65
            decline_adj += 0.045

        latency = max(85, int(rng.gauss(base_lat * lat_mult, base_lat * 0.25)))

        # Fraud & chargeback probability driven by realistic signals
        nocturnal_boost = 2.1 if (1 <= hour <= 4) else 1.0
        high_ticket_boost = 1.85 if amount > 750 else 1.0
        intl_boost = 1.6 if is_intl else 1.0

        fraud_prob = min(0.32, base_fraud * risk_mult * nocturnal_boost * high_ticket_boost * intl_boost)
        chargeback_prob = fraud_prob * 0.42

        roll = rng.random()
        if roll < fraud_prob:
            status = "FRAUD_FLAGGED"
            risk_score = round(min(99.5, rng.uniform(74.0, 99.2)), 1)
        elif roll < fraud_prob + chargeback_prob:
            status = "CHARGEBACK"
            risk_score = round(min(95.0, rng.uniform(52.0, 88.0)), 1)
        elif roll < fraud_prob + chargeback_prob + decline_adj:
            status = "DECLINED"
            risk_score = round(rng.uniform(22.0, 68.0), 1)
        else:
            status = "APPROVED"
            base_score = 12.0 + (15.0 if is_intl else 0.0) + (10.0 if amount > 750 else 0.0)
            risk_score = round(min(72.0, max(1.2, rng.gauss(base_score, 9.5))), 1)

        # Processing fee applies to approved & chargeback transactions
        fee_usd = round(amount * (fee_bps / 10_000.0), 2) if status in ("APPROVED", "CHARGEBACK") else 0.00

        rows.append(
            {
                "transaction_id": f"TXN-{idx:06d}",
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "customer_id": cid,
                "cohort_month": cohort_month,
                "payment_rail": rail_name,
                "merchant_category": cat_name,
                "region": region_name,
                "amount_usd": f"{amount:.2f}",
                "fee_usd": f"{fee_usd:.2f}",
                "status": status,
                "latency_ms": str(latency),
                "is_international": str(is_intl),
                "risk_score": f"{risk_score:.1f}",
            }
        )

    # Inject deterministic malformed records to exercise ETL quarantine rules
    malformed_types = [
        "missing_id",
        "negative_amount",
        "invalid_status",
        "bad_timestamp",
        "duplicate_id",
    ]
    for m_idx in range(1, NUM_MALFORMED_TXNS + 1):
        m_type = malformed_types[(m_idx - 1) % len(malformed_types)]
        bad_row = dict(rows[(m_idx * 37) % len(rows)])
        bad_row["transaction_id"] = f"TXN-BAD-{m_idx:04d}"
        if m_type == "missing_id":
            bad_row["transaction_id"] = ""
        elif m_type == "negative_amount":
            bad_row["amount_usd"] = f"{-round(rng.uniform(10.0, 500.0), 2):.2f}"
        elif m_type == "invalid_status":
            bad_row["status"] = "UNKNOWN_ERR"
        elif m_type == "bad_timestamp":
            bad_row["timestamp"] = "2026-13-45 99:00:00"
        elif m_type == "duplicate_id":
            bad_row["transaction_id"] = rows[m_idx]["transaction_id"]
        rows.append(bad_row)

    # Sort deterministically by timestamp string (malformed timestamps fall naturally)
    rng.shuffle(rows)

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "valid_generated": NUM_VALID_TXNS,
        "malformed_injected": NUM_MALFORMED_TXNS,
        "total_rows": len(rows),
    }


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    out_file = project_root / "data" / "raw_transactions.csv"
    stats = generate_dataset(out_file)
    print(f"Generated {stats['total_rows']} rows -> {out_file}")

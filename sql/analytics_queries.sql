-- ============================================================================
-- PayPulse Fintech Analytics — Analytical SQL Layer (SQLite / ANSI SQL)
-- ============================================================================

-- name: executive_kpis
SELECT
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT customer_id) AS active_customers,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS approved_gmv_usd,
    ROUND(SUM(amount_usd), 2) AS gross_attempted_usd,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN fee_usd ELSE 0 END), 2) AS net_fee_revenue_usd,
    ROUND(AVG(CASE WHEN status = 'APPROVED' THEN amount_usd END), 2) AS avg_ticket_usd,
    ROUND(100.0 * SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS approval_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) / COUNT(*), 2) AS risk_incident_rate_pct,
    ROUND(SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN amount_usd ELSE 0 END), 2) AS risk_exposure_usd,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms
FROM clean_transactions;

-- name: monthly_trends
SELECT
    SUBSTR(timestamp, 1, 7) AS month,
    COUNT(*) AS txn_count,
    COUNT(DISTINCT customer_id) AS active_customers,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS approved_gmv_usd,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN fee_usd ELSE 0 END), 2) AS fee_revenue_usd,
    ROUND(100.0 * SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS approval_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) / COUNT(*), 2) AS risk_rate_pct,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms
FROM clean_transactions
GROUP BY SUBSTR(timestamp, 1, 7)
ORDER BY month ASC;

-- name: rail_performance
SELECT
    payment_rail,
    COUNT(*) AS txn_count,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS approved_gmv_usd,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN fee_usd ELSE 0 END), 2) AS fee_revenue_usd,
    ROUND(AVG(CASE WHEN status = 'APPROVED' THEN amount_usd END), 2) AS avg_ticket_usd,
    ROUND(100.0 * SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS approval_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) / COUNT(*), 2) AS risk_rate_pct,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms
FROM clean_transactions
GROUP BY payment_rail
ORDER BY approved_gmv_usd DESC;

-- name: merchant_risk_matrix
SELECT
    merchant_category,
    COUNT(*) AS txn_count,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS approved_gmv_usd,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN fee_usd ELSE 0 END), 2) AS fee_revenue_usd,
    ROUND(AVG(CASE WHEN status = 'APPROVED' THEN amount_usd END), 2) AS avg_ticket_usd,
    ROUND(100.0 * SUM(CASE WHEN status = 'FRAUD_FLAGGED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS fraud_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status = 'CHARGEBACK' THEN 1 ELSE 0 END) / COUNT(*), 2) AS chargeback_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) / COUNT(*), 2) AS total_risk_rate_pct,
    ROUND(SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN amount_usd ELSE 0 END), 2) AS risk_exposure_usd
FROM clean_transactions
GROUP BY merchant_category
ORDER BY total_risk_rate_pct DESC;

-- name: regional_breakdown
SELECT
    region,
    COUNT(*) AS txn_count,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS approved_gmv_usd,
    ROUND(100.0 * SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS approval_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) / COUNT(*), 2) AS risk_rate_pct
FROM clean_transactions
GROUP BY region
ORDER BY approved_gmv_usd DESC;

-- name: hourly_risk_profile
SELECT
    CAST(SUBSTR(timestamp, 12, 2) AS INTEGER) AS hour_of_day,
    COUNT(*) AS txn_count,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS approved_gmv_usd,
    ROUND(100.0 * SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) / COUNT(*), 2) AS risk_rate_pct,
    ROUND(AVG(risk_score), 1) AS avg_risk_score
FROM clean_transactions
GROUP BY CAST(SUBSTR(timestamp, 12, 2) AS INTEGER)
ORDER BY hour_of_day ASC;

-- name: cohort_retention
WITH cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_customers
    FROM clean_transactions
    GROUP BY cohort_month
),
customer_months AS (
    SELECT DISTINCT
        customer_id,
        cohort_month,
        SUBSTR(timestamp, 1, 7) AS activity_month,
        (CAST(SUBSTR(timestamp, 1, 4) AS INTEGER) - CAST(SUBSTR(cohort_month, 1, 4) AS INTEGER)) * 12
        + (CAST(SUBSTR(timestamp, 6, 2) AS INTEGER) - CAST(SUBSTR(cohort_month, 6, 2) AS INTEGER)) AS month_offset
    FROM clean_transactions
    WHERE status = 'APPROVED'
)
SELECT
    cm.cohort_month,
    cs.cohort_customers,
    cm.month_offset,
    COUNT(DISTINCT cm.customer_id) AS retained_customers,
    ROUND(100.0 * COUNT(DISTINCT cm.customer_id) / cs.cohort_customers, 1) AS retention_pct
FROM customer_months cm
JOIN cohort_sizes cs ON cm.cohort_month = cs.cohort_month
WHERE cm.month_offset BETWEEN 0 AND 5
GROUP BY cm.cohort_month, cs.cohort_customers, cm.month_offset
ORDER BY cm.cohort_month ASC, cm.month_offset ASC;

-- name: top_risk_alerts
SELECT
    transaction_id,
    timestamp,
    customer_id,
    payment_rail,
    merchant_category,
    region,
    amount_usd,
    status,
    risk_score,
    CASE
        WHEN CAST(SUBSTR(timestamp, 12, 2) AS INTEGER) BETWEEN 1 AND 4 AND amount_usd >= 500 THEN 'Nocturnal High-Ticket'
        WHEN is_international = 1 AND amount_usd >= 750 THEN 'Cross-Border High-Value'
        WHEN status = 'CHARGEBACK' THEN 'Disputed Chargeback'
        ELSE 'High Risk Score'
    END AS alert_reason
FROM clean_transactions
WHERE status IN ('FRAUD_FLAGGED', 'CHARGEBACK')
ORDER BY risk_score DESC, amount_usd DESC
LIMIT 40;

-- name: filter_cube
SELECT
    SUBSTR(timestamp, 1, 7) AS m,
    payment_rail AS r,
    merchant_category AS c,
    COUNT(*) AS n,
    SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) AS ok,
    SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN 1 ELSE 0 END) AS rk,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN amount_usd ELSE 0 END), 2) AS gmv,
    ROUND(SUM(CASE WHEN status = 'APPROVED' THEN fee_usd ELSE 0 END), 2) AS fee,
    ROUND(SUM(CASE WHEN status IN ('FRAUD_FLAGGED', 'CHARGEBACK') THEN amount_usd ELSE 0 END), 2) AS exp,
    SUM(latency_ms) AS lat
FROM clean_transactions
GROUP BY SUBSTR(timestamp, 1, 7), payment_rail, merchant_category
ORDER BY m ASC;

-- name: dq_summary
SELECT
    quarantine_reason,
    COUNT(*) AS record_count
FROM quarantine_transactions
GROUP BY quarantine_reason
ORDER BY record_count DESC;

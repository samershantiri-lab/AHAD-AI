-- ============================================================
-- AHAD AI - research_market_data Audit (READ-ONLY)
-- ============================================================

-- 1) Total rows
SELECT COUNT(*) AS total_rows FROM research_market_data;

-- 2) Unique trade_id count
SELECT COUNT(DISTINCT trade_id) AS unique_trade_ids FROM research_market_data;

-- 3) MIN/MAX trade_id
SELECT MIN(trade_id) AS min_trade_id, MAX(trade_id) AS max_trade_id FROM research_market_data;

-- 4) MIN/MAX signal_timestamp
SELECT MIN(signal_timestamp) AS earliest_signal, MAX(signal_timestamp) AS latest_signal FROM research_market_data;

-- 5) collection_status distribution
SELECT collection_status, COUNT(*) AS count
FROM research_market_data
GROUP BY collection_status
ORDER BY count DESC;

-- 6) Funding Rate present (non-NULL)
SELECT COUNT(*) AS funding_rate_present FROM research_market_data WHERE funding_rate IS NOT NULL;

-- 7) Open Interest present (non-NULL)
SELECT COUNT(*) AS oi_present FROM research_market_data WHERE open_interest_contracts IS NOT NULL;

-- 8) Both present
SELECT COUNT(*) AS both_present
FROM research_market_data
WHERE funding_rate IS NOT NULL AND open_interest_contracts IS NOT NULL;

-- 9) Funding only
SELECT COUNT(*) AS funding_only
FROM research_market_data
WHERE funding_rate IS NOT NULL AND open_interest_contracts IS NULL;

-- 10) OI only
SELECT COUNT(*) AS oi_only
FROM research_market_data
WHERE funding_rate IS NULL AND open_interest_contracts IS NOT NULL;

-- 11) Neither present
SELECT COUNT(*) AS neither_present
FROM research_market_data
WHERE funding_rate IS NULL AND open_interest_contracts IS NULL;

-- 12) Coverage of trades 1-331
-- Adjust the range (1 and 331) if the actual current max trade id in `trades` differs.
SELECT
    (SELECT COUNT(DISTINCT t.id) FROM trades t
     JOIN research_market_data r ON r.trade_id = t.id
     WHERE t.id BETWEEN 1 AND 331) AS trades_with_record,
    (SELECT COUNT(*) FROM trades t
     WHERE t.id BETWEEN 1 AND 331
     AND NOT EXISTS (SELECT 1 FROM research_market_data r WHERE r.trade_id = t.id)) AS trades_without_record;

-- 13) First/last trade_id per status (OK vs FAILED)
SELECT 'OK - first' AS label, MIN(trade_id) AS trade_id FROM research_market_data WHERE collection_status = 'OK'
UNION ALL
SELECT 'OK - last', MAX(trade_id) FROM research_market_data WHERE collection_status = 'OK'
UNION ALL
SELECT 'FAILED - first', MIN(trade_id) FROM research_market_data WHERE collection_status = 'FAILED'
UNION ALL
SELECT 'FAILED - last', MAX(trade_id) FROM research_market_data WHERE collection_status = 'FAILED';

-- 14) Duplicate trade_id check
SELECT COUNT(*) AS trade_ids_with_multiple_rows
FROM (
    SELECT trade_id FROM research_market_data
    GROUP BY trade_id HAVING COUNT(*) > 1
) sub;

SELECT MAX(row_count) AS max_rows_for_single_trade_id
FROM (
    SELECT trade_id, COUNT(*) AS row_count
    FROM research_market_data
    GROUP BY trade_id
) sub;

-- 15) failure_reason distribution (FAILED rows only) - text values only, never row-level secrets
SELECT failure_reason, COUNT(*) AS count
FROM research_market_data
WHERE collection_status = 'FAILED'
GROUP BY failure_reason
ORDER BY count DESC;

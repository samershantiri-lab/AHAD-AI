-- ============================================================
-- AHAD AI - MASTER AUDIT - كل الاستعلامات المتبقية، Read-Only بالكامل
-- ============================================================

-- PART 3: SCHEMA
SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
WHERE table_name IN ('research_top_gainers','research_top_losers','research_runs','research_snapshots','research_comparisons','trades')
ORDER BY table_name, column_name;

-- PART 4 + 5: FULL DATASET + TEMPORAL SANITY (كامل، لا CURRENT_DATE)
SELECT 'GAINERS' AS tbl, COUNT(*) AS total_rows,
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 IS NOT NULL AND research_move_start_proxy_75 IS NOT NULL AND research_move_start_proxy_90 IS NOT NULL) AS total_with_all_proxies,
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 IS NULL OR research_move_start_proxy_75 IS NULL OR research_move_start_proxy_90 IS NULL) AS missing_any_proxy,
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 IS NOT NULL AND research_move_start_proxy_75 IS NOT NULL AND research_move_start_proxy_90 IS NOT NULL
    AND (research_move_start_proxy_60 < research_move_start_proxy_75 OR research_move_start_proxy_75 < research_move_start_proxy_90)) AS invalid_order,
  COUNT(DISTINCT (symbol, observed_date)) AS distinct_pairs,
  COUNT(*) - COUNT(DISTINCT (symbol, observed_date)) AS duplicates,
  MIN(observed_date) AS earliest_date, MAX(observed_date) AS latest_date
FROM research_top_gainers
UNION ALL
SELECT 'LOSERS', COUNT(*),
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 IS NOT NULL AND research_move_start_proxy_75 IS NOT NULL AND research_move_start_proxy_90 IS NOT NULL),
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 IS NULL OR research_move_start_proxy_75 IS NULL OR research_move_start_proxy_90 IS NULL),
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 IS NOT NULL AND research_move_start_proxy_75 IS NOT NULL AND research_move_start_proxy_90 IS NOT NULL
    AND (research_move_start_proxy_60 < research_move_start_proxy_75 OR research_move_start_proxy_75 < research_move_start_proxy_90)),
  COUNT(DISTINCT (symbol, observed_date)),
  COUNT(*) - COUNT(DISTINCT (symbol, observed_date)),
  MIN(observed_date), MAX(observed_date)
FROM research_top_losers;

-- PART 6: EVENT_TIME impact (T90 < signal_time <= T75)
SELECT 'GAINERS' AS tbl, COUNT(*) AS affected_trades
FROM research_top_gainers g JOIN trades t ON t.id = g.trade_id
WHERE g.trade_id IS NOT NULL AND g.research_move_start_proxy_90 IS NOT NULL AND g.research_move_start_proxy_75 IS NOT NULL
  AND t.signal_time > g.research_move_start_proxy_90 AND t.signal_time <= g.research_move_start_proxy_75
UNION ALL
SELECT 'LOSERS', COUNT(*)
FROM research_top_losers l JOIN trades t ON t.id = l.trade_id
WHERE l.trade_id IS NOT NULL AND l.research_move_start_proxy_90 IS NOT NULL AND l.research_move_start_proxy_75 IS NOT NULL
  AND t.signal_time > l.research_move_start_proxy_90 AND t.signal_time <= l.research_move_start_proxy_75;

-- PART 8: TRADE DNA COMPLETENESS
SELECT 'gainers' AS tbl, COUNT(*) AS total, COUNT(trade_id) AS present, COUNT(*)-COUNT(trade_id) AS missing FROM research_top_gainers
UNION ALL
SELECT 'losers', COUNT(*), COUNT(trade_id), COUNT(*)-COUNT(trade_id) FROM research_top_losers;

-- PART 9: MARKET CONTEXT COMPLETENESS
SELECT 'gainers' AS tbl, COUNT(*) AS total, COUNT(market_regime) AS regime, COUNT(market_health) AS health, COUNT(direction) AS direction FROM research_top_gainers
UNION ALL
SELECT 'losers', COUNT(*), COUNT(market_regime), COUNT(market_health), COUNT(direction) FROM research_top_losers;

-- PART 10: SNAPSHOTS
SELECT module_key, last_attempt_status, last_success_at, last_attempt_at FROM research_snapshots ORDER BY module_key;

-- PART 11: RUN HISTORY
SELECT run_timestamp, modules_total, modules_succeeded, modules_failed, modules_partial, total_duration_seconds
FROM research_runs ORDER BY run_timestamp DESC LIMIT 10;

-- PART 17: DATA QUALITY - impossible ranges
SELECT 'gainers' AS tbl, COUNT(*) FILTER (WHERE price < 0) AS negative_price,
  COUNT(*) FILTER (WHERE rsi_15m < 0 OR rsi_15m > 100) AS rsi_out_of_range,
  COUNT(*) FILTER (WHERE volume_ratio < 0) AS negative_volume_ratio
FROM research_top_gainers
UNION ALL
SELECT 'losers', COUNT(*) FILTER (WHERE price < 0), COUNT(*) FILTER (WHERE rsi_15m < 0 OR rsi_15m > 100), COUNT(*) FILTER (WHERE volume_ratio < 0)
FROM research_top_losers;

-- PART 18: TEMPORAL CONSISTENCY - future timestamps
SELECT 'gainers' AS tbl, COUNT(*) FILTER (WHERE recorded_at > NOW()) AS future_recorded_at,
  COUNT(*) FILTER (WHERE research_move_start_proxy_60 > NOW()) AS future_t60
FROM research_top_gainers
UNION ALL
SELECT 'losers', COUNT(*) FILTER (WHERE recorded_at > NOW()), COUNT(*) FILTER (WHERE research_move_start_proxy_60 > NOW())
FROM research_top_losers;

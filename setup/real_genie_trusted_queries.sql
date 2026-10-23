-- Trusted Genie SQL examples for the Real Data Agent.
-- In the Genie configuration UI replace REPLACE_CATALOG.REPLACE_SCHEMA
-- with the ACTUAL Unity Catalog identifiers created by the notebook.
-- These are individual examples: save each separately with its own title.
-- Do NOT run these against, or attach, the Synthetic-certified views.

-- EXAMPLE 1. Most recent Group quarterly net profit (EUR m).
SELECT date, net_profit_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE date = (SELECT MAX(date)
              FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly);

-- EXAMPLE 2. Group quarterly net interest income, most recent five periods.
SELECT date, nii_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE nii_m IS NOT NULL
ORDER BY date DESC LIMIT 5;

-- EXAMPLE 3. Reported Group CET1 ratio movement, Q1 to Q2 2026.
SELECT date, cet1_ratio_pct, cet1_capital_m, rwa_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE date IN (DATE '2026-03-31', DATE '2026-06-30')
ORDER BY date;

-- EXAMPLE 4. Wealth Management loans, deposits and RWA (EUR millions).
SELECT date, business_line, loans_m, deposits_m, rwa_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_segment_quarterly
WHERE business_line = 'Wealth Management'
ORDER BY date DESC;

-- EXAMPLE 5. Compare the four business lines at the latest reporting quarter.
SELECT business_line, date, loans_m, deposits_m, rwa_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_segment_quarterly
WHERE date = (SELECT MAX(date)
              FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_segment_quarterly)
ORDER BY business_line;

-- EXAMPLE 6. Group NII and NIM from the verified 2021-on historical series.
SELECT date, nii_m, nim_bps, source_url, review_status
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_nii_nim_2021
WHERE date BETWEEN DATE '2022-01-01' AND DATE '2023-12-31'
ORDER BY date;

-- EXAMPLE 7. Published Group liquidity in the latest available period.
SELECT date, lcr_pct, nsfr_pct, loans_m, deposits_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE lcr_pct IS NOT NULL
ORDER BY date DESC LIMIT 1;

-- EXAMPLE 8. Group P&L quarterly series without interpolating missing periods.
SELECT date, net_profit_m, operating_income_m, operating_expenses_m,
       impairment_charges_m, cost_income_ratio_pct
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE date >= DATE '2025-01-01'
ORDER BY date;

-- EXAMPLE 9. Correct comparison of Group capital and segment RWA:
-- TWO separately scoped datasets; do not pretend to calculate segment CET1.
SELECT date, cet1_ratio_pct, rwa_m AS group_rwa_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE date = DATE '2026-06-30';

-- EXAMPLE 10. When user asks for missing segment net interest margin,
-- query only the ACTUALLY disclosed fields; answer explicitly that segment NIM
-- is NOT provided in the attached views.
SELECT date, business_line, loans_m, deposits_m, rwa_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_segment_quarterly
WHERE business_line = 'Personal & Business Banking'
ORDER BY date DESC LIMIT 4;

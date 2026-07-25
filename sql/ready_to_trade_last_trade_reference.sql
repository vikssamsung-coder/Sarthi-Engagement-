/*
Reference SQL used by the Python report.

Input client codes come from Leads.csv rows where Ready To Trade Date is in
current month or previous month.
*/

SELECT
    UPPER(TRIM(client_code)) AS client_code_clean,
    MIN(CASE WHEN gross_brok > 0 THEN trade_date END) AS first_trade_date,
    MAX(CASE WHEN gross_brok > 0 THEN trade_date END) AS last_trade_date,
    COUNT(DISTINCT CASE WHEN gross_brok > 0 THEN trade_date END) AS traded_days_lifetime,
    COUNT(DISTINCT CASE
        WHEN gross_brok > 0
         AND trade_date >= @window_start
         AND trade_date <= @window_end
        THEN trade_date END) AS traded_days_window,
    COUNT(DISTINCT CASE
        WHEN gross_brok > 0
         AND trade_date >= @previous_month_start
         AND trade_date < @current_month_start
        THEN trade_date END) AS traded_days_last_month,
    COUNT(DISTINCT CASE
        WHEN gross_brok > 0
         AND trade_date >= @current_month_start
         AND trade_date < @next_month_start
        THEN trade_date END) AS traded_days_this_month,
    SUM(CASE
        WHEN gross_brok > 0
         AND trade_date >= @window_start
         AND trade_date <= @window_end
        THEN gross_brok ELSE 0 END) AS brokerage_window,
    SUM(CASE
        WHEN gross_brok > 0
         AND trade_date >= @previous_month_start
         AND trade_date < @current_month_start
        THEN gross_brok ELSE 0 END) AS brokerage_last_month,
    SUM(CASE
        WHEN gross_brok > 0
         AND trade_date >= @current_month_start
         AND trade_date < @next_month_start
        THEN gross_brok ELSE 0 END) AS brokerage_this_month
FROM clientwise_datewise_brokerage
WHERE gross_brok > 0
  AND UPPER(TRIM(client_code)) IN ('CLIENT1', 'CLIENT2')
GROUP BY UPPER(TRIM(client_code));

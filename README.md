# Sarthi Engagement

Utilities for lead-engagement tracking in Bigul/Sarthi CDP.

## Current module

### Ready-To-Trade Last Trade Report

This report identifies client codes from `Leads.csv` where **Ready To Trade Date** falls in:

- the current month
- the previous month

It then connects to MySQL table:

```text
sarthi_cdp.clientwise_datewise_brokerage
```

and adds:

- first trade date
- last trade date
- traded days lifetime
- traded days in current/previous month window
- brokerage in current month
- brokerage in previous month
- action bucket for RM follow-up

The script keeps every qualifying lead row. It does **not** deduplicate the original lead rows.

## Default paths

```text
Leads.csv : D:\Sarthi\Leads\Leads.csv
Output    : D:\Sarthi\Engagement\Output
```

## Setup

Install dependencies once:

```bat
pip install -r requirements.txt
```

Create a `.env` file from `.env.example` and fill your local MySQL password.

```text
SARTHI_DB_HOST=localhost
SARTHI_DB_PORT=3306
SARTHI_DB_USER=sarthi_user
SARTHI_DB_PASSWORD=your_password_here
SARTHI_DB_DATABASE=sarthi_cdp
LEADS_CSV_PATH=D:\Sarthi\Leads\Leads.csv
OUTPUT_DIR=D:\Sarthi\Engagement\Output
```

## Run

Double-click:

```text
run_ready_to_trade_report.bat
```

or run:

```bat
python src\ready_to_trade_last_trade_report.py
```

## Useful options

Run for a fixed anchor date:

```bat
python src\ready_to_trade_last_trade_report.py --anchor-date 2026-07-25
```

Write a CSV copy of only qualifying rows with `last_trade_date` added:

```bat
python src\ready_to_trade_last_trade_report.py --write-leads-copy
```

Debug only the Leads.csv date/client-code extraction without SQL:

```bat
python src\ready_to_trade_last_trade_report.py --skip-sql
```

Force the client-code column if auto-detection fails:

```bat
python src\ready_to_trade_last_trade_report.py --client-code-column "Client Code"
```

## Output workbook sheets

| Sheet | Purpose |
|---|---|
| `Summary_KPIs` | Run-level KPIs |
| `Summary_By_Bucket` | Month/status/action summary |
| `Ready_To_Trade_Detail` | One row per qualifying lead row with last trade date |
| `Client_Code_Aggregate` | One row per client code |
| `Missing_Client_Code` | Ready-to-trade rows where client code is missing |
| `Run_Info` | Source paths, date window, detected columns |

## Important

The script never modifies the original `Leads.csv`. It only writes output files under the configured output folder.

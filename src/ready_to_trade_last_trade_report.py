#!/usr/bin/env python3
r"""
Bigul · Sarthi Engagement
Ready-To-Trade Last Trade Report

Reads D:\Sarthi\Leads\Leads.csv, filters rows where Ready To Trade Date is
in current month or previous month, then fetches last traded date from
sarthi_cdp.clientwise_datewise_brokerage.

Original Leads.csv is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text

DEFAULT_LEADS_PATH = r"D:\Sarthi\Leads\Leads.csv"
DEFAULT_OUTPUT_DIR = r"D:\Sarthi\Engagement\Output"
BROKERAGE_TABLE = "clientwise_datewise_brokerage"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def norm_col(value: object) -> str:
    value = str(value or "").strip().lower().replace("'", "")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def compact_col(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def find_col(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    by_norm = {norm_col(c): c for c in columns}
    by_compact = {compact_col(c): c for c in columns}
    for cand in candidates:
        if norm_col(cand) in by_norm:
            return by_norm[norm_col(cand)]
    for cand in candidates:
        if compact_col(cand) in by_compact:
            return by_compact[compact_col(cand)]
    for col in columns:
        n = norm_col(col)
        for cand in candidates:
            c = norm_col(cand)
            if c and c in n:
                return col
    return None


def require_col(columns: Sequence[str], candidates: Sequence[str], label: str) -> str:
    col = find_col(columns, candidates)
    if not col:
        raise RuntimeError(
            f"Required column not found: {label}. Tried: {', '.join(candidates)}. "
            f"Available first 40 columns: {', '.join(map(str, columns[:40]))}"
        )
    return col


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"Leads.csv not found: {path}")
    for enc in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        try:
            log(f"Reading {path} using encoding={enc}")
            return pd.read_csv(path, dtype=str, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Unable to read file with supported encodings: {path}")


def parse_dates(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA, "null": pd.NA, "#NAME?": pd.NA})
    parsed = pd.to_datetime(s, errors="coerce")
    missing = parsed.isna() & s.notna()
    if missing.any():
        serial = pd.to_numeric(s[missing], errors="coerce")
        valid = serial.between(25000, 80000, inclusive="both")
        if valid.any():
            parsed.loc[serial[valid].index] = pd.to_datetime(serial[valid], unit="D", origin="1899-12-30")
    return parsed.dt.date


def clean_code(value: object) -> str:
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if not value or value.lower() in {"nan", "none", "null", "#name?"}:
        return ""
    value = re.sub(r"\.0$", "", value)
    return re.sub(r"\s+", "", value).upper()


def safe(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def short_hash(values: Iterable[object]) -> str:
    material = "|".join(safe(v) for v in values)
    return hashlib.sha1(material.encode("utf-8", errors="ignore")).hexdigest()[:16]


def month_window(anchor: date) -> dict[str, date | str]:
    current_start = anchor.replace(day=1)
    prev_start = current_start - relativedelta(months=1)
    next_start = current_start + relativedelta(months=1)
    return {
        "anchor": anchor,
        "previous_month_start": prev_start,
        "current_month_start": current_start,
        "next_month_start": next_start,
        "window_start": prev_start,
        "window_end": next_start - timedelta(days=1),
        "previous_month_label": prev_start.strftime("%b-%Y"),
        "current_month_label": current_start.strftime("%b-%Y"),
    }


def detect_columns(df: pd.DataFrame, forced_client_col: str | None = None) -> dict[str, str | None]:
    cols = list(df.columns)
    ready_col = require_col(cols, [
        "Ready To Trade Date", "Ready To Trade", "ReadyToTradeDate", "Ready To Trade On", "RTT Date"
    ], "Ready To Trade Date")
    client_col = forced_client_col or find_col(cols, [
        "Client Code", "client_code", "ClientCode", "Trading Code", "Terminal Code", "UCC", "Client ID", "Account Code"
    ])
    if forced_client_col and forced_client_col not in cols:
        raise RuntimeError(f"Forced client-code column not found: {forced_client_col}")
    return {
        "ready": ready_col,
        "client": client_col,
        "lead_number": find_col(cols, ["Lead Number", "Lead No", "Lead ID", "lead_number"]),
        "lead_name": find_col(cols, ["Lead Name", "lead_name"]),
        "lead_stage": find_col(cols, ["Lead Stage", "lead_stage"]),
        "lead_source": find_col(cols, ["Lead Source", "lead_source"]),
        "source_campaign": find_col(cols, ["Source Campaign", "source_campaign", "Campaign"]),
        "owner_name": find_col(cols, ["Owner Name", "owner_name", "Assigned RM", "RM Name"]),
        "customer_name": find_col(cols, ["Customer Name", "customer_name", "Full Name"]),
        "customer_phone": find_col(cols, ["Customer Phone", "Phone", "Mobile", "Mobile No", "Phone Number"]),
    }


def prepare_ready_rows(df: pd.DataFrame, cols: dict[str, str | None], win: dict[str, date | str]) -> pd.DataFrame:
    out = df.copy()
    out["ready_to_trade_date"] = parse_dates(out[cols["ready"]])  # type: ignore[index]
    out = out[
        out["ready_to_trade_date"].notna()
        & (out["ready_to_trade_date"] >= win["window_start"])
        & (out["ready_to_trade_date"] <= win["window_end"])
    ].copy()
    if out.empty:
        raise RuntimeError(f"No Ready To Trade Date rows found between {win['window_start']} and {win['window_end']}.")
    out["ready_month_bucket"] = out["ready_to_trade_date"].apply(
        lambda d: "THIS_MONTH" if d >= win["current_month_start"] else "LAST_MONTH"
    )
    out["client_code_clean"] = out[cols["client"]].map(clean_code) if cols["client"] else ""
    for new_col in ["lead_number", "lead_name", "lead_stage", "lead_source", "source_campaign", "owner_name", "customer_name", "customer_phone"]:
        source = cols.get(new_col)
        out[new_col] = out[source].map(safe) if source else ""
    out["lead_row_hash"] = out.apply(lambda r: short_hash([
        r.get("lead_number"), r.get("client_code_clean"), r.get("ready_to_trade_date"), r.get("lead_stage"), r.get("customer_phone")
    ]), axis=1)
    return out.reset_index(drop=False).rename(columns={"index": "source_row_number_zero_based"})


def db_engine():
    host = os.getenv("SARTHI_DB_HOST") or os.getenv("MYSQL_HOST") or "localhost"
    port = int(os.getenv("SARTHI_DB_PORT") or os.getenv("MYSQL_PORT") or "3306")
    user = os.getenv("SARTHI_DB_USER") or os.getenv("MYSQL_USER") or "sarthi_user"
    password = os.getenv("SARTHI_DB_PASSWORD") or os.getenv("MYSQL_PASSWORD") or ""
    database = os.getenv("SARTHI_DB_DATABASE") or os.getenv("MYSQL_DATABASE") or "sarthi_cdp"
    if not password:
        log("WARNING: DB password is blank. Set SARTHI_DB_PASSWORD or MYSQL_PASSWORD in .env.")
    log(f"Connecting to MySQL: {user}@{host}:{port}/{database}")
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4", pool_pre_ping=True)


def chunks(values: Sequence[str], size: int = 1000):
    for start in range(0, len(values), size):
        yield list(values[start:start + size])


def fetch_brokerage(engine, client_codes: Sequence[str], win: dict[str, date | str]) -> pd.DataFrame:
    codes = sorted({clean_code(c) for c in client_codes if clean_code(c)})
    empty_cols = [
        "client_code_clean", "first_trade_date", "last_trade_date", "traded_days_lifetime",
        "traded_days_window", "traded_days_last_month", "traded_days_this_month",
        "brokerage_window", "brokerage_last_month", "brokerage_this_month",
    ]
    if not codes:
        return pd.DataFrame(columns=empty_cols)
    stmt = text(f"""
        SELECT
            UPPER(TRIM(client_code)) AS client_code_clean,
            MIN(CASE WHEN gross_brok > 0 THEN trade_date END) AS first_trade_date,
            MAX(CASE WHEN gross_brok > 0 THEN trade_date END) AS last_trade_date,
            COUNT(DISTINCT CASE WHEN gross_brok > 0 THEN trade_date END) AS traded_days_lifetime,
            COUNT(DISTINCT CASE WHEN gross_brok > 0 AND trade_date >= :window_start AND trade_date <= :window_end THEN trade_date END) AS traded_days_window,
            COUNT(DISTINCT CASE WHEN gross_brok > 0 AND trade_date >= :previous_month_start AND trade_date < :current_month_start THEN trade_date END) AS traded_days_last_month,
            COUNT(DISTINCT CASE WHEN gross_brok > 0 AND trade_date >= :current_month_start AND trade_date < :next_month_start THEN trade_date END) AS traded_days_this_month,
            SUM(CASE WHEN gross_brok > 0 AND trade_date >= :window_start AND trade_date <= :window_end THEN gross_brok ELSE 0 END) AS brokerage_window,
            SUM(CASE WHEN gross_brok > 0 AND trade_date >= :previous_month_start AND trade_date < :current_month_start THEN gross_brok ELSE 0 END) AS brokerage_last_month,
            SUM(CASE WHEN gross_brok > 0 AND trade_date >= :current_month_start AND trade_date < :next_month_start THEN gross_brok ELSE 0 END) AS brokerage_this_month
        FROM {BROKERAGE_TABLE}
        WHERE gross_brok > 0
          AND UPPER(TRIM(client_code)) IN :codes
        GROUP BY UPPER(TRIM(client_code))
    """).bindparams(bindparam("codes", expanding=True))
    frames = []
    for i, code_chunk in enumerate(chunks(codes), 1):
        log(f"SQL chunk {i}: {len(code_chunk)} client codes")
        params = {
            "codes": code_chunk,
            "window_start": win["window_start"],
            "window_end": win["window_end"],
            "previous_month_start": win["previous_month_start"],
            "current_month_start": win["current_month_start"],
            "next_month_start": win["next_month_start"],
        }
        frames.append(pd.read_sql(stmt, engine, params=params))
    if not frames:
        return pd.DataFrame(columns=empty_cols)
    out = pd.concat(frames, ignore_index=True)
    for col in ["first_trade_date", "last_trade_date"]:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.date
    return out


def classify(row: pd.Series) -> str:
    if not row.get("client_code_clean"):
        return "NO_CLIENT_CODE_IN_LEADS"
    if pd.isna(row.get("last_trade_date")):
        return "READY_TO_TRADE_BUT_NEVER_TRADED"
    if row.get("last_trade_date") >= row.get("ready_to_trade_date"):
        return "TRADED_AFTER_READY_DATE"
    return "TRADED_BEFORE_READY_DATE_ONLY"


def action_bucket(row: pd.Series) -> str:
    status = row.get("engagement_status")
    if status == "NO_CLIENT_CODE_IN_LEADS":
        return "Fix client-code mapping in Leads.csv"
    if status == "READY_TO_TRADE_BUT_NEVER_TRADED":
        return "RM activation call: ready but no first trade"
    if status == "TRADED_BEFORE_READY_DATE_ONLY":
        return "Check stage/date quality: last trade before ready date"
    if row.get("traded_days_this_month", 0) > 0:
        return "Active this month: retain and grow"
    if row.get("traded_days_last_month", 0) > 0:
        return "Traded last month: win back this month"
    return "Review trading recency"


def enrich(ready: pd.DataFrame, brokerage: pd.DataFrame) -> pd.DataFrame:
    out = ready.merge(brokerage, on="client_code_clean", how="left")
    numeric = ["traded_days_lifetime", "traded_days_window", "traded_days_last_month", "traded_days_this_month", "brokerage_window", "brokerage_last_month", "brokerage_this_month"]
    for col in numeric:
        out[col] = pd.to_numeric(out.get(col, 0), errors="coerce").fillna(0)
    out["has_traded_ever"] = out["last_trade_date"].notna()
    out["has_traded_on_or_after_ready_date"] = out.apply(
        lambda r: pd.notna(r.get("last_trade_date")) and r.get("last_trade_date") >= r.get("ready_to_trade_date"), axis=1
    )
    out["days_ready_to_last_trade"] = out.apply(
        lambda r: None if pd.isna(r.get("last_trade_date")) else (r.get("last_trade_date") - r.get("ready_to_trade_date")).days, axis=1
    )
    out["engagement_status"] = out.apply(classify, axis=1)
    out["action_bucket"] = out.apply(action_bucket, axis=1)
    return out


def aggregate_codes(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail[detail["client_code_clean"].ne("")].copy()
    if d.empty:
        return pd.DataFrame()
    return d.sort_values(["client_code_clean", "ready_to_trade_date"]).groupby("client_code_clean", as_index=False).agg(
        lead_rows=("lead_row_hash", "count"),
        first_ready_to_trade_date=("ready_to_trade_date", "min"),
        latest_ready_to_trade_date=("ready_to_trade_date", "max"),
        ready_month_bucket=("ready_month_bucket", lambda x: ", ".join(sorted(set(map(str, x))))),
        lead_numbers=("lead_number", lambda x: ", ".join(sorted(set(v for v in map(str, x) if v)))),
        latest_lead_stage=("lead_stage", "last"),
        lead_source=("lead_source", "last"),
        owner_name=("owner_name", "last"),
        first_trade_date=("first_trade_date", "max"),
        last_trade_date=("last_trade_date", "max"),
        traded_days_lifetime=("traded_days_lifetime", "max"),
        traded_days_window=("traded_days_window", "max"),
        traded_days_last_month=("traded_days_last_month", "max"),
        traded_days_this_month=("traded_days_this_month", "max"),
        brokerage_window=("brokerage_window", "max"),
        brokerage_last_month=("brokerage_last_month", "max"),
        brokerage_this_month=("brokerage_this_month", "max"),
        engagement_status=("engagement_status", lambda x: ", ".join(sorted(set(map(str, x))))),
        action_bucket=("action_bucket", lambda x: ", ".join(sorted(set(map(str, x))))),
    )


def write_report(path: Path, detail: pd.DataFrame, code_agg: pd.DataFrame, run_info: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary_kpis = pd.DataFrame([
        ["Run Anchor Date", run_info["anchor_date"]],
        ["Window Start", run_info["window_start"]],
        ["Window End", run_info["window_end"]],
        ["Ready-To-Trade Lead Rows", len(detail)],
        ["Unique Client Codes", detail["client_code_clean"].replace("", pd.NA).dropna().nunique()],
        ["Rows Missing Client Code", detail["client_code_clean"].eq("").sum()],
        ["Rows Traded Ever", detail["has_traded_ever"].sum()],
        ["Rows Traded On/After Ready Date", detail["has_traded_on_or_after_ready_date"].sum()],
        ["Rows Ready But Never Traded", (detail["engagement_status"] == "READY_TO_TRADE_BUT_NEVER_TRADED").sum()],
    ], columns=["Metric", "Value"])
    summary_bucket = detail.groupby(["ready_month_bucket", "engagement_status", "action_bucket"], dropna=False).agg(
        lead_rows=("lead_row_hash", "count"),
        unique_client_codes=("client_code_clean", lambda x: x.replace("", pd.NA).dropna().nunique()),
        brokerage_window=("brokerage_window", "sum"),
        brokerage_last_month=("brokerage_last_month", "sum"),
        brokerage_this_month=("brokerage_this_month", "sum"),
    ).reset_index().sort_values(["ready_month_bucket", "lead_rows"], ascending=[True, False])
    detail_cols = [
        "ready_month_bucket", "ready_to_trade_date", "client_code_clean", "lead_number", "lead_name",
        "lead_stage", "lead_source", "source_campaign", "owner_name", "customer_name", "customer_phone",
        "first_trade_date", "last_trade_date", "traded_days_lifetime", "traded_days_window",
        "traded_days_last_month", "traded_days_this_month", "brokerage_window", "brokerage_last_month",
        "brokerage_this_month", "has_traded_ever", "has_traded_on_or_after_ready_date",
        "days_ready_to_last_trade", "engagement_status", "action_bucket", "source_row_number_zero_based", "lead_row_hash"
    ]
    detail_cols = [c for c in detail_cols if c in detail.columns]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_kpis.to_excel(writer, sheet_name="Summary_KPIs", index=False)
        summary_bucket.to_excel(writer, sheet_name="Summary_By_Bucket", index=False)
        detail[detail_cols].to_excel(writer, sheet_name="Ready_To_Trade_Detail", index=False)
        code_agg.to_excel(writer, sheet_name="Client_Code_Aggregate", index=False)
        detail[detail["client_code_clean"].eq("")][detail_cols].to_excel(writer, sheet_name="Missing_Client_Code", index=False)
        pd.DataFrame([run_info]).to_excel(writer, sheet_name="Run_Info", index=False)
        for ws in writer.sheets.values():
            ws.freeze_panes = "A2"
            for col_cells in ws.columns:
                length = min(max([len(str(c.value or "")) for c in col_cells[:200]] + [8]) + 2, 45)
                ws.column_dimensions[col_cells[0].column_letter].width = length
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ready-To-Trade current/previous month report with SQL last trade date.")
    p.add_argument("--leads-path", default=os.getenv("LEADS_CSV_PATH", DEFAULT_LEADS_PATH))
    p.add_argument("--output-dir", default=os.getenv("OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    p.add_argument("--anchor-date", default=os.getenv("REPORT_ANCHOR_DATE", ""), help="YYYY-MM-DD. Defaults to today.")
    p.add_argument("--client-code-column", default=os.getenv("CLIENT_CODE_COLUMN", ""))
    p.add_argument("--write-leads-copy", action="store_true", help="Write a review CSV copy with last_trade_date; original Leads.csv is not modified.")
    p.add_argument("--skip-sql", action="store_true", help="Debug Leads.csv extraction without SQL.")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv or sys.argv[1:])
    try:
        anchor = datetime.strptime(args.anchor_date, "%Y-%m-%d").date() if args.anchor_date else date.today()
        win = month_window(anchor)
        leads_path = Path(args.leads_path)
        output_dir = Path(args.output_dir)
        log("Starting Ready-To-Trade Last Trade report")
        log(f"Date window: {win['window_start']} to {win['window_end']}")
        leads = read_csv(leads_path)
        log(f"Loaded rows from Leads.csv: {len(leads):,}")
        cols = detect_columns(leads, args.client_code_column or None)
        log(f"Ready To Trade column: {cols['ready']}")
        log(f"Client code column: {cols['client'] or 'NOT_FOUND'}")
        ready = prepare_ready_rows(leads, cols, win)
        log(f"Ready-To-Trade rows in window: {len(ready):,}")
        if args.skip_sql:
            brokerage = pd.DataFrame(columns=["client_code_clean", "first_trade_date", "last_trade_date"])
        else:
            brokerage = fetch_brokerage(db_engine(), ready["client_code_clean"].tolist(), win)
        detail = enrich(ready, brokerage)
        code_agg = aggregate_codes(detail)
        run_info = {
            "run_timestamp": datetime.now().isoformat(timespec="seconds"),
            "leads_path": str(leads_path),
            "output_dir": str(output_dir),
            "anchor_date": win["anchor"].isoformat(),
            "window_start": win["window_start"].isoformat(),
            "window_end": win["window_end"].isoformat(),
            "ready_to_trade_column": cols["ready"],
            "client_code_column": cols["client"] or "NOT_FOUND",
            "source_rows_loaded": int(len(leads)),
            "ready_to_trade_rows": int(len(detail)),
            "unique_client_codes": int(detail["client_code_clean"].replace("", pd.NA).dropna().nunique()),
            "missing_client_code_rows": int(detail["client_code_clean"].eq("").sum()),
            "skip_sql": bool(args.skip_sql),
        }
        out = output_dir / f"Ready_To_Trade_Last_Trade_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        write_report(out, detail, code_agg, run_info)
        if args.write_leads_copy:
            csv_path = output_dir / f"Leads_ready_to_trade_with_last_trade_{datetime.now():%Y%m%d_%H%M%S}.csv"
            detail.to_csv(csv_path, index=False, encoding="utf-8-sig")
            log(f"Wrote review CSV copy: {csv_path}")
        log(f"Report completed successfully: {out}")
        return 0
    except Exception as exc:
        log(f"ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

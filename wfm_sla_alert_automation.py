"""
WFM SLA Risk Alert Automation
==============================
Part 3: Automation Challenge — SteadyMD WFM Take-Home Assignment
Author: Sachin Loddiya Karthik

WHAT IT AUTOMATES
-----------------
Replaces a manual daily workflow where a WFM analyst:
  1. Opens the staffing spreadsheet
  2. Scrolls through hundreds of rows looking for understaffed / SLA-risk hours
  3. Manually writes a summary email or Slack message

This script produces:
  - A console alert summary
  - A formatted daily digest (text/email-ready)
  - A filtered CSV of all flagged rows for drill-down

HOW TO RUN
----------
  python wfm_sla_alert_automation.py --file WFM_dashboard_input.xlsx
  python wfm_sla_alert_automation.py --file WFM_dashboard_input.xlsx --date 2026-02-14
  python wfm_sla_alert_automation.py --demo   # run with built-in sample data
"""

import argparse
import sys
from datetime import date, datetime

import pandas as pd

# ─────────────────────────────────────────────
# CONFIGURATION — adjust thresholds here
# ─────────────────────────────────────────────
CONFIG = {
    "sla_risk_threshold": 84.6,  # SLA% below this = SLA risk
    "critical_gap_threshold": 3,  # staffing gap >= this = critical gap
    "coverage_ratio_min": 0.90,  # coverage below this = critical
    "high_volume_percentile": 0.80,  # flag when volume is in top 20%
}

COLORS = {
    "RED": "\033[91m",
    "AMBER": "\033[93m",
    "GREEN": "\033[92m",
    "BLUE": "\033[94m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m",
}


def c(text: str, color: str) -> str:
    return f"{COLORS.get(color, '')}{text}{COLORS['RESET']}"


def load_data(filepath: str) -> pd.DataFrame:
    """Load and validate the WFM input file."""
    required_cols = [
        "date",
        "hour",
        "volume",
        "required_staff",
        "actual_staff",
        "sla_percent",
    ]

    try:
        df = pd.read_excel(filepath)
    except FileNotFoundError:
        raise SystemExit(f"ERROR: File not found — {filepath}")

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: Missing columns: {missing}")

    df["date"] = pd.to_datetime(df["date"])

    # Derive optional columns if not present (required - actual = positive means understaffed)
    if "staffing_gap" not in df.columns:
        df["staffing_gap"] = df["required_staff"] - df["actual_staff"]
    if "coverage_ratio" not in df.columns:
        df["coverage_ratio"] = df["actual_staff"] / df["required_staff"]

    return df


def detect_risks(df: pd.DataFrame) -> pd.DataFrame:
    """Apply risk detection logic and return flagged rows."""
    cfg = CONFIG
    vol_threshold = df["volume"].quantile(cfg["high_volume_percentile"])

    # Risk flags
    df["flag_sla_risk"] = df["sla_percent"] <= cfg["sla_risk_threshold"]
    df["flag_understaffed"] = df["actual_staff"] < df["required_staff"]
    df["flag_critical_gap"] = df["staffing_gap"] >= cfg["critical_gap_threshold"]
    df["flag_low_coverage"] = df["coverage_ratio"] < cfg["coverage_ratio_min"]
    df["flag_high_volume"] = df["volume"] >= vol_threshold

    # Severity scoring
    df["risk_score"] = (
        df["flag_sla_risk"].astype(int)
        + df["flag_understaffed"].astype(int)
        + df["flag_critical_gap"].astype(int)
        + df["flag_low_coverage"].astype(int)
    )

    df["severity"] = pd.cut(
        df["risk_score"],
        bins=[-1, 0, 1, 2, 10],
        labels=["OK", "LOW", "HIGH", "CRITICAL"],
    )

    return df[df["risk_score"] > 0].copy()


def generate_daily_summary(df_all: pd.DataFrame, target_date: date | None = None) -> dict:
    """Generate summary statistics for a given date (or all dates)."""
    if target_date:
        df = df_all[df_all["date"].dt.date == target_date]
        label = str(target_date)
    else:
        df = df_all
        label = "Full Period"

    if len(df) == 0:
        raise SystemExit(f"ERROR: No rows found for date={target_date}")

    total_hours = len(df)
    flagged = detect_risks(df.copy())

    summary = {
        "date_label": label,
        "total_hours": total_hours,
        "sla_risk_hours": int((df["sla_percent"] <= CONFIG["sla_risk_threshold"]).sum()),
        "understaffed_hours": int((df["actual_staff"] < df["required_staff"]).sum()),
        "critical_hours": int((flagged["severity"] == "CRITICAL").sum()) if len(flagged) else 0,
        "avg_sla": round(float(df["sla_percent"].mean()), 1),
        "min_sla": round(float(df["sla_percent"].min()), 1),
        "avg_coverage": round(float(df["coverage_ratio"].mean()), 3)
        if "coverage_ratio" in df.columns
        else None,
        "worst_hour": int(df.loc[df["sla_percent"].idxmin(), "hour"]),
        "worst_sla": round(float(df["sla_percent"].min()), 1),
        "flagged_rows": flagged,
    }
    return summary


def format_alert_message(summary: dict, include_detail: bool = True) -> str:
    """Format a human-readable alert message (Slack/email compatible)."""
    s = summary
    sla_status = (
        "🔴 RISK"
        if s["avg_sla"] < 88
        else ("🟡 MONITOR" if s["avg_sla"] < 92 else "🟢 OK")
    )

    lines = [
        "=" * 60,
        f"  WFM DAILY PERFORMANCE ALERT — {s['date_label']}",
        "=" * 60,
        "",
        f"  SLA STATUS:      {s['avg_sla']}% avg  {sla_status}",
        f"  Min SLA:         {s['worst_sla']}% (Hour {s['worst_hour']:02d}:00)",
        f"  SLA Risk Hours:  {s['sla_risk_hours']} / {s['total_hours']}",
        f"  Understaffed:    {s['understaffed_hours']} / {s['total_hours']} hours",
        f"  Critical Hours:  {s['critical_hours']} hours (SLA + staffing both failing)",
    ]

    if s.get("avg_coverage") is not None:
        cov_flag = " ⚠" if s["avg_coverage"] < 0.95 else ""
        lines.append(f"  Avg Coverage:    {s['avg_coverage']:.3f}{cov_flag}")

    if include_detail and len(s["flagged_rows"]) > 0:
        lines += ["", "  TOP RISK WINDOWS:"]
        top_risks = s["flagged_rows"].sort_values(
            ["risk_score", "staffing_gap", "sla_percent"],
            ascending=[False, False, True],
        ).head(5)
        for _, row in top_risks.iterrows():
            flags = []
            if bool(row.get("flag_sla_risk")):
                flags.append("SLA")
            if bool(row.get("flag_understaffed")):
                flags.append("UNDERSTAFFED")
            if bool(row.get("flag_critical_gap")):
                flags.append("CRITICAL GAP")
            if bool(row.get("flag_low_coverage")):
                flags.append("LOW COVERAGE")
            if bool(row.get("flag_high_volume")):
                flags.append("HIGH VOLUME")

            date_str = (
                row["date"].strftime("%b %d")
                if hasattr(row["date"], "strftime")
                else str(row["date"])
            )
            lines.append(
                f"  → {date_str} {int(row['hour']):02d}:00 | "
                f"SLA={float(row['sla_percent']):.0f}% | "
                f"Staff: {int(row['actual_staff'])}/{int(row['required_staff'])} req | "
                f"Gap={int(row['staffing_gap'])} | "
                f"[{', '.join(flags)}]"
            )

    lines += ["", "  RECOMMENDED ACTION:"]
    if s["critical_hours"] >= 3:
        lines.append("  🔴 CRITICAL: Escalate to operations manager immediately.")
        lines.append("     Consider calling in standby staff for flagged windows.")
    elif s["understaffed_hours"] > 10:
        lines.append("  🟡 MONITOR: Review schedule for understaffed hours.")
        lines.append("     Consider shift swaps or voluntary overtime.")
    else:
        lines.append("  🟢 Operations appear stable. Continue standard monitoring.")

    lines += [
        "",
        "  " + "-" * 56,
        "  [Auto-generated by WFM SLA Alert Automation v1.0]",
        "  To tune: update CONFIG thresholds in script header.",
        "=" * 60,
    ]

    return "\n".join(lines)


def run_pipeline(filepath: str, target_date: date | None = None, export_csv: bool = True):
    """Main pipeline: load → analyze → alert → export."""
    print(c("\nWFM SLA Risk Alert — Running...", "BLUE"))

    df = load_data(filepath)

    if target_date is None:
        target_date = df["date"].dt.date.max()
        print(f"  No date specified. Using latest: {target_date}")

    summary = generate_daily_summary(df, target_date)
    print(format_alert_message(summary))

    if export_csv and len(summary["flagged_rows"]) > 0:
        csv_path = f"wfm_risk_flags_{target_date}.csv"
        summary["flagged_rows"].to_csv(csv_path, index=False)
        print(f"\n  📄 Flagged rows exported: {csv_path}")

    print(c("\n  FULL PERIOD SUMMARY", "BOLD"))
    total_flagged = len(detect_risks(df.copy()))
    print(f"  Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  Total hours analyzed: {len(df)}")
    print(f"  Total flagged hours:  {total_flagged} ({total_flagged/len(df)*100:.1f}%)")
    print(f"  Overall avg SLA:      {df['sla_percent'].mean():.1f}%")
    print(
        f"  Understaffed rate:    {(df['actual_staff'] < df['required_staff']).mean()*100:.1f}%"
    )

    return summary


def run_demo():
    """Run a demo using synthetic data matching the assignment dataset."""
    import numpy as np

    np.random.seed(42)
    dates = pd.date_range("2026-02-14", periods=24, freq="h")
    df = pd.DataFrame(
        {
            "date": dates.date,
            "hour": range(24),
            "volume": np.random.randint(60, 160, 24),
            "avg_handle_time_min": np.random.uniform(7.0, 10.5, 24).round(2),
            "required_staff": np.random.randint(8, 20, 24),
            "scheduled_staff": np.random.randint(9, 22, 24),
            "actual_staff": np.random.randint(6, 19, 24),
            "sla_percent": np.clip(np.random.normal(92, 7, 24), 65, 100).round(1),
        }
    )
    df["staffing_gap"] = df["required_staff"] - df["actual_staff"]
    df["coverage_ratio"] = (df["actual_staff"] / df["required_staff"]).round(3)
    df["date"] = pd.to_datetime(df["date"])

    print(c("\n[DEMO MODE] Running with synthetic data for 2026-02-14...\n", "AMBER"))
    summary = generate_daily_summary(df, date(2026, 2, 14))
    summary["flagged_rows"] = detect_risks(df.copy())
    print(format_alert_message(summary))
    print(c("\n[DEMO COMPLETE] Run with --file your_data.xlsx for real data.\n", "GREEN"))


def parse_args():
    parser = argparse.ArgumentParser(description="WFM SLA Risk Alert Automation")
    parser.add_argument("--file", type=str, help="Path to WFM dashboard Excel file")
    parser.add_argument(
        "--date", type=str, help="Target date YYYY-MM-DD (default: latest)"
    )
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.demo:
        run_demo()
    elif args.file:
        target = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
        run_pipeline(args.file, target_date=target)
    else:
        print("Usage: python wfm_sla_alert_automation.py --file data.xlsx")
        print("       python wfm_sla_alert_automation.py --demo")
        sys.exit(1)


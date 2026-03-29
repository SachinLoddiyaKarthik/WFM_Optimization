---
output:
  word_document: default
  html_document: default
---
# Part 3: Automation Challenge — WFM SLA Risk Alert

## What I Automated

I automated a daily WFM risk-monitoring workflow that was previously manual:

1. Open staffing file and scan all hourly rows.
2. Identify SLA-risk + understaffed windows.
3. Summarize the day and draft an operations alert.
4. Export flagged rows for drill-down.

Automation file:

- `wfm_sla_alert_automation.py`

Input file:

- `WFM_dashboard_input.xlsx`

Outputs generated automatically:

- Console alert digest (Slack/email-ready text)
- Daily flagged CSV (for investigation), e.g. `wfm_risk_flags_2026-02-24.csv`
- Full-period summary metrics

## How It Works (Logic)

### 1) Load + Validate + Normalize

The script validates required columns (`date`, `hour`, `volume`, `required_staff`, `actual_staff`, `sla_percent`) and derives missing helper fields if needed:

- `staffing_gap = required_staff - actual_staff` (positive means understaffed)
- `coverage_ratio = actual_staff / required_staff`

### 2) Apply Risk Flags

Per row, it computes:

- `flag_sla_risk`: `sla_percent <= 84.6`
- `flag_understaffed`: `actual_staff < required_staff`
- `flag_critical_gap`: `staffing_gap >= 3`
- `flag_low_coverage`: `coverage_ratio < 0.90`
- `flag_high_volume`: `volume >= 80th percentile`

### 3) Score Severity

`risk_score` is the sum of key failure flags (SLA risk, understaffed, critical gap, low coverage), then mapped to:

- `OK`, `LOW`, `HIGH`, `CRITICAL`

### 4) Daily Alert + Drill-down Export

For a selected date (or latest date by default), it prints:

- SLA status, min SLA, risk-hour count, understaffed-hour count, critical-hour count
- Top 5 risk windows with exact hour + SLA + staffing gap + triggered flags
- Recommended action (escalate / monitor / stable)

It also exports flagged rows to CSV for follow-up.

## Example Run (Real Data)

Command used:

```bash
python wfm_sla_alert_automation.py --file WFM_dashboard_input.xlsx --date 2026-02-24
```

Observed output summary:

- Avg SLA: `90.8%` (MONITOR)
- SLA risk hours: `5 / 24`
- Understaffed hours: `16 / 24`
- Critical hours: `8`
- Avg coverage: `0.896`
- Exported file: `wfm_risk_flags_2026-02-24.csv`

## Estimated Time / Impact Saved

### Before automation (manual)

- Open workbook + scan hourly rows + identify risk windows + summarize + draft alert:
  ~25–40 minutes/day

### After automation

- Run one command + review generated digest:
  ~2–5 minutes/day

### Estimated savings

- ~20–35 minutes/day
- ~1.7 to 2.9 hours/week (assuming 5 workdays)
- Additional benefit: consistent criteria and reduced missed-risk windows

## Why This Improves WFM Operations

- Standardizes SLA/staffing risk detection with transparent thresholds.
- Produces a repeatable daily operating rhythm (alert + action list).
- Frees analyst time for root-cause analysis and intraday decision-making.
- Creates an auditable flagged-row dataset for manager review and trend tracking.


---
output:
  word_document: default
  html_document: default
---
# Part 5: Executive Summary (SteadyMD WFM Take-Home)

## How I used AI

I used an AI assistant to help outline the analytical approach, sanity-check formulas and logic, and tighten wording. All data wrangling, metric definitions, code (Python + Streamlit), Excel outputs, and final validation were done and owned by me.

---

## If you only remember 3 things

1. **SLA risk is concentrated in early-morning hours (roughly 00:00–08:00), especially mid-week, and is driven almost entirely by staffing gaps—not AHT.** Correlation between staffing gap and SLA is strongly negative; AHT is a weak driver in this sample compared with coverage.

2. **You can materially reduce risk by shifting coverage into those windows** (for example, prioritizing 08:00, 05:00, 06:00, 00:00, 04:00, 02:00 per the staffing-adjustment table). The next-week forecast recommends higher scheduled staff only on historically high-risk hours (buffered), which is a **reallocation mindset**: protect the fragile windows first before broad overstaffing.

3. **I built a daily risk alert plus an interactive Streamlit app** so leaders can see today’s risk windows, run alerts by date, upload a new month’s file, and track patterns—without waiting for a full analyst cycle.

---

## Objective

Assess whether staffing aligns with demand, identify SLA-risk patterns, and propose practical actions to improve service levels and workforce efficiency.

---

## How each deliverable maps to a real WFM ritual

| Part | Artifact | What ops / WFM would use it for |
|------|----------|--------------------------------|
| **Part 1** | `WFM_Part1_Dashboard.xlsx`, `WFM_Part1_Forecast_Staffing.xlsx` | **Weekly staffing review** — Is demand covered next week? Where do we add buffers vs. baseline? |
| **Part 2** | `WFM_Part2_Dashboard.xlsx` | **Daily performance huddle** — Yesterday’s SLA, staffing vs required, productivity proxy; drill to hour/day. |
| **Part 3** | `wfm_sla_alert_automation.py`, flagged CSVs | **Morning risk alert** — Before shifts, surface understaffed / SLA-risk hours for same-day action. |
| **Part 4** | `WFM_Part4_Performance_Monitoring_Insights.md` | **Monthly deep-dive** — Structural patterns by hour and day of week; what to fix in scheduling and forecasting. |
| **Bonus** | `app.py` (Streamlit) | **Living cockpit** — Upload new month’s Excel; KPIs and charts refresh; ties Parts 2–4 + automation in one place. |

One line per part: *this is what the WFM / ops team would actually open in a recurring meeting.*

---

## Key insights (supporting detail)

1. **Staffing-demand misalignment is frequent** — `52.4%` of hours are understaffed (`actual_staff < required_staff`).
2. **SLA risk is measurable and bounded** — bottom-10% SLA threshold (`sla_percent <= 84.6`); `10.4%` of hours are SLA-risk.
3. **Coverage is the primary SLA driver** — `corr(staffing_gap, sla_percent) ≈ -0.87`; `corr(coverage_ratio, sla_percent) ≈ 0.78`.
4. **Time-based patterns are actionable** — Risk clusters early morning; higher weekly pressure Tue / Wed / Fri.

---

## Biggest risks

- **Operational:** Repeated understaffed windows create avoidable SLA failures.
- **Intraday:** Early-hour low coverage produces critical risk spikes.
- **Process:** Manual-only monitoring misses windows or delays escalation.

---

## Recommended actions

1. **Set a measurable SLA-risk goal** — Example: move SLA-risk hours from **`10.4%`** of hour-rows toward **`<5%`** over an agreed horizon (pair with budget and official SLA targets).
2. **Protect high-risk hours first** — Use the staffing-adjustment and forecast sheets to add coverage in the top risk blocks before blanket increases; buffers are often **+1 to +3** heads on the worst early-morning blocks (see Part 4 gap ranges: ~**+0.6–1.1** at the hour level, **+5.31** on average in SLA-risk hours vs non-risk).
3. **Risk-based intraday rules** — Escalate when `actual_staff < required_staff` and SLA or coverage crosses thresholds.
4. **Operationalize alerts** — Daily script or Streamlit automation tab; route top windows to leadership.

---

## Quick win (0–2 weeks)

Run `wfm_sla_alert_automation.py` on a schedule (or use the Streamlit **Automation Demo** tab) and attach the flagged CSV to the morning standup.

---

## Longer-term improvement (1–2 quarters)

- Hourly forecasting with more history (seasonality, partner/LOB splits if applicable).
- Integrate with your real staffing model and SLA targets by line of business.
- Production pipeline: warehouse + BI (e.g. Snowflake + Looker) instead of file-only.

---

## Assumptions & how I’d harden this in production

- **Forecast:** Uses recent hour-of-day seasonality and a risk buffer on high-risk hours—not a full ARIMA/Prophet model. With more history I’d move to a proper time-series forecast by hour (and by segment if needed).
- **`required_staff`:** Treated as the modeled staffing need from the dataset; in production I’d align with your actual Erlang / staffing calculator and official SLA target.
- **AHT:** Used as a workload proxy; in this sample it did not dominate SLA misses compared with staffing gaps.
- **Data source:** Excel / upload is fine for the take-home; in production I’d point the app at a curated dataset (warehouse + refresh) with data-quality checks (e.g. negative `scheduled_staff` flagged upstream).

---

## Deliverables produced

- Part 1: `WFM_Part1_Dashboard.xlsx`, `WFM_Part1_Forecast_Staffing.xlsx`
- Part 2: `WFM_Part2_Dashboard.xlsx`
- Part 3: `wfm_sla_alert_automation.py`, `WFM_Part3_Automation_Challenge.md`
- Part 4: `WFM_Part4_Performance_Monitoring_Insights.md`
- Part 5: this file
- Bonus: `app.py`, `README.md`

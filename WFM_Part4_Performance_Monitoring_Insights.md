---
output:
  word_document: default
  html_document: default
---
# Part 4: Performance Monitoring & Insights

## Goal

Identify where performance is breaking (SLA dips and staffing gaps), detect time-based patterns, and recommend practical WFM actions.

## Where performance is breaking

- SLA risk threshold used: bottom 10% of `sla_percent` (<= `84.6`).
- Overall SLA-risk exposure: `10.4%` of hours.
- Understaffing frequency: `52.4%` of hours (`actual_staff < required_staff`).
- Core relationship: `corr(staffing_gap, sla_percent) = -0.870` (strong negative).
- Coverage relationship: `corr(coverage_ratio, sla_percent) = 0.778` (better coverage tracks better SLA).

Observed break pattern:

- In SLA-risk hours, average staffing gap is `+5.31` vs `-0.23` in non-risk hours.
- In SLA-risk hours, average coverage ratio is `0.46` vs `1.03` in non-risk hours.
- `100%` of SLA-risk hours are understaffed (vs `46.8%` for non-risk hours).

Interpretation:

- SLA misses are primarily staffing-coverage failures, not AHT-driven variance.
- AHT has weak relationship to SLA in this sample (`corr(avg_handle_time_min, sla_percent) = -0.024`).

## Patterns by time of day

Highest-risk hours by SLA-risk rate and staffing shortfall:

- `08:00` — risk rate `21.4%`, understaffed rate `64.3%`, avg gap `+1.04`
- `00:00` — risk rate `17.9%`, understaffed rate `46.4%`, avg gap `+0.86`
- `05:00` — risk rate `14.3%`, understaffed rate `57.1%`, avg gap `+0.79`
- `06:00` — risk rate `14.3%`, understaffed rate `60.7%`, avg gap `+0.61`
- `04:00` — lower risk frequency (`10.7%`) but largest avg gap (`+1.14`) and the lowest avg SLA (`90.76`)

Implication:

- Early-morning windows (`00:00` to `08:00`) are the most fragile and should be protected first.

## Patterns by day of week

Risk concentration by day:

- Highest SLA-risk days: `Wed` (`14.6%`), `Tue` (`13.5%`), `Fri` (`13.5%`)
- Lowest-risk days: `Mon` (`5.2%`) and `Sun` (`5.2%`)
- Weakest average SLA days: `Fri` (`92.19`), `Thu` (`92.21`), `Wed` (`92.40`)

Implication:

- Mid-week through Friday needs tighter staffing guardrails, especially in known risk hours.

## Answer: When are we most at risk?

Most at risk when these conditions overlap:

1. Hour is in the early-morning risk cluster (`00:00`, `04:00`, `05:00`, `06:00`, `08:00`).
2. Day is mid/late week (`Tue`/`Wed`/`Fri`).
3. Staffing gap is positive and large (`required_staff - actual_staff >= 3`).
4. Coverage ratio falls below ~`0.90` (or lower in extreme windows).

High-priority hour-day examples from the data include:

- `Wed 08:00` (high risk rate + large gap),
- `Tue 05:00`,
- `Thu 10:00`,
- plus several Fri/Sat windows with full understaffing incidence.

## Answer: What’s driving SLA misses?

Primary driver:

- Understaffing relative to required staffing (coverage shortfall).

Evidence:

- Strong negative correlation between gap and SLA (`-0.870`).
- Strong positive correlation between coverage and SLA (`0.778`).
- All SLA-risk hours are understaffed in this dataset (`100%` overlap).

Secondary factors:

- Higher volume increases SLA pressure when staffing does not scale accordingly (risk hours have higher average volume).
- AHT effect is small in this sample compared with staffing mismatch.

## 2–3 actionable recommendations

**Near-term target (example):** reduce SLA-risk hour share from **`10.4%`** toward **`<5%`** of hours—tune the threshold and timeline with leadership and budget.

1. **Protect high-risk hours with targeted coverage buffers**
   - Add explicit staffing buffers for `00:00`, `04:00`–`08:00` (especially `08:00`).
   - Size increments using this sample: worst **hours** often show average gaps around **`+0.6` to `+1.1`** FTE short; **SLA-risk hours overall** average **`+5.31`** gap vs non-risk; automation treats **`gap ≥ 3`** as critical—practical intraday levers are often on the order of **+1 to +3** heads on the worst blocks before gaps compound.
   - Prioritize Tue/Wed/Fri coverage in these windows before expanding broadly.

2. **Implement intraday risk triggers and same-day interventions**
   - Trigger an escalation when both conditions occur:
     - `actual_staff < required_staff`
     - `sla_percent <= 84.6` or `coverage_ratio < 0.90`
   - Use standby shifts, overtime offers, or shift swaps for flagged windows.

3. **Operationalize daily monitoring with automated alerting**
   - Run `wfm_sla_alert_automation.py` daily on latest data.
   - Route top 5 risk windows to operations leadership with recommended actions.
   - Track weekly trend of:
     - SLA-risk hour count,
     - understaffed hour count,
     - critical-hour count (gap + SLA failure).


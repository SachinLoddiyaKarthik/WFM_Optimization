## WFM take-home assets (workforce optimization)

### How I used AI (assignment requirement)

I used an AI assistant to brainstorm structure, sanity-check logic, and refine wording. I implemented all analysis, code, Excel workbooks, and validation myself.

---

### Bonus app: how tabs map to the assignment

The Streamlit app (`app.py`) is an optional **integrated cockpit** that mirrors the take-home parts. UI theme (dark + accent) lives in **`.streamlit/config.toml`** and applies locally and on [Streamlit Community Cloud](https://streamlit.io/cloud).

| App tab | Take-home part | What it’s for |
|---------|----------------|---------------|
| **Executive Overview** | **Part 4** (performance monitoring) | KPIs, correlations, top risk hours — monthly / leadership snapshot. |
| **Performance Monitoring** | **Part 2** (dashboard / reporting) | Volume vs staffing, SLA trend, productivity proxy, heatmap — daily huddle views. |
| **Forecast & Recommendations** | **Part 1** (next-week forecast) | Next-week staffing built **dynamically** from the loaded dataset (same logic whether you use default or uploaded data). Optional static workbook `WFM_Part1_Forecast_Staffing.xlsx` is only a reference. |
| **Automation Demo** | **Part 3** (automation challenge) | Same alert logic as `wfm_sla_alert_automation.py` — morning risk alert + CSV download. |
| **Bonus Insights** | **Optional** (not scored) | Plan vs execution vs demand, load-pressure index, Pareto + data-quality checks. **Last tab** so required views come first. |

**Data:** Sidebar upload of a new monthly `.xlsx` recalculates KPIs and charts. Default file: `WFM_sample_dataset.xlsx` (falls back to `WFM_dashboard_input.xlsx` if needed).

---

### What’s in this folder

- `app.py` — Streamlit bonus app (upload new month, interactive views)
- `.streamlit/config.toml` — app theme (dark mode, accent color)
- `wfm_sla_alert_automation.py` — Part 3 automation script
- `WFM_Part1_Dashboard.xlsx`, `WFM_Part1_Forecast_Staffing.xlsx`, `WFM_Part2_Dashboard.xlsx`
- `WFM_Part3_Automation_Challenge.md`, `WFM_Part4_Performance_Monitoring_Insights.md`, `WFM_Part5_Executive_Summary.md`

---

### Setup

```bash
python3 -m venv .venv_wfm_alert
source .venv_wfm_alert/bin/activate
pip install -r requirements.txt
```

### Run Streamlit app (bonus)

```bash
streamlit run app.py
```

### Run automation script

```bash
python wfm_sla_alert_automation.py --demo
python wfm_sla_alert_automation.py --file WFM_dashboard_input.xlsx
```

### Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) and create a new app.
3. Main file: `app.py`.
4. Share the public URL as an optional bonus link in your submission email.

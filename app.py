import pathlib
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

from wfm_sla_alert_automation import CONFIG, detect_risks, generate_daily_summary


st.set_page_config(
    page_title="WFM Optimization — Interactive Demo",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


BASE_DIR = pathlib.Path(__file__).resolve().parent
PRIMARY_DATA_FILE = BASE_DIR / "WFM_sample_dataset.xlsx"
FALLBACK_DATA_FILE = BASE_DIR / "WFM_dashboard_input.xlsx"
FORECAST_FILE = BASE_DIR / "WFM_Part1_Forecast_Staffing_v3.xlsx"
FORECAST_SHEET = "6_Next_Week_Forecast"
REQUIRED_COLUMNS = {
    "date",
    "hour",
    "volume",
    "avg_handle_time_min",
    "required_staff",
    "actual_staff",
    "sla_percent",
}


def finalize_chart(fig, *, unified_hover: bool = True):
    """Match Plotly styling to Streamlit dark theme (see `.streamlit/config.toml`)."""
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified" if unified_hover else "closest",
        font=dict(size=13),
        title=dict(font=dict(size=15)),
        margin=dict(l=52, r=36, t=56, b=52),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


@st.cache_data
def _prepare_base_df(df: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["date"] = pd.to_datetime(df["date"])
    df["hour"] = df["hour"].astype(int)
    # scheduled_staff is optional in raw HR files; default to actual if absent
    if "scheduled_staff" not in df.columns:
        df["scheduled_staff"] = df["actual_staff"]
    if "staffing_gap" not in df.columns:
        df["staffing_gap"] = df["required_staff"] - df["actual_staff"]
    if "coverage_ratio" not in df.columns:
        df["coverage_ratio"] = df["actual_staff"] / df["required_staff"]
    if "sla_risk" not in df.columns:
        df["sla_risk"] = df["sla_percent"] <= CONFIG["sla_risk_threshold"]
    if "understaffed" not in df.columns:
        df["understaffed"] = df["actual_staff"] < df["required_staff"]
    if "dow" not in df.columns:
        df["dow"] = df["date"].dt.day_name().str[:3]
    if "volume_per_staff" not in df.columns:
        df["volume_per_staff"] = df["volume"] / df["actual_staff"].replace({0: pd.NA})
    # Bonus views: planning vs execution vs demand
    df["planning_gap"] = df["scheduled_staff"] - df["required_staff"]
    df["adh_gap"] = df["actual_staff"] - df["scheduled_staff"]
    df["workload_minutes"] = df["volume"] * df["avg_handle_time_min"]
    cap = df["actual_staff"].where(df["actual_staff"] > 0) * 60.0
    df["load_pressure_index"] = df["workload_minutes"] / cap
    df["date_hour"] = df["date"] + pd.to_timedelta(df["hour"], unit="h")
    return df


@st.cache_data
def load_base_data() -> pd.DataFrame:
    if PRIMARY_DATA_FILE.exists():
        return _prepare_base_df(pd.read_excel(PRIMARY_DATA_FILE))
    if FALLBACK_DATA_FILE.exists():
        return _prepare_base_df(pd.read_excel(FALLBACK_DATA_FILE))
    raise FileNotFoundError("No default input found (`WFM_sample_dataset.xlsx` or `WFM_dashboard_input.xlsx`).")


@st.cache_data
def load_uploaded_data(file_bytes: bytes) -> pd.DataFrame:
    return _prepare_base_df(pd.read_excel(BytesIO(file_bytes)))


@st.cache_data
def load_forecast_data() -> pd.DataFrame:
    if not FORECAST_FILE.exists():
        return pd.DataFrame()
    try:
        fc = pd.read_excel(FORECAST_FILE, sheet_name=FORECAST_SHEET)
    except Exception:
        return pd.DataFrame()
    if "date" in fc.columns:
        fc["date"] = pd.to_datetime(fc["date"])
    if "hour" in fc.columns:
        fc["hour"] = fc["hour"].astype(int)
    return fc


@st.cache_data
def build_dynamic_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a simple next-week hourly forecast from the currently loaded dataset.
    This keeps the app dynamic for any new monthly file upload.
    """
    x = df.copy()
    x["date"] = pd.to_datetime(x["date"])
    x["hour"] = x["hour"].astype(int)

    # Ensure risk flags exist for buffer logic
    if "sla_risk" not in x.columns:
        x["sla_risk"] = x["sla_percent"] <= CONFIG["sla_risk_threshold"]
    if "understaffed" not in x.columns:
        x["understaffed"] = x["actual_staff"] < x["required_staff"]

    max_date = x["date"].dt.date.max()
    forecast_start = pd.Timestamp(max_date) + pd.Timedelta(days=1)
    forecast_dates = [forecast_start + pd.Timedelta(days=i) for i in range(7)]

    # Use last 7 days if available, otherwise all data
    cutoff = pd.Timestamp(max_date) - pd.Timedelta(days=6)
    hist = x[x["date"] >= cutoff].copy()
    if hist.empty:
        hist = x.copy()

    # Hourly demand and staffing efficiency
    vol_by_hour = hist.groupby("hour")["volume"].mean()
    req_per_vol = hist.groupby("hour")[["required_staff", "volume"]].apply(
        lambda g: (g["required_staff"] / g["volume"]).replace([pd.NA, float("inf"), float("-inf")], pd.NA).dropna().mean()
    )
    global_req_per_vol = (
        (hist["required_staff"] / hist["volume"])
        .replace([pd.NA, float("inf"), float("-inf")], pd.NA)
        .dropna()
        .mean()
    )

    # Risk-based buffer from historical risky understaffed windows
    risky = hist[(hist["sla_risk"]) & (hist["understaffed"]) & (hist["actual_staff"] > 0)].copy()
    if len(risky) > 0:
        buffer_mult = float((risky["required_staff"] / risky["actual_staff"]).median())
    else:
        buffer_mult = 1.10
    buffer_mult = float(min(max(buffer_mult, 1.0), 1.5))

    # High-risk hour rule: top quartile risk rate by hour
    hour_risk = hist.groupby("hour")["sla_risk"].mean()
    q75 = float(hour_risk.quantile(0.75))

    rows = []
    for d in forecast_dates:
        for h in range(24):
            f_vol = float(vol_by_hour.get(h, hist["volume"].mean()))
            rpv = req_per_vol.get(h, global_req_per_vol)
            rpv = float(rpv if pd.notna(rpv) else global_req_per_vol)
            f_req = f_vol * rpv
            high_risk_hour = float(hour_risk.get(h, 0.0)) >= q75
            f_rec = f_req * buffer_mult if high_risk_hour else f_req
            rows.append(
                {
                    "date": d,
                    "hour": h,
                    "forecast_volume": f_vol,
                    "forecast_required_staff": f_req,
                    "recommended_scheduled_staff": f_rec,
                    "buffer_applied": high_risk_hour,
                }
            )

    fc = pd.DataFrame(rows)
    return fc


def filter_df(df: pd.DataFrame) -> pd.DataFrame:
    """Sidebar filters — keeps the main canvas clean for charts."""
    st.sidebar.markdown("### Filters")
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    date_range = st.sidebar.date_input(
        "Date range",
        (min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        help="All charts below respect this range.",
    )
    hours_all = sorted(df["hour"].unique().tolist())
    selected_hours = st.sidebar.multiselect(
        "Hours to include",
        hours_all,
        default=hours_all,
        help="Slice to peak intervals or focus on a narrow band.",
    )
    business_only = st.sidebar.checkbox(
        "Business hours only (7–19)",
        value=False,
        help="Intersects your hour selection with 7:00–19:00.",
    )
    if not selected_hours:
        st.sidebar.warning("No hours selected — using all hours.")
        selected_hours = hours_all
    eff_hours = [h for h in selected_hours if 7 <= h <= 19] if business_only else selected_hours
    if business_only and not eff_hours:
        st.sidebar.warning("No selected hours fall in 7–19 — using full business band.")
        eff_hours = [h for h in hours_all if 7 <= h <= 19]
    if len(date_range) != 2:
        start_date, end_date = min_date, max_date
    else:
        start_date, end_date = date_range
    return df[
        (df["date"].dt.date >= start_date)
        & (df["date"].dt.date <= end_date)
        & (df["hour"].isin(eff_hours))
    ]


def at_a_glance(dff: pd.DataFrame) -> None:
    """Above-the-fold strip: signal without scrolling."""
    if dff.empty:
        return
    c1, c2, c3, c4, c5 = st.columns(5)
    n = len(dff)
    risk_share = float(dff["sla_risk"].mean())
    under_share = float(dff["understaffed"].mean())
    span_days = (dff["date"].max() - dff["date"].min()).days + 1
    c1.metric("Filtered rows", f"{n:,}", help="Hour-level rows after sidebar filters.")
    c2.metric("Avg SLA", f"{dff['sla_percent'].mean():.1f}%")
    c3.metric("SLA risk (share)", pct(risk_share), help="Rows at/below the risk threshold from automation config.")
    c4.metric("Understaffed (share)", pct(under_share))
    c5.metric("Calendar span", f"{span_days}d", help="Days covered in the selected date range.")


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def score_all_windows(df: pd.DataFrame) -> pd.DataFrame:
    """Same flag logic as `detect_risks`, but scores every row (ranking / Pareto)."""
    x = df.copy()
    cfg = CONFIG
    vol_threshold = x["volume"].quantile(cfg["high_volume_percentile"])
    x["flag_sla_risk"] = x["sla_percent"] <= cfg["sla_risk_threshold"]
    x["flag_understaffed"] = x["actual_staff"] < x["required_staff"]
    x["flag_critical_gap"] = x["staffing_gap"] >= cfg["critical_gap_threshold"]
    x["flag_low_coverage"] = x["coverage_ratio"] < cfg["coverage_ratio_min"]
    x["flag_high_volume"] = x["volume"] >= vol_threshold
    x["risk_score"] = (
        x["flag_sla_risk"].astype(int)
        + x["flag_understaffed"].astype(int)
        + x["flag_critical_gap"].astype(int)
        + x["flag_low_coverage"].astype(int)
    )
    x["severity"] = pd.cut(
        x["risk_score"],
        bins=[-1, 0, 1, 2, 10],
        labels=["OK", "LOW", "HIGH", "CRITICAL"],
    )
    return x


def bonus_insights(df: pd.DataFrame) -> None:
    st.subheader("Bonus Insights")
    st.caption(
        "Optional add-on (not part of the core take-home): planning (scheduled vs required), execution "
        "(actual vs scheduled), and demand pressure (workload vs capacity). If `scheduled_staff` is missing, "
        "it defaults to `actual_staff`."
    )

    with st.expander("Data quality snapshot", expanded=False):
        n = len(df)
        neg_sched = int((df["scheduled_staff"] < 0).sum())
        neg_actual = int((df["actual_staff"] < 0).sum())
        bad_req = int((df["required_staff"] <= 0).sum())
        extreme_cov = int((df["coverage_ratio"] > 2.0).sum())
        lpi_high = int((df["load_pressure_index"] > 1.25).sum())
        q99 = float(df["volume_per_staff"].quantile(0.99))
        prod_spike = int((df["volume_per_staff"] > q99).sum()) if pd.notna(q99) else 0
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Rows", f"{n:,}")
        c2.metric("Neg. scheduled", neg_sched)
        c3.metric("Neg. actual", neg_actual)
        c4.metric("Non-pos. required", bad_req)
        c5.metric("Coverage > 2×", extreme_cov)
        c6.metric("LPI > 1.25", lpi_high)
        st.caption(
            f"Extreme productivity proxy (vol/staff > 99th pct): {prod_spike} hour-rows. "
            "Use these checks before trusting downstream charts."
        )
        if neg_sched > 0:
            st.warning(
                f"{neg_sched} row(s) have negative `scheduled_staff` — worth a quick source check "
                "(data entry, reversals, or borrow logic)."
            )

    df_day = df.copy()
    df_day["day"] = df_day["date"].dt.date
    by_day = (
        df_day.groupby("day", as_index=False)
        .agg(
            required_staff=("required_staff", "sum"),
            scheduled_staff=("scheduled_staff", "sum"),
            actual_staff=("actual_staff", "sum"),
            avg_lpi=("load_pressure_index", "mean"),
        )
    )
    fig_triple = px.line(
        by_day,
        x="day",
        y=["required_staff", "scheduled_staff", "actual_staff"],
        markers=True,
        title="Plan vs Execution — Staff-Hours (Required vs Scheduled vs Actual)",
    )
    fig_triple.update_layout(legend_title_text="")
    st.plotly_chart(finalize_chart(fig_triple), width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        plan_gap_pct = float((df["planning_gap"] < 0).mean()) if len(df) else 0.0
        adh_pct = float((df["adh_gap"] != 0).mean()) if len(df) else 0.0
        st.metric("Hours under-planned (sched < req)", pct(plan_gap_pct))
        st.metric("Hours with schedule adherence variance", pct(adh_pct))
    with c2:
        fig_lpi = px.line(by_day, x="day", y="avg_lpi", markers=True, title="Load Pressure Index (avg by day)")
        fig_lpi.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="1.0 = at capacity")
        fig_lpi.update_layout(yaxis_title="LPI (workload min / capacity min)")
        st.plotly_chart(finalize_chart(fig_lpi), width="stretch")

    st.markdown("**Pareto — where risk concentrates**")
    scored = score_all_windows(df)
    risky = scored[scored["risk_score"] > 0].copy()
    if risky.empty:
        st.info("No scored risk windows in the current filter (try widening the date range).")
        return
    thr = float(CONFIG["sla_risk_threshold"])
    risky["risk_priority"] = (
        risky["risk_score"].astype(float) * 1000.0
        + risky["staffing_gap"].clip(lower=0) * 10.0
        + (thr - risky["sla_percent"]).clip(lower=0)
    )
    risky = risky.sort_values(["risk_priority", "date", "hour"], ascending=[False, True, True])
    w = risky["risk_score"].astype(float)
    total_w = float(w.sum()) or 1.0
    risky["cum_pct_risk_mass"] = (w.cumsum() / total_w * 100.0).round(1)
    risky["window"] = risky["date"].dt.strftime("%Y-%m-%d") + " @ " + risky["hour"].astype(str) + ":00"
    show_cols = [
        "window",
        "sla_percent",
        "required_staff",
        "scheduled_staff",
        "actual_staff",
        "staffing_gap",
        "risk_score",
        "severity",
        "cum_pct_risk_mass",
    ]
    pareto = risky[show_cols].head(20)
    pareto = pareto.rename(
        columns={
            "window": "Window",
            "sla_percent": "SLA %",
            "required_staff": "Req",
            "scheduled_staff": "Sched",
            "actual_staff": "Actual",
            "staffing_gap": "Gap",
            "risk_score": "Score",
            "severity": "Severity",
            "cum_pct_risk_mass": "Cum. % of risk mass",
        }
    )
    st.dataframe(pareto, width="stretch", hide_index=True)
    st.caption(
        "Sorted by **risk priority** (integer score first, then staffing gap, then how far SLA sits below threshold). "
        "Cumulative % still uses integer risk mass (same flags as Part 3)."
    )

    topn = risky.head(12).copy()
    topn["rank"] = range(1, len(topn) + 1)
    topn["rank_label"] = "#" + topn["rank"].astype(str)
    # Color by continuous priority so the chart still reads when every row is the same severity (e.g. all CRITICAL).
    fig_bar = px.bar(
        topn,
        x="rank_label",
        y="risk_priority",
        color="risk_priority",
        color_continuous_scale="Reds",
        title="Top 12 windows — risk priority (tie-broken when score = 4)",
        custom_data=["window", "risk_score", "sla_percent", "staffing_gap", "severity"],
    )
    fig_bar.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Severity=%{customdata[4]}<br>"
            "Priority=%{y:.1f} "
            "(1000×score + 10×max(gap,0) + max(0, SLA threshold−SLA))<br>"
            "Score=%{customdata[1]} | SLA=%{customdata[2]:.1f}% | Gap=%{customdata[3]}<extra></extra>"
        )
    )
    ymin = float(topn["risk_priority"].min())
    ymax = float(topn["risk_priority"].max())
    pad = max((ymax - ymin) * 0.2, 8.0)
    fig_bar.update_layout(
        xaxis_title="Worst → better (by priority rank)",
        xaxis_tickangle=0,
        yaxis=dict(
            title="Risk priority (zoomed to these 12 rows)",
            range=[ymin - pad, ymax + pad],
        ),
        coloraxis_colorbar=dict(title="Priority<br>(darker = worse)"),
    )
    st.plotly_chart(finalize_chart(fig_bar, unified_hover=False), width="stretch")
    st.caption(
        "Bar color = same priority score as height (useful when severity is all CRITICAL). "
        "Y-axis zoomed to these 12 points. Hover for window, SLA, gap, severity."
    )


def executive_overview(df: pd.DataFrame) -> None:
    st.subheader("Executive Overview")
    total_rows = len(df)
    risk_hours = int(df["sla_risk"].sum())
    understaffed_hours = int(df["understaffed"].sum())
    avg_cov = float(df["coverage_ratio"].mean())
    avg_sla = float(df["sla_percent"].mean())
    corr_gap = float(df[["staffing_gap", "sla_percent"]].corr().iloc[0, 1])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Avg SLA", f"{avg_sla:.1f}%")
    c2.metric("SLA Risk Hours", f"{risk_hours}/{total_rows}", pct(risk_hours / total_rows))
    c3.metric("Understaffed Hours", f"{understaffed_hours}/{total_rows}", pct(understaffed_hours / total_rows))
    c4.metric("Avg Coverage", f"{avg_cov:.3f}")
    c5.metric("Corr(Gap, SLA)", f"{corr_gap:.3f}")

    top_hours = (
        df.groupby("hour", as_index=False)
        .agg(risk_rate=("sla_risk", "mean"), avg_gap=("staffing_gap", "mean"), avg_sla=("sla_percent", "mean"))
        .sort_values(["risk_rate", "avg_gap"], ascending=[False, False])
        .head(6)
    )
    top_hours = top_hours.rename(
        columns={
            "hour": "Hour",
            "risk_rate": "SLA Risk Rate",
            "avg_gap": "Avg Staffing Gap",
            "avg_sla": "Avg SLA %",
        }
    )
    top_hours["SLA Risk Rate"] = (top_hours["SLA Risk Rate"] * 100).round(1)
    top_hours["Avg Staffing Gap"] = top_hours["Avg Staffing Gap"].round(2)
    top_hours["Avg SLA %"] = top_hours["Avg SLA %"].round(2)
    st.caption("Top risk hours (highest SLA-risk rate + staffing gap):")
    st.dataframe(top_hours, width="stretch", hide_index=True)


def performance_monitoring(df: pd.DataFrame) -> None:
    st.subheader("Performance Monitoring")
    df = df.copy()
    df["date_day"] = df["date"].dt.date
    by_day = (
        df.groupby("date_day", as_index=False)
        .agg(
            volume=("volume", "sum"),
            required_staff=("required_staff", "sum"),
            actual_staff=("actual_staff", "sum"),
            avg_sla=("sla_percent", "mean"),
            avg_aht=("avg_handle_time_min", "mean"),
            avg_volume_per_staff=("volume_per_staff", "mean"),
            risk_hours=("sla_risk", "sum"),
        )
        .rename(columns={"date_day": "date"})
    )
    by_day["risk_day"] = by_day["risk_hours"] > 0

    c1, c2 = st.columns(2)
    with c1:
        fig_staff = px.line(
            by_day,
            x="date",
            y=["required_staff", "actual_staff"],
            markers=True,
            title="Daily staff-hours — required vs actual",
        )
        fig_staff.update_layout(legend_title_text="")
        st.plotly_chart(finalize_chart(fig_staff), width="stretch")
    with c2:
        fig_sla = px.line(by_day, x="date", y="avg_sla", markers=True, title="SLA Performance Over Time")
        fig_sla.add_hline(y=CONFIG["sla_risk_threshold"], line_dash="dash", line_color="orange", annotation_text=f"Risk threshold ({CONFIG['sla_risk_threshold']:.1f})")
        risk_points = by_day[by_day["risk_day"]]
        if not risk_points.empty:
            fig_sla.add_scatter(x=risk_points["date"], y=risk_points["avg_sla"], mode="markers", marker=dict(color="red", size=9), name="Days w/ SLA risk")
        fig_sla.update_layout(legend_title_text="")
        st.plotly_chart(finalize_chart(fig_sla), width="stretch")

    c3, c4 = st.columns(2)
    with c3:
        fig_prod = px.line(by_day, x="date", y="avg_volume_per_staff", markers=True, title="Productivity Proxy (Volume per Staff)")
        fig_prod.update_layout(legend_title_text="")
        st.plotly_chart(finalize_chart(fig_prod), width="stretch")
    with c4:
        fig_aht = px.line(by_day, x="date", y="avg_aht", markers=True, title="AHT Trend")
        fig_aht.update_layout(legend_title_text="")
        st.plotly_chart(finalize_chart(fig_aht), width="stretch")

    heat = (
        df.groupby(["dow", "hour"], as_index=False)
        .agg(risk_rate=("sla_risk", "mean"))
        .pivot(index="dow", columns="hour", values="risk_rate")
        .reindex(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    )
    fig_heat = px.imshow(
        (heat * 100),
        labels=dict(x="Hour", y="Day of week", color="SLA risk rate"),
        title="SLA Risk Heatmap (Day x Hour)",
        aspect="auto",
    )
    fig_heat.update_coloraxes(colorbar_title_text="Risk %")
    st.plotly_chart(finalize_chart(fig_heat, unified_hover=False), width="stretch")


def forecast_and_recommendations(fc: pd.DataFrame) -> None:
    st.subheader("Forecast & Staffing Recommendations")
    if fc.empty:
        st.info("No forecast could be built (empty dataset). Upload a valid monthly file or restore the sample Excel.")
        return

    req_col = "forecast_required_staff"
    rec_col = "recommended_scheduled_staff"
    if req_col not in fc.columns or rec_col not in fc.columns:
        st.warning("Forecast columns missing expected fields.")
        return

    by_hour = (
        fc.groupby("hour", as_index=False)
        .agg(
            forecast_required_staff=(req_col, "mean"),
            recommended_scheduled_staff=(rec_col, "mean"),
        )
    )
    by_hour["increment"] = by_hour["recommended_scheduled_staff"] - by_hour["forecast_required_staff"]
    by_hour["increment_pct"] = (by_hour["recommended_scheduled_staff"] / by_hour["forecast_required_staff"] - 1.0) * 100

    fig = px.line(
        by_hour,
        x="hour",
        y=["forecast_required_staff", "recommended_scheduled_staff"],
        markers=True,
        title="Next-Week Staffing: Forecast Required vs Recommended Scheduled",
    )
    fig.update_layout(legend_title_text="")
    st.plotly_chart(finalize_chart(fig), width="stretch")

    st.caption("Top adjustment windows")
    show = by_hour.sort_values("increment", ascending=False).head(8).copy()
    show = show.rename(
        columns={
            "hour": "Hour",
            "forecast_required_staff": "Forecast Required",
            "recommended_scheduled_staff": "Recommended Scheduled",
            "increment": "Increment",
            "increment_pct": "Increment %",
        }
    )
    show["Forecast Required"] = show["Forecast Required"].round(2)
    show["Recommended Scheduled"] = show["Recommended Scheduled"].round(2)
    show["Increment"] = show["Increment"].round(2)
    show["Increment %"] = show["Increment %"].round(1)
    st.dataframe(show, width="stretch", hide_index=True)


def automation_demo(df: pd.DataFrame) -> None:
    st.subheader("Automation Demo — Daily SLA Risk Alert")
    selected_date = st.date_input("Run alert for date", value=df["date"].max().date(), min_value=df["date"].min().date(), max_value=df["date"].max().date())
    summary = generate_daily_summary(df, selected_date)
    flagged = detect_risks(df[df["date"].dt.date == selected_date].copy())

    c1, c2, c3 = st.columns(3)
    c1.metric("Avg SLA", f"{summary['avg_sla']:.1f}%")
    c2.metric("Understaffed Hours", f"{summary['understaffed_hours']}/{summary['total_hours']}")
    c3.metric("Critical Hours", str(summary["critical_hours"]))

    st.write("Top flagged windows")
    if flagged.empty:
        st.success("No flagged windows for this date.")
    else:
        show_cols = [
            "date",
            "hour",
            "sla_percent",
            "required_staff",
            "actual_staff",
            "staffing_gap",
            "risk_score",
            "severity",
        ]
        table = flagged.sort_values(["risk_score", "staffing_gap", "sla_percent"], ascending=[False, False, True])[show_cols].head(20)
        table = table.rename(
            columns={
                "date": "Date",
                "hour": "Hour",
                "sla_percent": "SLA %",
                "required_staff": "Required",
                "actual_staff": "Actual",
                "staffing_gap": "Gap",
                "risk_score": "Risk Score",
                "severity": "Severity",
            }
        )
        table["Date"] = pd.to_datetime(table["Date"]).dt.strftime("%Y-%m-%d")
        st.dataframe(table, width="stretch", hide_index=True)
        flagged_csv = flagged.copy()
        flagged_csv["date"] = pd.to_datetime(flagged_csv["date"]).dt.strftime("%Y-%m-%d")
        st.download_button(
            label="Download flagged rows CSV",
            data=flagged_csv.to_csv(index=False).encode("utf-8"),
            file_name=f"wfm_risk_flags_{selected_date}.csv",
            mime="text/csv",
        )


def main() -> None:
    st.title("Workforce optimization")
    st.markdown(
        "Monitor **staffing, SLA risk, forecasts, and automation-ready alerts** in one interactive workspace. "
        "Use the sidebar to swap data and narrow the story — everything below updates together."
    )

    with st.expander("Reviewer map — how tabs line up with the assignment", expanded=False):
        st.markdown(
            """
- **Executive Overview** → **Part 4** (performance monitoring — KPIs, top risk hours).
- **Performance Monitoring** → **Part 2** (dashboard / reporting — trends & heatmap).
- **Forecast & Recommendations** → **Part 1** (next-week staffing — generated dynamically from the loaded dataset; optional static workbook for reference).
- **Automation Demo** → **Part 3** (SLA risk alert — same logic as `wfm_sla_alert_automation.py`).
- **Bonus Insights** → **Optional** (plan vs execution vs demand, load pressure, Pareto + data-quality checks — not required by the assignment).

**Rituals:** weekly staffing review (Parts 1 + Forecast tab), daily huddle (Part 2 views), morning alert (Part 3 / Automation tab), monthly deep-dive (Part 4 + Executive Overview).
            """
        )

    st.sidebar.markdown("### Data")
    uploaded_file = st.sidebar.file_uploader(
        "Upload monthly WFM Excel",
        type=["xlsx", "xls"],
        help="If provided, the app recalculates all KPIs/charts from this uploaded file.",
    )
    if uploaded_file is not None:
        try:
            df = load_uploaded_data(uploaded_file.getvalue())
            st.sidebar.success("Using uploaded file")
        except Exception as exc:
            st.sidebar.error("Could not read uploaded file.")
            st.error(f"Upload failed: {exc}")
            st.stop()
    else:
        try:
            df = load_base_data()
        except FileNotFoundError as exc:
            st.error(str(exc))
            st.stop()
        default_name = PRIMARY_DATA_FILE.name if PRIMARY_DATA_FILE.exists() else FALLBACK_DATA_FILE.name
        st.sidebar.info(f"Using default file: {default_name}")

    # Dynamic forecast is always generated from the currently loaded dataset.
    # This makes forecast behavior consistent for both default and uploaded files.
    fc_dynamic = build_dynamic_forecast(df)
    # Keep static forecast file as fallback/reference only.
    fc_static = load_forecast_data()
    fc = fc_dynamic if not fc_dynamic.empty else fc_static
    dff = filter_df(df)
    if dff.empty:
        st.error("No rows match your filters. Widen the date range or include more hours in the sidebar.")
        st.stop()

    st.divider()
    at_a_glance(dff)
    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "Executive Overview",
            "Performance Monitoring",
            "Forecast & Recommendations",
            "Automation Demo",
            "Bonus Insights",
        ]
    )
    with tab1:
        executive_overview(dff)
    with tab2:
        performance_monitoring(dff)
    with tab3:
        forecast_and_recommendations(fc)
    with tab4:
        automation_demo(df)
    with tab5:
        bonus_insights(dff)

    st.divider()
    st.caption("Interactive demo · Upload your own monthly extract or run on the bundled sample · Plotly charts · Filters apply app-wide")


if __name__ == "__main__":
    main()

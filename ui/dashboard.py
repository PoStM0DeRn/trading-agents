"""Streamlit Dashboard — Trading Agents System (MOEX / RUB / LLM)."""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from streamlit_autorefresh import st_autorefresh

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.bootstrap import load_config, init_system
from stream.lmstudio_monitor import monitor as lm_monitor

logger = logging.getLogger(__name__)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Agents — MOEX",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ═══ GLOBAL ═══ */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --bg-primary: #0f1117;
        --bg-secondary: #1a1d27;
        --bg-card: #22262f;
        --bg-card-hover: #2a2e38;
        --accent-green: #00e6b8;
        --accent-red: #ff5c6c;
        --accent-blue: #4d94ff;
        --accent-purple: #b388ff;
        --accent-orange: #ffb347;
        --text-primary: #ffffff;
        --text-secondary: #d1d5db;
        --text-muted: #9ca3af;
        --border: #2d3340;
        --gradient-green: linear-gradient(135deg, #00e6b8 0%, #00d4aa 100%);
        --gradient-red: linear-gradient(135deg, #ff5c6c 0%, #ff4757 100%);
        --gradient-blue: linear-gradient(135deg, #4d94ff 0%, #3b82f6 100%);
        --gradient-purple: linear-gradient(135deg, #b388ff 0%, #a855f7 100%);
        --gradient-dark: linear-gradient(135deg, #22262f 0%, #1a1d27 100%);
        --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.4);
        --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.5);
        --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.6);
    }

    .stApp {
        background: var(--bg-primary);
    }

    /* ═══ HEADER ═══ */
    .main-header {
        background: linear-gradient(135deg, #1a1f2e 0%, #0f172a 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px 28px;
        margin-bottom: 24px;
        box-shadow: var(--shadow-md);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .main-header h1 {
        font-family: 'Inter', sans-serif;
        font-size: 28px;
        font-weight: 700;
        color: #ffffff;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    }

    .main-header .subtitle {
        font-size: 13px;
        color: #9ca3af;
        margin-top: 4px;
    }

    .mode-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 16px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 700;
        font-family: 'Inter', sans-serif;
    }

    .mode-badge.paper {
        background: rgba(77, 148, 255, 0.2);
        color: #80b3ff;
        border: 1px solid rgba(77, 148, 255, 0.4);
    }

    .mode-badge.live {
        background: rgba(0, 230, 184, 0.2);
        color: #00e6b8;
        border: 1px solid rgba(0, 230, 184, 0.4);
    }

    /* ═══ METRIC CARDS ═══ */
    div[data-testid="stMetric"] {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: var(--shadow-sm);
        transition: all 0.3s ease;
    }

    div[data-testid="stMetric"]:hover {
        background: var(--bg-card-hover);
        box-shadow: var(--shadow-md);
        transform: translateY(-2px);
    }

    div[data-testid="stMetric"] label {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        font-weight: 700;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-family: 'Inter', sans-serif;
        font-size: 32px;
        font-weight: 700;
        color: #ffffff;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    }

    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        font-family: 'Inter', sans-serif;
        font-size: 14px;
        font-weight: 600;
    }

    /* ═══ CARDS ═══ */
    .card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 24px;
        box-shadow: var(--shadow-sm);
        transition: all 0.3s ease;
        margin-bottom: 16px;
    }

    .card:hover {
        box-shadow: var(--shadow-md);
    }

    .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--border);
    }

    .card-title {
        font-family: 'Inter', sans-serif;
        font-size: 16px;
        font-weight: 600;
        color: #ffffff;
    }

    /* ═══ POSITION CARDS ═══ */
    .position-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px;
        box-shadow: var(--shadow-sm);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }

    .position-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
    }

    .position-card.long::before {
        background: var(--gradient-green);
    }

    .position-card.short::before {
        background: var(--gradient-red);
    }

    .position-card:hover {
        box-shadow: var(--shadow-md);
        transform: translateY(-2px);
    }

    .position-ticker {
        font-family: 'Inter', sans-serif;
        font-size: 24px;
        font-weight: 700;
        color: #ffffff;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    }

    .position-side {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .position-side.long {
        background: rgba(0, 230, 184, 0.2);
        color: #00e6b8;
        border: 1px solid rgba(0, 230, 184, 0.4);
    }

    .position-side.short {
        background: rgba(255, 92, 108, 0.2);
        color: #ff5c6c;
        border: 1px solid rgba(255, 92, 108, 0.4);
    }

    .position-pnl {
        font-family: 'Inter', sans-serif;
        font-size: 24px;
        font-weight: 700;
    }

    .position-pnl.profit {
        color: #00e6b8;
        text-shadow: 0 0 10px rgba(0, 230, 184, 0.3);
    }

    .position-pnl.loss {
        color: #ff5c6c;
        text-shadow: 0 0 10px rgba(255, 92, 108, 0.3);
    }

    .position-details {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-top: 16px;
    }

    .position-detail {
        text-align: center;
        padding: 8px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 8px;
    }

    .position-detail-label {
        font-size: 11px;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }

    .position-detail-value {
        font-family: 'Inter', sans-serif;
        font-size: 14px;
        font-weight: 600;
        color: #ffffff;
    }

    /* ═══ SL/TP BADGES ═══ */
    .sl-tp-container {
        display: flex;
        gap: 8px;
        margin-top: 12px;
    }

    .sl-badge, .tp-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
    }

    .sl-badge {
        background: rgba(255, 92, 108, 0.15);
        color: #ff7a85;
        border: 1px solid rgba(255, 92, 108, 0.3);
    }

    .tp-badge {
        background: rgba(0, 230, 184, 0.15);
        color: #33e6c5;
        border: 1px solid rgba(0, 230, 184, 0.3);
    }

    /* ═══ BUTTONS ═══ */
    .stButton > button {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        border-radius: 10px;
        padding: 10px 24px;
        transition: all 0.3s ease;
        border: none;
    }

    .stButton > button[kind="primary"] {
        background: var(--gradient-blue);
        color: #ffffff;
        box-shadow: 0 4px 12px rgba(77, 148, 255, 0.4);
    }

    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(77, 148, 255, 0.5);
        transform: translateY(-1px);
    }

    /* ═══ TABS ═══ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: var(--bg-secondary);
        padding: 6px;
        border-radius: 12px;
        border: 1px solid var(--border);
    }

    .stTabs [data-baseweb="tab"] {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        border-radius: 8px;
        padding: 10px 20px;
        color: #d1d5db;
        transition: all 0.3s ease;
    }

    .stTabs [aria-selected="true"] {
        background: var(--bg-card);
        color: #ffffff;
        box-shadow: var(--shadow-sm);
    }

    /* ═══ SIDEBAR ═══ */
    section[data-testid="stSidebar"] {
        background: var(--bg-secondary);
        border-right: 1px solid var(--border);
    }

    /* ═══ SCROLLBAR ═══ */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
    }

    ::-webkit-scrollbar-thumb {
        background: #4b5563;
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #6b7280;
    }

    /* ═══ ANIMATIONS ═══ */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    .fade-in {
        animation: fadeIn 0.5s ease-out;
    }

    .pulse {
        animation: pulse 2s infinite;
    }

    /* ═══ EXPANDER ═══ */
    .streamlit-expanderHeader {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        color: #ffffff;
    }

    /* ═══ STATUS INDICATORS ═══ */
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
    }

    .status-dot.active {
        background: #00e6b8;
        box-shadow: 0 0 10px rgba(0, 230, 184, 0.6);
    }

    .status-dot.inactive {
        background: #9ca3af;
    }

    .status-dot.warning {
        background: #ffb347;
        box-shadow: 0 0 10px rgba(255, 179, 71, 0.6);
    }

    .status-dot.error {
        background: #ff5c6c;
        box-shadow: 0 0 10px rgba(255, 92, 108, 0.6);
    }

    /* ═══ PROGRESS BAR ═══ */
    .stProgress > div > div {
        background: var(--gradient-blue);
        border-radius: 4px;
    }

    /* ═══ DIVIDER ═══ */
    hr {
        border: none;
        border-top: 1px solid var(--border);
        margin: 24px 0;
    }
</style>
""", unsafe_allow_html=True)


# ── System init (cached) ─────────────────────────────────────────────────────
@st.cache_resource
def get_system():
    config = load_config()
    components = init_system(config)

    return components.supervisor, components.llm_client, components.tinvest, components.config

def _safe_rerun():
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════════
def render_header(config: dict):
    paper = config.get("trading", {}).get("paper_trading", True)
    mode_class = "paper" if paper else "live"
    mode_text = "📝 PAPER" if paper else "💰 LIVE"
    status_class = "active" if paper else "warning"

    st.markdown(f"""
    <div class="main-header">
        <div>
            <h1>📈 Trading Agents</h1>
            <div class="subtitle">Multi-Agent LLM System · MOEX · T-Invest</div>
        </div>
        <div style="display: flex; align-items: center; gap: 16px;">
            <div style="text-align: right;">
                <div style="font-size: 12px; color: var(--text-muted);">Capital</div>
                <div style="font-size: 20px; font-weight: 700; color: var(--text-primary);">{config.get('trading', {}).get('initial_capital', 0):,.0f} ₽</div>
            </div>
            <div class="mode-badge {mode_class}">
                <span class="status-dot {status_class}"></span>
                {mode_text}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("🎯 Risk/Trade", f"{config.get('risk', {}).get('default_risk_per_trade', 1)}%")
    with c2:
        st.metric("📊 Max Positions", config.get("trading", {}).get("max_positions", 10))
    with c3:
        st.metric("⚖️ Max Position", f"{config.get('trading', {}).get('max_position_percent', 20)}%")
    with c4:
        st.metric("📈 Leverage", f"×{config.get('trading', {}).get('max_leverage', 1.0)}")
    with c5:
        allow_shorts = config.get('trading', {}).get('allow_shorts', False)
        shorts_text = "ON" if allow_shorts else "OFF"
        shorts_class = "active" if allow_shorts else "inactive"
        st.metric("📉 Shorts", shorts_text)

    # LLM metrics row (auto-refreshing fragment)
    render_llm_metrics(config)


# ══════════════════════════════════════════════════════════════════════════════
#  LLM METRICS FRAGMENT (auto-refresh every 3s)
# ══════════════════════════════════════════════════════════════════════════════
@st.fragment(run_every=timedelta(seconds=3))
def render_llm_metrics(config: dict):
    llm_stats = lm_monitor.get_stats()
    llm_model = config.get("lmstudio", {}).get("model", "—")

    speed = llm_stats.get("tokens_per_sec", 0)
    avg_speed = llm_stats.get("avg_tokens_per_sec", 0)

    l1, l2, l3 = st.columns(3)
    with l1:
        st.metric("⚡ LLM Speed", f"{speed:.1f} tok/s")
    with l2:
        st.metric("📊 Avg Speed", f"{avg_speed:.1f} tok/s")
    with l3:
        st.metric("🤖 Model", llm_model)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1: TRADING CYCLE + SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════
def render_cycle_tab(supervisor, config: dict):
    col_scan, col_single, col_scheduler = st.columns([1.2, 1, 1])

    # ── Scan + Run ──────────────────────────────────────────────────────────
    with col_scan:
        st.markdown("""
        <div class="card">
            <div class="card-header">
                <span class="card-title">🔍 Scan + Trade</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        scanner_config = config.get("scanner", {})
        scan_max_picks = st.number_input(
            "Max Tickers", min_value=1, max_value=20,
            value=scanner_config.get("max_picks", 5),
            key="scan_cycle_max_picks",
        )
        scan_use_llm = st.toggle(
            "Use LLM", value=scanner_config.get("use_llm", True),
            key="scan_cycle_use_llm",
        )

        if st.button("🔍 Scan → ▶️ Run Cycle", type="primary", width="stretch", key="scan_and_run"):
            from tools import ticker_scanner, virtual_portfolio
            from integrations.tinvest import TInvestClient

            with st.spinner("Step 1: Scanning MOEX market..."):
                try:
                    tinvest_config = config.get("tinvest", {})
                    tinvest_client = TInvestClient(
                        token=tinvest_config.get("token", ""),
                        account_id=tinvest_config.get("account_id", ""),
                    )
                    tinvest_client.connect()
                    ticker_scanner.set_clients(supervisor.llm, tinvest_client, config)

                    current_positions = virtual_portfolio.get_positions()
                    balance_info = virtual_portfolio.get_balance()
                    capital = balance_info["current_balance"]

                    scan_result = ticker_scanner.scan_market(
                        max_picks=scan_max_picks,
                        sectors=scanner_config.get("sectors"),
                        min_volume=scanner_config.get("min_volume", 10000),
                        open_positions=current_positions,
                        capital=capital,
                        use_llm=scan_use_llm,
                    )
                    tinvest_client.close()

                    tickers = [t["ticker"] for t in scan_result.get("selected_tickers", [])]

                    if not tickers:
                        st.warning("Scanner returned no tickers")
                        return

                    outlook = scan_result.get("market_outlook", "neutral")
                    st.success(f"Scanned {scan_result.get('total_scanned', 0)} shares → Selected: {', '.join(tickers)} (outlook: {outlook})")

                except Exception as e:
                    st.error(f"Scanner failed: {e}")
                    return

            # Step 2: Run cycle with scanned tickers
            st.markdown("---")
            st.info(f"Step 2: Running trading cycle for {len(tickers)} scanned tickers...")

            with st.spinner("Running trading cycle..."):
                progress = st.progress(0, text="Starting...")
                total = len(tickers)
                report = None
                for i, ticker in enumerate(tickers):
                    progress.progress(i / total, text=f"Analyzing {ticker} ({i+1}/{total})...")
                    try:
                        report = supervisor.run_trading_cycle(tickers=[ticker], max_iterations=1)
                    except Exception as e:
                        st.error(f"Error on {ticker}: {e}")
                        continue
                    progress.progress((i + 1) / total, text=f"{ticker} — done")
                progress.progress(1.0, text="Cycle complete!")
                st.success("Scan + Cycle completed!")
                if report:
                    _render_cycle_report(report)

    # ── Single Run ────────────────────────────────────────────────────────────
    with col_single:
        st.markdown("""
        <div class="card">
            <div class="card-header">
                <span class="card-title">🚀 Manual Cycle</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        tickers_input = st.text_area(
            "Tickers (comma separated)",
            value=", ".join(config.get("watchlist", [])),
            height=68,
            key="cycle_tickers",
            label_visibility="collapsed",
        )

        if st.button("▶️  Run Cycle", type="primary", width="stretch", key="single_run"):
            tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
            if not tickers:
                st.warning("Enter at least one ticker")
            else:
                with st.spinner("Running trading cycle..."):
                    progress = st.progress(0, text="Starting...")
                    total = len(tickers)
                    report = None
                    for i, ticker in enumerate(tickers):
                        progress.progress(i / total, text=f"Analyzing {ticker} ({i+1}/{total})...")
                        try:
                            report = supervisor.run_trading_cycle(tickers=[ticker], max_iterations=1)
                        except Exception as e:
                            st.error(f"Error on {ticker}: {e}")
                            continue
                        progress.progress((i + 1) / total, text=f"{ticker} — done")
                    progress.progress(1.0, text="Cycle complete!")
                    st.success("Trading cycle completed!")
                    if report:
                        _render_cycle_report(report)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    with col_scheduler:
        st.markdown("""
        <div class="card">
            <div class="card-header">
                <span class="card-title">⏰ Auto Scheduler</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        from tools.scheduler import TradingScheduler

        if "scheduler" not in st.session_state:
            st.session_state.scheduler = TradingScheduler(supervisor, config)

        scheduler = st.session_state.scheduler
        status = scheduler.get_status()

        interval = st.number_input(
            "Interval (minutes)",
            min_value=1,
            max_value=120,
            value=status.get("interval_minutes", 15),
            key="scheduler_interval",
        )

        sched_tickers = st.text_input(
            "Tickers",
            value=", ".join(status.get("tickers", config.get("watchlist", []))),
            key="sched_tickers_input",
            label_visibility="collapsed",
        )

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("▶️  Start", width="stretch", disabled=status["running"], key="sched_start"):
                tickers_list = [t.strip().upper() for t in sched_tickers.split(",") if t.strip()]
                scheduler.start(interval_minutes=interval, tickers=tickers_list)
                st.success("Scheduler started!")
                _safe_rerun()
        with btn_col2:
            if st.button("⏹  Stop", width="stretch", disabled=not status["running"], key="sched_stop"):
                scheduler.stop()
                st.info("Scheduler stopped")
                _safe_rerun()

        # Status indicator
        if status["running"]:
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: rgba(0, 212, 170, 0.1); border-radius: 8px; border: 1px solid rgba(0, 212, 170, 0.2);">
                <span class="status-dot active pulse"></span>
                <span style="color: #00d4aa; font-weight: 600;">Running</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 8px; padding: 12px; background: rgba(100, 116, 139, 0.1); border-radius: 8px; border: 1px solid rgba(100, 116, 139, 0.2);">
                <span class="status-dot inactive"></span>
                <span style="color: #94a3b8; font-weight: 600;">Stopped</span>
            </div>
            """, unsafe_allow_html=True)

        info_cols = st.columns(3)
        with info_cols[0]:
            st.metric("Cycles", status["cycles_run"])
        with info_cols[1]:
            st.metric("Interval", f"{status['interval_minutes']} min")
        with info_cols[2]:
            next_run = status.get("next_run", "—")
            if next_run and next_run != "—":
                try:
                    from datetime import timezone
                    next_dt = datetime.fromisoformat(next_run)
                    if next_dt.tzinfo is None:
                        next_dt = next_dt.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(timezone.utc)
                    mins_left = max(0, int((next_dt - now_utc).total_seconds() / 60))
                    st.metric("Next", f"in {mins_left} min")
                except Exception:
                    st.metric("Next", next_run[:16])
            else:
                st.metric("Next", "—")

    st.markdown("---")

    # Recent cycles
    if status.get("recent_logs"):
        st.markdown("### 📋 Recent Cycles")
        for entry in status["recent_logs"][:5]:
            ts = entry.get("time", "?")[:16]
            cid = entry.get("cycle_id", "?")[:8]
            tickers_count = len(entry.get("tickers", []))
            proposals = entry.get("proposals", 0)
            approved = entry.get("approved", 0)
            executed = entry.get("executed", 0)
            errors = entry.get("errors", 0)

            status_icon = "✅" if errors == 0 else "❌"
            st.markdown(
                f"{status_icon} `{ts}` · cycle `{cid}` · "
                f"{tickers_count} tickers · {proposals} proposals · "
                f"{approved} approved · {executed} executed"
            )
    else:
        st.info("No cycles yet. Click 'Start' or run a manual cycle.")


def _render_cycle_report(report: dict):
    st.markdown("---")
    st.markdown("### 📋 Cycle Report")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Tickers", len(report.get("tickers_analyzed", [])))
    with c2:
        st.metric("Proposals", report.get("proposals_generated", 0))
    with c3:
        st.metric("Approved", report.get("proposals_approved", 0))
    with c4:
        st.metric("Executed", report.get("orders_placed", 0))

    steps = report.get("steps", [])
    for step in steps:
        ticker = step.get("ticker", "?")
        proposals = step.get("proposals", [])
        if proposals:
            st.markdown(f"#### {ticker}")
            for p in proposals:
                action = p.get("action", "?")
                confidence = p.get("confidence", 0)
                strategy = p.get("strategy", "?")
                rationale = p.get("rationale", "")

                if "LONG" in action:
                    emoji = "🟢"
                    color = "#00d4aa"
                elif "SHORT" in action:
                    emoji = "🔴"
                    color = "#ff4757"
                else:
                    emoji = "⚪"
                    color = "#94a3b8"

                st.markdown(
                    f"""<div style="display: flex; align-items: center; gap: 12px; padding: 12px; 
                    background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 8px;">
                        <span style="font-size: 20px;">{emoji}</span>
                        <div>
                            <span style="font-weight: 700; color: {color};">{action}</span>
                            <span style="color: var(--text-muted); margin-left: 8px;">{confidence:.0%} · {strategy}</span>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                if rationale:
                    st.caption(f"💡 {rationale[:200]}")

    errors = report.get("errors", [])
    if errors:
        st.warning(f"Errors: {len(errors)}")
        for err in errors:
            st.caption(f"⚠ {err}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2: POSITIONS
# ══════════════════════════════════════════════════════════════════════════════
def _get_tinvest_client(config: dict):
    if "tinvest_client" not in st.session_state:
        from integrations.tinvest import TInvestClient
        tinvest_config = config.get("tinvest", {})
        client = TInvestClient(
            token=tinvest_config.get("token", ""),
            account_id=tinvest_config.get("account_id", ""),
        )
        client.connect()
        st.session_state.tinvest_client = client
    return st.session_state.tinvest_client


def _fetch_current_prices(config: dict, tickers: list[str]) -> dict:
    current_prices = {}
    if not tickers:
        return current_prices

    try:
        client = _get_tinvest_client(config)
        for ticker in tickers:
            try:
                quote = client.get_quote(ticker)
                price = quote.get("last", 0)
                if price > 0:
                    current_prices[ticker] = price
            except Exception as e:
                logger.warning(f"Failed to get price for {ticker}: {e}")
    except Exception as e:
        logger.error(f"T-Invest client error: {e}")
        if "tinvest_client" in st.session_state:
            try:
                st.session_state.tinvest_client.close()
            except Exception:
                pass
            del st.session_state.tinvest_client

    return current_prices


def render_positions_tab(config: dict):
    from tools import virtual_portfolio

    # Header with refresh
    col_header, col_refresh = st.columns([4, 1])
    with col_header:
        st.markdown("""
        <div class="card">
            <div class="card-header">
                <span class="card-title">💼 Portfolio Overview</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_refresh:
        if st.button("🔄 Refresh", width="stretch", key="refresh_prices"):
            if "last_price_update" in st.session_state:
                del st.session_state.last_price_update

    # Price cache
    price_cache_ttl = 300
    now_ts = time.time()
    last_update = st.session_state.get("last_price_update", 0)
    price_age = now_ts - last_update

    need_refresh = price_age > price_cache_ttl
    current_prices = st.session_state.get("current_prices", {})

    if need_refresh:
        positions_raw = virtual_portfolio.get_positions()
        tickers_in_positions = list(set(p["ticker"] for p in positions_raw))

        if tickers_in_positions:
            with st.spinner("Fetching prices..."):
                current_prices = _fetch_current_prices(config, tickers_in_positions)
                st.session_state.current_prices = current_prices
                st.session_state.last_price_update = now_ts

    summary = virtual_portfolio.get_account_summary(current_prices)

    total = summary["total_value"]
    init = summary["initial_capital"]
    total_pnl = summary["total_pnl"]
    pnl_percent = (total_pnl / init * 100) if init else 0

    # Get positions early for commission calculation
    positions = summary["positions"]
    total_commission = sum(p.get("commission", 0) for p in positions)

    # Portfolio metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("💰 Balance", f"{summary['current_balance']:,.2f} ₽")
    with c2:
        st.metric("📊 In Positions", f"{summary['positions_value']:,.2f} ₽")
    with c3:
        st.metric("📈 Total P&L", f"{total_pnl:+,.2f} ₽", delta=f"{pnl_percent:+.2f}%")
    with c4:
        st.metric("🏦 Total Value", f"{total:,.2f} ₽", delta=f"{total - init:+,.2f} ₽")
    with c5:
        st.metric("💸 Commissions", f"-{total_commission:,.2f} ₽")

    # Margin info
    borrowed = summary.get("borrowed", 0)
    if borrowed > 0:
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Debt", f"{borrowed:,.2f} ₽")
        with m2:
            st.metric("Own Capital", f"{summary.get('own_capital', 0):,.2f} ₽")
        with m3:
            margin_level = summary.get("margin_level", 0)
            st.metric("Margin Level", f"{margin_level:,.1f}%")
        with m4:
            st.metric("Leverage", f"{summary.get('leverage_used', 0):.2f}x")

    if not positions:
        st.info("No open positions. Run a trading cycle to open positions.")
        return

    st.markdown("---")
    st.markdown("### 📋 Open Positions")

    # Position cards
    for pos in positions:
        ticker = pos.get("ticker", "?")
        side = pos.get("side", "LONG")
        qty = pos.get("quantity", 0)
        entry = pos.get("entry_price", 0)
        current = pos.get("current_price", entry)
        pnl = pos.get("pnl", 0)
        pnl_pct = pos.get("pnl_percent", 0)
        sl = pos.get("stop_loss", 0)
        tp = pos.get("take_profit", 0)
        strategy = pos.get("strategy", "?")
        opened = pos.get("opened_at", "")[:16]
        commission = pos.get("commission", 0)

        side_class = "long" if side == "LONG" else "short"
        pnl_class = "profit" if pnl >= 0 else "loss"
        pnl_icon = "▲" if pnl >= 0 else "▼"

        # Calculate SL/TP distances
        sl_distance = ""
        tp_distance = ""
        if sl > 0 and current > 0:
            if side == "LONG":
                sl_pct = (current - sl) / current * 100
                sl_distance = f"({sl_pct:.1f}%)"
            else:
                sl_pct = (sl - current) / current * 100
                sl_distance = f"({sl_pct:.1f}%)"
        if tp > 0 and current > 0:
            if side == "LONG":
                tp_pct = (tp - current) / current * 100
                tp_distance = f"({tp_pct:.1f}%)"
            else:
                tp_pct = (current - tp) / current * 100
                tp_distance = f"({tp_pct:.1f}%)"

        st.markdown(f"""
        <div class="position-card {side_class}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span class="position-ticker">{ticker}</span>
                        <span class="position-side {side_class}">{side}</span>
                        <span style="font-size: 12px; color: var(--text-muted);">×{qty}</span>
                    </div>
                    <div style="margin-top: 8px; font-size: 12px; color: var(--text-muted);">
                        {strategy} · opened {opened}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div class="position-pnl {pnl_class}">
                        {pnl_icon} {abs(pnl):,.2f} ₽
                    </div>
                    <div style="font-size: 13px; color: {'#00d4aa' if pnl >= 0 else '#ff4757'};">
                        {pnl_pct:+.2f}%
                    </div>
                </div>
            </div>
            <div class="position-details">
                <div class="position-detail">
                    <div class="position-detail-label">Entry</div>
                    <div class="position-detail-value">{entry:.2f} ₽</div>
                </div>
                <div class="position-detail">
                    <div class="position-detail-label">Current</div>
                    <div class="position-detail-value">{current:.2f} ₽</div>
                </div>
                <div class="position-detail">
                    <div class="position-detail-label">P&L</div>
                    <div class="position-detail-value" style="color: {'#00e6b8' if pnl >= 0 else '#ff5c6c'};">{pnl:+,.2f} ₽</div>
                </div>
                <div class="position-detail">
                    <div class="position-detail-label">Commission</div>
                    <div class="position-detail-value" style="color: #9ca3af;">{commission:,.2f} ₽</div>
                </div>
            </div>
            <div class="sl-tp-container">
                <span class="sl-badge">🔴 SL: {sl:.2f} {sl_distance}</span>
                <span class="tp-badge">🟢 TP: {tp:.2f} {tp_distance}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # P&L Chart
    if any(p.get("pnl", 0) != 0 for p in positions):
        st.markdown("---")
        df = pd.DataFrame(positions)
        fig = go.Figure()
        colors = ["#00d4aa" if x >= 0 else "#ff4757" for x in df["pnl"]]
        fig.add_trace(go.Bar(
            x=df["ticker"],
            y=df["pnl"],
            marker_color=colors,
            marker_line_color=colors,
            marker_line_width=1,
            text=[f"{x:+,.0f}₽" for x in df["pnl"]],
            textposition="outside",
            textfont=dict(size=12, color="#94a3b8"),
        ))
        fig.update_layout(
            template="plotly_dark",
            height=300,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=30, b=0),
            title=dict(text="P&L by Position", font=dict(size=14, color="#94a3b8")),
            xaxis=dict(showgrid=False, color="#64748b"),
            yaxis=dict(showgrid=True, gridcolor="rgba(100,116,139,0.2)", color="#64748b"),
        )
        st.plotly_chart(fig, width="stretch")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3: STATISTICS
# ══════════════════════════════════════════════════════════════════════════════
def render_statistics_tab():
    from tools.memory import get_trade_statistics, get_all_trades, get_equity_history
    stats = get_trade_statistics()

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="card-title">📊 Trading Statistics</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if stats.get("total_trades", 0) == 0:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Trades", 0)
        with c2:
            st.metric("Win Rate", "—")
        with c3:
            st.metric("Profit Factor", "—")
        with c4:
            st.metric("Total P&L", "0 ₽")
        st.info("No trades yet. Statistics will appear after executed trades.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("📊 Total Trades", stats["total_trades"])
    with c2:
        win_rate = stats.get("win_rate", 0)
        st.metric("🎯 Win Rate", f"{win_rate:.1f}%")
    with c3:
        st.metric("💰 Profit Factor", f"{stats.get('profit_factor', 0):.2f}")
    with c4:
        st.metric("📈 Avg P&L", f"{stats.get('avg_pnl', 0):,.2f} ₽")
    with c5:
        total_pnl = stats.get('total_pnl', 0)
        pnl_color = "#00d4aa" if total_pnl >= 0 else "#ff4757"
        st.metric("💎 Total P&L", f"{total_pnl:+,.2f} ₽")

    # Risk metrics row
    c1, c2, c3 = st.columns(3)
    with c1:
        sharpe = stats.get("sharpe_ratio", 0)
        st.metric("📐 Sharpe Ratio", f"{sharpe:.2f}")
    with c2:
        sortino = stats.get("sortino_ratio", 0)
        st.metric("📉 Sortino Ratio", f"{sortino:.2f}")
    with c3:
        max_dd = stats.get("max_drawdown", 0)
        st.metric("⚠️ Max Drawdown", f"{max_dd:.1f}%")

    # ── Risk Dashboard ──
    st.markdown("---")
    st.markdown("### 🛡️ Risk Dashboard")
    risk_cols = st.columns(4)
    with risk_cols[0]:
        total_commission = stats.get("total_commission", 0)
        st.metric("💸 Total Commission", f"-{total_commission:,.2f} ₽")
    with risk_cols[1]:
        total_trades = stats.get("total_trades", 0)
        avg_trade_value = (stats.get("total_pnl", 0) / total_trades) if total_trades > 0 else 0
        st.metric("📊 Avg Trade P&L", f"{avg_trade_value:+,.2f} ₽")
    with risk_cols[2]:
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        win_loss_ratio = (wins / losses) if losses > 0 else float("inf")
        st.metric("⚖️ Win/Loss Ratio", f"{win_loss_ratio:.2f}")
    with risk_cols[3]:
        expectancy = ((stats.get("win_rate", 0) / 100 * stats.get("avg_pnl", 0)) -
                      ((1 - stats.get("win_rate", 0) / 100) * abs(stats.get("avg_pnl", 0))))
        st.metric("🎯 Expectancy", f"{expectancy:+,.2f} ₽")

    # ── Net Exposure ──
    st.markdown("---")
    st.markdown("### 📊 Net Exposure")
    try:
        from tools.virtual_portfolio import get_positions, get_balance
        positions = get_positions()
        balance_info = get_balance()

        if positions:
            long_value = sum(
                p["quantity"] * p["entry_price"]
                for p in positions if p.get("side") == "LONG"
            )
            short_value = sum(
                p["quantity"] * p["entry_price"]
                for p in positions if p.get("side") == "SHORT"
            )
            total_value = balance_info.get("total_value", 100000)
            net_exposure = ((long_value - short_value) / total_value * 100) if total_value > 0 else 0

            exp_cols = st.columns(4)
            with exp_cols[0]:
                st.metric("🟢 Long Exposure", f"{long_value:,.0f} ₽")
            with exp_cols[1]:
                st.metric("🔴 Short Exposure", f"{short_value:,.0f} ₽")
            with exp_cols[2]:
                net_color = "#00d4aa" if net_exposure >= 0 else "#ff4757"
                st.metric("📊 Net Exposure", f"{net_exposure:+.1f}%")
            with exp_cols[3]:
                st.metric("💼 Positions", f"{len(positions)}")

            # Exposure bar
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=["Long", "Short", "Net"],
                y=[long_value, short_value, long_value - short_value],
                marker_color=["#00d4aa", "#ff5c6c", "#4d94ff"],
                text=[f"{long_value:,.0f}₽", f"{short_value:,.0f}₽", f"{long_value - short_value:+,.0f}₽"],
                textposition="outside",
            ))
            fig.update_layout(
                template="plotly_dark",
                height=250,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=30, b=0),
                showlegend=False,
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No open positions — net exposure is 0%")
    except Exception as e:
        st.warning(f"Could not calculate exposure: {e}")

    # ── Trade Journal ──
    st.markdown("---")
    st.markdown("### 📓 Trade Journal")
    trades = get_all_trades()
    if trades:
        # Filter by ticker
        ticker_options = list(set(t.get("ticker", "") for t in trades))
        selected_ticker = st.selectbox(
            "Filter by ticker",
            options=["All"] + sorted(ticker_options),
            key="journal_ticker_filter",
        )

        filtered_trades = trades
        if selected_ticker != "All":
            filtered_trades = [t for t in trades if t.get("ticker") == selected_ticker]

        # Summary stats
        total_trades = len(filtered_trades)
        winning_trades = len([t for t in filtered_trades if (t.get("pnl") or 0) > 0])
        losing_trades = len([t for t in filtered_trades if (t.get("pnl") or 0) < 0])

        journal_cols = st.columns(4)
        with journal_cols[0]:
            st.metric("Total Trades", total_trades)
        with journal_cols[1]:
            st.metric("Winning", winning_trades)
        with journal_cols[2]:
            st.metric("Losing", losing_trades)
        with journal_cols[3]:
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")

        # Trade details table
        display_cols = [c for c in ["ticker", "action", "quantity", "entry_price", "exit_price",
                                     "pnl", "commission", "strategy", "status", "opened_at", "closed_at"]
                       if c in pd.DataFrame(filtered_trades).columns]

        if display_cols:
            st.dataframe(
                pd.DataFrame(filtered_trades)[display_cols],
                width="stretch",
                hide_index=True,
            )
    else:
        st.info("No trades recorded yet.")

    # ── Equity Curve ──
    equity_data = get_equity_history()
    if equity_data:
        st.markdown("---")
        st.markdown("### 📈 Equity Curve")
        df_equity = pd.DataFrame(equity_data)
        if "timestamp" in df_equity.columns and "equity" in df_equity.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_equity["timestamp"],
                y=df_equity["equity"],
                mode="lines+markers",
                name="Equity",
                line=dict(color="#3b82f6", width=2),
                marker=dict(size=4),
                fill="tozeroy",
                fillcolor="rgba(59,130,246,0.1)",
            ))
            initial = stats.get("initial_capital", 100000)
            fig.add_hline(y=initial, line_dash="dash", line_color="#64748b",
                          annotation_text=f"Initial: {initial:,.0f}")
            fig.update_layout(
                template="plotly_dark",
                height=300,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=30, b=0),
                xaxis=dict(showgrid=False, color="#64748b"),
                yaxis=dict(showgrid=True, gridcolor="rgba(100,116,139,0.2)", color="#64748b"),
            )
            st.plotly_chart(fig, width="stretch")

    trades = get_all_trades()
    if trades:
        st.markdown("---")
        st.markdown("### 📜 Trade History")
        df = pd.DataFrame(trades)
        display_cols = [c for c in ["ticker", "action", "quantity", "entry_price", "exit_price",
                                     "pnl", "commission", "strategy", "status", "opened_at", "closed_at"]
                        if c in df.columns]
        st.dataframe(df[display_cols], width="stretch", hide_index=True)

        if "pnl" in df.columns and df["pnl"].notna().any():
            fig = go.Figure()
            colors = ["#00d4aa" if x >= 0 else "#ff4757" for x in df["pnl"].fillna(0)]
            fig.add_trace(go.Scatter(
                x=df["closed_at"],
                y=df["pnl"].cumsum(),
                mode="lines+markers",
                name="Cumulative P&L",
                line=dict(color="#3b82f6", width=2),
                marker=dict(size=6, color=colors),
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#64748b")
            fig.update_layout(
                template="plotly_dark",
                height=300,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=30, b=0),
                title=dict(text="Cumulative P&L", font=dict(size=14, color="#94a3b8")),
                xaxis=dict(showgrid=False, color="#64748b"),
                yaxis=dict(showgrid=True, gridcolor="rgba(100,116,139,0.2)", color="#64748b"),
            )
            st.plotly_chart(fig, width="stretch")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4: LESSONS
# ══════════════════════════════════════════════════════════════════════════════
def render_lessons_tab():
    from tools.memory import get_all_lessons, analyze_loss_pattern

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="card-title">📚 Trading Lessons</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Loss patterns from SQL analysis
    st.markdown("### 🔍 Loss Patterns")
    tickers_to_check = st.multiselect(
        "Select tickers",
        options=["SBER", "GAZP", "LKOH", "GMKN", "YDEX", "VTBR", "ROSN", "NVTK"],
        default=["SBER", "GAZP"],
        key="lessons_tickers",
    )

    if tickers_to_check:
        for ticker in tickers_to_check:
            patterns = analyze_loss_pattern(ticker)
            if patterns:
                with st.expander(f"⚠️ {ticker} — {len(patterns)} pattern(s)", expanded=True):
                    for p in patterns:
                        st.markdown(f"""
                        **Strategy:** {p.get('strategy', 'N/A')} ·
                        **RSI Bucket:** {p.get('rsi_bucket', 'N/A')} ·
                        **Sentiment:** {p.get('sentiment_label', 'N/A')} ·
                        **Volatility:** {p.get('volatility_regime', 'N/A')}
                        """)
                        cols = st.columns(4)
                        cols[0].metric("Trades", p.get('times_observed', 0))
                        cols[1].metric("Losses", p.get('times_lost', 0))
                        cols[2].metric("Win Rate", f"{p.get('win_rate', 0):.1f}%")
                        cols[3].metric("Avg P&L", f"{p.get('avg_pnl', 0):+,.2f} ₽")

    # Manually stored lessons
    st.markdown("---")
    st.markdown("### 💡 Stored Lessons")

    ticker_filter = st.selectbox(
        "Filter by ticker",
        options=["All", "SBER", "GAZP", "LKOH", "GMKN", "YDEX", "VTBR", "ROSN", "NVTK"],
        key="lessons_ticker_filter",
    )

    lessons = get_all_lessons(
        ticker=ticker_filter if ticker_filter != "All" else None
    )

    if lessons:
        for lesson in lessons:
            severity = lesson.get("severity", "info")
            severity_colors = {
                "critical": "#ff5c6c",
                "warning": "#ffb347",
                "info": "#4d94ff",
            }
            color = severity_colors.get(severity, "#9ca3af")

            with st.expander(
                f"[{severity.upper()}] {lesson.get('ticker', '?')} — "
                f"{lesson.get('pattern_description', 'N/A')[:80]}"
            ):
                st.markdown(f"**Strategy:** {lesson.get('strategy', 'N/A')}")
                st.markdown(f"**Times Observed:** {lesson.get('times_observed', 0)}")
                st.markdown(f"**Times Lost:** {lesson.get('times_lost', 0)}")
                st.markdown(f"**Win Rate:** {lesson.get('win_rate', 0):.1f}%")
                st.markdown(f"**Confidence:** {lesson.get('confidence', 0):.2f}")

                try:
                    conditions = json.loads(lesson.get("conditions", "{}"))
                    if conditions:
                        st.markdown("**Conditions:**")
                        st.json(conditions)
                except Exception:
                    pass
    else:
        st.info("No lessons stored yet. Lessons will appear after losing trades are analyzed.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 5: OPTIMIZATION
# ══════════════════════════════════════════════════════════════════════════════
def render_optimization_tab():
    from tools.memory import get_strategy_performance

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="card-title">⚡ Parameter Optimization</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📊 Strategy Performance")

    # Strategy comparison
    strategies = ["momentum", "mean_reversion", "breakout", "trend_following"]
    selected_strategies = st.multiselect(
        "Select strategies to compare",
        options=strategies,
        default=strategies[:2],
        key="opt_strategies",
    )

    tickers = ["SBER", "GAZP", "LKOH", "GMKN", "YDEX", "VTBR", "ROSN", "NVTK"]
    selected_tickers = st.multiselect(
        "Select tickers",
        options=tickers,
        default=tickers[:3],
        key="opt_tickers",
    )

    if selected_strategies and selected_tickers:
        performance_data = []
        for ticker in selected_tickers:
            for strategy in selected_strategies:
                perf = get_strategy_performance(ticker, strategy)
                if perf.get("total_trades", 0) > 0:
                    performance_data.append({
                        "Ticker": ticker,
                        "Strategy": strategy,
                        "Trades": perf.get("total_trades", 0),
                        "Win Rate": f"{perf.get('win_rate', 0):.1f}%",
                        "Avg P&L": f"{perf.get('avg_pnl', 0):+,.2f}",
                        "Total P&L": f"{perf.get('total_pnl', 0):+,.2f}",
                    })

        if performance_data:
            st.dataframe(pd.DataFrame(performance_data), width="stretch", hide_index=True)
        else:
            st.info("No performance data available for selected strategies/tickers.")

    # Current configuration
    st.markdown("---")
    st.markdown("### ⚙️ Current Configuration")

    try:
        import yaml
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Risk Parameters**")
            st.json(config.get("risk", {}))
        with col2:
            st.markdown("**Trading Parameters**")
            trading = config.get("trading", {})
            st.json({
                "max_positions": trading.get("max_positions"),
                "max_position_percent": trading.get("max_position_percent"),
                "max_sector_exposure": trading.get("max_sector_exposure"),
                "max_leverage": trading.get("max_leverage"),
            })
    except Exception as e:
        st.warning(f"Could not load configuration: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 6: LOGS
# ══════════════════════════════════════════════════════════════════════════════
def render_logs_tab():
    from tools.memory import get_agent_logs

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="card-title">📜 Agent Logs</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    agents = ["Supervisor", "NewsIntelligence", "MarketData", "Strategy",
              "Critic", "RiskManager", "PortfolioManager", "Execution", "Memory"]

    col1, col2 = st.columns([1, 3])
    with col1:
        selected_agent = st.selectbox("Agent", ["All"] + agents, key="log_agent")
        limit = st.slider("Records", 10, 200, 50, key="log_limit")

    agent_filter = None if selected_agent == "All" else selected_agent
    logs = get_agent_logs(limit=limit, agent_name=agent_filter)

    with col2:
        if not logs:
            st.info("No logs yet")
            return

        agent_icons = {
            "Supervisor": "🧠", "NewsIntelligence": "📰", "MarketData": "📊",
            "Strategy": "🎯", "Critic": "🔍", "RiskManager": "🛡️",
            "PortfolioManager": "💼", "Execution": "⚡", "Memory": "💾",
        }

        for entry in logs:
            agent = entry.get("agent_name", "?")
            action = entry.get("action", "?")
            ts = entry.get("timestamp", "?")
            icon = agent_icons.get(agent, "🤖")

            with st.expander(f"{icon} {agent} — {action}  `{ts}`"):
                try:
                    inp = json.loads(entry.get("input_data", "{}"))
                    st.markdown("**Input:**")
                    st.json(inp)
                except Exception:
                    st.text(entry.get("input_data", ""))

                try:
                    out = json.loads(entry.get("output_data", "{}"))
                    st.markdown("**Output:**")
                    st.json(out)
                except Exception:
                    st.text(entry.get("output_data", ""))


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 8: SCANNER
# ══════════════════════════════════════════════════════════════════════════════
def render_scanner_tab(config: dict):
    from tools import ticker_scanner, virtual_portfolio
    from integrations.tinvest import TInvestClient

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="card-title">🔍 LLM Ticker Scanner</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    scanner_config = config.get("scanner", {})

    # Scanner settings
    col1, col2, col3 = st.columns(3)
    with col1:
        max_picks = st.number_input(
            "Max Tickers to Select",
            min_value=1, max_value=20,
            value=scanner_config.get("max_picks", 5),
            key="scanner_max_picks",
        )
    with col2:
        min_volume = st.number_input(
            "Min Average Volume",
            min_value=0, max_value=10000000,
            value=scanner_config.get("min_volume", 10000),
            step=10000,
            key="scanner_min_volume",
        )
    with col3:
        use_llm = st.toggle(
            "Use LLM Analysis",
            value=scanner_config.get("use_llm", True),
            key="scanner_use_llm",
        )

    # Sector filter
    available_sectors = ["oil_gas", "finance", "technology", "mining", "energy", "telecom", "pharma", "retail", "other"]
    selected_sectors = st.multiselect(
        "Filter by Sectors",
        options=available_sectors,
        default=scanner_config.get("sectors", available_sectors),
        key="scanner_sectors",
    )

    # Scan button
    if st.button("🔍 Run Scanner", type="primary", width="stretch", key="run_scanner_btn"):
        with st.spinner("Scanning MOEX market..."):
            try:
                # Initialize scanner
                llm_client = get_system()[1]
                tinvest_config = config.get("tinvest", {})
                tinvest_client = TInvestClient(
                    token=tinvest_config.get("token", ""),
                    account_id=tinvest_config.get("account_id", ""),
                )
                tinvest_client.connect()

                ticker_scanner.set_clients(llm_client, tinvest_client, config)

                # Get current positions
                current_positions = virtual_portfolio.get_positions()
                balance_info = virtual_portfolio.get_balance()
                capital = balance_info["current_balance"]

                # Run scan
                scan_result = ticker_scanner.scan_market(
                    max_picks=max_picks,
                    sectors=selected_sectors if selected_sectors else None,
                    min_volume=min_volume,
                    open_positions=current_positions,
                    capital=capital,
                    use_llm=use_llm,
                )

                tinvest_client.close()

                if scan_result.get("error"):
                    st.error(f"Scanner error: {scan_result['error']}")
                else:
                    st.success(f"Scan complete! Selected {len(scan_result.get('selected_tickers', []))} tickers")
                    st.session_state["last_scan"] = scan_result

            except Exception as e:
                st.error(f"Scanner failed: {e}")

    # Display results
    last_scan = st.session_state.get("last_scan") or ticker_scanner.get_latest_scan()

    if last_scan:
        st.markdown("---")
        st.markdown("### 📋 Scan Results")

        # Scan info
        scan_time = last_scan.get("scan_time", "?")
        method = last_scan.get("method", "unknown")
        total_scanned = last_scan.get("total_scanned", 0)
        outlook = last_scan.get("market_outlook", "neutral")

        info_cols = st.columns(4)
        with info_cols[0]:
            st.metric("🕐 Scan Time", scan_time[:16] if scan_time else "?")
        with info_cols[1]:
            st.metric("📊 Method", method.upper())
        with info_cols[2]:
            st.metric("🔍 Scanned", total_scanned)
        with info_cols[3]:
            outlook_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(outlook, "❓")
            st.metric("🔮 Market Outlook", f"{outlook_emoji} {outlook}")

        # Selected tickers
        selected = last_scan.get("selected_tickers", [])
        if selected:
            st.markdown("#### ✅ Selected Tickers")
            for i, ticker_info in enumerate(selected):
                ticker = ticker_info.get("ticker", "?")
                reason = ticker_info.get("reason", "")
                score = ticker_info.get("score", 0)
                sector = ticker_info.get("sector", "unknown")
                risk = ticker_info.get("risk_level", "medium")

                risk_color = {"low": "#00d4aa", "medium": "#ffb347", "high": "#ff5c6c"}.get(risk, "#9ca3af")

                st.markdown(f"""
                <div style="display: flex; align-items: center; gap: 16px; padding: 16px; 
                background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 8px;">
                    <div style="font-size: 24px; font-weight: 700; color: #fff; min-width: 80px;">{ticker}</div>
                    <div style="flex: 1;">
                        <div style="font-size: 13px; color: var(--text-secondary);">{reason}</div>
                        <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
                            Sector: {sector} · Score: {score} · Risk: <span style="color: {risk_color};">{risk}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Add to watchlist button
            if st.button("➕ Add Selected to Watchlist", key="add_to_watchlist"):
                current_watchlist = config.get("watchlist", [])
                new_tickers = [t["ticker"] for t in selected if t["ticker"] not in current_watchlist]
                if new_tickers:
                    # Update config
                    try:
                        import yaml
                        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
                        with open(config_path, "r", encoding="utf-8") as f:
                            full_config = yaml.safe_load(f)
                        full_config["watchlist"] = current_watchlist + new_tickers
                        with open(config_path, "w", encoding="utf-8") as f:
                            yaml.dump(full_config, f, allow_unicode=True, default_flow_style=False)
                        st.success(f"Added {len(new_tickers)} tickers to watchlist: {', '.join(new_tickers)}")
                        st.cache_resource.clear()
                    except Exception as e:
                        st.error(f"Failed to update watchlist: {e}")
                else:
                    st.info("All selected tickers already in watchlist")

        # All candidates
        candidates = last_scan.get("all_candidates", [])
        if candidates:
            st.markdown("---")
            st.markdown("#### 📊 All Candidates (Top 20)")

            df = pd.DataFrame(candidates[:20])
            display_cols = [c for c in ["ticker", "name", "price", "sector", "avg_volume", "volatility", "score"]
                           if c in df.columns]
            if display_cols:
                st.dataframe(df[display_cols], width="stretch", hide_index=True)

        # Scan history
        st.markdown("---")
        st.markdown("#### 📜 Scan History")
        history = ticker_scanner.get_scan_history(limit=5)
        if history:
            for entry in history:
                scan_time = entry.get("scan_time", "?")[:16]
                method = entry.get("method", "?")
                selected_count = entry.get("selected_count", 0)
                tickers = entry.get("selected_tickers", [])
                ticker_list = ", ".join([t.get("ticker", "?") for t in tickers[:5]])

                with st.expander(f"🕐 {scan_time} · {method.upper()} · {selected_count} tickers"):
                    st.markdown(f"**Selected:** {ticker_list}")
                    st.json(entry)
        else:
            st.info("No scan history yet. Run a scan to see results.")
    else:
        st.info("No scan results. Click 'Run Scanner' to analyze MOEX market.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 9: SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
def render_settings_tab(config: dict):
    from tools.config_manager import (
        load_yaml, save_yaml, load_env, save_env,
        validate_config, validate_env, log_change, get_audit_log,
        PARAM_SCHEMA, _deep_get, _deep_set, init_audit_table,
    )

    init_audit_table()

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="card-title">⚙️ System Settings</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Загружаем "сырые" данные (без подстановки env)
    raw_config = load_yaml()
    raw_env = load_env()

    # Собираем изменения: {dotted_key: (old, new)}
    changes: dict[str, tuple] = {}

    tab_trading, tab_risk, tab_schedule, tab_llm, tab_watchlist, tab_sectors, tab_api, tab_audit = st.tabs([
        "💹 Trading", "🛡️ Risk", "⏰ Schedule", "🤖 LLM", "📋 Watchlist", "🏭 Sectors", "🔑 API Keys", "📜 Audit Log",
    ])

    # ── Trading ────────────────────────────────────────────────────────────────
    with tab_trading:
        st.markdown("### 💹 Trading Parameters")

        trading = raw_config.get("trading", {})

        col1, col2 = st.columns(2)
        with col1:
            paper = st.toggle("Paper Trading (виртуальный режим)", value=trading.get("paper_trading", True), key="set_paper")
            allow_shorts = st.toggle("Allow Shorts (шорт-позиции)", value=trading.get("allow_shorts", True), key="set_shorts")
            initial_capital = st.number_input(
                "Initial Capital (₽)", min_value=10000, max_value=1_000_000_000,
                value=int(trading.get("initial_capital", 100000)), step=10000, key="set_capital",
            )
            max_positions = st.number_input(
                "Max Positions", min_value=1, max_value=50,
                value=int(trading.get("max_positions", 10)), key="set_max_pos",
            )
        with col2:
            max_pos_pct = st.number_input(
                "Max Position %", min_value=1.0, max_value=100.0,
                value=float(trading.get("max_position_percent", 20.0)), step=1.0, key="set_max_pos_pct",
            )
            max_sector = st.number_input(
                "Max Sector Exposure %", min_value=5.0, max_value=100.0,
                value=float(trading.get("max_sector_exposure", 40.0)), step=5.0, key="set_max_sector",
            )
            max_short = st.number_input(
                "Max Short Exposure %", min_value=0.0, max_value=100.0,
                value=float(trading.get("max_short_exposure", 20.0)), step=5.0, key="set_max_short",
            )
            max_daily_loss = st.number_input(
                "Max Daily Loss %", min_value=0.1, max_value=20.0,
                value=float(trading.get("max_daily_loss_percent", 2.0)), step=0.5, key="set_daily_loss",
            )

        st.markdown("#### Leverage & Margin")
        lev1, lev2, lev3, lev4 = st.columns(4)
        with lev1:
            max_lev = st.number_input(
                "Max Leverage", min_value=1.0, max_value=10.0,
                value=float(trading.get("max_leverage", 3.0)), step=0.5, key="set_max_lev",
            )
        with lev2:
            def_lev = st.number_input(
                "Default Leverage", min_value=1.0, max_value=10.0,
                value=float(trading.get("default_leverage", 3.0)), step=0.5, key="set_def_lev",
            )
        with lev3:
            margin_call = st.number_input(
                "Margin Call %", min_value=10, max_value=200,
                value=int(trading.get("margin_call_percent", 50)), key="set_margin_call",
            )
        with lev4:
            liquidation = st.number_input(
                "Liquidation %", min_value=5, max_value=150,
                value=int(trading.get("liquidation_percent", 30)), key="set_liquidation",
            )

        st.markdown("#### Profit Target")
        pt1, pt2 = st.columns(2)
        with pt1:
            profit_target = st.number_input(
                "Profit Target % (0 = off)", min_value=0.0, max_value=100.0,
                value=float(trading.get("profit_target_percent", 0.0)), step=1.0, key="set_profit_target",
            )

        if profit_target > 0:
            from tools.profit_locker import get_lock_status
            lock_status = get_lock_status()
            if lock_status.get("is_locked"):
                lock_info = lock_status.get("last_lock", {})
                st.warning(
                    f"🔒 PROFIT LOCK ACTIVE | Equity: {lock_info.get('equity', 0):,.2f} ₽ | "
                    f"Locked at: {lock_info.get('locked_at', '?')}"
                )
            else:
                st.info(f"Profit target: +{profit_target:.0f}% ({100000 * (1 + profit_target / 100):,.0f} ₽ at 100k base)")

        # Сохраняем изменения
        new_trading = {
            "paper_trading": paper,
            "allow_shorts": allow_shorts,
            "initial_capital": initial_capital,
            "max_positions": max_positions,
            "max_position_percent": max_pos_pct,
            "max_sector_exposure": max_sector,
            "max_short_exposure": max_short,
            "max_daily_loss_percent": max_daily_loss,
            "max_leverage": max_lev,
            "default_leverage": def_lev,
            "margin_call_percent": margin_call,
            "liquidation_percent": liquidation,
            "profit_target_percent": profit_target,
            "currency": trading.get("currency", "RUB"),
        }
        for k, v in new_trading.items():
            old = trading.get(k)
            if old != v:
                changes[f"trading.{k}"] = (old, v)
        raw_config["trading"] = new_trading

    # ── Risk ───────────────────────────────────────────────────────────────────
    with tab_risk:
        st.markdown("### 🛡️ Risk Parameters")

        risk = raw_config.get("risk", {})
        col1, col2 = st.columns(2)
        with col1:
            risk_per_trade = st.number_input(
                "Risk per Trade %", min_value=0.1, max_value=10.0,
                value=float(risk.get("default_risk_per_trade", 1.0)), step=0.1, key="set_risk_pct",
            )
            min_rr = st.number_input(
                "Min Risk/Reward Ratio", min_value=0.5, max_value=10.0,
                value=float(risk.get("min_rr_ratio", 1.5)), step=0.1, key="set_min_rr",
            )
        with col2:
            max_corr = st.number_input(
                "Max Correlation", min_value=0.0, max_value=1.0,
                value=float(risk.get("max_correlation", 0.7)), step=0.05, key="set_max_corr",
            )
            short_sl = st.toggle(
                "Short Stop-Loss Required", value=risk.get("short_stop_loss_required", True), key="set_short_sl",
            )

        new_risk = {
            "default_risk_per_trade": risk_per_trade,
            "min_rr_ratio": min_rr,
            "max_correlation": max_corr,
            "short_stop_loss_required": short_sl,
        }
        for k, v in new_risk.items():
            old = risk.get(k)
            if old != v:
                changes[f"risk.{k}"] = (old, v)
        raw_config["risk"] = new_risk

    # ── Schedule ───────────────────────────────────────────────────────────────
    with tab_schedule:
        st.markdown("### ⏰ Schedule Parameters")

        sched = raw_config.get("schedule", {})
        col1, col2 = st.columns(2)
        with col1:
            interval = st.number_input(
                "Cycle Interval (min)", min_value=1, max_value=480,
                value=int(sched.get("cycle_interval_minutes", 15)), key="set_interval",
            )
            cycle_timeout = st.number_input(
                "Cycle Timeout (sec)", min_value=60, max_value=7200,
                value=int(sched.get("cycle_timeout", 600)), step=30, key="set_timeout",
            )
        with col2:
            trading_hours = st.text_input(
                "Trading Hours", value=sched.get("trading_hours", "10:00-18:45"), key="set_hours",
            )
            timezone = st.selectbox(
                "Timezone",
                options=["Europe/Moscow", "UTC", "US/Eastern", "Asia/Tokyo", "Europe/London"],
                index=0, key="set_tz",
            )

        new_sched = {
            "trading_hours": trading_hours,
            "timezone": timezone,
            "cycle_interval_minutes": interval,
            "cycle_timeout": cycle_timeout,
            "pre_market_scan": sched.get("pre_market_scan", "09:00"),
        }
        for k, v in new_sched.items():
            old = sched.get(k)
            if old != v:
                changes[f"schedule.{k}"] = (old, v)
        raw_config["schedule"] = new_sched

    # ── LLM ────────────────────────────────────────────────────────────────────
    with tab_llm:
        st.markdown("### 🤖 LLM Settings (LM Studio)")

        llm = raw_config.get("lmstudio", {})
        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("LM Studio Host", value=llm.get("host", "http://localhost:1234"), key="set_llm_host")
            model = st.text_input("Model Name", value=llm.get("model", "fingpt-mt-llama-3-8b-lora"), key="set_llm_model")
        with col2:
            temperature = st.slider(
                "Temperature", min_value=0.0, max_value=2.0,
                value=float(llm.get("temperature", 0.3)), step=0.05, key="set_temp",
            )

        # Проверка доступности LM Studio
        try:
            import httpx
            resp = httpx.get(f"{host}/v1/models", timeout=3)
            if resp.status_code == 200:
                models_data = resp.json()
                models = [m.get("id", "?") for m in models_data.get("data", [])]
                if models:
                    st.success(f"LM Studio доступен. Модели: {', '.join(models[:5])}")
                else:
                    st.warning("LM Studio доступен, но модели не найдены")
            else:
                st.warning(f"LM Studio вернул статус {resp.status_code}")
        except Exception:
            st.warning("LM Studio недоступен (автономный режим)")

        new_llm = {
            "host": host,
            "model": model,
            "temperature": temperature,
        }
        for k, v in new_llm.items():
            old = llm.get(k)
            if old != v:
                changes[f"lmstudio.{k}"] = (old, v)
        raw_config["lmstudio"] = new_llm

    # ── Watchlist ──────────────────────────────────────────────────────────────
    with tab_watchlist:
        st.markdown("### 📋 Watchlist")

        current_watchlist = raw_config.get("watchlist", [])
        watchlist_str = st.text_area(
            "Tickers (по одному на строку или через запятую)",
            value="\n".join(current_watchlist),
            height=200, key="set_watchlist",
        )

        parsed = []
        for line in watchlist_str.replace(",", "\n").splitlines():
            t = line.strip().upper()
            if t:
                parsed.append(t)

        st.caption(f"Активных тикеров: {len(parsed)}")

        if set(parsed) != set(current_watchlist):
            changes["watchlist"] = (current_watchlist, parsed)
        raw_config["watchlist"] = parsed

    # ── Sectors ────────────────────────────────────────────────────────────────
    with tab_sectors:
        st.markdown("### 🏭 Sector Mapping")

        sectors = raw_config.get("sectors", {})
        new_sectors = {}

        for sector_name, tickers in sectors.items():
            col_name, col_tickers = st.columns([1, 3])
            with col_name:
                new_name = st.text_input("Sector", value=sector_name, key=f"sec_name_{sector_name}")
            with col_tickers:
                new_tickers = st.text_input(
                    "Tickers",
                    value=", ".join(tickers) if isinstance(tickers, list) else str(tickers),
                    key=f"sec_tickers_{sector_name}",
                )
            parsed_t = [t.strip().upper() for t in new_tickers.split(",") if t.strip()]
            new_sectors[new_name] = parsed_t
            if set(parsed_t) != set(tickers if isinstance(tickers, list) else []):
                changes[f"sectors.{sector_name}"] = (tickers, parsed_t)

        # Добавить новый сектор
        st.markdown("---")
        new_sec_name = st.text_input("New Sector Name", key="new_sector_name")
        new_sec_tickers = st.text_input("New Sector Tickers (comma separated)", key="new_sector_tickers")
        if st.button("➕ Add Sector", key="add_sector_btn"):
            if new_sec_name and new_sec_tickers:
                parsed_new = [t.strip().upper() for t in new_sec_tickers.split(",") if t.strip()]
                new_sectors[new_sec_name] = parsed_new
                changes[f"sectors.{new_sec_name}"] = (None, parsed_new)
                st.success(f"Sector '{new_sec_name}' added")
                _safe_rerun()

        raw_config["sectors"] = new_sectors

    # ── API Keys ───────────────────────────────────────────────────────────────
    with tab_api:
        st.markdown("### 🔑 API Keys & Tokens")
        st.info("Токены сохраняются в .env файл. Изменения требуют перезапуска.")

        col1, col2 = st.columns(2)
        with col1:
            tinvest_token = st.text_input(
                "T-Invest Token",
                value=raw_env.get("TINVEST_TOKEN", ""),
                type="password", key="set_token",
            )
            tinvest_account = st.text_input(
                "T-Invest Account ID",
                value=raw_env.get("TINVEST_ACCOUNT_ID", ""),
                type="password", key="set_account",
            )
        with col2:
            tg_token = st.text_input(
                "Telegram Bot Token",
                value=raw_env.get("TELEGRAM_BOT_TOKEN", ""),
                type="password", key="set_tg_token",
            )
            tg_chat = st.text_input(
                "Telegram Chat ID",
                value=raw_env.get("TELEGRAM_CHAT_ID", ""),
                type="password", key="set_tg_chat",
            )

        st.markdown("#### LM Studio (from .env)")
        lm_host_env = st.text_input(
            "LMSTUDIO_HOST",
            value=raw_env.get("LMSTUDIO_HOST", "http://localhost:1234"), key="set_lm_host_env",
        )
        lm_model_env = st.text_input(
            "LMSTUDIO_MODEL",
            value=raw_env.get("LMSTUDIO_MODEL", "default"), key="set_lm_model_env",
        )

        st.markdown("#### Trading (from .env)")
        init_cap_env = st.number_input(
            "INITIAL_CAPITAL", min_value=10000, max_value=1_000_000_000,
            value=int(raw_env.get("INITIAL_CAPITAL", "100000")), step=10000, key="set_cap_env",
        )
        daily_loss_env = st.number_input(
            "MAX_DAILY_LOSS_PERCENT", min_value=0.1, max_value=20.0,
            value=float(raw_env.get("MAX_DAILY_LOSS_PERCENT", "2.0")), step=0.5, key="set_loss_env",
        )
        paper_env = st.toggle(
            "PAPER_TRADING", value=raw_env.get("PAPER_TRADING", "true").lower() == "true", key="set_paper_env",
        )

        new_env = {
            "TINVEST_TOKEN": tinvest_token,
            "TINVEST_ACCOUNT_ID": tinvest_account,
            "LMSTUDIO_HOST": lm_host_env,
            "LMSTUDIO_MODEL": lm_model_env,
            "NEWS_API_KEY": raw_env.get("NEWS_API_KEY", ""),
            "TELEGRAM_BOT_TOKEN": tg_token,
            "TELEGRAM_CHAT_ID": tg_chat,
            "INITIAL_CAPITAL": str(init_cap_env),
            "MAX_DAILY_LOSS_PERCENT": str(daily_loss_env),
            "PAPER_TRADING": str(paper_env).lower(),
        }
        for k, v in new_env.items():
            old = raw_env.get(k, "")
            if old != v:
                changes[f"env.{k}"] = (old, v)

    # ── Save Button ────────────────────────────────────────────────────────────
    st.markdown("---")

    # Валидация
    yaml_errors = validate_config(raw_config)
    env_errors = validate_env(new_env)

    if yaml_errors:
        for err in yaml_errors:
            st.error(f"⚠️ {err}")
    if env_errors:
        for err in env_errors:
            st.error(f"⚠️ {err}")

    save_col1, save_col2, save_col3 = st.columns([2, 1, 1])
    with save_col1:
        if changes:
            st.info(f"📝 {len(changes)} parameter(s) changed")
        else:
            st.success("✅ No changes")

    with save_col2:
        if st.button("💾 Save Settings", type="primary", width="stretch", disabled=bool(yaml_errors or env_errors)):
            try:
                save_yaml(raw_config)
                save_env(new_env)
                for key, (old_val, new_val) in changes.items():
                    section = key.split(".")[0] if "." in key else "env"
                    param = key.split(".")[-1] if "." in key else key
                    log_change(section, param, old_val, new_val)
                st.success(f"✅ Saved {len(changes)} change(s)")
                st.cache_resource.clear()
                time.sleep(0.5)
                _safe_rerun()
            except Exception as e:
                st.error(f"Save error: {e}")

    with save_col3:
        if st.button("🔄 Reload", width="stretch"):
            _safe_rerun()

    # ── Audit Log ──────────────────────────────────────────────────────────────
    with tab_audit:
        st.markdown("### 📜 Configuration Audit Log")

        audit_limit = st.slider("Records", 10, 500, 50, key="audit_limit")
        audit_entries = get_audit_log(limit=audit_limit)

        if audit_entries:
            df_audit = pd.DataFrame(audit_entries)
            display_cols = [c for c in ["timestamp", "section", "param", "old_value", "new_value", "source"]
                           if c in df_audit.columns]
            st.dataframe(df_audit[display_cols], width="stretch", hide_index=True)
        else:
            st.info("No configuration changes recorded yet.")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    try:
        supervisor, llm_client, client, config = get_system()
    except Exception as e:
        st.error(f"Initialization error: {e}")
        st.stop()

    st_autorefresh(interval=300000, key="global_refresh")

    render_header(config)

    tab_cycle, tab_positions, tab_scanner, tab_stats, tab_lessons, tab_opt, tab_logs, tab_settings = st.tabs([
        "🚀 Trading Cycle", "💼 Positions", "🔍 Scanner", "📊 Statistics", "📚 Lessons", "⚡ Optimization", "📜 Logs", "⚙️ Settings",
    ])

    with tab_cycle:
        render_cycle_tab(supervisor, config)
    with tab_positions:
        render_positions_tab(config)
    with tab_scanner:
        render_scanner_tab(config)
    with tab_stats:
        render_statistics_tab()
    with tab_lessons:
        render_lessons_tab()
    with tab_opt:
        render_optimization_tab()
    with tab_logs:
        render_logs_tab()
    with tab_settings:
        render_settings_tab(config)


if __name__ == "__main__":
    main()

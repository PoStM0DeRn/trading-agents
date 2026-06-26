# Runbook — Trading Agents System

## Table of contents

1. [Startup](#1-startup)
2. [Operation](#2-operation)
3. [Monitoring](#3-monitoring)
4. [Troubleshooting](#4-troubleshooting)
5. [Recovery](#5-recovery)
6. [Configuration reference](#6-configuration-reference)
7. [Database](#7-database)
8. [Backup](#8-backup)
9. [Deployment](#9-deployment)

---

## 1. Startup

### Normal start

```bash
# Activate environment
.venv\Scripts\activate

# Run one trading cycle
python main.py

# Start with dashboard + background loop
python main.py --stream --port 8000
```

### What happens on start

1. `load_config()` reads `config/settings.yaml`, resolves `${ENV_VAR}` placeholders
2. `validate_config()` checks required env vars in `.env`
3. `init_system()` in `tools/bootstrap.py`:
   - Creates `LMStudioClient` (pings `/v1/models`)
   - Creates `TInvestClient` (gRPC connect)
   - Injects clients into tool modules (`tools.market_data`, `tools.execution`, etc.)
   - Initializes SQLite at `data/trading_memory.db`
   - Creates all sub-agents (news, market_data, strategy_group, critic, risk, portfolio, execution, memory)
4. Data cleanup: removes records older than `retention_days` (default 90)
5. Sentry init (if `SENTRY_DSN` is set)
6. In live mode: prompts for `CONFIRM LIVE`
7. Either runs one cycle (default) or starts FastAPI + background loop (`--stream`)

### Startup order dependencies

```
main.py
 ├── 1. core/logging_setup.py
 ├── 2. config/settings.yaml
 │    └── config/settings.py (validate)
 ├── 3. config/secrets.py (.env)
 ├── 4. integrations/lmstudio_client.py
 ├── 5. integrations/tinvest.py
 ├── 6. tools/market_data.py (client injection)
 ├── 7. tools/memory.py (DB init)
 ├── 8. agents/supervisor.py (creates all sub-agents)
 └── 9. Run cycle or start stream
```

### Health check on start

The system logs warnings (not fatal) if:
- LM Studio is unreachable → trading cycle skipped
- T-Invest client fails → paper trading only
- Telegram bot token missing → alerts disabled
- Sentry DSN missing → error reporting disabled

---

## 2. Operation

### Modes of operation

| Mode | Command | Behavior |
|------|---------|----------|
| Single cycle | `python main.py` | Runs one cycle for all watchlist tickers, exits |
| Stream mode | `python main.py --stream` | Starts FastAPI dashboard + infinite background loop |
| Single ticker | `python run_single_cycle.py` | Runs one cycle for SBER only |
| Backtest | `python -m backtester` | Historical simulation (no live calls) |
| Dashboard only | `streamlit run ui/dashboard.py` | Streamlit monitoring UI |

### The trading cycle

Each cycle runs the following steps (implemented in `SupervisorAgent.run_trading_cycle`, 510 lines):

```
0. Health check ──→ skip if LLM unavailable
0. Position monitoring ──→ close SL/TP hits, update trailing stops
0. Drawdown check ──→ halt or pause if max drawdown exceeded
0. Bootstrap close ──→ force-close oldest position after N cycles
0. Margin monitoring ──→ liquidate if margin < threshold
0. Profit locker ──→ close all if portfolio hit target %
    │
    ▼
For each ticker in watchlist:
  ├── NewsAgent + MarketDataAgent (parallel, 2 threads)
  ├── StrategyAgentGroup (3 parallel LLMs: trend, contrarian, bearish)
  │     └── Deduplication + max confidence
  │
  └── For each proposal:
        ├── CriticAgent (LLM review + historical performance)
        ├── RiskManagerAgent (position sizing, margin, daily loss)
        ├── PortfolioManagerAgent (sector/short exposure, max positions)
        ├── ExecutionAgent (virtual portfolio or real order)
        ├── MemoryAgent (store trade + market context)
        └── Store equity snapshot
```

### Cycle output

```python
{
    "tickers_analyzed": [...],
    "proposals_generated": 3,
    "proposals_approved": 1,
    "orders_placed": 1,
    "orders_closed": 0,
    "errors": [],
    "steps": [{"ticker": "SBER", "proposals": [...]}]
}
```

### Stopping the system

- **Single cycle mode**: exits automatically after one cycle
- **Stream mode**: `Ctrl+C` to stop the FastAPI server (background loop is daemon thread)
- **Abnormal**: `taskkill /F /PID <pid>` (Windows) or `kill -9 <pid>` (Linux)

---

## 3. Monitoring

### Logs

```
data/trading.log          # Human-readable (colored console + file)
data/trading.jsonl        # JSON-structured logs (for log aggregators)
```

Log format (file): `[timestamp] [level] module: message`

### Metrics (Prometheus)

Available at `http://localhost:8000/metrics` (stream mode only):

| Metric | Type | Description |
|--------|------|-------------|
| `trading_cycles_total` | Counter | Cycles run, labelled by status |
| `orders_total` | Counter | Orders placed, labelled by side/status |
| `llm_request_duration_seconds` | Histogram | LLM call latency |
| `portfolio_value` | Gauge | Current portfolio value (RUB) |
| `drawdown_percent` | Gauge | Current drawdown from peak |
| `errors_total` | Counter | System errors |

### Health endpoint

```
GET http://localhost:8000/health
```

Returns:
```json
{
    "status": "ok",
    "services": {
        "llm": true,
        "broker": true,
        "db": true
    },
    "uptime": "2h 34m",
    "paper_trading": true
}
```

### Dashboard (stream mode)

Open `http://localhost:8000` for the WebSocket dashboard showing:
- Real-time portfolio value
- Open positions
- Recent trades
- Agent activity
- LM Studio status
- System health

### Streamlit dashboard

```bash
streamlit run ui/dashboard.py
```

### Sentry

If `SENTRY_DSN` is configured, errors are automatically captured. Check your Sentry dashboard for:
- Trading cycle failures
- Uncaught exceptions
- Reconciliation mismatches

### Telegram alerts

Configured via `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env`. Alerts sent for:
- System start/stop
- Drawdown limit reached
- Reconciliation mismatches
- Critical errors

---

## 4. Troubleshooting

### Symptom: LM Studio not available

```
[WARNING] LM Studio is not available!
Trading cycle skipped.
```

**Check:**
```bash
curl http://localhost:1234/v1/models
```

**Fix:**
1. Open LM Studio
2. Load a model (e.g., Qwen 3.5-9b)
3. Start the inference server (port 1234 by default)
4. Verify: `curl http://localhost:1234/v1/models` returns JSON

### Symptom: T-Invest connection failed

```
[WARNING] T-Invest connection failed: ...
```

**Check:**
1. Is `TINVEST_TOKEN` set in `.env`?
2. Is the token valid? (tinkoff/invest API sandbox or prod)
3. Is internet available? (gRPC to `invest-public-api.tinkoff.ru:443`)

**Fix:** Update `.env` with a valid token. The system works in paper-trading-only mode even without T-Invest.

### Symptom: JSON parsing error from LLM

```
[ERROR] Failed to parse LLM response: ...
```

This happens when LM Studio returns malformed JSON. The system falls back to HOLD/no-action.

**Check:**
1. Is the model appropriate? (tested with Qwen 3.5-9b)
2. Is the temperature too high? (recommended: 0.3)
3. Check `data/trading.jsonl` for the raw LLM response

**Fix:** Lower `temperature` in `config/settings.yaml` or switch to a more reliable model.

### Symptom: Cycle hangs or times out

```
[ERROR] Trading cycle error: ...
```

**Check:**
1. Is LM Studio overloaded? (check its UI)
2. Is the `cycle_timeout` in config sufficient? (default 600s)
3. Are all external services reachable?

**Fix:**
1. Wait for the current cycle to timeout (600s)
2. Restart with `python main.py`
3. Reduce `max_iterations` or increase `cycle_timeout`

### Symptom: Database locked

```
[ERROR] database is locked
```

SQLite cannot handle concurrent writes. This happens if two processes try to write simultaneously.

**Check:**
1. Is another instance of the system running?
2. Is there a stuck process?

```bash
# Windows
tasklist | findstr python

# Kill all python processes (careful!)
taskkill /F /IM python.exe
```

**Fix:** Ensure only one instance runs at a time. The system uses WAL mode and busy_timeout to minimize this.

### Symptom: No proposals generated

```
Proposals generated: 0
```

**Check:**
1. Are there tickers in the watchlist?
2. Is LM Studio returning valid responses?
3. Do strategy agents have enough market data?

**Common causes:**
- LLM returns HOLD for all strategies (normal if no clear signals)
- Market data agent fails to get quotes (check quote endpoint)
- Strategy circuit breaker blocks all strategies (check logs for "Circuit breaker")

### Symptom: Orders not executing

```
Orders placed: 0  (but proposals_approved > 0)
```

**Check:**
1. Paper trading mode? (virtual portfolio should show the position)
2. Live mode? Check T-Invest account for the order
3. Check `data/trading_memory.db` → `virtual_positions` table

---

## 5. Recovery

### Reset paper trading account

```bash
python reset_account.py
```

This clears all positions, resets balance to 100,000 RUB, and clears trade history.

### Recover from corrupted database

```bash
# 1. Check current state
python check_db.py

# 2. If corrupted, restore from backup
copy data\trading_memory.db.bak data\trading_memory.db

# 3. Or reinitialize
del data\trading_memory.db
# Next run will create it fresh
```

### Roll back a deployment

```bash
git revert HEAD --no-edit
git push
# Redeploy
```

### Force-stop stream mode

```bash
# Find the port process
netstat -ano | findstr :8000
taskkill /F /PID <pid>
```

### Emergency halt (live trading)

1. `Ctrl+C` the running process
2. Check T-Invest account for any open orders
3. Manually close positions via T-Invest app if needed

---

## 6. Configuration reference

### `.env` file

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TINVEST_TOKEN` | For live | — | Tinkoff Investments API token |
| `TINVEST_ACCOUNT_ID` | For live | — | Account ID from T-Invest |
| `LMSTUDIO_HOST` | Yes | `http://localhost:1234` | LM Studio server URL |
| `LMSTUDIO_MODEL` | Yes | `default` | Model name in LM Studio |
| `NEWS_API_KEY` | No | — | News API key (newsapi.org) |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | No | — | Target chat ID for alerts |
| `INITIAL_CAPITAL` | No | `100000` | Starting capital for paper trading |
| `MAX_DAILY_LOSS_PERCENT` | No | `2.0` | Max daily loss before halt |
| `PAPER_TRADING` | No | `true` | `true` = paper, `false` = live |

### Key `settings.yaml` parameters

| Path | Default | Description |
|------|---------|-------------|
| `trading.paper_trading` | `true` | Paper/live mode toggle |
| `trading.initial_capital` | `100000` | Virtual starting capital |
| `trading.max_leverage` | `3.0` | Max leverage allowed |
| `trading.max_position_percent` | `20.0` | Max single position % of capital |
| `trading.max_daily_loss_percent` | `2.0` | Halt trading if daily loss exceeds |
| `trading.max_total_drawdown` | `15.0` | Halt if drawdown from peak exceeds |
| `trading.profit_target_percent` | `1.0` | Close all if portfolio profit exceeds |
| `trading.max_positions` | `10` | Max concurrent open positions |
| `trading.max_sector_exposure` | `40.0` | Max % of portfolio in one sector |
| `trading.max_short_exposure` | `20.0` | Max % of portfolio in shorts |
| `trading.allow_shorts` | `true` | Enable short selling |
| `risk.default_risk_per_trade` | `1.0` | % of capital risked per trade |
| `risk.min_rr_ratio` | `1.5` | Minimum risk/reward ratio |
| `schedule.cycle_interval_minutes` | `15` | Minutes between cycles (stream mode) |
| `schedule.trading_hours` | `10:00-18:45` | MOEX trading session |
| `scanner.enabled` | `true` | Enable LLM market scanner |
| `scanner.max_picks` | `5` | Max tickers from scanner |

---

## 7. Database

### SQLite (`data/trading_memory.db`)

The main database. Created automatically on first run.

**Key tables:**

| Table | Description |
|-------|-------------|
| `trades` | All executed trades |
| `events` | System events (starts, stops, errors) |
| `agent_logs` | Per-agent action logs |
| `trade_contexts` | Market context at trade time |
| `trade_lessons` | LLM-generated loss analysis |
| `virtual_account` | Paper trading account (balance, margin) |
| `virtual_positions` | Open/closed paper positions |
| `equity_snapshots` | Portfolio value over time |
| `config_audit` | Configuration change history |
| `profit_lock` | Take-profit lock state |
| `scheduler_logs` | Scheduler run history |

### Migration (Alembic)

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 8. Backup

### What to back up

| Path | Frequency | Retention |
|------|-----------|-----------|
| `data/trading_memory.db` | Daily | 30 days |
| `data/system_state.json` | Daily | 30 days |
| `.env` | Once | Permanent |
| `config/settings.yaml` | On change | Via git |

### Manual backup

```bash
copy data\trading_memory.db data\trading_memory.db.$(Get-Date -Format yyyyMMdd)
```

### Automated backup (Windows Task Scheduler)

```xml
<task>
  <triggers><daily>09:00</daily></triggers>
  <actions>
    <exec>powershell.exe</exec>
    <args>Copy-Item C:\Trading\data\trading_memory.db C:\Backups\trading_memory.db.$(Get-Date -Format yyyyMMdd)</args>
  </actions>
</task>
```

---

## 9. Deployment

### Prerequisites for production

- Python 3.12
- LM Studio with a loaded model (autostart recommended)
- Sufficient RAM/VRAM for the LLM model
- Stable internet connection (for T-Invest API)

### Windows service (using NSSM)

```bash
nssm install TradingAgents "C:\path\to\.venv\Scripts\python.exe" "C:\path\to\main.py"
nssm set TradingAgents AppStdout "C:\path\to\data\trading.log"
nssm set TradingAgents AppStderr "C:\path\to\data\trading.log"
nssm set TradingAgents Start SERVICE_AUTO_START
nssm start TradingAgents
```

### systemd (Linux)

```ini
[Unit]
Description=Trading Agents
After=network.target

[Service]
Type=simple
User=trading
WorkingDirectory=/opt/trading_agents
ExecStart=/opt/trading_agents/.venv/bin/python main.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Docker

```bash
docker build -t trading-agents .
docker run -d --name trading --restart unless-stopped \
  -v /path/to/data:/app/data \
  -v /path/to/.env:/app/.env \
  trading-agents
```

### Health check automation

Configure your monitoring system to poll `GET /health` every 60 seconds. Alert if:
- Status is not "ok"
- `uptime` exceeds 24h without a trading cycle  
- Any service returns `false` for more than 5 consecutive checks

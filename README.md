# Trading Agents

Multi-agent trading system for MOEX (Moscow Exchange) powered by local LLMs (LM Studio). Agents collaborate to research, critique, risk-manage, and execute trades with both paper-trading and live modes.

## Architecture

```
                 ┌──────────────────────────────────────────────────┐
                 │                  main.py                         │
                 │   load_config → init_system → run_trading_cycle  │
                 └──────────────┬───────────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                                     ▼
    ┌──────────────────┐                ┌─────────────────────┐
    │  Single Cycle     │                │  Stream Mode         │
    │  (default)        │                │  (--stream flag)     │
    │                   │                │  FastAPI + WebSocket  │
    │  python main.py   │                │  + background loop   │
    └──────────────────┘                └─────────────────────┘
```

### Agent pipeline (inside a trading cycle)

```
NewsAgent ──┐
            ├─► StrategyAgentGroup ──► CriticAgent ──► RiskManager ──► PortfolioManager ──► ExecutionAgent
MarketAgent ┘   (3 parallel LLMs)       │                 │                  │                    │
                                           │                 │                  │                    │
                                    reviews proposals   sizes positions    checks exposure     places orders
```

### Package layout

```
├── agents/              # Multi-agent orchestration
│   ├── base_agent.py        ABC with LLM calling + tool dispatch
│   ├── supervisor.py        Orchestrator (1111 lines, runs the full cycle)
│   ├── strategy_agents.py   3 strategies: trend, contrarian, bearish
│   ├── critic.py            LLM-based proposal review
│   ├── risk_manager.py      Position sizing, margin, daily loss
│   ├── portfolio_manager.py Diversification, sector/short exposure
│   ├── news_agent.py        News gathering + LLM analysis
│   ├── market_data_agent.py Technical analysis + microstructure
│   ├── execution_agent.py   Order placement (virtual / real)
│   └── memory_agent.py      Trade persistence + loss analysis
├── backtester/          # Historical backtesting (python -m backtester)
│   ├── engine.py            Main loop
│   ├── mock_agents.py       Simplified agents for backtesting
│   ├── config.py, report.py, slippage.py, historical_data.py
├── config/
│   ├── settings.yaml        All trading parameters
│   ├── settings.py          validate_config() at startup
│   ├── secrets.py           Pydantic BaseSettings from .env
│   └── prompts/*.md         System prompts per agent
├── core/                # Infrastructure
│   ├── orchestrator.py      TradingCycleFSM (state machine)
│   ├── message_bus.py       Typed pub/sub MessageBus
│   ├── database.py          SQLAlchemy engine factory (sync + async)
│   ├── state.py             JSON-persisted system state
│   ├── health.py            LLM / broker / DB health checks
│   ├── reconciliation.py    Local ↔ broker position comparison
│   ├── logging_setup.py     structlog + JSON rotating file
│   └── models/              13 SQLAlchemy ORM models
├── integrations/        # External API wrappers
│   ├── lmstudio_client.py   OpenAI-compatible → LM Studio
│   ├── tinvest.py           Tinkoff Investments gRPC
│   └── moex_scanner.py      MOEX share listing
├── tools/               # Stateless utilities
│   ├── market_data.py       Quotes, technical indicators, ATR, RSI, MACD, Bollinger
│   ├── risk_calculations.py Position sizing (Kelly-like), commission
│   ├── memory.py            SQLite: trades, events, lessons, equity snapshots
│   ├── virtual_portfolio.py Paper trading engine
│   ├── drawdown.py          Max drawdown + circuit breaker
│   ├── profit_locker.py     Portfolio take-profit locking
│   ├── margin_monitor.py    Margin level + liquidation
│   ├── news.py              News search, sentiment, entity detection
│   ├── patterns.py          Candlestick pattern detection (O(n) after fix)
│   ├── microstructure.py    Order book imbalance, volume profile, OBV
│   ├── advanced_analysis.py Ichimoku, Fibonacci, ADX
│   ├── ticker_scanner.py    LLM-driven market scan
│   ├── scheduler.py         Time-based trading schedule
│   ├── validator.py         Ticker, action, side, number validation
│   ├── prompts.py           Prompt loader (cached from config/prompts/*.md)
│   ├── metrics.py           Prometheus counters, gauges, histograms
│   └── service.py           Telegram alerts
├── stream/              # Real-time dashboard
│   ├── server.py            FastAPI + WebSocket
│   ├── broadcaster.py       Aggregates system state → WebSocket clients
│   └── static/              HTML/JS dashboard
├── ui/                  # Streamlit dashboard
│   └── dashboard.py
├── tests/               # Pytest suite (42 tests)
│   ├── conftest.py          Fixtures: MockLLMClient, MockTInvestClient, paper_config
│   └── mocks/               Reusable mock classes
├── adhoc/               # Manual test scripts (moved from root, not in pytest)
├── data/                # Runtime data (gitignored)
│   ├── trading_memory.db    SQLite database
│   └── system_state.json    JSON state file
└── alembic/             # DB migration scripts
```

## Quick start

### Prerequisites

- Python 3.12+
- [LM Studio](https://lmstudio.ai/) running locally with a model loaded (tested with Qwen 3.5-9b)
- T-Invest API token (optional, for live trading)

### Install

```bash
git clone <repo>
cd trading_agents
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install
```

### Configure

```bash
cp .env.example .env
# Edit .env with your settings
```

Minimal `.env`:
```env
LMSTUDIO_HOST=http://localhost:1234
LMSTUDIO_MODEL=qwen/qwen3.5-9b
PAPER_TRADING=true
```

### Run

```bash
# Single trading cycle (SBER)
python run_single_cycle.py

# Full cycle with all watchlist tickers
python main.py

# Start dashboard + background trading
python main.py --stream

# Backtest
python -m backtester --tickers SBER,GAZP --period 1y --interval 1d
```

## Dashboards & Management

Система имеет два интерфейса — WebSocket dashboard для real-time мониторинга и Streamlit dashboard для полного управления.

### WebSocket Dashboard (`http://localhost:8000`)

Запускается через `python main.py --stream`. Real-time мониторинг всех компонентов:

| Раздел | Отображает |
|--------|-----------|
| **Portfolio** | Баланс, P&L, количество позиций, leverage |
| **Agent Pipeline** | Активность агентов в реальном времени, статус каждого шага цикла |
| **LM Studio** | Скорость генерации (tok/s), VRAM, количество запросов/токенов, график скорости |
| **Equity Curve** | График стоимости портфеля (Plotly) |
| **Last Trades** | Последние сделки с деталями |

### Streamlit Dashboard (полное управление системой)

Запускается через `streamlit run ui/dashboard.py`. Даёт полный контроль над всеми аспектами системы:

| Вкладка | Возможности |
|---------|-------------|
| **Cycle** | Запуск trading cycle вручную, настройка авто-расписания, запуск MOEX сканера |
| **Positions** | Просмотр открытых/закрытых позиций, обновление цен |
| **Statistics** | P&L графики, win rate, performance по стратегиям, распределение по секторам |
| **Lessons** | LLM-анализ убыточных сделок, паттерны потерь |
| **Optimization** | Сравнение стратегий по R/R, прибыли, аллокация капитала |
| **Logs** | Детальные логи всех агентов с фильтрацией по агенту и типу действия |
| **Scanner** | MOEX скринер: отбор tickers по ликвидности, секторам, с LLM-анализом |
| **Settings** | Полная конфигурация: капитал, плечо, risk limits, watchlist, scheduler, LLM |

## Configuration

Key sections in `config/settings.yaml`:

| Section | Description |
|---------|-------------|
| `lmstudio` | LLM host, model, temperature |
| `trading` | Capital, leverage, risk limits, drawdown thresholds |
| `risk` | Per-trade risk %, min R/R ratio, correlation limits |
| `schedule` | Cycle interval, trading hours, timezone |
| `sectors` | Ticker → sector mapping |
| `watchlist` | Tickers to scan each cycle |
| `scanner` | LLM market scan settings |

## Testing

```bash
pytest tests/ -v            # 42 tests
pytest tests/ --cov         # With coverage
ruff check agents/ tools/   # Lint
python -m mypy tools/prompts.py  # Type check (selected files)
```

## Key design decisions

- **Local LLM first** — all LLM calls go through LM Studio (OpenAI-compatible API). No cloud dependency.
- **Client injection** — T-Invest client injected into tool modules at startup via `set_client()`, avoiding circular imports and enabling mock injection in tests.
- **Paper trading by default** — all trades go through SQLite-based virtual portfolio unless explicitly configured for live trading.
- **Prompts as files** — each agent's system prompt lives in `config/prompts/*.md`, loaded and cached by `tools/prompts.py`.
- **Ad-hoc scripts in `adhoc/`** — old manual test scripts are preserved but excluded from pytest auto-discovery.

## Live trading

To enable live trading:

1. Set `PAPER_TRADING=false` in `.env`
2. Provide `TINVEST_TOKEN` and `TINVEST_ACCOUNT_ID` in `.env`
3. Run `python main.py` — you will be prompted to type `CONFIRM LIVE`

> ⚠️ The system uses real money when `PAPER_TRADING=false`. Start with paper trading.

## Project stats

| Metric | Value |
|--------|-------|
| Python files | ~75 |
| Functions | ~567 |
| Pytest tests | 42 / 42 pass |
| Ruff | 0 errors |
| Python | 3.12 |

# Trading System Fixes - Summary

## What Was Fixed

### Previous Fixes (from earlier session)
1. Risk Manager position capping
2. News source filtering
3. LM Studio response_format removal
4. Strategy agents MOEX limitations
5. T-Invest API d_long/d_short filter removal
6. T-Invest API sector mapping
7. Qwen 3.5-9b JSON parsing

---

### New Fixes (this session)

#### Tier 1: Critical Bugs

**8. supervisor.py:500 — NameError (CRITICAL)**
- `market_data.get_current_quote(t)` used undefined module `market_data`
- Fixed: Changed to `from tools.market_data import get_current_quote`

**9. market_data_agent.py:136 — Unregistered tool**
- `get_volume_pressure` was called but never registered in `default_tools`
- Fixed: Added `"get_volume_pressure": micro_tools.get_volume_pressure`

**10. strategy_agents.py:155 — RSI key mismatch**
- Used lowercase `"rsi"` but MarketDataAgent stores uppercase `"RSI"`
- Fixed: Changed to `indicators.get("RSI")`

**11. portfolio_manager.py:186 — Always-true condition**
- `if sector:` was always True since `_get_ticker_sector` returns `"unknown"` string
- Fixed: Changed to `if sector and sector != "unknown":`

**12. ticker_scanner.py:203 — Typo "market_outview"**
- Always fell back to `"neutral"`, losing LLM outlook
- Fixed: Changed to `result.get("market_outlook", "neutral")`

**13. bootstrap.py:8 — Wrong PROJECT_ROOT**
- `Path(__file__).parent` resolved to `tools/` dir, not project root
- Fixed: Changed to `Path(__file__).parent.parent`

**14. ticker_scanner.py:40 — Wrong ticker name**
- `"Magnit"` instead of `"MGNT"` (company name vs ticker symbol)
- Fixed: Changed to `"MGNT"`

#### Tier 2: High Impact

**15. execution_agent.py:287-292 — Dead code**
- `get_order_status` was called but result never used
- Fixed: Removed dead call

**16. Unused imports cleaned across 13 files**
- `json` removed from: base_agent, risk_manager, portfolio_manager, supervisor, market_data_agent
- `datetime` removed from: strategy_agents, corporate, correlations, short_specific, market_data, news
- `Optional` removed from: base_agent, risk_calculations, news
- `io` removed from: config_manager
- `numpy` removed from: portfolio_manager

**17. SQLite access consolidated**
- Added `memory.get_raw_conn()` and `memory.get_conn` public aliases
- `virtual_portfolio.py` and `profit_locker.py` now use `memory.get_raw_conn()`
- `service.py` now uses `memory.get_db_path()` instead of hardcoded path
- `check_db.py`, `_dbcheck.py`, `reset_account.py` now use `memory.get_db_path()`

#### Tier 3: Code Quality

**18. datetime.utcnow() replaced (26 occurrences)**
- All replaced with `datetime.now(timezone.utc)` across 12 files
- Added `timezone` import where missing

**19. service.py:78 — Cyrillic К fixed**
- `"OКТП"` contained Cyrillic "К" (U+041A) instead of Latin "K"
- Replaced with `"MCHL"` (correct MOEX ticker)

**20. market_data_agent.py:316-328 — Misleading log**
- Logged `"llm_analyze"` but file never calls LLM
- Removed from tool_calls list, added `get_volume_pressure`

**21. memory.py:557 — Hardcoded LIMIT**
- `get_all_lessons()` ignored its own function signature
- Added `limit` parameter with default 100

**22. _dbcheck.py — Dead code removed**
- File was 3 lines: connect to DB, create cursor, do nothing
- Replaced with deprecation notice

#### Tier 4: Performance

**23. Strategy agents parallelized**
- 3 sequential LLM calls now run in parallel via `ThreadPoolExecutor`
- Expected ~3x speedup for strategy generation

**24. O(n^2) pattern detection fixed**
- Added `_precompute_trends()` for vectorized trend calculation
- `detect_hammer`, `detect_inverted_hammer`, `detect_shooting_star` now O(n)

**25. News + Market Data parallelized**
- Sequential data collection now runs in parallel via `ThreadPoolExecutor`
- Expected ~2x speedup for data collection phase

---

## Files Modified

| File | Changes |
|------|---------|
| `agents/supervisor.py` | Fixed NameError, parallelized data collection, removed unused import, datetime fix |
| `agents/market_data_agent.py` | Registered get_volume_pressure, fixed log, removed unused import, datetime fix |
| `agents/strategy_agents.py` | Fixed RSI key, parallelized LLM calls, removed unused import |
| `agents/portfolio_manager.py` | Fixed sector check, removed unused imports (json, numpy) |
| `agents/execution_agent.py` | Removed dead get_order_status call |
| `agents/critic.py` | datetime fix |
| `agents/news_agent.py` | datetime fix |
| `agents/memory_agent.py` | datetime fix |
| `agents/base_agent.py` | Removed unused Optional import |
| `agents/risk_manager.py` | Removed unused json import |
| `tools/bootstrap.py` | Fixed PROJECT_ROOT path |
| `tools/ticker_scanner.py` | Fixed typo, fixed Magnit->MGNT |
| `tools/memory.py` | Added get_raw_conn(), get_conn, timezone import, get_all_lessons limit param |
| `tools/virtual_portfolio.py` | Use memory.get_raw_conn(), datetime fix |
| `tools/profit_locker.py` | Use memory.get_raw_conn(), datetime fix |
| `tools/service.py` | Use memory.get_db_path(), fixed Cyrillic К, datetime fix |
| `tools/corporate.py` | Removed unused datetime imports |
| `tools/correlations.py` | Removed unused datetime imports |
| `tools/short_specific.py` | Removed unused datetime imports |
| `tools/market_data.py` | Removed unused datetime import |
| `tools/risk_calculations.py` | Removed unused Optional import |
| `tools/config_manager.py` | Removed unused io import |
| `tools/news.py` | Removed unused Optional import |
| `tools/scheduler.py` | datetime fix |
| `tools/patterns.py` | Fixed O(n^2) pattern detection |
| `core/state.py` | datetime fix |
| `core/message_bus.py` | datetime fix |
| `check_db.py` | Use memory.get_db_path() |
| `_dbcheck.py` | Replaced with deprecation notice |
| `reset_account.py` | Use memory.get_db_path(), datetime fix |

---

## How to Run

```bash
# Run single trading cycle
python run_single_cycle.py

# Run all tickers from config
python main.py

# Run integration tests
python integration_test.py
```

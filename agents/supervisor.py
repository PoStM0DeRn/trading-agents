"""Supervisor Agent — оркестратор торгового цикла."""

import concurrent.futures
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from agents.base_agent import BaseAgent
from agents.news_agent import NewsIntelligenceAgent
from agents.market_data_agent import MarketDataAgent
from agents.strategy_agents import StrategyAgentGroup
from agents.critic import CriticAgent
from agents.risk_manager import RiskManagerAgent
from agents.portfolio_manager import PortfolioManagerAgent
from agents.execution_agent import ExecutionAgent
from agents.memory_agent import MemoryAgent
from tools.service import send_alert
from tools.trailing_stop import check_trailing_stops
from tools import ticker_scanner
from core.health import ServiceHealth
from tools.drawdown import check_drawdown
from tools.prompts import load_prompt
from core.reconciliation import reconcile
from tools.metrics import cycles_total, orders_total, drawdown_percent, errors_total, portfolio_value

logger = logging.getLogger(__name__)




@dataclass
class StrategyCircuitBreaker:
    strategy_name: str
    max_consecutive_losses: int = 5
    cooldown_cycles: int = 10
    consecutive_losses: int = 0
    cooldown_until: Optional[datetime] = None

    def is_blocked(self) -> bool:
        """Check if strategy is currently in cooldown.

        Returns:
            bool: True if in cooldown period, False otherwise.

        """
        if self.cooldown_until and datetime.now(timezone.utc) < self.cooldown_until:
            return True
        return False

    def remaining_cooldown(self) -> str:
        """Return remaining cooldown time.

        Returns:
            str: Remaining cooldown as a formatted string, "none" if not set, "expired" if elapsed.

        """
        if not self.cooldown_until:
            return "none"
        remaining = self.cooldown_until - datetime.now(timezone.utc)
        if remaining.total_seconds() <= 0:
            return "expired"
        return f"{remaining.total_seconds() / 60:.0f}min"

    def record_trade(self, pnl: float):
        """Record a trade result and update consecutive losses for the strategy.

        Args:
            pnl: Profit and loss value. Non-negative resets losses, negative increments counter.

        """
        if pnl >= 0:
            self.consecutive_losses = 0
            self.cooldown_until = None
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.cooldown_until = datetime.now(timezone.utc) + timedelta(
                    minutes=self.cooldown_cycles * 15
                )
                return "blocked"
        return "ok"


class SupervisorAgent(BaseAgent):
    """Оркестратор — управляет всем пайплайном."""

    def __init__(self, llm_client: Any, config: Optional[dict] = None, tinvest_client: Any = None):
        """Initialize SupervisorAgent with all sub-agents.

        Args:
            llm_client: The LLM client instance.
            config: Configuration dictionary. Defaults to None.
            tinvest_client: The T-Invest client instance. Defaults to None.

        """
        super().__init__(
            name="Supervisor",
            llm_client=llm_client,
            system_prompt=load_prompt("supervisor"),
        )
        self.config = config or {}
        self.paper_trading = self.config.get("paper_trading", True)
        self._tinvest = tinvest_client

        # Инициализация всех агентов
        self.news_agent = NewsIntelligenceAgent(llm_client)
        self.market_data_agent = MarketDataAgent(llm_client)
        self.strategy_group = StrategyAgentGroup(llm_client)
        self.critic = CriticAgent(llm_client)
        self.risk_manager = RiskManagerAgent(llm_client, config=self.config)
        self.portfolio_manager = PortfolioManagerAgent(
            llm_client, config=self.config, paper_trading=self.paper_trading
        )
        self.execution_agent = ExecutionAgent(
            llm_client, paper_trading=self.paper_trading
        )
        self.memory_agent = MemoryAgent(llm_client)

        self._cycle_count = 0
        self._analyzed_tickers = set()
        self._agent_timeout = 120
        self._last_scan_time = None
        self._scan_results = None
        self._health = ServiceHealth()
        self._circuit_breakers: dict[str, StrategyCircuitBreaker] = {}

    @property
    def health(self) -> ServiceHealth:
        """Return the ServiceHealth instance for external monitoring.

        Returns:
            ServiceHealth: The health monitor instance.

        """
        return self._health

    def _run_with_timeout(self, func, *args, timeout: int = None, **kwargs):
        """Запуск функции с таймаутом."""
        timeout = timeout or self._agent_timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.error(f"Agent step timed out after {timeout}s")
                raise TimeoutError(f"Agent step exceeded {timeout}s timeout")
            except Exception as e:
                logger.error(f"Agent step failed: {e}")
                raise

    def _run_scanner(self) -> list[str]:
        """Запуск LLM-сканера для определения лучших тикеров."""
        from datetime import timezone as tz

        scanner_config = self.config.get("scanner", {})
        refresh_interval = scanner_config.get("refresh_interval_minutes", 60) * 60  # в секунды

        # Проверяем, нужно ли обновлять скан
        now = datetime.now(tz.utc)
        if self._last_scan_time:
            elapsed = (now - self._last_scan_time).total_seconds()
            if elapsed < refresh_interval and self._scan_results:
                logger.info(f"[Scanner] Using cached scan results (age {elapsed/60:.1f}min)")
                cached_tickers = [t["ticker"] for t in self._scan_results.get("selected_tickers", [])]
                if cached_tickers:
                    return cached_tickers

        logger.info("[Scanner] Running LLM ticker scanner...")

        try:
            # Инициализируем сканер с текущим T-Invest клиентом
            from integrations.tinvest import TInvestClient
            tinvest_config = self.config.get("tinvest", {})
            tinvest_client = TInvestClient(
                token=tinvest_config.get("token", ""),
                account_id=tinvest_config.get("account_id", ""),
            )
            tinvest_client.connect()
            ticker_scanner.set_clients(self.llm, tinvest_client, self.config)

            # Получаем текущие позиции
            current_positions = []
            capital = self.config.get("trading", {}).get("initial_capital", 100000)
            if self.paper_trading:
                from tools import virtual_portfolio
                balance_info = virtual_portfolio.get_balance()
                capital = balance_info["current_balance"]
                current_positions = virtual_portfolio.get_positions()

            # Запускаем сканирование
            scan_config = self.config.get("scanner", {})
            scan_result = ticker_scanner.scan_market(
                max_picks=scan_config.get("max_picks", 5),
                sectors=scan_config.get("sectors"),
                min_volume=scan_config.get("min_volume", 10000),
                open_positions=current_positions,
                capital=capital,
                use_llm=scan_config.get("use_llm", True),
            )

            tinvest_client.close()

            if scan_result.get("error"):
                logger.error(f"[Scanner] Error: {scan_result['error']}")
                return []

            # Извлекаем тикеры
            selected = scan_result.get("selected_tickers", [])
            tickers = [t["ticker"] for t in selected]

            logger.info(
                f"[Scanner] Selected {len(tickers)} tickers: {', '.join(tickers)} "
                f"(out of {scan_result.get('total_scanned', 0)} scanned, "
                f"method: {scan_result.get('method', 'unknown')})"
            )

            # Сохраняем результат
            self._last_scan_time = now
            self._scan_results = scan_result

            # Telegram alert о результатах сканера
            if tickers:
                ticker_list = ", ".join(tickers[:5])
                outlook = scan_result.get("market_outlook", "neutral")
                send_alert(
                    f"🔍 LLM SCANNER: {len(tickers)} тикеров выбрано\n"
                    f"Тикеры: {ticker_list}\n"
                    f"Прогноз рынка: {outlook}\n"
                    f"Просканировано: {scan_result.get('total_scanned', 0)} акций",
                    severity="info"
                )

            return tickers

        except Exception as e:
            logger.error(f"[Scanner] Scanner failed: {e}", exc_info=True)
            return []

    def _refresh_balance(self) -> tuple[float, list, float]:
        """Refresh balance from virtual portfolio. Returns (capital, positions, borrowed)."""
        from tools import virtual_portfolio
        info = virtual_portfolio.get_balance()
        capital = info["current_balance"]
        borrowed = info.get("borrowed", 0)
        positions = virtual_portfolio.get_positions()
        return capital, positions, borrowed

    def run_trading_cycle(self, tickers: list[str] = None, max_iterations: int = 3) -> dict:
        """Запуск полного торгового цикла.

        Возвращает итоговый отчёт.
        """
        self._cycle_count += 1
        self._analyzed_tickers.clear()
        cycle_id = str(uuid.uuid4())
        logger.info(f"=== Starting trading cycle #{self._cycle_count} ({cycle_id}) ===")

        health_results = self._health.check_all(
            llm_client=self.llm_client,
            tinvest_client=getattr(self, '_tinvest', None),
        )
        skip_reason = self._health.should_skip_cycle()
        if skip_reason:
            logger.warning(f"Skipping cycle: {skip_reason}")
            send_alert(f"Cycle skipped: {skip_reason}", severity="warning")
            return {
                "cycle_id": cycle_id,
                "cycle_number": self._cycle_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tickers_analyzed": [],
                "proposals_generated": 0,
                "proposals_approved": 0,
                "orders_placed": 0,
                "errors": [f"Skipped: {skip_reason}"],
                "steps": [],
                "skipped_tickers": [],
                "health": health_results,
            }
        can_trade = self._health.can_execute_orders()
        if not can_trade:
            logger.warning("Broker unavailable — limiting to analysis only")

        report = {
            "cycle_id": cycle_id,
            "cycle_number": self._cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tickers_analyzed": [],
            "proposals_generated": 0,
            "proposals_approved": 0,
            "orders_placed": 0,
            "errors": [],
            "steps": [],
            "skipped_tickers": [],
        }

        if not tickers:
            # Проверяем настройки сканера
            scanner_config = self.config.get("scanner", {})
            if scanner_config.get("enabled", False) and scanner_config.get("scan_before_cycle", False):
                # Запускаем сканер для определения тикеров
                tickers = self._run_scanner()
                if not tickers:
                    tickers = self.config.get("watchlist", ["SBER"])
            else:
                tickers = self.config.get("watchlist", ["SBER"])

        # Получаем текущий баланс и позиции
        borrowed = 0
        current_prices = {}
        if self.paper_trading:
            capital, positions, borrowed = self._refresh_balance()
            logger.info(f"Paper trading mode: balance = {capital:.2f} RUB, borrowed = {borrowed:.2f}, positions = {len(positions)}")
        else:
            try:
                from tools.execution import get_account_balance, get_positions
                balance = get_account_balance()
                positions = get_positions()
                capital = balance.get("total", self.config.get("initial_capital", 100000))
            except Exception as e:
                logger.error(f"Failed to get account data: {e}")
                balance = {"total": self.config.get("initial_capital", 100000)}
                positions = []
                capital = self.config.get("initial_capital", 100000)

        report["capital"] = capital
        report["open_positions"] = len(positions)

        # ── Шаг 0: Position Monitor — проверка SL/TP ──
        position_closes = []
        if positions:
            logger.info("Step 0: Position Monitor — checking SL/TP...")
            try:
                from tools.position_monitor import check_positions_for_close, execute_closes

                # Получаем текущие цены для позиций
                tickers_in_positions = list(set(p["ticker"] for p in positions))
                current_prices = {}
                for t in tickers_in_positions:
                    try:
                        from tools.market_data import get_current_quote
                        q = get_current_quote(t)
                        price = q.get("last", q.get("price", 0))
                        if price > 0:
                            current_prices[t] = price
                    except Exception as e:
                        logger.warning(f"Failed to get price for {t}: {e}")

                # Проверяем SL/TP
                to_close = check_positions_for_close(current_prices)
                if to_close:
                    logger.info(f"[Monitor] {len(to_close)} position(s) triggered SL/TP")
                    close_results = execute_closes(to_close)
                    position_closes = close_results

                    # Telegram alerts: закрытие позиций по SL/TP
                    for close in close_results:
                        pnl_val = close.get("pnl", 0)
                        reason = close.get("reason", "unknown")
                        send_alert(
                            f"ЗАКРЫТИЕ (SL/TP): {close['ticker']} {close['side']}\n"
                            f"P&L: {pnl_val:+.2f}\n"
                            f"Причина: {reason}",
                            severity="info" if pnl_val >= 0 else "warning"
                        )

                    # Сохранение событий о закрытии позиций
                    if self.paper_trading:
                        try:
                            from tools.memory import store_event
                            for close in close_results:
                                pnl_val = close.get("pnl", 0)
                                store_event({
                                    "event_type": close["reason"],
                                    "ticker": close["ticker"],
                                    "description": f"{close['side']} {close['quantity']} {close['ticker']} closed by {close['reason']}: P&L={pnl_val:+.2f}",
                                    "impact_score": abs(pnl_val) / 1000,
                                    "sentiment": "negative" if pnl_val < 0 else "positive",
                                    "source": "position_monitor",
                                })
                        except Exception as e:
                            logger.error(f"Failed to store close events: {e}")
                    # Обновляем баланс после закрытий
                    if self.paper_trading:
                        capital, positions, _ = self._refresh_balance()
                        logger.info(f"[Monitor] After closes: balance={capital:.2f}, positions={len(positions)}")
                else:
                    logger.info("[Monitor] No SL/TP triggers")

                # Trailing Stop: обновление стопов
                if positions:
                    try:
                        trailing_updates = check_trailing_stops(positions, current_prices, self.config)
                        if trailing_updates:
                            logger.info(f"[Trailing] {len(trailing_updates)} stop(s) updated")
                            from tools.virtual_portfolio import update_stop_loss
                            for update in trailing_updates:
                                trade_id = update.get("trade_id")
                                new_stop = update.get("new_stop")
                                if trade_id and new_stop:
                                    update_stop_loss(trade_id, new_stop)
                                    send_alert(
                                        f"TRAILING STOP: {update['ticker']}\n"
                                        f"Стоп: {update['old_stop']:.2f} → {new_stop:.2f}\n"
                                        f"Цена: {update['current_price']:.2f}\n"
                                        f"Закрытая прибыль: {update['locked_profit']:+.2f} ({update['locked_profit_percent']:+.1f}%)",
                                        severity="info"
                                    )
                    except Exception as e:
                        logger.error(f"Trailing stop update failed: {e}")
            except Exception as e:
                logger.error(f"Position monitor failed: {e}")
                report["errors"].append(f"PositionMonitor: {e}")

        report["position_closes"] = len(position_closes)

        # ── Drawdown Check ──
        try:
            current_equity = capital
            if self.paper_trading:
                from tools.virtual_portfolio import get_margin_level
                margin_info = get_margin_level(current_prices)
                current_equity = margin_info.get("own_capital", capital)
            dd_result = check_drawdown(current_equity, self.config)
            drawdown_percent.set(dd_result["drawdown"] / 100)
            if dd_result["action"] == "halt":
                send_alert(
                    f"🚨 MAX DRAWDOWN: {dd_result['drawdown']:.1f}%\n"
                    f"Trading halted — equity dropped from peak",
                    severity="critical"
                )
                report["drawdown"] = dd_result
                report["errors"].append(f"Drawdown halt: {dd_result['drawdown']:.1f}%")
                cycles_total.labels(status="halt").inc()
                return report
            if dd_result["action"] == "pause":
                send_alert(
                    f"⚠️ DRAWDOWN LIMIT: {dd_result['drawdown']:.1f}%\n"
                    f"Pausing new trades until next cycle",
                    severity="warning"
                )
                report["drawdown"] = dd_result
                cycles_total.labels(status="paused").inc()
                logger.info("Drawdown pause — skipping ticker analysis")
                return report
            report["drawdown"] = dd_result
        except Exception as e:
            logger.error(f"Drawdown check failed: {e}")
            errors_total.labels(service="drawdown").inc()

        # ── Шаг 0.3: Bootstrap — закрытие старых позиций для запуска learning loop ──
        MAX_POSITION_AGE_CYCLES = self.config.get("trading", {}).get("max_position_age_cycles", 5)
        if self.paper_trading and self._cycle_count >= MAX_POSITION_AGE_CYCLES:
            try:
                from tools.virtual_portfolio import get_positions, close_position
                from tools.memory import store_event
                remaining = get_positions()
                if remaining:
                    oldest = min(remaining, key=lambda p: p.get("opened_at", ""))
                    opened_at = oldest.get("opened_at", "")
                    if opened_at:
                        from datetime import datetime as _dt
                        try:
                            opened_dt = _dt.fromisoformat(opened_at)
                            age_seconds = (_dt.utcnow() - opened_dt).total_seconds()
                            age_cycles = int(age_seconds / 60)  # approx cycles
                        except Exception:
                            age_cycles = MAX_POSITION_AGE_CYCLES

                        if age_cycles >= MAX_POSITION_AGE_CYCLES:
                            trade_id = oldest["trade_id"]
                            ticker = oldest["ticker"]
                            side = oldest["side"]
                            qty = oldest["quantity"]
                            entry = oldest["entry_price"]
                            logger.info(
                                f"[Bootstrap] Force-closing oldest position: {side} {qty} {ticker} "
                                f"(age ~{age_cycles} cycles, entry={entry:.2f})"
                            )
                            # Получаем текущую цену для закрытия
                            close_price = entry  # fallback
                            try:
                                from tools.market_data import get_current_quote
                                q = get_current_quote(ticker)
                                close_price = q.get("last", q.get("price", entry))
                            except Exception:
                                pass

                            close_result = close_position(trade_id, close_price)
                            if close_result.get("status") == "closed":
                                pnl = close_result.get("pnl", 0)
                                logger.info(f"[Bootstrap] Closed: P&L={pnl:+.2f}")
                                report["position_closes"] = report.get("position_closes", 0) + 1
                                position_closes.append({
                                    "trade_id": trade_id,
                                    "ticker": ticker,
                                    "side": side,
                                    "quantity": qty,
                                    "entry_price": entry,
                                    "close_price": close_price,
                                    "reason": "bootstrap_timeout",
                                    "pnl": pnl,
                                })
                                # Store event
                                try:
                                    store_event({
                                        "event_type": "bootstrap_timeout",
                                        "ticker": ticker,
                                        "description": f"Bootstrap: {side} {qty} {ticker} force-closed after {age_cycles} cycles: P&L={pnl:+.2f}",
                                        "impact_score": abs(pnl) / 1000,
                                        "sentiment": "negative" if pnl < 0 else "positive",
                                        "source": "bootstrap",
                                    })
                                except Exception:
                                    pass
                                # Update capital
                                capital, positions, _ = self._refresh_balance()
            except Exception as e:
                logger.error(f"Bootstrap close failed: {e}")

        # ── Шаг 0.5: Margin Monitor — проверка маржинального уровня ──
        margin_alert = None
        if self.paper_trading and borrowed > 0:
            logger.info("Step 0.5: Margin Monitor — checking margin level...")
            try:
                from tools.margin_monitor import check_margin_level, execute_liquidation

                margin_status = check_margin_level(current_prices)
                margin_alert = margin_status

                if margin_status["status"] == "liquidation":
                    logger.critical(
                        f"[Margin] LIQUIDATION: severity={margin_status['margin_level']:.1f}% "
                        f"— closing all positions"
                    )
                    # Telegram alert: ликвидация
                    send_alert(
                        f"ЛИКВИДАЦИЯ: Margin severity={margin_status['margin_level']:.1f}%\n"
                        f"Закрытие всех позиций",
                        severity="critical"
                    )
                    liq_result = execute_liquidation(
                        margin_status["positions_to_liquidate"], current_prices
                    )
                    report["margin_liquidation"] = liq_result

                    # Telegram alert: результат ликвидации
                    send_alert(
                        f"Ликвидация завершена\n"
                        f"P&L: {liq_result['total_pnl']:+.2f}\n"
                        f"Позиций закрыто: {liq_result['positions_closed']}",
                        severity="warning" if liq_result['total_pnl'] < 0 else "info"
                    )

                    # Обновляем баланс после ликвидации
                    capital, positions, _ = self._refresh_balance()
                    logger.info(
                        f"[Margin] After liquidation: balance={capital:.2f}, "
                        f"positions={len(positions)}, P&L={liq_result['total_pnl']:.2f}"
                    )
                elif margin_status["status"] == "margin_call":
                    logger.warning(
                        f"[Margin] MARGIN CALL: severity={margin_status['margin_level']:.1f}% "
                        f"— reducing worst position"
                    )
                    # Telegram alert: margin call
                    send_alert(
                        f"MARGIN CALL: Margin severity={margin_status['margin_level']:.1f}%\n"
                        f"Сокращение худшей позиции",
                        severity="critical"
                    )
                    liq_result = execute_liquidation(
                        margin_status["positions_to_liquidate"], current_prices
                    )
                    report["margin_call_close"] = liq_result
                    capital, positions, _ = self._refresh_balance()
                else:
                    logger.info(
                        f"[Margin] OK: severity={margin_status['margin_level']:.1f}%, "
                        f"leverage_used={margin_status['leverage_used']:.2f}x"
                    )
            except Exception as e:
                logger.error(f"Margin monitor failed: {e}")
                report["errors"].append(f"MarginMonitor: {e}")

        report["margin_status"] = margin_alert["status"] if margin_alert else "no_borrowed"

        # ── Step 0.7: Profit Locker — Portfolio take-profit ──
        profit_target = self.config.get("trading", {}).get("profit_target_percent", 0)
        if profit_target > 0:
            try:
                from tools.virtual_portfolio import get_margin_level, get_positions as get_vp_positions, close_position as vp_close_position
                from tools.profit_locker import (
                    check_profit_target, record_profit_lock, should_skip_cycle,
                    update_initial_capital,
                )

                # Проверяем паузу после фиксации
                skip_check = should_skip_cycle(self._cycle_count)
                if skip_check["just_expired"]:
                    # Пауза закончилась — обновляем initial_capital до текущего equity
                    new_equity = get_margin_level().get("own_capital", capital)
                    update_initial_capital(new_equity)
                    logger.info(f"[ProfitLocker] Lock expired — new initial_capital = {new_equity:.2f}")
                if skip_check["skip"]:
                    logger.info(f"⏸ {skip_check['reason']} — skipping ticker analysis")
                    report["profit_locked"] = True
                    report["profit_lock_info"] = skip_check.get("lock_info")
                    return report

                # Считаем текущий equity
                vp_positions = get_vp_positions()
                if vp_positions:
                    current_prices_for_lock = {}
                    for p in vp_positions:
                        t = p["ticker"]
                        if t not in current_prices_for_lock:
                            try:
                                from tools.market_data import get_current_quote
                                q = get_current_quote(t)
                                price = q.get("last", q.get("price", 0))
                                if price > 0:
                                    current_prices_for_lock[t] = price
                            except Exception:
                                pass
                    margin_info = get_margin_level(current_prices_for_lock)
                else:
                    margin_info = get_margin_level()

                equity = margin_info.get("own_capital", capital)
                initial_cap = self.config.get("trading", {}).get("initial_capital", 100000)

                result = check_profit_target(equity, initial_cap, profit_target)

                if result["triggered"]:
                    # Закрываем ВСЕ позиции
                    closed_count = 0
                    total_pnl = 0
                    for pos in vp_positions:
                        ticker_price = current_prices_for_lock.get(pos["ticker"], pos["entry_price"])
                        close_result = vp_close_position(pos["trade_id"], ticker_price)
                        if close_result.get("status") == "closed":
                            closed_count += 1
                            total_pnl += close_result.get("pnl", 0)
                            logger.info(
                                f"[ProfitLocker] Closed {pos['side']} {pos['quantity']} {pos['ticker']} "
                                f"@ {ticker_price:.2f} | P&L={close_result.get('pnl', 0):+.2f}"
                            )

                    # Записываем событие фиксации
                    record_profit_lock(
                        equity=equity,
                        initial_capital=initial_cap,
                        target_percent=profit_target,
                        total_pnl=total_pnl,
                        positions_closed=closed_count,
                        unlock_after_cycle=self._cycle_count + 2,
                    )

                    # Обновляем баланс
                    capital, positions, _ = self._refresh_balance()
                    positions = []

                    report["profit_locked"] = True
                    report["profit_lock_pnl"] = total_pnl
                    report["profit_lock_equity"] = equity

                    send_alert(
                        f"💰 ФИКСАЦИЯ ПРИБЫЛИ: +{result['profit_pct']:.1f}%\n"
                        f"Equity: {equity:,.2f} ₽ (цель: {result['target']:,.2f} ₽)\n"
                        f"P&L: {total_pnl:+,.2f} ₽\n"
                        f"Закрыто позиций: {closed_count}",
                        severity="info"
                    )

                    logger.info(
                        f"💰 PROFIT LOCKED: equity={equity:.2f}, "
                        f"target={result['target']:.2f}, pnl={total_pnl:+.2f}, "
                        f"closed={closed_count}"
                    )
                else:
                    report["profit_locked"] = False

            except Exception as e:
                logger.error(f"Profit locker failed: {e}")
                report["errors"].append(f"ProfitLocker: {e}")

        for ticker in tickers:
            if ticker in self._analyzed_tickers:
                logger.info(f"--- Skipping {ticker} (already analyzed) ---")
                report["skipped_tickers"].append(ticker)
                continue
            logger.info(f"--- Analyzing {ticker} ---")
            ticker_report = self._analyze_ticker(ticker, capital, positions)
            self._analyzed_tickers.add(ticker)
            report["tickers_analyzed"].append(ticker)
            report["proposals_generated"] += len(ticker_report.get("proposals", []))
            report["proposals_approved"] += ticker_report.get("approved", 0)
            report["orders_placed"] += ticker_report.get("executed", 0)
            report["steps"].append(ticker_report)

        # Анализ убытков от предыдущих циклов
        loss_analysis = self._trigger_loss_analysis()
        report["loss_analysis"] = loss_analysis

        # Сохранение снимка equity для построения кривой капитала
        if self.paper_trading:
            try:
                from tools.memory import store_equity_snapshot
                from tools.virtual_portfolio import get_balance, get_positions as get_vp_positions
                balance_info = get_balance()
                vp_positions = get_vp_positions()
                positions_value = sum(p["quantity"] * p["entry_price"] for p in vp_positions)
                total_value = balance_info["current_balance"] + positions_value
                store_equity_snapshot(
                    total_value=total_value,
                    balance=balance_info["current_balance"],
                    positions_value=positions_value,
                    pnl=total_value - balance_info["initial_capital"],
                    borrowed=balance_info.get("borrowed", 0),
                    positions_count=len(vp_positions),
                    cycle_id=str(self._cycle_count),
                )
            except Exception as e:
                logger.error(f"Failed to store equity snapshot: {e}")

        logger.info(f"=== Cycle #{self._cycle_count} complete ===")
        logger.info(
            f"  Proposals: {report['proposals_generated']}, "
            f"Approved: {report['proposals_approved']}, "
            f"Executed: {report['orders_placed']}, "
            f"Skipped: {len(report['skipped_tickers'])}, "
            f"Loss lessons: {loss_analysis.get('lessons_stored', 0)}"
        )

        # ── Reconciliation ──
        try:
            if not self.paper_trading:
                rec_result = reconcile(paper_trading=self.paper_trading)
                report["reconciliation"] = rec_result
                if not rec_result.get("ok", True):
                    errors_total.labels(service="reconciliation").inc()
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            report["errors"].append(f"Reconciliation: {e}")
            errors_total.labels(service="reconciliation").inc()

        # ── Metrics ──
        status = "error" if report.get("errors") else "success"
        cycles_total.labels(status=status).inc()
        if report.get("orders_placed", 0) > 0:
            orders_total.labels(side="buy", status="placed").inc(report["orders_placed"])
        portfolio_val = report.get("portfolio_value", 0)
        if portfolio_val:
            portfolio_value.set(portfolio_val)

        return report

    def _analyze_ticker(self, ticker: str, capital: float, positions: list) -> dict:
        """Анализ одного тикера: Data → LLM Strategy → Critic → Risk → Execute.

        Flow:
        1. Collect data (News + Market Data)
        2. Strategy Agent Group generates proposals (3 LLM strategies)
        3. Critic reviews each proposal
        4. Risk Manager calculates position
        5. Portfolio Manager validates
        6. Execution Agent places order
        7. Memory Agent stores result
        """
        result = {
            "ticker": ticker,
            "proposals": [],
            "approved": 0,
            "executed": 0,
            "errors": [],
        }

        # Шаг 1: Сбор данных (параллельно)
        logger.info(f"[{ticker}] Step 1: Collecting data...")
        news_briefing = {"events": [], "overall_sentiment": "neutral"}
        market_snapshot = {"quote": {}, "indicators": {}}

        def _collect_news():
            try:
                return self._run_with_timeout(self.news_agent.process, {"ticker": ticker})
            except (TimeoutError, Exception) as e:
                logger.error(f"News agent failed for {ticker}: {e}")
                result["errors"].append(f"News: {e}")
                return {"events": [], "overall_sentiment": "neutral"}

        def _collect_market():
            try:
                return self._run_with_timeout(self.market_data_agent.process, {"ticker": ticker})
            except (TimeoutError, Exception) as e:
                logger.error(f"Market data agent failed for {ticker}: {e}")
                result["errors"].append(f"MarketData: {e}")
                return {"quote": {}, "indicators": {}}

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            news_future = executor.submit(_collect_news)
            market_future = executor.submit(_collect_market)
            try:
                news_briefing = news_future.result(timeout=self._agent_timeout + 10)
            except (concurrent.futures.TimeoutError, Exception) as e:
                logger.error(f"News collection timed out for {ticker}: {e}")
                result["errors"].append(f"NewsTimeout: {e}")
            try:
                market_snapshot = market_future.result(timeout=self._agent_timeout + 10)
            except (concurrent.futures.TimeoutError, Exception) as e:
                logger.error(f"Market data collection timed out for {ticker}: {e}")
                result["errors"].append(f"MarketDataTimeout: {e}")

        # Шаг 2: LLM стратегии генерируют предложения
        logger.info(f"[{ticker}] Step 2: Strategy agents generating proposals...")
        ticker_positions = [p for p in positions if p.get("ticker") == ticker]
        try:
            proposals = self.strategy_group.process({
                "ticker": ticker,
                "news_briefing": news_briefing,
                "market_snapshot": market_snapshot,
                "current_positions": ticker_positions,
            })
        except Exception as e:
            logger.error(f"Strategy agents failed for {ticker}: {e}")
            proposals = []
            result["errors"].append(f"Strategy: {e}")

        if not proposals:
            logger.info(f"[{ticker}] No proposals generated — HOLD")
            return result

        # Circuit Breaker: фильтруем proposal от заблокированных стратегий
        blocked_strategies = {
            name for name, cb in self._circuit_breakers.items() if cb.is_blocked()
        }
        if blocked_strategies:
            before = len(proposals)
            proposals = [p for p in proposals if p.get("strategy") not in blocked_strategies]
            blocked_count = before - len(proposals)
            if blocked_count:
                logger.info(f"[{ticker}] Circuit breaker blocked {blocked_count} proposal(s) from: {blocked_strategies}")
                result["circuit_breaker_blocked"] = blocked_count
            if not proposals:
                logger.info(f"[{ticker}] All proposals blocked by circuit breaker — HOLD")
                return result

        logger.info(f"[{ticker}] Generated {len(proposals)} proposal(s)")

        # Дедупликация: если несколько стратегий предлагают одно действие —
        # оставляем proposal с максимальным confidence
        seen_actions: dict[str, dict] = {}
        for p in proposals:
            action_key = p.get("action", "HOLD")
            confidence = p.get("confidence", 0)
            if action_key not in seen_actions or confidence > seen_actions[action_key].get("confidence", 0):
                seen_actions[action_key] = p
        deduped = list(seen_actions.values())
        if len(deduped) < len(proposals):
            dropped = len(proposals) - len(deduped)
            logger.info(f"[{ticker}] Deduplication: {dropped} duplicate proposal(s) removed, {len(deduped)} kept")
        proposals = deduped

        # Шаги 3-7: Каждое proposal через Critic → Risk → Portfolio → Execute
        for proposal in proposals:
            action = proposal.get("action", "?")
            confidence = proposal.get("confidence", 0)
            strategy = proposal.get("strategy", "?")
            logger.info(f"[{ticker}] Proposal: {action} (confidence={confidence:.0%}, strategy={strategy})")

            result["proposals"].append(proposal)

            ticker_result = self._process_proposal(
                proposal, ticker, capital, positions, news_briefing, market_snapshot
            )
            if ticker_result.get("approved"):
                result["approved"] += 1
            if ticker_result.get("executed"):
                result["executed"] += 1

        return result

    def _process_proposal(
        self, proposal: dict, ticker: str, capital: float,
        positions: list, news: dict, market: dict
    ) -> dict:
        """Send a single proposal through Critic → Risk Manager → Portfolio → Execute pipeline.

        Args:
            proposal: Trading proposal dict with action, confidence, strategy.
            ticker: The ticker symbol.
            capital: Current available capital.
            positions: List of current open positions.
            news: News briefing data.
            market: Market snapshot data.

        Returns:
            dict: Result with 'approved' and 'executed' boolean flags.

        """
        result = {"approved": False, "executed": False}
        proposal_id = proposal.get("id", str(uuid.uuid4()))

        # Шаг 3: Критик
        logger.info(f"[{ticker}] Step 3: Critic review...")
        try:
            verdict = self.critic.process({
                "proposal": proposal,
                "news_briefing": news,
                "market_snapshot": market,
            })
        except Exception as e:
            logger.error(f"Critic failed: {e}")
            verdict = {"status": "NeedClarification", "warnings": [str(e)]}

        if verdict.get("status") == "Rejected":
            logger.info(f"[{ticker}] Proposal {proposal_id} rejected by Critic")
            return result

        # Шаг 4: Risk Manager
        logger.info(f"[{ticker}] Step 4: Risk calculation...")
        try:
            order = self.risk_manager.process({
                "proposal": proposal,
                "verdict": verdict,
                "capital": capital,
                "current_positions": positions,
            })
        except Exception as e:
            logger.error(f"Risk Manager failed: {e}")
            order = {"status": "rejected", "reason": str(e)}

        if order.get("status") != "approved":
            reason = order.get("reason", "unknown")
            logger.warning(f"[{ticker}] Proposal {proposal_id} rejected by Risk Manager: {reason}")
            return result

        result["approved"] = True

        # Шаг 5: Portfolio Manager
        logger.info(f"[{ticker}] Step 5: Portfolio check...")
        try:
            portfolio_verdict = self.portfolio_manager.process({
                "order": order,
                "current_positions": positions,
                "portfolio_value": capital,
            })
        except Exception as e:
            logger.error(f"Portfolio Manager failed: {e}")
            portfolio_verdict = {"status": "Rejected", "rationale": f"PortfolioManager error: {e}"}

        if portfolio_verdict.get("status") == "Rejected":
            reason = portfolio_verdict.get("rationale", "no reason provided")
            logger.info(f"[{ticker}] Proposal {proposal_id} rejected by Portfolio Manager: {reason}")
            return result

        # Шаг 6: Исполнение
        logger.info(f"[{ticker}] Step 6: Execution...")
        try:
            exec_result = self.execution_agent.process({"order": order})
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            exec_result = {"status": "error", "error": str(e)}

        exec_status = exec_result.get("status", "")
        if exec_status in ("placed", "filled") or exec_status == "closed":
            result["executed"] = True

            # Для закрытия — P&L уже записан в close_position
            if exec_status == "closed":
                pnl = exec_result.get("pnl", 0)
                logger.info(f"[{ticker}] Position closed: P&L={pnl:+.2f}")
                result["close_pnl"] = pnl

                # Circuit Breaker: записываем P&L для стратегии
                strategy_name = proposal.get("strategy", "unknown")
                if strategy_name not in self._circuit_breakers:
                    self._circuit_breakers[strategy_name] = StrategyCircuitBreaker(
                        strategy_name=strategy_name,
                        max_consecutive_losses=self.config.get("trading", {}).get("max_consecutive_losses", 5),
                        cooldown_cycles=self.config.get("trading", {}).get("cb_cooldown_cycles", 10),
                    )
                cb_status = self._circuit_breakers[strategy_name].record_trade(pnl)
                if cb_status == "blocked":
                    logger.warning(f"Circuit breaker blocked strategy '{strategy_name}' after {self._circuit_breakers[strategy_name].consecutive_losses} consecutive losses")
                    send_alert(
                        f"🚫 CIRCUIT BREAKER: Стратегия {strategy_name}\n"
                        f"Заблокирована после {self._circuit_breakers[strategy_name].max_consecutive_losses} убыточных сделок подряд\n"
                        f"Разблокировка через {self._circuit_breakers[strategy_name].remaining_cooldown()}",
                        severity="warning"
                    )

                # Telegram alert: закрытие позиции
                action_name = proposal.get("action", "CLOSE")
                send_alert(
                    f"ЗАКРЫТИЕ: {ticker} {action_name}\n"
                    f"P&L: {pnl:+.2f}\n"
                    f"Стратегия: {proposal.get('strategy', 'unknown')}",
                    severity="info" if pnl >= 0 else "warning"
                )
                return result

            # Telegram alert: открытие позиции
            action_name = proposal.get("action", "OPEN")
            price = order.get("entry_price_limit", 0)
            quantity = order.get("quantity", 0)
            sl = order.get("stop_loss", 0)
            tp = order.get("take_profit", 0)
            send_alert(
                f"ОТКРЫТИЕ: {ticker} {action_name}\n"
                f"Цена: {price}\n"
                f"Количество: {quantity}\n"
                f"SL: {sl}, TP: {tp}\n"
                f"Стратегия: {proposal.get('strategy', 'unknown')}",
                severity="info"
            )

            # Шаг 7: Сохранение в память (для новых позиций)
            memory_trade_id = exec_result.get("trade_id", proposal_id)
            logger.info(f"[{ticker}] Step 7: Storing in memory (trade_id={memory_trade_id})...")
            try:
                self.memory_agent.process({
                    "action": "store_trade",
                    "data": {
                        "trade_id": memory_trade_id,
                        "ticker": ticker,
                        "action": proposal.get("action"),
                        "quantity": order.get("quantity"),
                        "entry_price": order.get("entry_price_limit"),
                        "stop_loss": order.get("stop_loss"),
                        "take_profit": order.get("take_profit"),
                        "strategy": proposal.get("strategy"),
                        "rationale": proposal.get("rationale"),
                        "status": "open",
                    },
                })
            except Exception as e:
                logger.error(f"Memory store failed: {e}")

            # Шаг 8: Сохранение рыночного контекста
            logger.info(f"[{ticker}] Step 8: Storing market context...")
            try:
                self.memory_agent.process({
                    "action": "store_context",
                    "data": {
                        "trade_id": memory_trade_id,
                        "ticker": ticker,
                        "market_snapshot": market,
                        "news_briefing": news,
                    },
                })
            except Exception as e:
                logger.error(f"Context store failed: {e}")

        return result

    def _trigger_loss_analysis(self) -> dict:
        """Анализ убыточных сделок из предыдущих циклов.

        Ищет закрытые сделки с pnl < 0 за последний час, запускает
        SQL-анализ паттернов + LLM root cause analysis.
        """
        result = {"lessons_stored": 0, "analyzed": 0, "errors": []}

        try:
            import sqlite3
            from tools.memory import get_db_path
            conn = sqlite3.connect(get_db_path(), timeout=5)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Берём закрытые убыточные сделки за последний час
            cursor.execute("""
                SELECT trade_id, ticker, strategy FROM trades
                WHERE status = 'closed'
                  AND pnl < 0
                  AND closed_at >= datetime('now', '-1 hour')
            """)
            losing_trades = [dict(row) for row in cursor.fetchall()]
            conn.close()

        except Exception as e:
            logger.error(f"Failed to query losing trades: {e}")
            result["errors"].append(str(e))
            return result

        for trade in losing_trades:
            trade_id = trade.get("trade_id")
            try:
                analysis = self.memory_agent.process({
                    "action": "analyze_loss",
                    "data": {"trade_id": trade_id},
                })
                result["analyzed"] += 1
                if analysis.get("status") == "lesson_stored":
                    result["lessons_stored"] += 1
                    logger.info(
                        f"Loss lesson stored for {trade.get('ticker')}/"
                        f"{trade.get('strategy')}: {analysis.get('severity')}"
                    )
            except Exception as e:
                logger.error(f"Loss analysis failed for {trade_id}: {e}")
                result["errors"].append(f"{trade_id}: {e}")

        return result

    def process(self, input_data: dict) -> dict:
        """Обработка: запуск цикла по запросу."""
        tickers = input_data.get("tickers", None)
        return self.run_trading_cycle(tickers)

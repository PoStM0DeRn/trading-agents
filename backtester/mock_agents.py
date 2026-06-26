import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class BacktestSupervisor:
    """Supervisor wrapper for backtest mode with historical data."""

    def __init__(self, supervisor, all_candles: dict, news_cache: dict = None, config: dict = None):
        self.supervisor = supervisor
        self.all_candles = all_candles
        self.news_cache = news_cache or {}
        self.config = config or {}
        self._trade_log = []

    def run_cycle(
        self, tickers: list[str], bar_index: int,
        current_prices: dict, capital: float, positions: list
    ) -> dict:
        cycle_id = str(uuid.uuid4())[:8]
        self.supervisor._cycle_count += 1
        self.supervisor._analyzed_tickers.clear()

        report = {
            "cycle_id": cycle_id,
            "cycle_number": self.supervisor._cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tickers_analyzed": [],
            "proposals_generated": 0,
            "proposals_approved": 0,
            "orders_placed": 0,
            "errors": [],
            "steps": [],
            "skipped_tickers": [],
        }

        # Position Monitor
        position_closes = []
        if positions:
            try:
                from tools.position_monitor import check_positions_for_close, execute_closes
                tickers_in_pos = list(set(p["ticker"] for p in positions))
                prices_for_monitor = {t: current_prices.get(t, 0) for t in tickers_in_pos if current_prices.get(t, 0) > 0}
                if prices_for_monitor:
                    to_close = check_positions_for_close(prices_for_monitor)
                    if to_close:
                        close_results = execute_closes(to_close)
                        position_closes = close_results
                        for cr in close_results:
                            if cr.get("status") == "closed":
                                self._trade_log.append({
                                    "type": "close",
                                    "ticker": cr.get("ticker"),
                                    "pnl": cr.get("pnl", 0),
                                    "bar_index": bar_index,
                                })
            except Exception as e:
                logger.error(f"Position monitor failed: {e}")

        report["position_closes"] = len(position_closes)

        # Margin Monitor
        borrowed = 0
        if self.supervisor.paper_trading:
            try:
                from tools import virtual_portfolio
                balance_info = virtual_portfolio.get_balance()
                borrowed = balance_info.get("borrowed", 0)
            except Exception:
                pass

        if borrowed > 0:
            try:
                from tools.margin_monitor import check_margin_level, execute_liquidation
                margin_status = check_margin_level(current_prices)
                if margin_status["status"] == "liquidation":
                    liq_result = execute_liquidation(margin_status["positions_to_liquidate"], current_prices)
                    report["margin_liquidation"] = liq_result
                elif margin_status["status"] == "margin_call":
                    liq_result = execute_liquidation(margin_status["positions_to_liquidate"], current_prices)
                    report["margin_call_close"] = liq_result
            except Exception as e:
                logger.error(f"Margin monitor failed: {e}")

        # Per-ticker analysis
        for ticker in tickers:
            if ticker in self.supervisor._analyzed_tickers:
                report["skipped_tickers"].append(ticker)
                continue

            candles = self.all_candles.get(ticker, [])
            if not candles or bar_index >= len(candles):
                continue

            ticker_report = self._analyze_ticker_backtest(
                ticker, bar_index, current_prices, capital, positions
            )
            self.supervisor._analyzed_tickers.add(ticker)
            report["tickers_analyzed"].append(ticker)
            report["proposals_generated"] += len(ticker_report.get("proposals", []))
            report["proposals_approved"] += ticker_report.get("approved", 0)
            report["orders_placed"] += ticker_report.get("executed", 0)
            report["steps"].append(ticker_report)

        return report

    def _analyze_ticker_backtest(
        self, ticker: str, bar_index: int,
        current_prices: dict, capital: float, positions: list
    ) -> dict:
        result = {
            "ticker": ticker,
            "proposals": [],
            "approved": 0,
            "executed": 0,
            "errors": [],
        }

        candles = self.all_candles.get(ticker, [])

        # Patch market_data tools
        self._patch_market_data(ticker, candles, bar_index, current_prices)

        # Patch news tools
        self._patch_news(ticker)

        # Step 1: Data collection
        try:
            news_briefing = self.supervisor.news_agent.process({"ticker": ticker})
        except Exception as e:
            logger.error(f"News agent failed for {ticker}: {e}")
            news_briefing = {"events": [], "overall_sentiment": "neutral"}
            result["errors"].append(f"News: {e}")

        try:
            market_snapshot = self.supervisor.market_data_agent.process({"ticker": ticker})
        except Exception as e:
            logger.error(f"Market data agent failed for {ticker}: {e}")
            market_snapshot = {"quote": {}, "indicators": {}}
            result["errors"].append(f"MarketData: {e}")

        # Step 2: Strategy
        ticker_positions = [p for p in positions if p.get("ticker") == ticker]
        try:
            proposals = self.supervisor.strategy_group.process({
                "ticker": ticker,
                "news_briefing": news_briefing,
                "market_snapshot": market_snapshot,
                "current_positions": ticker_positions,
            })
        except Exception as e:
            logger.error(f"Strategy failed for {ticker}: {e}")
            proposals = []
            result["errors"].append(f"Strategy: {e}")

        if not proposals:
            return result

        # Steps 3-7: Each proposal
        for proposal in proposals:
            action = proposal.get("action", "?")
            confidence = proposal.get("confidence", 0)
            strategy = proposal.get("strategy", "?")
            logger.info(f"[{ticker}] Proposal: {action} (conf={confidence:.0%}, strat={strategy})")

            result["proposals"].append(proposal)
            ticker_result = self._process_proposal_backtest(
                proposal, ticker, capital, positions, news_briefing, market_snapshot
            )
            if ticker_result.get("approved"):
                result["approved"] += 1
            if ticker_result.get("executed"):
                result["executed"] += 1
                self._trade_log.append({
                    "type": "open",
                    "ticker": ticker,
                    "action": action,
                    "strategy": strategy,
                    "confidence": confidence,
                    "bar_index": bar_index,
                })

        return result

    def _process_proposal_backtest(
        self, proposal: dict, ticker: str, capital: float,
        positions: list, news: dict, market: dict
    ) -> dict:
        result = {"approved": False, "executed": False}
        action = proposal.get("action", "?")
        confidence = proposal.get("confidence", 0)

        # Critic
        try:
            verdict = self.supervisor.critic.process({
                "proposal": proposal,
                "news_briefing": news,
                "market_snapshot": market,
            })
        except Exception as e:
            logger.warning(f"[{ticker}] Critic failed: {e}")
            verdict = {"status": "NeedClarification", "warnings": [str(e)]}

        if verdict.get("status") == "Rejected":
            logger.info(f"[{ticker}] REJECTED by Critic: {verdict.get('rationale', '')}")
            return result

        # Risk Manager
        try:
            order = self.supervisor.risk_manager.process({
                "proposal": proposal,
                "verdict": verdict,
                "capital": capital,
                "current_positions": positions,
            })
        except Exception as e:
            logger.warning(f"[{ticker}] Risk Manager failed: {e}")
            order = {"status": "rejected", "reason": str(e)}

        if order.get("status") != "approved":
            reason = order.get("reason", "unknown")
            logger.info(f"[{ticker}] REJECTED by Risk Manager: {reason}")
            return result

        result["approved"] = True

        # Portfolio Manager
        try:
            portfolio_verdict = self.supervisor.portfolio_manager.process({
                "order": order,
                "current_positions": positions,
                "portfolio_value": capital,
            })
        except Exception as e:
            logger.warning(f"[{ticker}] Portfolio Manager failed: {e}")
            portfolio_verdict = {"status": "Rejected", "rationale": str(e)}

        if portfolio_verdict.get("status") == "Rejected":
            logger.info(f"[{ticker}] REJECTED by Portfolio: {portfolio_verdict.get('rationale', '')}")
            return result

        # Execution
        try:
            exec_result = self.supervisor.execution_agent.process({"order": order})
        except Exception as e:
            logger.warning(f"[{ticker}] Execution failed: {e}")
            exec_result = {"status": "error", "error": str(e)}

        exec_status = exec_result.get("status", "")
        if exec_status in ("placed", "filled") or exec_status == "closed":
            result["executed"] = True

            # Apply slippage to execution
            try:
                from backtester.slippage import apply_slippage_to_execution
                slippage_result = apply_slippage_to_execution(
                    entry_price=order.get("entry_price_limit", 0),
                    quantity=order.get("quantity", 0),
                    side=order.get("action", ""),
                    config=self.config,
                )
                if slippage_result["slippage_amount"] > 0:
                    logger.info(
                        f"[{ticker}] Slippage applied: {slippage_result['original_price']:.2f} "
                        f"→ {slippage_result['adjusted_price']:.2f} "
                        f"({slippage_result['slippage_amount']:.2f})"
                    )
                    exec_result["slippage"] = slippage_result
            except Exception as e:
                logger.warning(f"Slippage calculation failed: {e}")

        return result

    def _patch_market_data(self, ticker: str, candles: list, bar_index: int, current_prices: dict):
        import tools.market_data as md

        candle = candles[bar_index] if bar_index < len(candles) else None
        if not candle:
            return

        _original_get_quote = md.get_current_quote
        _original_get_history = md.get_historical_data

        def mock_get_quote(*args, **kwargs):
            t = kwargs.get("ticker", args[0] if args else "")
            if t == ticker:
                return {
                    "ticker": t,
                    "last": candle["close"],
                    "bid": candle["close"] - 0.5,
                    "ask": candle["close"] + 0.5,
                    "spread": 1.0,
                    "timestamp": candle.get("time", ""),
                }
            return _original_get_quote(*args, **kwargs)

        def mock_get_history(*args, **kwargs):
            t = kwargs.get("ticker", args[0] if args else "")
            if t == ticker:
                return candles[:bar_index + 1]
            return _original_get_history(*args, **kwargs)

        md.get_current_quote = mock_get_quote
        md.get_historical_data = mock_get_history
        md._client = None

        # Also patch the agent's tool references
        mda = self.supervisor.market_data_agent
        if "get_current_quote" in mda.tools:
            mda.tools["get_current_quote"] = mock_get_quote
        if "get_historical_data" in mda.tools:
            mda.tools["get_historical_data"] = mock_get_history

    def _patch_news(self, ticker: str):
        import tools.news as news_mod

        cached = self.news_cache.get(ticker, {
            "articles": [
                {"headline": "Рынок стабилен", "summary": "Нейтральные новости для ticker", "source": "cached", "date": "", "ticker": ticker}
            ],
            "overall_sentiment": "neutral",
            "overall_impact": 0.3,
        })

        original_search = news_mod.search_news

        def mock_search(**kwargs):
            t = kwargs.get("ticker", kwargs.get("t", ""))
            if t == ticker:
                return cached.get("articles", [])
            return original_search(**kwargs)

        news_mod.search_news = mock_search

        # Also patch the agent's tool references
        na = self.supervisor.news_agent
        if "search_news" in na.tools:
            na.tools["search_news"] = mock_search
        if "get_news_sentiment" in na.tools:
            na.tools["get_news_sentiment"] = lambda **kw: {"positive": 0.3, "negative": 0.3, "neutral": 0.4, "articles_count": 1}

    def get_trade_log(self) -> list[dict]:
        return self._trade_log

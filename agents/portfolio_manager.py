"""Portfolio Manager — контроль диверсификации и лимитов."""

import logging

from agents.base_agent import BaseAgent
from tools import risk_calculations as risk_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)




class PortfolioManagerAgent(BaseAgent):
    """Агент управления портфелем."""

    def __init__(self, llm_client, config: dict = None, tools: dict = None, paper_trading: bool = True):
        super().__init__(
            name="PortfolioManager",
            llm_client=llm_client,
            system_prompt=load_prompt("portfolio_manager"),
            tools=self._build_tools({
                "calculate_portfolio_risk": risk_tools.calculate_portfolio_risk,
                "get_positions": lambda: self._get_positions(),
            }, tools),
        )
        self.config = config or {}
        self.paper_trading = paper_trading
        trading = self.config.get("trading", {})
        self.max_positions = trading.get("max_positions", 10)
        self.max_position_percent = trading.get("max_position_percent", 15.0)
        self.max_sector_exposure = trading.get("max_sector_exposure", 40.0)
        self.max_short_exposure = trading.get("max_short_exposure", 20.0)

    def _get_positions(self):
        """Получение позиций: виртуальных или реальных."""
        if self.paper_trading:
            try:
                from tools import virtual_portfolio
                return virtual_portfolio.get_positions()
            except Exception as e:
                logger.warning(f"Failed to get virtual positions: {e}")
                return []
        try:
            from tools import market_data as md_tools
            client = md_tools._client
            if client:
                return client.get_positions()
        except Exception as e:
            logger.warning(f"Failed to get positions from T-Invest: {e}")
        return []

    def _get_ticker_sector(self, ticker: str) -> str:
        """Получить сектор тикера из конфигурации."""
        sectors = self.config.get("sectors", {})
        for sector_name, tickers in sectors.items():
            if ticker in tickers:
                return sector_name
        return "unknown"

    def _calc_sector_exposure(self, sector: str, positions: list, portfolio_value: float) -> float:
        """Рассчитать экспозицию по сектору в процентах."""
        sector_tickers = self.config.get("sectors", {}).get(sector, [])
        sector_value = sum(
            abs(p.get("quantity", 0) * p.get("average_price", p.get("entry_price", 0)))
            for p in positions
            if p.get("ticker") in sector_tickers
        )
        return (sector_value / portfolio_value * 100) if portfolio_value > 0 else 0

    def _check_correlation(self, ticker: str, positions: list) -> list:
        """Проверить корреляцию нового тикера с существующими позициями."""
        warnings = []
        self.config.get("risk", {}).get("max_correlation", 0.7)

        if not positions:
            return warnings

        try:

            # Get historical prices for correlation calculation
            tickers_to_check = [p.get("ticker") for p in positions if p.get("ticker") != ticker]
            if not tickers_to_check:
                return warnings

            # Simplified: check if tickers are in same sector (high correlation proxy)
            new_sector = self._get_ticker_sector(ticker)
            for pos in positions:
                pos_ticker = pos.get("ticker")
                pos_sector = self._get_ticker_sector(pos_ticker)

                if new_sector == pos_sector and new_sector != "unknown":
                    warnings.append(
                        f"High correlation risk: {ticker} and {pos_ticker} are both in {new_sector} sector"
                    )

        except Exception as e:
            logger.warning(f"Correlation check failed: {e}")

        return warnings

    def process(self, input_data: dict) -> dict:
        """Обработка: проверка ограничений портфеля.

        input_data: {
            "order": {...},
            "current_positions": [...],
            "portfolio_value": 100000
        }
        """
        order = input_data.get("order", {})
        positions = input_data.get("current_positions", [])
        portfolio_value = input_data.get("portfolio_value", 100000)

        proposal_id = order.get("proposal_id", "")
        action = order.get("action", "")
        ticker = order.get("ticker", "")
        quantity = order.get("quantity", 0)
        entry_price = order.get("entry_price_limit", 0)

        warnings = []
        order_value = quantity * entry_price
        order_percent = (order_value / portfolio_value * 100) if portfolio_value > 0 else 0

        # Проверка количества позиций
        long_count = sum(1 for p in positions if p.get("quantity", 0) > 0)
        short_count = sum(1 for p in positions if p.get("quantity", 0) < 0)

        if action in ("LONG_OPEN",) and long_count >= self.max_positions:
            warnings.append(f"Max long positions ({self.max_positions}) reached")

        if action in ("SHORT_OPEN",) and short_count >= self.max_positions:
            warnings.append(f"Max short positions ({self.max_positions}) reached")

        # Проверка размера позиции
        if order_percent > self.max_position_percent:
            warnings.append(
                f"Position size {order_percent:.1f}% exceeds max {self.max_position_percent}%"
            )

        # Проверка шорт-экспозиции
        if "SHORT" in action:
            current_short_value = sum(
                abs(p.get("quantity", 0) * p.get("average_price", p.get("entry_price", 0)))
                for p in positions if p.get("quantity", 0) < 0
            )
            new_short_value = current_short_value + order_value
            short_percent = (new_short_value / portfolio_value * 100) if portfolio_value > 0 else 0

            if short_percent > self.max_short_exposure:
                warnings.append(
                    f"Short exposure {short_percent:.1f}% exceeds max {self.max_short_exposure}%"
                )

        # Проверка секторальной экспозиции
        sector = self._get_ticker_sector(ticker)
        if sector and sector != "unknown":
            sector_exposure = self._calc_sector_exposure(sector, positions, portfolio_value)
            new_sector_exposure = sector_exposure + order_percent

            if new_sector_exposure > self.max_sector_exposure:
                warnings.append(
                    f"Sector {sector} exposure {new_sector_exposure:.1f}% exceeds max {self.max_sector_exposure}%"
                )

        # Проверка корреляции
        correlation_warnings = self._check_correlation(ticker, positions)
        warnings.extend(correlation_warnings)

        # Проверка дублирования позиции
        existing_tickers = [p.get("ticker") for p in positions]
        if ticker in existing_tickers:
            warnings.append(f"Already have position in {ticker}")

        # Определяем статус
        critical_warnings = [w for w in warnings if "exceeds max" in w or "Max" in w]
        status = "Rejected" if critical_warnings else "Approved"

        result = self._format_message("portfolio_verdict", {
            "proposal_id": proposal_id,
            "ticker": ticker,
            "action": action,
            "status": status,
            "portfolio_metrics": {
                "total_positions": len(positions),
                "long_positions": long_count,
                "short_positions": short_count,
                "order_value": round(order_value, 2),
                "order_percent": round(order_percent, 2),
            },
            "warnings": warnings,
            "rationale": (
                "Approved: within portfolio limits"
                if status == "Approved"
                else f"Rejected: {'; '.join(critical_warnings)}"
            ),
        })

        self.log_action(
            input_data={"proposal_id": proposal_id, "ticker": ticker},
            output_data=result,
            tool_calls=["portfolio_check"],
        )

        return result

"""Execution Agent — исполнение ордеров (реальный или виртуальный)."""

import logging

from typing import Any, Optional

from agents.base_agent import BaseAgent
from tools import execution as exec_tools
from tools import risk_calculations as risk_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)




class ExecutionAgent(BaseAgent):
    """Агент исполнения."""

    def __init__(self, llm_client: Any, tools: Optional[dict] = None, paper_trading: bool = True):
        super().__init__(
            name="Execution",
            llm_client=llm_client,
            system_prompt=load_prompt("execution"),
            tools=self._build_tools({
                "place_order": exec_tools.place_order,
                "cancel_order": exec_tools.cancel_order,
                "get_order_status": exec_tools.get_order_status,
                "calculate_total_commission": risk_tools.calculate_total_commission,
            }, tools),
        )
        self.paper_trading = paper_trading

    def process(self, input_data: dict) -> dict:
        """Обработка: исполнение одобренного ордера.

        input_data: {"order": {...}}
        """
        order = input_data.get("order", {})

        proposal_id = order.get("proposal_id", "")
        ticker = order.get("ticker", "")
        action = order.get("action", "")
        quantity = order.get("quantity", 0)
        entry_price = order.get("entry_price_limit", 0)
        side = order.get("side", "BUY")
        stop_loss = order.get("stop_loss", 0)
        take_profit = order.get("take_profit", 0)
        strategy = order.get("strategy", "")
        rationale = order.get("rationale", "")
        leverage = order.get("leverage", 1.0)

        if ticker:
            try:
                ticker = self._validate_ticker(ticker)
            except ValueError as e:
                return self._format_message("execution_result", {
                    "proposal_id": proposal_id,
                    "status": "rejected",
                    "reason": f"Invalid ticker: {e}",
                })
        if action:
            try:
                action = self._validate_action(action)
                order["action"] = action
            except ValueError:
                pass

        if order.get("status") != "approved":
            return self._format_message("execution_result", {
                "proposal_id": proposal_id,
                "status": "skipped",
                "reason": "Order not approved",
            })

        # ── Закрытие позиции (CLOSE_LONG / CLOSE_SHORT) ──
        if action in ("CLOSE_LONG", "CLOSE_SHORT"):
            closing_trade_id = order.get("closing_trade_id")
            if not closing_trade_id:
                return self._format_message("execution_result", {
                    "proposal_id": proposal_id,
                    "status": "rejected",
                    "reason": "No closing_trade_id",
                })

            if self.paper_trading:
                return self._execute_close_virtual(
                    proposal_id=proposal_id,
                    trade_id=closing_trade_id,
                    ticker=ticker,
                    action=action,
                    close_price=entry_price,
                )
            else:
                return self._execute_close_real(
                    proposal_id=proposal_id,
                    trade_id=closing_trade_id,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    close_price=entry_price,
                    side=side,
                )

        # Финальная проверка комиссии
        commission = 0
        try:
            commission_result = self._call_tool(
                "calculate_total_commission",
                ticker=ticker,
                quantity=quantity,
                price=entry_price,
                side=side,
            )
            commission = commission_result.get("commission_amount", 0)
            logger.info(f"Commission: {commission:.2f} RUB ({commission_result.get('commission_percent', 0):.2f}%)")
        except Exception as e:
            logger.warning(f"Commission check failed: {e}")

        # ВИРТУАЛЬНОЕ ИСПОЛНЕНИЕ
        if self.paper_trading:
            return self._execute_virtual(
                proposal_id=proposal_id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                entry_price=entry_price,
                side=side,
                stop_loss=stop_loss,
                take_profit=take_profit,
                commission=commission,
                strategy=strategy,
                rationale=rationale,
                leverage=leverage,
            )

        # РЕАЛЬНОЕ ИСПОЛНЕНИЕ
        return self._execute_real(
            proposal_id=proposal_id,
            ticker=ticker,
            action=action,
            quantity=quantity,
            entry_price=entry_price,
            side=side,
            commission=commission,
        )

    def _execute_virtual(self, **kwargs: Any) -> dict:
        """Виртуальное исполнение через SQLite."""
        from tools import virtual_portfolio

        result = virtual_portfolio.open_position(
            ticker=kwargs["ticker"],
            side="LONG" if "LONG" in kwargs["action"] else "SHORT",
            quantity=kwargs["quantity"],
            entry_price=kwargs["entry_price"],
            stop_loss=kwargs["stop_loss"],
            take_profit=kwargs["take_profit"],
            commission=kwargs["commission"],
            strategy=kwargs["strategy"],
            rationale=kwargs["rationale"],
            leverage=kwargs.get("leverage", 1.0),
            trade_id=kwargs["proposal_id"],
        )

        exec_result = self._format_message("execution_result", {
            "proposal_id": kwargs["proposal_id"],
            "trade_id": result.get("trade_id"),
            "status": result.get("status", "error"),
            "ticker": kwargs["ticker"],
            "action": kwargs["action"],
            "quantity": kwargs["quantity"],
            "filled_price": kwargs["entry_price"],
            "commission": kwargs["commission"],
            "side": kwargs["side"],
            "paper_trading": True,
        })

        self.log_action(
            input_data={"proposal_id": kwargs["proposal_id"], "ticker": kwargs["ticker"], "mode": "virtual"},
            output_data=exec_result,
            tool_calls=["virtual_portfolio.open_position"],
        )

        return exec_result

    def _execute_close_virtual(self, **kwargs: Any) -> dict:
        """Виртуальное закрытие позиции через SQLite."""
        from tools.virtual_portfolio import close_position

        result = close_position(
            trade_id=kwargs["trade_id"],
            close_price=kwargs["close_price"],
        )

        exec_result = self._format_message("execution_result", {
            "proposal_id": kwargs["proposal_id"],
            "trade_id": kwargs["trade_id"],
            "status": result.get("status", "error"),
            "ticker": kwargs["ticker"],
            "action": kwargs["action"],
            "filled_price": kwargs["close_price"],
            "pnl": result.get("pnl", 0),
            "paper_trading": True,
        })

        self.log_action(
            input_data={"proposal_id": kwargs["proposal_id"], "ticker": kwargs["ticker"], "mode": "virtual_close"},
            output_data=exec_result,
            tool_calls=["virtual_portfolio.close_position"],
        )

        return exec_result

    def _execute_close_real(self, **kwargs: Any) -> dict:
        """Реальное закрытие позиции через T-Invest API."""
        try:
            result = self._call_tool(
                "place_order",
                ticker=kwargs["ticker"],
                quantity=kwargs["quantity"],
                order_type="market",
                side=kwargs["side"],
                paper_trading=False,
            )
        except Exception as e:
            logger.error(f"Close order failed: {e}")
            return self._format_message("execution_result", {
                "proposal_id": kwargs["proposal_id"],
                "status": "error",
                "error": str(e),
            })

        grpc_status = result.get("status", "")
        status_map = {
            "EXECUTION_REPORT_STATUS_NEW": "placed",
            "EXECUTION_REPORT_STATUS_FILL": "filled",
            "EXECUTION_REPORT_STATUS_CANCELLED": "cancelled",
            "EXECUTION_REPORT_STATUS_REJECTED": "rejected",
        }
        exec_status = status_map.get(grpc_status, grpc_status or "placed")

        exec_result = self._format_message("execution_result", {
            "proposal_id": kwargs["proposal_id"],
            "trade_id": kwargs["trade_id"],
            "order_id": result.get("order_id"),
            "status": exec_status,
            "ticker": kwargs["ticker"],
            "action": kwargs["action"],
            "quantity": kwargs["quantity"],
            "filled_price": result.get("filled_price", kwargs["close_price"]),
            "paper_trading": False,
        })

        self.log_action(
            input_data={"proposal_id": kwargs["proposal_id"], "ticker": kwargs["ticker"], "mode": "real_close"},
            output_data=exec_result,
            tool_calls=["place_order"],
        )

        return exec_result

    def _execute_real(self, **kwargs) -> dict:
        """Реальное исполнение через T-Invest API."""
        try:
            result = self._call_tool(
                "place_order",
                ticker=kwargs["ticker"],
                quantity=kwargs["quantity"],
                order_type="limit",
                side=kwargs["side"],
                price_limit=kwargs["entry_price"],
                paper_trading=False,
            )
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return self._format_message("execution_result", {
                "proposal_id": kwargs["proposal_id"],
                "status": "error",
                "error": str(e),
            })

        order_id = result.get("order_id")

        # Маппинг gRPC статусов в понятные имена
        grpc_status = result.get("status", "")
        status_map = {
            "EXECUTION_REPORT_STATUS_NEW": "placed",
            "EXECUTION_REPORT_STATUS_FILL": "filled",
            "EXECUTION_REPORT_STATUS_PARTIALLY_FILLED": "partial",
            "EXECUTION_REPORT_STATUS_CANCELLED": "cancelled",
            "EXECUTION_REPORT_STATUS_REJECTED": "rejected",
        }
        exec_status = status_map.get(grpc_status, grpc_status or "placed")

        exec_result = self._format_message("execution_result", {
            "proposal_id": kwargs["proposal_id"],
            "order_id": order_id,
            "status": exec_status,
            "ticker": kwargs["ticker"],
            "action": kwargs["action"],
            "quantity": kwargs["quantity"],
            "filled_price": result.get("filled_price", kwargs["entry_price"]),
            "commission": kwargs["commission"],
            "side": kwargs["side"],
            "paper_trading": False,
        })

        self.log_action(
            input_data={"proposal_id": kwargs["proposal_id"], "ticker": kwargs["ticker"], "mode": "real"},
            output_data=exec_result,
            tool_calls=["place_order", "get_order_status"],
        )

        return exec_result

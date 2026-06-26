"""Risk Manager — математический расчёт позиций и управление рисками."""

import logging
import uuid

from agents.base_agent import BaseAgent
from tools import risk_calculations as risk_tools
from tools import short_specific as short_tools
from tools import memory as memory_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)




class RiskManagerAgent(BaseAgent):
    """Агент управления рисками."""

    def __init__(self, llm_client, config: dict = None, tools: dict = None):
        super().__init__(
            name="RiskManager",
            llm_client=llm_client,
            system_prompt=load_prompt("risk_manager"),
            tools=self._build_tools({
                "calculate_position_size_long": risk_tools.calculate_position_size_long,
                "calculate_position_size_short": risk_tools.calculate_position_size_short,
                "calculate_position_size_leveraged": risk_tools.calculate_position_size_leveraged,
                "calculate_total_commission": risk_tools.calculate_total_commission,
                "calculate_cycle_commission": risk_tools.calculate_cycle_commission,
                "check_volume_limit": risk_tools.check_volume_limit,
                "check_short_availability": short_tools.check_short_availability,
                "get_borrow_rate": short_tools.get_borrow_rate,
            }, tools),
        )
        self.config = config or {}
        risk = self.config.get("risk", {})
        self.default_risk = risk.get("default_risk_per_trade", 1.0)
        self.min_rr_ratio = risk.get("min_rr_ratio", 1.5)
        trading = self.config.get("trading", {})
        self.max_leverage = trading.get("max_leverage", 3.0)
        self.default_leverage = trading.get("default_leverage", 3.0)
        self.max_position_percent = trading.get("max_position_percent", 15.0)

    def _cap_position_size(self, quantity: int, entry_price: float, capital: float,
                           result_sizes: dict, leverage: float, proposal_id: str,
                           ticker: str, action: str):
        """Cap position size by max_position_percent. Returns rejection dict or None."""
        if entry_price <= 0 or capital <= 0:
            return None
        order_percent = (quantity * entry_price) / capital * 100
        if order_percent <= self.max_position_percent:
            return None
        max_quantity = int(capital * self.max_position_percent / 100 / entry_price)
        if max_quantity < 1:
            return self._format_message("approved_order", {
                "proposal_id": proposal_id, "ticker": ticker, "action": action,
                "status": "rejected",
                "reason": f"Position too small: min size requires >{self.max_position_percent}% of capital",
            })
        logger.info(f"[Risk] Position capped: {quantity} → {max_quantity} shares ({order_percent:.1f}% → {self.max_position_percent}%)")
        result_sizes["quantity"] = max_quantity
        result_sizes["total_cost"] = max_quantity * entry_price
        result_sizes["own_required"] = max_quantity * entry_price / leverage
        result_sizes["borrowed"] = max_quantity * entry_price - result_sizes["own_required"]
        return None

    def process(self, input_data: dict) -> dict:
        """Обработка: расчёт параметров сделки.

        input_data: {
            "proposal": {...},
            "verdict": {...},
            "capital": 100000,
            "current_positions": [...]
        }
        """
        proposal = input_data.get("proposal", {})
        verdict = input_data.get("verdict", {})
        capital = input_data.get("capital", 100000)
        current_positions = input_data.get("current_positions", [])

        proposal_id = proposal.get("id", str(uuid.uuid4()))
        ticker = proposal.get("ticker", "")
        action = proposal.get("action", "HOLD")
        stop_loss = proposal.get("suggested_stop_loss", 0)
        take_profit = proposal.get("suggested_take_profit", 0)

        if ticker:
            try:
                ticker = self._validate_ticker(ticker)
            except ValueError as e:
                return self._format_message("approved_order", {
                    "proposal_id": proposal_id,
                    "ticker": ticker,
                    "action": action,
                    "status": "rejected",
                    "reason": f"Invalid ticker: {e}",
                })

        # Проверяем вердикт критика
        if verdict.get("status") == "Rejected":
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": verdict.get("rationale", "Rejected by Critic"),
            })

        # ── Daily loss limit check ──
        daily_loss_check = self._check_daily_loss_limit()
        if not daily_loss_check["allowed"]:
            logger.warning(f"[Risk] DAILY LOSS LIMIT: {daily_loss_check['reason']}")
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": f"DAILY LOSS LIMIT: {daily_loss_check['reason']}",
            })

        # ── Learning: критические блокировки ──
        strategy = proposal.get("strategy", "")
        try:
            critical = memory_tools.get_critical_blocks(
                ticker=ticker, strategy=strategy
            )
            if critical:
                reason = critical[0].get("pattern_description", "Critical loss pattern")
                win_rate = critical[0].get("win_rate", 0)
                logger.warning(
                    f"[Risk] BLOCKED {ticker}/{strategy}: {reason} "
                    f"(win_rate={win_rate}%)"
                )
                return self._format_message("approved_order", {
                    "proposal_id": proposal_id,
                    "ticker": ticker,
                    "action": action,
                    "status": "rejected",
                    "reason": f"CRITICAL BLOCK: {reason} (historical win rate: {win_rate}%)",
                })
        except Exception as e:
            logger.warning(f"Failed to check critical blocks: {e}")

        # ── Learning: корректировка risk_percent по win_rate ──
        risk_percent = self.config.get("risk", {}).get("default_risk_per_trade", 1.0)
        performance_adjustment = 1.0

        try:
            perf = memory_tools.get_strategy_performance(
                ticker=ticker, strategy=strategy
            )
            total_trades = perf.get("total_trades", 0)
            win_rate = perf.get("win_rate", 0)

            if total_trades >= 5:
                if win_rate < 30:
                    performance_adjustment = 0.25
                    logger.warning(
                        f"[Risk] {ticker}/{strategy}: win_rate={win_rate}% "
                        f"({total_trades} trades) → position reduced to 25%"
                    )
                elif win_rate < 40:
                    performance_adjustment = 0.5
                    logger.info(
                        f"[Risk] {ticker}/{strategy}: win_rate={win_rate}% "
                        f"({total_trades} trades) → position reduced to 50%"
                    )
                elif win_rate < 50:
                    performance_adjustment = 0.75
                    logger.info(
                        f"[Risk] {ticker}/{strategy}: win_rate={win_rate}% "
                        f"({total_trades} trades) → position reduced to 75%"
                    )
        except Exception as e:
            logger.warning(f"Failed to get strategy performance: {e}")

        risk_percent *= performance_adjustment

        # Получаем текущую цену
        from tools.market_data import get_current_quote
        quote = get_current_quote(ticker)
        entry_price = quote.get("ask" if "BUY" in action or action == "LONG_OPEN" else "bid", 0)

        if entry_price <= 0:
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": "Invalid entry price",
            })

        # Расчёт позиции (risk_percent уже скорректирован выше)

        leverage = self.default_leverage
        result_sizes = {"own_required": 0, "borrowed": 0}

        # Проверка маржинального уровня ПЕРЕД открытием новой позиции
        if action in ("LONG_OPEN", "SHORT_OPEN"):
            try:
                from tools.margin_monitor import check_margin_level
                existing_prices = {}
                for p in (current_positions or []):
                    t = p.get("ticker")
                    if t:
                        try:
                            from tools.market_data import get_current_quote
                            q = get_current_quote(t)
                            existing_prices[t] = q.get("last", p.get("entry_price", 0))
                        except Exception:
                            existing_prices[t] = p.get("entry_price", 0)

                margin_status = check_margin_level(existing_prices)
                if margin_status["status"] == "liquidation":
                    return self._format_message("approved_order", {
                        "proposal_id": proposal_id,
                        "ticker": ticker,
                        "action": action,
                        "status": "rejected",
                        "reason": f"BLOCKED: Margin level {margin_status['margin_level']:.1f}% < 30% liquidation threshold",
                    })
                if margin_status["status"] == "margin_call":
                    # При margin call — уменьшаем плечо
                    leverage = 1.0
                    logger.warning(
                        f"[Risk] Margin call active (level={margin_status['margin_level']:.1f}%) "
                        f"— forced leverage=1.0 for new position"
                    )
                elif margin_status["leverage_used"] >= self.max_leverage:
                    leverage = 1.0
                    logger.warning(
                        f"[Risk] Max leverage {self.max_leverage}x already used "
                        f"— forced leverage=1.0 for new position"
                    )
            except Exception as e:
                logger.warning(f"Margin check failed: {e}")

        try:
            if action == "LONG_OPEN":
                # Validate SL is below entry
                if stop_loss >= entry_price:
                    return self._format_message("approved_order", {
                        "proposal_id": proposal_id,
                        "ticker": ticker,
                        "action": action,
                        "status": "rejected",
                        "reason": f"Invalid SL: {stop_loss} must be below entry {entry_price}",
                    })
                result_sizes = self._call_tool(
                    "calculate_position_size_leveraged",
                    capital=capital,
                    risk_percent=risk_percent,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss,
                    leverage=leverage,
                    side="LONG",
                )
                quantity = result_sizes["quantity"]

                # Cap position size
                reject = self._cap_position_size(quantity, entry_price, capital, result_sizes, leverage, proposal_id, ticker, action)
                if reject:
                    return reject
                quantity = result_sizes["quantity"]  # Re-read after capping

                side = "BUY"
            elif action == "SHORT_OPEN":
                # Validate SL is above entry
                if stop_loss <= entry_price:
                    return self._format_message("approved_order", {
                        "proposal_id": proposal_id,
                        "ticker": ticker,
                        "action": action,
                        "status": "rejected",
                        "reason": f"Invalid SL: {stop_loss} must be above entry {entry_price}",
                    })
                # Проверка доступности шорта
                short_avail = self._call_tool("check_short_availability", ticker=ticker)
                if not short_avail.get("available", False):
                    return self._format_message("approved_order", {
                        "proposal_id": proposal_id,
                        "ticker": ticker,
                        "action": action,
                        "status": "rejected",
                        "reason": "Short not available",
                    })

                self._call_tool("get_borrow_rate", ticker=ticker)
                result_sizes = self._call_tool(
                    "calculate_position_size_leveraged",
                    capital=capital,
                    risk_percent=risk_percent,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss,
                    leverage=leverage,
                    side="SHORT",
                )
                quantity = result_sizes["quantity"]

                # Cap position size
                reject = self._cap_position_size(quantity, entry_price, capital, result_sizes, leverage, proposal_id, ticker, action)
                if reject:
                    return reject
                quantity = result_sizes["quantity"]  # Re-read after capping

                side = "SELL"

            elif action in ("CLOSE_LONG", "CLOSE_SHORT"):
                # Закрытие существующей позиции — одобряем с текущим размером
                closing_trade_id = proposal.get("closing_trade_id")
                if not closing_trade_id:
                    return self._format_message("approved_order", {
                        "proposal_id": proposal_id,
                        "ticker": ticker,
                        "action": action,
                        "status": "rejected",
                        "reason": "No closing_trade_id provided",
                    })

                # Находим позицию
                position = None
                for p in current_positions:
                    if p.get("trade_id") == closing_trade_id:
                        position = p
                        break

                if not position:
                    return self._format_message("approved_order", {
                        "proposal_id": proposal_id,
                        "ticker": ticker,
                        "action": action,
                        "status": "rejected",
                        "reason": f"Position {closing_trade_id} not found",
                    })

                quantity = position.get("quantity", 0)
                side = "SELL" if action == "CLOSE_LONG" else "BUY"
                # Для закрытия: используем bid (продажа) или ask (покрытие)
                entry_price = quote.get("bid" if action == "CLOSE_LONG" else "ask", entry_price)

                logger.info(
                    f"[Risk] APPROVED close {action}: {quantity} {ticker} "
                    f"@ {entry_price:.2f} (trade_id={closing_trade_id})"
                )

            else:
                return self._format_message("approved_order", {
                    "proposal_id": proposal_id,
                    "ticker": ticker,
                    "action": action,
                    "status": "rejected",
                    "reason": f"Unsupported action: {action}",
                })
        except ValueError as e:
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": str(e),
            })

        # Расчёт комиссий
        try:
            commission = self._call_tool(
                "calculate_cycle_commission",
                ticker=ticker,
                quantity=quantity,
                entry_price=entry_price,
                exit_price=take_profit if take_profit else entry_price,
                side=f"{action}",
            )
        except Exception as e:
            logger.warning(f"Commission calc failed: {e}")
            commission = {"total_commission": 0, "total_commission_percent": 0}

        # Проверка объёма
        try:
            volume_check = self._call_tool(
                "check_volume_limit", ticker=ticker, quantity=quantity
            )
        except Exception:
            volume_check = {"allowed": True}

        if not volume_check.get("allowed", True):
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": "Volume limit exceeded",
            })

        # Проверка комиссии относительно ожидаемой прибыли
        expected_profit = abs(take_profit - entry_price) * quantity
        commission_amount = commission.get("total_commission", 0)
        if expected_profit > 0 and commission_amount > expected_profit * 0.1:
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": f"Commission {commission_amount:.0f}RUB > 10% of expected profit {expected_profit:.0f}RUB",
            })

        # Расчёт R/R
        if action == "LONG_OPEN":
            risk_per_share = entry_price - stop_loss
            reward_per_share = take_profit - entry_price
        else:
            risk_per_share = stop_loss - entry_price
            reward_per_share = entry_price - take_profit

        rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0

        if rr_ratio < self.min_rr_ratio:
            return self._format_message("approved_order", {
                "proposal_id": proposal_id,
                "ticker": ticker,
                "action": action,
                "status": "rejected",
                "reason": f"R/R ratio {rr_ratio:.2f} below minimum {self.min_rr_ratio}",
            })

        # Финальный одобренный ордер
        result = self._format_message("approved_order", {
            "proposal_id": proposal_id,
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
            "entry_price_limit": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "side": side,
            "leverage": leverage,
            "own_required": result_sizes.get("own_required", quantity * entry_price) if action in ("LONG_OPEN", "SHORT_OPEN") else quantity * entry_price,
            "borrowed": result_sizes.get("borrowed", 0) if action in ("LONG_OPEN", "SHORT_OPEN") else 0,
            "commission_cycle_estimate": commission.get("total_commission", 0) if isinstance(commission, dict) else 0,
            "commission_percent": commission.get("total_commission_percent", 0) if isinstance(commission, dict) else 0,
            "expected_rr_ratio": round(rr_ratio, 2) if rr_ratio else 0,
            "risk_per_trade": round(risk_percent, 2),
            "performance_adjustment": round(performance_adjustment, 2),
            "closing_trade_id": proposal.get("closing_trade_id"),
            "status": "approved",
        })

        self.log_action(
            input_data={"proposal_id": proposal_id, "ticker": ticker, "action": action},
            output_data=result,
            tool_calls=["calculate_position", "calculate_commission", "check_volume"],
        )

        return result

    def _check_daily_loss_limit(self) -> dict:
        """Проверка дневного лимита убытков."""
        try:
            import sqlite3
            from tools.memory import get_db_path
            from datetime import date

            conn = sqlite3.connect(get_db_path(), timeout=5)
            cursor = conn.cursor()

            # Получаем P&L за сегодня
            today = date.today().isoformat()
            cursor.execute("""
                SELECT COALESCE(SUM(pnl), 0) as total_pnl
                FROM trades
                WHERE status = 'closed'
                  AND closed_at >= ?
            """, (today,))
            result = cursor.fetchone()
            today_pnl = result[0] if result else 0
            conn.close()

            max_daily_loss_percent = self.config.get("trading", {}).get("max_daily_loss_percent", 2.0)
            initial_capital = self.config.get("trading", {}).get("initial_capital", 100000)

            if today_pnl < 0:
                loss_percent = abs(today_pnl) / initial_capital * 100
                if loss_percent >= max_daily_loss_percent:
                    return {
                        "allowed": False,
                        "reason": f"Daily loss {loss_percent:.1f}% exceeds limit {max_daily_loss_percent}%"
                    }

            return {"allowed": True, "today_pnl": today_pnl}

        except Exception as e:
            logger.warning(f"Failed to check daily loss limit: {e}")
            return {"allowed": True}

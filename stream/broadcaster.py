"""Broadcaster — сбор данных и отправка через WebSocket."""

import time
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class Broadcaster:
    """Сбор данных из всех источников и отправка клиентам."""

    def __init__(self):
        self._clients: set = set()
        self._lmstudio_monitor = None
        self._agent_monitor = None
        self._price_feed = None
        self._config = {}
        self._last_equity: list = []

    def set_lmstudio_monitor(self, monitor):
        """Установить монитор LM Studio."""
        self._lmstudio_monitor = monitor

    def set_agent_monitor(self, monitor):
        """Установить монитор агентов."""
        self._agent_monitor = monitor

    def set_price_feed(self, feed):
        """Установить фид цен."""
        self._price_feed = feed

    def set_config(self, config: dict):
        """Установить конфигурацию."""
        self._config = config

    def add_client(self, websocket):
        """Добавить WebSocket клиент."""
        self._clients.add(websocket)
        logger.info(f"Client connected. Total: {len(self._clients)}")

    def remove_client(self, websocket):
        """Удалить WebSocket клиент."""
        self._clients.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self._clients)}")

    def _get_portfolio_data(self) -> dict:
        """Получить данные портфеля."""
        try:
            from tools.virtual_portfolio import get_balance, get_positions
            balance_info = get_balance()
            positions = get_positions()

            return {
                "balance": round(balance_info.get("current_balance", 0), 2),
                "initial_capital": balance_info.get("initial_capital", 0),
                "borrowed": round(balance_info.get("borrowed", 0), 2),
                "positions_count": len(positions),
                "positions": positions,
            }
        except Exception as e:
            logger.debug(f"Portfolio data error: {e}")
            return {"balance": 0, "initial_capital": 0, "borrowed": 0,
                    "positions_count": 0, "positions": []}

    def _get_equity_curve(self) -> list:
        """Получить кривую капитала."""
        try:
            from tools.memory import get_equity_history
            history = get_equity_history(limit=100)
            return [[h.get("timestamp"), h.get("total_value", 0)] for h in history]
        except Exception as e:
            logger.debug(f"Equity curve error: {e}")
            return []

    def _get_last_trades(self, limit: int = 10) -> list:
        """Получить последние сделки."""
        try:
            from tools.memory import get_all_trades
            trades = get_all_trades(status=None, limit=limit)
            return [
                {
                    "ticker": t.get("ticker"),
                    "action": t.get("action"),
                    "side": "LONG" if "LONG" in (t.get("action") or "") else "SHORT",
                    "pnl": t.get("pnl"),
                    "pnl_percent": round(
                        (t.get("pnl", 0) / (t.get("entry_price", 1) * t.get("quantity", 1))) * 100
                        if t.get("entry_price") and t.get("quantity") else 0, 1
                    ),
                    "strategy": t.get("strategy"),
                    "time": t.get("opened_at", "")[:16] if t.get("opened_at") else "",
                    "status": t.get("status"),
                }
                for t in trades[:limit]
            ]
        except Exception as e:
            logger.debug(f"Last trades error: {e}")
            return []

    def _get_positions_summary(self) -> list:
        """Получить сводку по позициям."""
        try:
            from tools.virtual_portfolio import get_positions
            positions = get_positions()
            return [
                {
                    "ticker": p.get("ticker"),
                    "side": p.get("side"),
                    "quantity": p.get("quantity"),
                    "entry_price": p.get("entry_price"),
                    "stop_loss": p.get("stop_loss"),
                    "take_profit": p.get("take_profit"),
                    "strategy": p.get("strategy"),
                    "leverage": p.get("leverage", 1),
                }
                for p in positions
            ]
        except Exception as e:
            logger.debug(f"Positions summary error: {e}")
            return []

    def build_snapshot(self) -> dict:
        """Собрать полный снимок для WebSocket."""
        portfolio = self._get_portfolio_data()
        equity_curve = self._get_equity_curve()
        last_trades = self._get_last_trades()
        positions = self._get_positions_summary()

        # LM Studio
        lmstudio_status = {}
        if self._lmstudio_monitor:
            lmstudio_status = self._lmstudio_monitor.get_full_status(
                model=self._config.get("lmstudio", {}).get("model", "unknown"),
                is_online=True,
            )

        # Agents
        agent_states = {}
        pipeline_progress = {}
        if self._agent_monitor:
            pipeline_progress = self._agent_monitor.get_pipeline_progress()
            agent_states = pipeline_progress.get("agents", {})

        # P&L calculation
        for pos in positions:
            # Упрощённый расчёт — нужна текущая цена
            pass

        pnl_percent = 0
        if portfolio.get("initial_capital", 0) > 0:
            pnl_percent = round(
                (portfolio["balance"] - portfolio["initial_capital"])
                / portfolio["initial_capital"] * 100, 1
            )

        # Leverage calculation
        leverage = 1.0
        if portfolio.get("balance", 0) > 0 and portfolio.get("borrowed", 0) > 0:
            leverage = round(
                (portfolio["balance"] + portfolio["borrowed"]) / portfolio["balance"], 1
            )

        return {
            "timestamp": time.time(),
            "portfolio": {
                "balance": portfolio["balance"],
                "initial_capital": portfolio["initial_capital"],
                "pnl_percent": pnl_percent,
                "positions_count": portfolio["positions_count"],
                "leverage": leverage,
                "borrowed": portfolio["borrowed"],
            },
            "lmstudio": lmstudio_status,
            "agents": agent_states,
            "pipeline": {
                "current_step": pipeline_progress.get("current_step"),
                "progress": pipeline_progress.get("progress", 0),
            },
            "equity_curve": equity_curve,
            "last_trades": last_trades,
            "positions": positions,
        }

    async def broadcast(self):
        """Отправить данные всем подключённым клиентам."""
        if not self._clients:
            return

        loop = asyncio.get_running_loop()
        snapshot = await loop.run_in_executor(None, self.build_snapshot)
        message = json.dumps(snapshot, default=str)

        disconnected = set()
        for client in self._clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        for client in disconnected:
            self._clients.discard(client)


# Глобальный экземпляр
broadcaster = Broadcaster()

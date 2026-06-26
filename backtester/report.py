import json
import csv
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class BacktestReport:
    """Generates performance report from backtest results."""

    def __init__(self, config):
        self.config = config

    def generate(
        self,
        equity_curve: list[dict],
        cycle_results: list[dict],
        trade_log: list[dict],
        initial_capital: float,
    ) -> dict:
        equity_values = [e["total_value"] for e in equity_curve] if equity_curve else [initial_capital]

        final_equity = equity_values[-1] if equity_values else initial_capital
        total_pnl = final_equity - initial_capital
        total_pnl_pct = (total_pnl / initial_capital) * 100

        # Trade statistics
        opens = [t for t in trade_log if t.get("type") == "open"]
        closes = [t for t in trade_log if t.get("type") == "close"]

        total_trades = len(opens)
        winning_trades = len([c for c in closes if c.get("pnl", 0) > 0])
        losing_trades = len([c for c in closes if c.get("pnl", 0) < 0])
        win_rate = (winning_trades / len(closes) * 100) if closes else 0

        # P&L distribution
        pnls = [c.get("pnl", 0) for c in closes]
        total_profit = sum(p for p in pnls if p > 0)
        total_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float("inf")
        avg_pnl = np.mean(pnls) if pnls else 0

        # Total commission from trade log
        total_commission = sum(t.get("commission", 0) for t in trade_log)

        # Risk metrics
        max_drawdown = self._calc_max_drawdown(equity_values)
        sharpe = self._calc_sharpe(equity_values)
        sortino = self._calc_sortino(equity_values)

        # Strategy breakdown
        strategy_stats = {}
        for o in opens:
            strat = o.get("strategy", "unknown")
            if strat not in strategy_stats:
                strategy_stats[strat] = {"count": 0, "wins": 0, "losses": 0}
            strategy_stats[strat]["count"] += 1

        for c in closes:
            strat = c.get("strategy", "unknown")
            if strat in strategy_stats:
                if c.get("pnl", 0) > 0:
                    strategy_stats[strat]["wins"] += 1
                else:
                    strategy_stats[strat]["losses"] += 1

        for strat, stats in strategy_stats.items():
            total = stats["wins"] + stats["losses"]
            stats["win_rate"] = (stats["wins"] / total * 100) if total > 0 else 0

        # Cycle statistics
        total_cycles = len(cycle_results)
        total_proposals = sum(r.get("proposals_generated", 0) for r in cycle_results)
        total_approved = sum(r.get("proposals_approved", 0) for r in cycle_results)
        total_orders = sum(r.get("orders_placed", 0) for r in cycle_results)
        total_errors = sum(len(r.get("errors", [])) for r in cycle_results)

        results = {
            "config": {
                "tickers": self.config.tickers,
                "period": self.config.period,
                "interval": self.config.interval,
                "initial_capital": initial_capital,
                "max_leverage": self.config.max_leverage,
            },
            "performance": {
                "initial_capital": initial_capital,
                "final_equity": round(final_equity, 2),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_pct": round(total_pnl_pct, 2),
                "total_commission": round(total_commission, 2),
            },
            "trades": {
                "total": total_trades,
                "winning": winning_trades,
                "losing": losing_trades,
                "win_rate": round(win_rate, 2),
                "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
                "avg_pnl": round(avg_pnl, 2),
                "total_profit": round(total_profit, 2),
                "total_loss": round(total_loss, 2),
            },
            "risk": {
                "max_drawdown_pct": round(max_drawdown, 2),
                "sharpe_ratio": round(sharpe, 3),
                "sortino_ratio": round(sortino, 3),
            },
            "strategies": strategy_stats,
            "cycles": {
                "total": total_cycles,
                "proposals_generated": total_proposals,
                "proposals_approved": total_approved,
                "orders_placed": total_orders,
                "errors": total_errors,
            },
            "equity_curve": equity_curve,
            "trade_log": trade_log,
            "timestamp": datetime.now().isoformat(),
        }

        return results

    def _calc_max_drawdown(self, equity_values: list[float]) -> float:
        if len(equity_values) < 2:
            return 0.0
        peak = equity_values[0]
        max_dd = 0.0
        for val in equity_values:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _calc_sharpe(self, equity_values: list[float], risk_free_rate: float = 0.0) -> float:
        if len(equity_values) < 2:
            return 0.0
        returns = []
        for i in range(1, len(equity_values)):
            if equity_values[i - 1] > 0:
                ret = (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                returns.append(ret)
        if not returns:
            return 0.0
        returns = np.array(returns)
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        if std_ret == 0:
            return 0.0
        return (mean_ret - risk_free_rate) / std_ret * np.sqrt(252)

    def _calc_sortino(self, equity_values: list[float], risk_free_rate: float = 0.0) -> float:
        if len(equity_values) < 2:
            return 0.0
        returns = []
        for i in range(1, len(equity_values)):
            if equity_values[i - 1] > 0:
                ret = (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                returns.append(ret)
        if not returns:
            return 0.0
        returns = np.array(returns)
        mean_ret = np.mean(returns)
        downside = returns[returns < 0]
        downside_std = np.std(downside) if len(downside) > 0 else 0
        if downside_std == 0:
            return 0.0
        return (mean_ret - risk_free_rate) / downside_std * np.sqrt(252)

    def save(self, results: dict):
        output_dir = self.config.get_output_path()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Text report
        txt_path = output_dir / f"report_{timestamp}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._format_text(results))
        logger.info(f"Report saved: {txt_path}")

        # Trade log CSV
        csv_path = output_dir / f"trades_{timestamp}.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["type", "ticker", "action", "strategy", "confidence", "pnl", "bar_index"])
            writer.writeheader()
            for trade in results.get("trade_log", []):
                writer.writerow(trade)
        logger.info(f"Trade log saved: {csv_path}")

        # Equity curve JSON
        json_path = output_dir / f"equity_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results.get("equity_curve", []), f, indent=2)
        logger.info(f"Equity curve saved: {json_path}")

        # Full results JSON
        full_path = output_dir / f"full_results_{timestamp}.json"
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Full results saved: {full_path}")

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info("BACKTEST RESULTS")
        logger.info(f"{'='*60}")
        perf = results.get("performance", {})
        trades = results.get("trades", {})
        risk = results.get("risk", {})
        logger.info(f"Initial Capital: {perf.get('initial_capital', 0):,.0f} RUB")
        logger.info(f"Final Equity:    {perf.get('final_equity', 0):,.0f} RUB")
        logger.info(f"Total P&L:       {perf.get('total_pnl', 0):+,.0f} RUB ({perf.get('total_pnl_pct', 0):+.2f}%)")
        logger.info(f"{'-'*60}")
        logger.info(f"Total Trades:    {trades.get('total', 0)}")
        logger.info(f"Win Rate:        {trades.get('win_rate', 0):.1f}%")
        logger.info(f"Profit Factor:   {trades.get('profit_factor', 0)}")
        logger.info(f"Avg P&L:         {trades.get('avg_pnl', 0):+,.0f} RUB")
        logger.info(f"{'-'*60}")
        logger.info(f"Max Drawdown:    {risk.get('max_drawdown_pct', 0):.2f}%")
        logger.info(f"Sharpe Ratio:    {risk.get('sharpe_ratio', 0):.3f}")
        logger.info(f"Sortino Ratio:   {risk.get('sortino_ratio', 0):.3f}")

        strats = results.get("strategies", {})
        if strats:
            logger.info(f"{'-'*60}")
            logger.info("Strategy Breakdown:")
            for strat, stats in strats.items():
                logger.info(f"  {strat}: {stats['count']} trades, WR={stats.get('win_rate', 0):.1f}%")

        logger.info(f"{'='*60}")

    def _format_text(self, results: dict) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("BACKTEST REPORT")
        lines.append(f"Generated: {results.get('timestamp', 'N/A')}")
        lines.append("=" * 60)

        config = results.get("config", {})
        lines.append(f"\nConfiguration:")
        lines.append(f"  Tickers: {', '.join(config.get('tickers', []))}")
        lines.append(f"  Period: {config.get('period', 'N/A')}")
        lines.append(f"  Interval: {config.get('interval', 'N/A')}")
        lines.append(f"  Initial Capital: {config.get('initial_capital', 0):,.0f} RUB")
        lines.append(f"  Max Leverage: x{config.get('max_leverage', 1)}")

        perf = results.get("performance", {})
        lines.append(f"\nPerformance:")
        lines.append(f"  Initial Capital: {perf.get('initial_capital', 0):,.0f} RUB")
        lines.append(f"  Final Equity:    {perf.get('final_equity', 0):,.0f} RUB")
        lines.append(f"  Total P&L:       {perf.get('total_pnl', 0):+,.0f} RUB ({perf.get('total_pnl_pct', 0):+.2f}%)")

        trades = results.get("trades", {})
        lines.append(f"\nTrade Statistics:")
        lines.append(f"  Total Trades:    {trades.get('total', 0)}")
        lines.append(f"  Winning:         {trades.get('winning', 0)}")
        lines.append(f"  Losing:          {trades.get('losing', 0)}")
        lines.append(f"  Win Rate:        {trades.get('win_rate', 0):.1f}%")
        lines.append(f"  Profit Factor:   {trades.get('profit_factor', 0)}")
        lines.append(f"  Avg P&L:         {trades.get('avg_pnl', 0):+,.0f} RUB")

        risk = results.get("risk", {})
        lines.append(f"\nRisk Metrics:")
        lines.append(f"  Max Drawdown:    {risk.get('max_drawdown_pct', 0):.2f}%")
        lines.append(f"  Sharpe Ratio:    {risk.get('sharpe_ratio', 0):.3f}")
        lines.append(f"  Sortino Ratio:   {risk.get('sortino_ratio', 0):.3f}")

        strats = results.get("strategies", {})
        if strats:
            lines.append(f"\nStrategy Breakdown:")
            for strat, stats in strats.items():
                lines.append(f"  {strat}:")
                lines.append(f"    Trades: {stats['count']}")
                lines.append(f"    Win Rate: {stats.get('win_rate', 0):.1f}%")

        cycles = results.get("cycles", {})
        lines.append(f"\nPipeline Statistics:")
        lines.append(f"  Total Cycles:        {cycles.get('total', 0)}")
        lines.append(f"  Proposals Generated: {cycles.get('proposals_generated', 0)}")
        lines.append(f"  Proposals Approved:  {cycles.get('proposals_approved', 0)}")
        lines.append(f"  Orders Placed:       {cycles.get('orders_placed', 0)}")
        lines.append(f"  Errors:              {cycles.get('errors', 0)}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

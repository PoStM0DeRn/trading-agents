from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BacktestConfig:
    tickers: list[str] = field(default_factory=lambda: ["SBER", "GAZP", "LKOH", "GMKN", "YDEX", "VTBR", "ROSN", "NVTK"])
    period: str = "1y"
    interval: str = "1h"
    initial_capital: float = 100000.0
    max_leverage: float = 3.0
    default_leverage: float = 3.0
    output_dir: str = "backtest_results"
    verbose: bool = False
    use_llm: bool = True
    trading_hours_start: int = 10
    trading_hours_end: int = 18
    trading_minutes_end: int = 45
    max_positions: int = 10
    max_position_percent: float = 20.0
    default_risk_per_trade: float = 1.0
    min_rr_ratio: float = 1.5
    commission_min: float = 19.99
    commission_percent: float = 0.3

    def get_period_days(self) -> int:
        multiplier = {"3m": 90, "6m": 180, "1y": 365, "2y": 730}
        return multiplier.get(self.period, 365)

    def get_interval_seconds(self) -> int:
        intervals = {"1h": 3600, "4h": 14400, "1d": 86400}
        return intervals.get(self.interval, 3600)

    def get_output_path(self) -> Path:
        path = Path(self.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

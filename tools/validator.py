"""Input validation utilities for agent entry points."""

import re
import logging

logger = logging.getLogger(__name__)

KNOWN_TICKERS = {
    "SBER", "GAZP", "LKOH", "GMKN", "YDEX", "VTBR", "ROSN", "NVTK",
    "SNGS", "TATN", "ALRS", "PLZL", "PHOR", "AFLT", "MOEX", "RGSS",
    "FEES", "TRNF", "NMTP", "FLOT", "SBMX", "BREX", "TCSG", "OZON",
    "VKCO", "QIWI", "CHMF", "MAGN", "NLMK", "MCHL", "IRAO", "MGNT",
    "SNGSP",
}

VALID_ACTIONS = {"BUY", "SELL", "HOLD", "CLOSE", "LONG_OPEN", "SHORT_OPEN", "LONG_CLOSE", "SHORT_CLOSE"}
VALID_SIDES = {"BUY", "SELL"}


def validate_ticker(ticker: str) -> str:
    """Validate ticker: uppercase, alphanumeric 1-5 chars, known MOEX or US ticker."""
    if not ticker or not isinstance(ticker, str):
        raise ValueError(f"Invalid ticker: {ticker!r}")
    ticker_upper = ticker.strip().upper()
    if not re.match(r"^[A-Z]{1,5}$", ticker_upper):
        raise ValueError(f"Invalid ticker format: {ticker_upper!r}")
    if ticker_upper not in KNOWN_TICKERS:
        logger.warning(f"Unknown ticker: {ticker_upper}")
    return ticker_upper


def validate_positive_number(value, name: str = "value") -> float:
    """Validate value is a positive number."""
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {type(value).__name__}")
    if val <= 0:
        raise ValueError(f"{name} must be positive, got {val}")
    return val


def validate_action(action: str) -> str:
    """Validate trading action is one of the allowed values."""
    if not action or not isinstance(action, str):
        raise ValueError(f"Invalid action: {action!r}")
    action_upper = action.strip().upper()
    if action_upper not in VALID_ACTIONS:
        raise ValueError(f"Unknown action: {action_upper}, valid: {sorted(VALID_ACTIONS)}")
    return action_upper


def validate_side(side: str) -> str:
    """Validate order side (BUY/SELL)."""
    if not side or not isinstance(side, str):
        raise ValueError(f"Invalid side: {side!r}")
    side_upper = side.strip().upper()
    if side_upper not in VALID_SIDES:
        raise ValueError(f"Unknown side: {side_upper}, valid: {sorted(VALID_SIDES)}")
    return side_upper


def validate_period(period: str) -> str:
    """Validate period string like 1mo, 3mo, 1y, 1d, 1w."""
    valid_periods = {"1d", "5d", "1w", "2w", "1mo", "3mo", "6mo", "1y"}
    if period not in valid_periods:
        raise ValueError(f"Invalid period: {period}, valid: {sorted(valid_periods)}")
    return period


def validate_interval(interval: str) -> str:
    """Validate interval string like 1m, 5m, 15m, 1h, 1d."""
    valid_intervals = {"1m", "5m", "15m", "1h", "1d"}
    if interval not in valid_intervals:
        raise ValueError(f"Invalid interval: {interval}, valid: {sorted(valid_intervals)}")
    return interval


def validate_proposal(proposal: dict) -> list[str]:
    """Validate a trading proposal dict. Returns list of error messages."""
    errors = []
    action = proposal.get("action", "")
    try:
        proposal["action"] = validate_action(action)
    except ValueError as e:
        errors.append(str(e))

    if "confidence" in proposal:
        try:
            conf = float(proposal["confidence"])
            if not 0 <= conf <= 1:
                errors.append(f"confidence must be 0-1, got {conf}")
        except (TypeError, ValueError):
            errors.append(f"confidence must be a number, got {type(proposal['confidence']).__name__}")

    if "stop_loss" in proposal and proposal["stop_loss"] is not None:
        try:
            proposal["stop_loss"] = validate_positive_number(proposal["stop_loss"], "stop_loss")
        except ValueError as e:
            errors.append(str(e))

    if "take_profit" in proposal and proposal["take_profit"] is not None:
        try:
            proposal["take_profit"] = validate_positive_number(proposal["take_profit"], "take_profit")
        except ValueError as e:
            errors.append(str(e))

    return errors


def validate_safe(fn):
    """Decorator: catches ValueError and returns error dict instead of raising."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation failed in {fn.__name__}: {e}")
            return {"error": str(e)}
    return wrapper

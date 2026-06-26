"""Менеджер конфигурации — чтение, запись, валидация, audit log."""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

# ── Schema: валидация параметров ──────────────────────────────────────────────
# (min, max, type, description)
PARAM_SCHEMA = {
    "trading.initial_capital":        (10000, 1_000_000_000, int,   "Начальный капитал (₽)"),
    "trading.max_daily_loss_percent": (0.1,   20.0,          float, "Макс. дневной убыток (%)"),
    "trading.max_positions":          (1,     50,            int,   "Макс. кол-во позиций"),
    "trading.max_position_percent":   (1.0,   100.0,         float, "Макс. доля позиции (%)"),
    "trading.max_sector_exposure":    (5.0,   100.0,         float, "Макс. секторальный曝光 (%)"),
    "trading.max_short_exposure":     (0.0,   100.0,         float, "Макс. шорт-экспозиция (%)"),
    "trading.max_leverage":           (1.0,   10.0,          float, "Макс. кредитное плечо"),
    "trading.default_leverage":       (1.0,   10.0,          float, "Плечение по умолчанию"),
    "trading.margin_call_percent":    (10,    200,           int,   "Маржин-колл (%)"),
    "trading.liquidation_percent":    (5,     150,           int,   "Ликвидация (%)"),
    "risk.default_risk_per_trade":    (0.1,   10.0,          float, "Риск на сделку (%)"),
    "risk.min_rr_ratio":              (0.5,   10.0,          float, "Мин. Risk/Reward"),
    "risk.max_correlation":           (0.0,   1.0,           float, "Макс. корреляция"),
    "schedule.cycle_interval_minutes":(1,     480,           int,   "Интервал циклов (мин)"),
    "schedule.cycle_timeout":         (60,    7200,          int,   "Таймаут цикла (сек)"),
    "lmstudio.temperature":          (0.0,   2.0,           float, "Temperature LLM"),
}


def _deep_get(d: dict, key: str, default=None):
    """Получить значение по dotted key: 'trading.max_positions'."""
    keys = key.split(".")
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


def _deep_set(d: dict, key: str, value: Any):
    """Установить значение по dotted key."""
    keys = key.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


# ── YAML ──────────────────────────────────────────────────────────────────────

def load_yaml() -> dict:
    """Загрузить settings.yaml."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(config: dict):
    """Сохранить settings.yaml."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("settings.yaml saved")


# ── .ENV ──────────────────────────────────────────────────────────────────────

_ENV_PATTERN = re.compile(r"^([A-Z_]+)=(.*)$", re.MULTILINE)


def load_env() -> dict:
    """Загрузить .env в словарь."""
    result = {}
    if not ENV_PATH.exists():
        return result
    content = ENV_PATH.read_text(encoding="utf-8")
    for match in _ENV_PATTERN.finditer(content):
        result[match.group(1)] = match.group(2)
    return result


def save_env(env: dict):
    """Сохранить словарь в .env (перезаписывает файл)."""
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(".env saved")


# ── Валидация ─────────────────────────────────────────────────────────────────

def validate_config(config: dict) -> list[str]:
    """Валидация конфига. Возвращает список ошибок."""
    errors = []
    for key, (lo, hi, typ, desc) in PARAM_SCHEMA.items():
        val = _deep_get(config, key)
        if val is None:
            continue
        try:
            val = typ(val)
        except (ValueError, TypeError):
            errors.append(f"{desc} ({key}): должно быть {typ.__name__}")
            continue
        if not (lo <= val <= hi):
            errors.append(f"{desc} ({key}): {val} вне диапазона [{lo}, {hi}]")
    return errors


def validate_env(env: dict) -> list[str]:
    """Валидация .env параметров."""
    errors = []
    token = env.get("TINVEST_TOKEN", "")
    if token and token != "your_tinvest_token_here" and len(token) < 10:
        errors.append("TINVEST_TOKEN слишком короткий")
    account = env.get("TINVEST_ACCOUNT_ID", "")
    if account and account != "your_account_id_here" and not account.isdigit():
        errors.append("TINVEST_ACCOUNT_ID должен быть числом")
    host = env.get("LMSTUDIO_HOST", "")
    if host and not host.startswith("http"):
        errors.append("LMSTUDIO_HOST должен начинаться с http:// или https://")
    return errors


# ── Audit Log ─────────────────────────────────────────────────────────────────

def _get_audit_db() -> str:
    """Путь к БД для audit log."""
    db_path = PROJECT_ROOT / "data" / "trading_memory.db"
    return str(db_path)


def init_audit_table():
    """Создать таблицу config_audit если не существует."""
    conn = sqlite3.connect(_get_audit_db())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            section TEXT,
            param TEXT,
            old_value TEXT,
            new_value TEXT,
            source TEXT DEFAULT 'dashboard'
        )
    """)
    conn.commit()
    conn.close()


def log_change(section: str, param: str, old_value: Any, new_value: Any, source: str = "dashboard"):
    """Записать изменение конфига в audit log."""
    try:
        conn = sqlite3.connect(_get_audit_db())
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO config_audit (section, param, old_value, new_value, source)
            VALUES (?, ?, ?, ?, ?)
        """, (section, param, str(old_value), str(new_value), source))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")


def get_audit_log(limit: int = 100) -> list[dict]:
    """Получить последние записи audit log."""
    try:
        conn = sqlite3.connect(_get_audit_db())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM config_audit ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


# ── Комбинированные операции ──────────────────────────────────────────────────

def load_full_config() -> dict:
    """Загрузить и объединить settings.yaml + .env."""
    config = load_yaml()
    env = load_env()

    # Подстановка переменных окружения
    def resolve_env(obj):
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return env.get(env_var, obj)
        elif isinstance(obj, dict):
            return {k: resolve_env(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve_env(i) for i in obj]
        return obj

    return resolve_env(config)


def save_full_config(config: dict, env: dict, changes: dict | None = None):
    """Сохранить конфиг и .env с audit log.

    changes: dict of {dotted_key: (old_value, new_value)} для audit log
    """
    save_yaml(config)
    save_env(env)

    if changes:
        for key, (old_val, new_val) in changes.items():
            section = key.split(".")[0] if "." in key else "env"
            param = key.split(".")[-1] if "." in key else key
            log_change(section, param, old_val, new_val)


def is_first_run() -> bool:
    """True if .env missing OR tokens are placeholders OR DB empty."""
    if not ENV_PATH.exists():
        return True
    env = load_env()
    token = env.get("TINVEST_TOKEN", "")
    if not token or token == "your_tinvest_token_here":
        return True
    # Check DB has trades table with data
    try:
        from tools.memory import get_raw_conn
        with get_raw_conn() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            if cnt == 0:
                return True
    except Exception:
        return True
    return False

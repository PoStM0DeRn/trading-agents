"""Shared initialization for main.py and run_single_cycle.py.

Returns SystemComponents NamedTuple with named fields for type-safe access.
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from dotenv import load_dotenv
from config.secrets import secrets

if TYPE_CHECKING:
    from integrations.lmstudio_client import LMStudioClient
    from integrations.tinvest import TInvestClient
    from agents.supervisor import SupervisorAgent

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
load_dotenv(PROJECT_ROOT / ".env")

# Verify external service tokens (non-blocking, logs warnings)
_auth_results = secrets.verify_auth()


class SystemComponents(NamedTuple):
    """Контейнер для всех компонентов системы после инициализации.

    Поля:
        llm_client  — LM Studio клиент (LLM)
        tinvest     — T-Invest клиент (брокерский API)
        supervisor  — SupervisorAgent (оркестратор торгового цикла)
        config      — загруженная конфигурация (settings.yaml)
    """
    llm_client: LMStudioClient
    tinvest: "TInvestClient"
    supervisor: "SupervisorAgent"
    config: dict


def load_config() -> dict:
    """Загрузить settings.yaml с интерполяцией переменных окружения."""
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    def resolve_env(obj):
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            return os.getenv(obj[2:-1], obj)
        elif isinstance(obj, dict):
            return {k: resolve_env(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve_env(i) for i in obj]
        return obj

    return resolve_env(config)


def create_llm_client(config: dict, logger=None) -> LMStudioClient:
    """Создать и проверить LM Studio клиент."""
    from integrations.lmstudio_client import LMStudioClient

    lmstudio_config = config.get("lmstudio", {})
    llm_client = LMStudioClient(
        host=lmstudio_config.get("host", "http://localhost:1234"),
        model=lmstudio_config.get("model", "default"),
        temperature=lmstudio_config.get("temperature", 0.3),
    )

    if not llm_client.is_available():
        if logger:
            logger.warning("LM Studio is not available!")
    elif logger:
        logger.info(f"LM Studio connected. Models: {llm_client.list_models()}")

    return llm_client


def create_tinvest_client(config: dict, logger=None) -> TInvestClient:
    """Создать и подключить T-Invest клиент."""
    from integrations.tinvest import TInvestClient

    tinvest = TInvestClient()
    try:
        tinvest.connect()
        if logger:
            logger.info("T-Invest client connected.")
    except Exception as e:
        if logger:
            logger.warning(f"T-Invest connection failed: {e}")

    return tinvest


def inject_clients(tinvest_client, llm_client=None, config=None):
    """Инжекция клиентов в tool-модули (замена глобалов)."""
    from tools import market_data, execution, short_specific
    from tools import microstructure, correlations, patterns, corporate
    from tools import news as news_tools

    market_data.set_client(tinvest_client)
    execution.set_client(tinvest_client)
    short_specific.set_client(tinvest_client)
    if config:
        short_specific.set_config(config)
    microstructure.set_client(tinvest_client)
    correlations.set_client(tinvest_client)
    patterns.set_client(tinvest_client)
    corporate.set_client(tinvest_client)
    if llm_client:
        news_tools.set_llm_client(llm_client)


def init_db():
    """Инициализировать SQLite БД."""
    from tools.memory import init_db as _init_db

    _init_db(str(PROJECT_ROOT / "data" / "trading_memory.db"))


def init_system(config: dict, logger=None) -> SystemComponents:
    """Инициализировать все компоненты системы.

    Создаёт LLM клиент, T-Invest клиент, инжектирует зависимости
    в tool-модули, инициализирует БД и создаёт SupervisorAgent.

    Возвращает SystemComponents с именованными полями:
        llm_client, tinvest, supervisor, config
    """
    llm_client = create_llm_client(config, logger)
    tinvest = create_tinvest_client(config, logger)
    inject_clients(tinvest_client=tinvest, llm_client=llm_client, config=config)
    init_db()

    from agents.supervisor import SupervisorAgent

    supervisor = SupervisorAgent(llm_client, config=config, tinvest_client=tinvest)

    return SystemComponents(llm_client, tinvest, supervisor, config)

# Production Readiness Plan

> Текущая оценка: **3.5–4 / 10**  
> Целевая оценка: **8+ / 10**

---

## Этап 0: Быстрые победы (1–2 дня)

| # | Задача | Описание | Файлы | Приоритет |
|---|--------|----------|-------|-----------|
| 0.1 | Валидация `.env` на старте | Добавить вызов `validate_config()` в `main.py` и `run_single_cycle.py` до запуска цикла | `main.py`, `config/settings.py` | Critical |
| 0.2 | Удалить `print()` из кода | Заменить все `print()` на `logger.*` | Весь проект (grep `print(`) | High |
| 0.3 | Зафиксировать версии зависимостей | Прописать точные версии в `requirements.txt` | `requirements.txt` | High |
| 0.4 | Удалить неиспользуемые зависимости | Оставить только реально используемые пакеты | `requirements.txt` | Medium |

---

## Этап 1: Error Handling & Resilience (1 неделя)

### 1.1 Retry-декоратор для внешних вызовов

Создать `tools/retry.py`:

```python
import asyncio
import functools
from typing import Type, Tuple

def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Асинхронный retry с exponential backoff + jitter."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries - 1:
                        raise
                    delay = min(base_delay * 2 ** attempt, max_delay)
                    await asyncio.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
```

**Применить к:**
- `data/moex.py` — все запросы к MOEX ISS API
- `agents/llm.py` — запросы к LM Studio
- `data/news.py` — парсинг новостных сайтов
- `integrations/telegram.py` — отправка сообщений

### 1.2 Graceful Degradation

Создать `core/health.py`:

```python
class ServiceHealth:
    llm_available: bool
    moex_available: bool
    db_available: bool
    last_check: datetime
```

- Supervisor проверяет health перед каждым циклом
- Если LLM недоступен — пропустить этот цикл, залогировать, не падать
- Если MOEX API недоступен — использовать кэшированные данные, не падать

### 1.3 Таймауты на все внешние вызовы

- LLM: `aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))`
- MOEX: `timeout=10`
- News scraping: `timeout=15`
- Telegram: `timeout=10`

### 1.4 Circuit Breaker для убыточных стратегий

Добавить в `core/supervisor.py`:

```python
class CircuitBreaker:
    max_consecutive_losses: int = 5
    cooldown_cycles: int = 10
    cooldown_until: Optional[datetime] = None
```

- Если стратегия показала N убыточных сделок подряд — перевести её в cooldown
- Не предлагать новые сделки по ней в течение M циклов
- Сбросить счётчик после успешной сделки

---

## Этап 2: Security (3–4 дня)

### 2.1 Input Validation

Добавить Pydantic-валидацию для всех точек входа:

- `agents/base.py` — валидация ticker-строк (только допустимые MOEX тикеры)
- `ui/` — все поля ввода в Gradio должны проходить через Pydantic
- `integrations/telegram.py` — валидация команд от пользователя

### 2.2 Secrets Management

- Добавить проверку наличия всех обязательных переменных в `.env` при старте
- Никогда не логировать сырые значения secrets (только `***`)
- Добавить `secrets.py`:

```python
from pydantic import SecretStr

class Secrets(BaseSettings):
    MOEX_TOKEN: SecretStr
    TELEGRAM_BOT_TOKEN: SecretStr
    SENTRY_DSN: SecretStr = ""
    LLM_API_KEY: SecretStr = ""

    def log_safe(self):
        return {
            k: (v if not isinstance(v, SecretStr) else "***")
            for k, v in self.dict().items()
        }
```

### 2.3 API Authentication Checks

При старте проверять:
- `MOEX_TOKEN` — тестовый запрос к ISS API (`/eng/stock/...`)
- `LLM_API_KEY` — тестовый запрос к `/v1/models`
- `TELEGRAM_BOT_TOKEN` — `getMe()` через Telegram API

При неудаче — WARN в лог, continue (не блокировать, но предупредить).

---

## Этап 3: Trade Safety (3–4 дня)

### 3.1 Idempotency для ордеров

Добавить поле `idempotency_key` в модель `Order`:

```sql
ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR(64) UNIQUE;
```

Генерация: `sha256(f"{ticker}_{action}_{quantity}_{date}_{session_id}")`

В executor: перед отправкой ордера проверить, нет ли уже ордера с таким же ключом.

### 3.2 Trade Reconciliation

Добавить модуль `core/reconciliation.py`:

```python
async def reconcile():
    """Сравнивает наши ордера с фактическими позициями у брокера."""
    local_positions = await get_local_positions()
    broker_positions = await get_broker_positions()
    
    for ticker in all_tickers:
        local_qty = local_positions.get(ticker, 0)
        broker_qty = broker_positions.get(ticker, 0)
        if local_qty != broker_qty:
            logger.error(f"Reconciliation mismatch: {ticker}: {local_qty} vs {broker_qty}")
            # Отправить алерт в Telegram
```

Запускать после каждого цикла (только в live mode).

### 3.3 Paper/Live Mode Isolation

Добавить `trading_mode` в конфиг:

```python
class TradingMode(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"
```

- В `PAPER` режиме:
  - Ордера НЕ отправляются брокеру
  - Все исполнения симулируются
  - Максимальный депозит виртуальный
  - В логе префикс `[PAPER]`

- В `LIVE` режиме:
  - Ордера отправляются реальному брокеру
  - Reconciliation обязателен
  - Лимит на количество сделок в день (конфигурируется)

Блокировка: при первом запуске в `LIVE` — запросить подтверждение через Telegram/консоль.

### 3.4 Maximum Drawdown Limit

Добавить в `core/supervisor.py`:

```python
max_daily_drawdown: float = 0.05  # 5% от портфеля
max_total_drawdown: float = 0.15  # 15% от портфеля
```

При превышении — аварийная остановка торговли, алерт через Telegram.

---

## Этап 4: Observability & Monitoring (3–4 дня)

### 4.1 Structured Logging

Заменить текущий логгер на `structlog`:

```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
```

Все логи в JSON — легко парсить через Logstash/Datadog/ELK.

### 4.2 Health Check Endpoint

Добавить в `ui/server.py`:

```python
@routes.get("/health")
async def health_check():
    return jsonify({
        "status": "ok",
        "services": {
            "llm": health.llm_available,
            "moex": health.moex_available,
            "db": health.db_available,
        },
        "uptime": str(datetime.now() - start_time),
        "last_cycle": str(supervisor.last_cycle_time),
        "trading_mode": config.trading_mode,
    })
```

### 4.3 Sentry Integration (апгрейд)

```python
import sentry_sdk
from sentry_sdk.integrations.loguru import LoguruIntegration

sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    traces_sample_rate=0.2,  # 20% транзакций
    profiles_sample_rate=0.1,
    environment=config.ENVIRONMENT,
    release=__version__,
)
```

Добавить capture для:
- Failed trading cycles
- Uncaught exceptions в корутинах
- Reconciliation errors
- Circuit breaker triggers

### 4.4 Метрики для Prometheus

Добавить `tools/metrics.py`:

```python
from prometheus_client import Counter, Histogram, Gauge

cycles_total = Counter("trading_cycles_total", "Total trading cycles", ["status"])
orders_total = Counter("orders_total", "Total orders", ["side", "status"])
llm_latency = Histogram("llm_request_duration_seconds", "LLM request latency")
portfolio_value = Gauge("portfolio_value_usd", "Current portfolio value")
```

Экспортировать через `/metrics` endpoint в Gradio/uvicorn.

### 4.5 Telegram Alerts

- Настройка алертов на критические события:
  - Circuit breaker activated
  - Reconciliation mismatch
  - Max drawdown exceeded
  - LLM/MOEX unavailable > 5 минут
  - Новая версия кода (CI/CD deploy)

---

## Этап 5: Database & Migrations (2–3 дня)

### 5.1 Сделать миграции идемпотентными

Проверить и исправить `alembic/versions/*`:

```python
# Вместо:
op.create_table("orders", ...)
# Использовать:
if not inspector.has_table("orders"):
    op.create_table("orders", ...)
```

### 5.2 Добавить Foreign Key Constraints

- `orders.user_id → users.id`
- `orders.account_id → accounts.id`
- `trades.order_id → orders.id`
- `agent_logs.cycle_id → trading_cycles.id`

### 5.3 Connection Pooling

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    config.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,   # Пересоздание соединения через час
)
```

### 5.4 Data Retention & Cleanup

Добавить задачу очистки старых данных:

```python
async def cleanup_old_data(retention_days=90):
    """Удаляет записи старше N дней."""
    cutoff = datetime.now() - timedelta(days=retention_days)
    await db.execute(delete(AgentLog).where(AgentLog.created_at < cutoff))
    await db.execute(delete(Order).where(Order.created_at < cutoff and Order.status == 'filled'))
```

---

## Этап 6: Testing & CI/CD (1 неделя)

### 6.1 Unit Tests для агентов

`tests/test_analyst.py`, `tests/test_trader.py`, `tests/test_critic.py`:

```python
@pytest.mark.asyncio
async def test_analyst_research(mock_llm, mock_moex):
    analyst = AnalystAgent(...)
    result = await analyst.research("SBER")
    assert result is not None
    assert "ticker" in result
    assert "analysis" in result
    mock_llm.assert_called_once()
```

### 6.2 Integration Tests

`tests/test_integration.py`:

```python
@pytest.mark.integration
async def test_full_cycle():
    supervisor = Supervisor(...)
    result = await supervisor.run_cycle()
    assert result.success
    assert len(result.proposals) > 0
```

### 6.3 Mocking Strategy

Создать `tests/mocks/`:

- `mock_llm.py` — возвращает предопределённые JSON-ответы
- `mock_moex.py` — возвращает закэшированные данные по тикерам
- `mock_broker.py` — симулирует исполнение ордеров

### 6.4 CI/CD Pipeline

`.github/workflows/test.yml`:

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-dev.txt
      - run: pytest --cov=agents --cov=core --cov=data --cov-report=term-missing
      - run: ruff check .
      - run: mypy .
```

`.github/workflows/deploy.yml` (условный):

```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to server
        run: |
          rsync -avz --delete ./ user@server:/app/
          ssh user@server "cd /app && docker-compose up -d --build"
```

### 6.5 Pre-commit Hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
```

---

## Этап 7: Code Quality & Refactoring (3–4 дня)

### 7.1 Type Hints Coverage

- Пройтись по всем файлам, добавить пропущенные type hints
- Включить `mypy --strict` в CI
- Особое внимание: `agents/*.py`, `core/supervisor.py`, `data/moex.py`

### 7.2 Исправить sync-in-async в stream/

В `stream/server.py`:

```python
# ВМЕСТО:
db_session = Session()

# ИСПОЛЬЗОВАТЬ:
async with AsyncSession() as session:
    ...
```

### 7.3 Вынести prompts в конфиг

- `config/prompts/analyst.md`
- `config/prompts/trader.md`
- `config/prompts/critic.md`
- `config/prompts/summarizer.md`

Загружать через `PromptManager`:

```python
class PromptManager:
    @staticmethod
    def load(prompt_name: str, **kwargs) -> str:
        path = Path(f"config/prompts/{prompt_name}.md")
        template = path.read_text()
        return template.format(**kwargs)
```

### 7.4 Добавить `__init__.py` и публичное API

- Определить `__all__` в каждом `__init__.py`
- Создать публичный API для внешнего использования (например, для Telegram бота)

### 7.5 Документировать архитектуру

Добавить docstrings ко всем публичным классам и методам (Google-style):

```python
class Supervisor:
    """Оркестратор trading cycle.
    
    Отвечает за последовательный вызов агентов и выполнение ордеров.
    Каждый цикл: Research -> Signal -> Execute -> Reconcile.
    """
```

---

## Этап 8: Производственное развертывание (3–4 дня)

### 8.1 Docker-контейнеризация

`Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml`:

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
    restart: unless-stopped
    
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: trading
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  pgdata:
```

### 8.2 Supervisor / systemd

`trading-agents.service`:

```ini
[Unit]
Description=Trading Agents
After=network.target

[Service]
Type=simple
User=trading
WorkingDirectory=/app
ExecStart=/app/.venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 8.3 Backup Strategy

- Ежедневный бэкап SQLite/PostgreSQL
- Еженедельный бэкап конфигурации
- Retention: 30 дней

### 8.4 Runbook

Создать `RUNBOOK.md`:

- Как запустить
- Как остановить
- Как обновить
- Что делать при падении
- Куда смотреть логи
- Как откатить миграцию

---

## Итоговая карта

| Этап | Время | Критичность | Результат |
|------|-------|-------------|-----------|
| 0: Быстрые победы | 1–2 дня | 🔴 | Чистый код, безопасный конфиг |
| 1: Error Handling | 1 неделя | 🔴 | Не падает при отказах внешних сервисов |
| 2: Security | 3–4 дня | 🔴 | Валидация, secrets, auth checks |
| 3: Trade Safety | 3–4 дня | 🔴 | Нет дублей, контроль рисков |
| 4: Observability | 3–4 дня | 🟡 | JSON-логи, Sentry, метрики, алерты |
| 5: Database | 2–3 дня | 🟡 | Идемпотентность, FK, pool |
| 6: Testing & CI/CD | 1 неделя | 🟡 | Тесты, авто-проверки, деплой |
| 7: Code Quality | 3–4 дня | 🟢 | Type hints, рефакторинг |
| 8: Deploy | 3–4 дня | 🟢 | Docker, backup, runbook |

**Итого: ~4–6 недель** при full-time работе одного разработчика.

**Score после всех этапов: 8.5–9 / 10**

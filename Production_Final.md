# Production Readiness Plan — Trading Agents

**Current score: 6.0 / 10**  
**Target: 9.0 / 10**

---

## Этапы

| Этап | Время | Оценка после | Результат |
|------|-------|-------------|-----------|
| [0. Foundation](#0-foundation) | 15 мин | 6.5 → 7.5 | Git, структура |
| [1. Version Control & CI](#1-version-control--ci) | 1 день | 7.5 → 8.5 | GitHub Actions, ruff, pytest |
| [2. Containerization & Deploy](#2-containerization--deploy) | 1 день | 8.5 → 9.0 | Docker, docker-compose, systemd |
| [3. Code Quality — God Methods](#3-code-quality--god-methods) | 1 день | — | Рефакторинг supervisor, risk_manager |
| [4. Testing](#4-testing) | 2–3 дня | — | Supervisor, Risk Manager, Core |
| [5. Infrastructure Hardening](#5-infrastructure-hardening) | 1 день | — | Бэкапы, логи, мониторинг |
| [6. Security](#6-security) | 1 день | — | Auth, rate-limit, audit |
| [7. Monitoring & Alerting](#7-monitoring--alerting) | 1 день | — | Health-check automation |
| [8. Production Deploy](#8-production-deploy) | 1 день | 9.0 | systemd, supervisor, runbook |

---

## 0. Foundation

**⏱ 15 минут · Без этого ничего не имеет смысла**

```bash
cd C:\Users\User\Desktop\trading_agents
git init
git add -A
git commit -m "feat: initial trading agents system"

# gitignore уже есть — проверить что там data/ и .env
```

**Почему:** без git нет истории, нет отката, нет CI/CD, нет code review. Это базовый слой для всего остального.

**Проверка:** `git log --oneline` показывает хотя бы один коммит.

---

## 1. Version Control & CI

**⏱ 4–6 часов · Оценка после: 8.5**

### 1.1 GitHub репозиторий

```bash
gh repo create trading-agents --private --source=. --remote=origin --push
```

### 1.2 CI Pipeline (`.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install deps
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Ruff
        run: ruff check agents/ tools/ core/ config/ stream/ tests/

      - name: PyTest
        run: python -m pytest tests/ -v --tb=short --cov=agents --cov=tools --cov=core

      - name: Mypy
        run: python -m mypy tools/prompts.py tools/validator.py core/health.py agents/base_agent.py

  notify:
    needs: [quality]
    if: failure()
    runs-on: ubuntu-latest
    steps:
      - name: Telegram alert
        run: |
          curl -s "https://api.telegram.org/bot${{ secrets.TELEGRAM_TOKEN }}/sendMessage" \
            -d "chat_id=${{ secrets.TELEGRAM_CHAT_ID }}" \
            -d "text=❌ CI failed: ${{ github.repository }}@${{ github.sha }}"
```

### 1.3 Pre-commit hooks (уже есть — проверить)

```bash
pre-commit install
pre-commit run --all-files
```

Файл `.pre-commit-config.yaml` уже настроен на ruff + format.

### 1.4 Branch protection (GitHub)

После первого пуша — включить в настройках репозитория:
- Require CI to pass before merge
- Require 1 review for main branch
- Do not allow bypass

**Проверка:** `git push origin main` → Actions run → зеленый статус.

---

## 2. Containerization & Deploy

**⏱ 4–6 часов · Оценка после: 9.0**

### 2.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "main.py", "--stream", "--port", "8000"]
```

### 2.2 docker-compose.yml

```yaml
version: "3.9"

services:
  trading:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
      - ./.env:/app/.env
    env_file: .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: trading
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: ${DB_PASSWORD:-trading}
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    profiles:
      - postgres  # не включается по умолчанию

volumes:
  pgdata:
```

### 2.3 .dockerignore

```
.git/
.gitignore
__pycache__/
*.pyc
data/*.db
data/*.db-*
data/*.log
data/logs/
data/system_state.json
.env
.venv/
adhoc/
```

### 2.4 Windows service (NSSM)

```powershell
# Установка
nssm install TradingAgents "C:\path\to\.venv\Scripts\python.exe" "C:\path\to\trading_agents\main.py --stream --port 8000"
nssm set TradingAgents AppStdout "C:\path\to\trading_agents\data\trading.log"
nssm set TradingAgents AppStderr "C:\path\to\trading_agents\data\trading.log"
nssm set TradingAgents Start SERVICE_AUTO_START
nssm start TradingAgents

# Статус
nssm status TradingAgents

# Стоп
nssm stop TradingAgents
```

### 2.5 systemd (Linux)

Создать `/etc/systemd/system/trading-agents.service`:

```ini
[Unit]
Description=Trading Agents
After=network.target

[Service]
Type=simple
User=trading
Group=trading
WorkingDirectory=/opt/trading_agents
ExecStart=/opt/trading_agents/.venv/bin/python main.py --stream --port 8000
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
EnvironmentFile=/opt/trading_agents/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-agents
sudo systemctl start trading-agents
sudo systemctl status trading-agents
```

**Проверка:** `docker compose up -d` → `curl localhost:8000/health` возвращает 200.

---

## 3. Code Quality — God Methods

**⏱ 1 день**

### 3.1 Рефакторинг `supervisor.py` (1111 строк → ~600)

Текущая архитектура — всё в одном классе. Разделить:

```
agents/
├── supervisor.py           ← оркестратор (~200 строк, только run_trading_cycle + process)
├── cycle_runner.py         ← вынесенный цикл с шагами
├── proposal_pipeline.py    ← _process_proposal (критик → риск → портфель → исполнение)
└── position_monitor.py     ← SL/TP, трейлинг, маржин, drawdown
```

**Паттерн миграции:**
1. Создать `cycle_runner.py` — перенести туда `run_trading_cycle` (510 строк)
2. Создать `proposal_pipeline.py` — перенести `_process_proposal` (172 строки)
3. Создать `position_monitor.py` — перенести проверки SL/TP, drawdown, margin, profit locker
4. В `supervisor.py` оставить только `__init__` + делегирование

### 3.2 Рефакторинг `risk_manager.py:process` (389 строк → ~150)

```python
def process(self, input_data: dict) -> dict:
    action = input_data.get("proposal", {}).get("action")
    handler = {
        "LONG_OPEN": self._handle_long_open,
        "SHORT_OPEN": self._handle_short_open,
        "LONG_CLOSE": self._handle_long_close,
        "SHORT_CLOSE": self._handle_short_close,
    }
    handler_func = handler.get(action, self._handle_unknown)
    return handler_func(input_data)
```

Создать отдельные методы-обработчики для каждого action типа. Каждый — 30–50 строк вместо 389.

### 3.3 Удалить `adhoc/` из репозитория (опционально)

21 файл, ~2,500 LOC, никем не используется.

```bash
git rm -r adhoc/
git commit -m "chore: remove ad-hoc test scripts from repo"
```

Или оставить для истории — решать вам.

**Проверка:** `ruff check agents/` → 0 errors. `pytest tests/` → 42 passed.

---

## 4. Testing

**⏱ 2–3 дня**

### 4.1 Supervisor cycle test (самое важное)

**Файл:** `tests/test_supervisor_cycle.py`

```python
"""Tests for SupervisorAgent trading cycle."""


def test_cycle_skipped_when_llm_down(mock_llm, paper_config):
    """LLM недоступен → цикл пропущен, не падать."""
    mock_llm._available = False
    ...


def test_cycle_runs_full_pipeline(mock_llm, mock_tinvest, paper_config):
    """Полный цикл: новости → стратегия → критик → риск → портфель → исполнение."""
    ...


def test_drawdown_halts_trading(mock_llm, paper_config):
    """Превышен max_total_drawdown → цикл остановлен."""
    ...


def test_margin_liquidation(mock_llm, paper_config):
    """Margin ниже порога → принудительная ликвидация."""
    ...


def test_profit_locker_closes_all(mock_llm, paper_config):
    """Достигнут profit_target → все позиции закрыты."""
    ...
```

### 4.2 Risk manager tests

**Файл:** `tests/test_risk_manager_full.py`

```python
def test_long_position_sizing(): ...
def test_short_position_sizing(): ...
def test_daily_loss_limit(): ...
def test_rr_ratio_rejection(): ...
def test_commission_check(): ...
def test_margin_check(): ...
def test_performance_adjustment(): ...
```

### 4.3 Core module tests

**Файл:** `tests/test_core.py`

```python
def test_fsm_transitions(): ...       # TradingCycleFSM
def test_fsm_invalid_transition(): ...
def test_message_bus_pub_sub(): ...   # MessageBus
def test_system_state_persistence(): ...  # SystemState
def test_health_check(): ...          # ServiceHealth
def test_reconciliation(): ...        # reconcile
```

### 4.4 Integration test (1 файл)

**Файл:** `tests/test_integration.py`

```python
@pytest.mark.integration
def test_full_cycle_pipeline(mock_llm, mock_tinvest, paper_config):
    """Сквозной тест: proposal → critic → risk → portfolio → execution."""
    ...
```

### 4.5 Целевые метрики покрытия

| Модуль | Текущее | Цель |
|--------|---------|------|
| `agents/supervisor.py` | 0% | 60% |
| `agents/risk_manager.py` | 15% | 70% |
| `tools/memory.py` | 0% | 50% |
| `core/orchestrator.py` | 0% | 90% |
| `core/state.py` | 0% | 80% |
| `core/health.py` | 0% | 80% |
| `stream/broadcaster.py` | 0% | 60% |
| **Общее** | **~8%** | **> 40%** |

**Проверка:** `pytest tests/ --cov --cov-report=term-missing` показывает > 40%.

---

## 5. Infrastructure Hardening

**⏱ 1 день**

### 5.1 Backup

Создать `scripts/backup.ps1`:

```powershell
param(
    [string]$BackupDir = "C:\Backups\TradingAgents",
    [int]$RetentionDays = 30
)

$date = Get-Date -Format "yyyyMMdd-HHmmss"
$db = "C:\Trading\data\trading_memory.db"
$state = "C:\Trading\data\system_state.json"
$config = "C:\Trading\config\settings.yaml"
$envFile = "C:\Trading\.env"

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

# Backup DB
if (Test-Path $db) {
    Copy-Item $db "$BackupDir\trading_memory_$date.db"
    Write-Host "DB backed up: $BackupDir\trading_memory_$date.db"
}

# Backup state
if (Test-Path $state) {
    Copy-Item $state "$BackupDir\system_state_$date.json"
}

# Backup config
Copy-Item $config "$BackupDir\settings_$date.yaml"
Copy-Item $envFile "$BackupDir\.env_$date"

# Clean old
Get-ChildItem $BackupDir -Filter "*.db" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays)
} | Remove-Item

Write-Host "Backup complete. Retention: $RetentionDays days"
```

Настроить в Task Scheduler: ежедневно в 03:00.

Для Linux — cron:
```bash
0 3 * * * /opt/trading_agents/scripts/backup.sh
```

### 5.2 Log rotation

В `core/logging_setup.py` уже есть ротация. Проверить:

```python
# Должно быть (уже есть):
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler("data/trading.log", maxBytes=10*1024*1024, backupCount=5)
```

### 5.3 Graceful shutdown

В `stream/server.py` уже есть `lifespan` context manager. Убедиться что при `SIGTERM`:

1. Завершается текущий цикл (или прерывается по timeout)
2. Сохраняется state
3. Закрываются соединения (LLM, T-Invest, SQLite)

### 5.4 Resource limits

```yaml
# В settings.yaml добавить:
resources:
  max_memory_mb: 4096
  max_cpu_percent: 80
  max_disk_gb: 10
```

**Проверка:** `scripts/backup.ps1` создаёт файл в `C:\Backups\`.

---

## 6. Security

**⏱ 1 день**

### 6.1 Dashboard аутентификация

В `stream/server.py` добавить basic auth на все маршруты:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

@app.get("/")
async def index(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != secrets.DASHBOARD_USERNAME:
        raise HTTPException(status_code=401)
    if credentials.password != secrets.DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401)
    ...
```

Добавить в `.env`:
```env
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<random_password>
```

### 6.2 Rate limiting

Через middleware:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/health")
@limiter.limit("10/minute")
async def health():
    ...
```

### 6.3 Audit log

Добавить логирование всех API запросов:

```python
@app.middleware("http")
async def audit_log(request, call_next):
    logger.info(f"API: {request.method} {request.url.path} from {request.client.host}")
    response = await call_next(request)
    return response
```

### 6.4 Secrets rotation

- Пароль дашборда менять каждые 90 дней
- T-Invest токен — не хранить в git (уже в .env, .env в .gitignore)
- Никогда не логировать `.env` значения (уже сделано в `secrets.py`)

**Проверка:** `curl localhost:8000/` без авторизации возвращает 401.

---

## 7. Monitoring & Alerting

**⏱ 1 день**

### 7.1 Uptime monitoring

UptimeRobot / Better Uptime: проверить `GET /health` каждые 5 минут.
Алерт если ответ не 200 в течение 2 минут.

```yaml
# alerts.yml для UptimeRobot:
monitors:
  - name: Trading Agents Health
    url: https://your-server.com/health
    interval: 300
    timeout: 30
    alert_contacts:
      - telegram: "@username"
```

### 7.2 Prometheus + Grafana

В `tools/metrics.py` уже есть метрики. Добавить в docker-compose:

```yaml
prometheus:
  image: prom/prometheus
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
  depends_on:
    - prometheus
```

Grafana dashboard: portfolio_value, drawdown_percent, orders_total, llm_latency.

### 7.3 Watchdog

Создать `scripts/watchdog.py`:

```python
"""Проверяет что система работает. Запускать по cron каждые 5 минут."""
import urllib.request
import sys

try:
    resp = urllib.request.urlopen("http://localhost:8000/health", timeout=10)
    data = json.loads(resp.read())
    if data["status"] != "ok":
        print(f"UNHEALTHY: {data}")
        sys.exit(1)
    print(f"OK: uptime={data.get('uptime')}, mode={data.get('trading_mode')}")
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
```

### 7.4 Sentry alerts

Уже настроено. Проверить:
```python
# main.py (уже есть)
if secrets.SENTRY_DSN:
    sentry_sdk.init(dsn=secrets.SENTRY_DSN, ...)
```

Добавить capture для:
- Каждый `run_trading_cycle` — транзакция в Sentry
- Каждый rejection proposal — breadcrumb
- Каждый error в цикле — capture_exception

### 7.5 Telegram alerts (уже есть)

Проверить что алерты приходят на:

| Событие | Уровень |
|---------|---------|
| System start/stop | info |
| Drawdown limit | warning |
| Cycle failure | error |
| Reconciliation mismatch | critical |
| Circuit breaker triggered | warning |
| LLM unavailable > 5 checks | critical |

**Проверка:** отключить LM Studio → через 5 циклов приходит алерт в Telegram.

---

## 8. Production Deploy

**⏱ 1 день · Финальная оценка: 9.0**

### 8.1 Чеклист перед деплоем

```markdown
- [ ] git init + first commit
- [ ] GitHub repo created
- [ ] CI passes on push
- [ ] Docker build succeeds
- [ ] docker-compose up работает локально
- [ ] .env заполнен (не дефолтный)
- [ ] PAPER_TRADING=true (ещё не live)
- [ ] Backup script установлен
- [ ] Log rotation работает
- [ ] Dashboard auth включена
- [ ] Health-check отвечает
- [ ] Uptime monitor настроен
- [ ] Sentry DSN настроен
- [ ] Telegram bot активен
- [ ] Systemd/NSSM service установлен
- [ ] All 42+ pytest тестов проходят
- [ ] ruff 0 errors
```

### 8.2 Первый запуск на сервере

```bash
git clone git@github.com:user/trading-agents.git
cd trading-agents

# Настройка
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env  # заполнить

# Проверка
python main.py  # один цикл, убедиться что работает

# Деплой
sudo systemctl start trading-agents
sudo systemctl status trading-agents

# Docker вариант
docker compose up -d
docker compose logs -f
```

### 8.3 Процесс обновления

```bash
# 1. Pull
git pull origin main

# 2. Проверить зависимости
pip install -r requirements.txt --upgrade

# 3. Миграции БД (если есть)
alembic upgrade head

# 4. Перезапуск
sudo systemctl restart trading-agents
# или
docker compose up -d --build
```

### 8.4 Rollback план

```bash
# Git rollback
git revert HEAD --no-edit
git push

# Restart
sudo systemctl restart trading-agents

# Если БД мигрировала
alembic downgrade -1

# Restore from backup
copy C:\Backups\trading_memory_20250101.db data\trading_memory.db
```

### 8.5 Финальный чек-лист "Готов к production"

```markdown
- [ ] **Система под version control** (git + GitHub)
- [ ] **CI прогоняет тесты + lint** при каждом push
- [ ] **Docker образ собирается** и публикуется
- [ ] **docker-compose поднимает** весь стек одной командой
- [ ] **Backup БД** настроен и проверен
- [ ] **Log rotation** активен
- [ ] **Graceful shutdown** — система не теряет данные при stop
- [ ] **Health-check** доступен и используется мониторингом
- [ ] **Uptime monitor** опрашивает /health каждые 5 минут
- [ ] **Telegram/Sentry алерты** приходят на критические ошибки
- [ ] **Dashboard защищён** паролем (basic auth)
- [ ] **Secrets в .env**, .env в .gitignore
- [ ] **systemd/NSSM** — автозапуск при перезагрузке
- [ ] **Покрытие тестами > 40%**
- [ ] **God-методы разбиты** (supervisor, risk_manager)
- [ ] **Актуальный RUNBOOK** лежит рядом с кодом
```

---

## Сводная карта

```
Этап 0: Foundation          ████████████████░░░░  15 мин    [DONE]
Этап 1: Version Control     ████████████████░░░░  1 день    [PENDING]
Этап 2: Containerization    ████████████████░░░░  1 день    [PENDING]
Этап 3: God Methods         ████████████████░░░░  1 день    [PENDING]
Этап 4: Testing             ████████████████████░  2-3 дня  [PENDING]
Этап 5: Infrastructure      ████████████████░░░░  1 день    [PENDING]
Этап 6: Security            ████████████████░░░░  1 день    [PENDING]
Этап 7: Monitoring          ████████████████░░░░  1 день    [PENDING]
Этап 8: Production Deploy   ████████████████░░░░  1 день    [PENDING]
                                                         ─────────
                     Всего:                              ~9-10 дней
```

### Текущее состояние vs Production

```
Сейчас:    Функциональность ████████░░  Инфраструктура ███░░░░░░░  Тесты ███░░░░░░░
Цель:      Функциональность █████████░  Инфраструктура ████████░░  Тесты ████████░░
```

**6.0 → 9.0 за ~10 дней full-time.**

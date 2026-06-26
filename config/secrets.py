"""Centralized secrets management with Pydantic BaseSettings."""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class Secrets(BaseSettings):
    TINVEST_TOKEN: str = ""
    TINVEST_ACCOUNT_ID: str = ""
    LMSTUDIO_HOST: str = "http://localhost:1234"
    NEWS_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SENTRY_DSN: str = ""
    INITIAL_CAPITAL: float = 100000.0
    MAX_DAILY_LOSS_PERCENT: float = 2.0
    PAPER_TRADING: bool = True

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def log_safe(self) -> dict:
        """Return secrets dict with sensitive values masked."""
        result = {}
        for k, v in self.model_dump().items():
            if "TOKEN" in k or "SECRET" in k or "KEY" in k:
                result[k] = v[:4] + "..." if v and len(v) > 4 else ""
            else:
                result[k] = v
        return result

    def verify_auth(self) -> dict[str, bool]:
        """Verify external service tokens on startup. Returns {service: ok} dict."""
        results = {}

        if self.TINVEST_TOKEN:
            try:
                from tinkoff.invest import Client
                with Client(token=self.TINVEST_TOKEN) as client:
                    client.instruments.find_instrument(query="SBER")
                results["tinvest"] = True
                logger.info("T-Invest token verified")
            except Exception as e:
                results["tinvest"] = False
                logger.warning(f"T-Invest token verification failed: {e}")
        else:
            results["tinvest"] = False
            logger.warning("T-Invest token not configured")

        if self.TELEGRAM_BOT_TOKEN:
            try:
                import httpx
                resp = httpx.get(
                    f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/getMe",
                    timeout=10.0,
                )
                results["telegram"] = resp.status_code == 200 and resp.json().get("ok", False)
                if results["telegram"]:
                    bot_name = resp.json().get("result", {}).get("first_name", "unknown")
                    logger.info(f"Telegram bot verified: {bot_name}")
                else:
                    logger.warning("Telegram bot token verification failed")
            except Exception as e:
                results["telegram"] = False
                logger.warning(f"Telegram verification error: {e}")
        else:
            results["telegram"] = False
            logger.info("Telegram bot not configured — alerts disabled")

        if self.LMSTUDIO_HOST:
            try:
                import httpx
                resp = httpx.get(f"{self.LMSTUDIO_HOST}/v1/models", timeout=5.0)
                results["lmstudio"] = resp.status_code == 200
                if results["lmstudio"]:
                    logger.info(f"LM Studio available at {self.LMSTUDIO_HOST}")
                else:
                    logger.warning(f"LM Studio returned status {resp.status_code}")
            except Exception as e:
                results["lmstudio"] = False
                logger.warning(f"LM Studio not available at {self.LMSTUDIO_HOST}: {e}")
        else:
            results["lmstudio"] = False
            logger.warning("LM Studio host not configured")

        return results


secrets = Secrets()

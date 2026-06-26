"""Служебные инструменты."""

import logging

from config.secrets import secrets

logger = logging.getLogger(__name__)


def send_alert(message: str, severity: str = "info") -> None:
    """Отправляет уведомление (Telegram, email).

    severity: 'info', 'warning', 'critical'
    """
    # Telegram
    bot_token = secrets.TELEGRAM_BOT_TOKEN
    chat_id = secrets.TELEGRAM_CHAT_ID

    if bot_token and chat_id:
        try:
            import httpx
            emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity, "📢")
            text = f"{emoji} [{severity.upper()}]\n{message}"
            httpx.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10.0,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    # Всегда логируем
    log_level = {
        "info": logging.INFO,
        "warning": logging.WARNING,
        "critical": logging.CRITICAL,
    }.get(severity, logging.INFO)
    logger.log(log_level, f"ALERT: {message}")

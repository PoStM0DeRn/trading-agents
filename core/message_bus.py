"""Шина сообщений для обмена данными между агентами."""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Message:
    """Структурированное сообщение между агентами."""

    def __init__(
        self,
        msg_type: str,
        sender: str,
        data: dict,
        recipient: Optional[str] = None,
    ):
        self.type = msg_type
        self.sender = sender
        self.recipient = recipient
        self.data = data
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.id = f"{sender}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "sender": self.sender,
            "recipient": self.recipient,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        msg = cls(
            msg_type=d.get("type", ""),
            sender=d.get("sender", ""),
            data=d.get("data", {}),
            recipient=d.get("recipient"),
        )
        msg.timestamp = d.get("timestamp", msg.timestamp)
        msg.id = d.get("id", msg.id)
        return msg

    def __repr__(self):
        return f"<Message: {self.type} from {self.sender}>"


class MessageBus:
    """Шина сообщений для агентов."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: list[Message] = []

    def subscribe(self, msg_type: str, callback: Callable):
        """Подписка на тип сообщения."""
        if msg_type not in self._subscribers:
            self._subscribers[msg_type] = []
        self._subscribers[msg_type].append(callback)

    def publish(self, message: Message):
        """Публикация сообщения."""
        self._history.append(message)
        logger.debug(f"Message published: {message}")

        # Уведомляем подписчиков
        subscribers = self._subscribers.get(message.type, [])
        for callback in subscribers:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Subscriber callback failed: {e}")

        # Уведомляем подписчиков на все сообщения
        all_subscribers = self._subscribers.get("*", [])
        for callback in all_subscribers:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Wildcard subscriber failed: {e}")

    def get_history(
        self,
        msg_type: Optional[str] = None,
        sender: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Получить историю сообщений."""
        messages = self._history

        if msg_type:
            messages = [m for m in messages if m.type == msg_type]
        if sender:
            messages = [m for m in messages if m.sender == sender]

        return [m.to_dict() for m in messages[-limit:]]

    def clear_history(self):
        """Очистка истории."""
        self._history.clear()

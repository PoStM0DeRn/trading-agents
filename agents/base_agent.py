"""Базовый класс для всех агентов."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from integrations.lmstudio_client import LMStudioClient
from tools.validator import validate_ticker, validate_positive_number, validate_action, validate_side

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Базовый класс агента с LLM и инструментами."""

    def __init__(
        self,
        name: str,
        llm_client: LMStudioClient,
        system_prompt: str = "",
        tools: dict = None,
    ):
        self.name = name
        self.llm = llm_client
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self._conversation_history: list[dict] = []

    @classmethod
    def _build_tools(cls, default: dict, override: dict | None = None) -> dict:
        if override:
            default.update(override)
        return default

    def _call_llm(self, user_message: str, context: dict = None) -> dict:
        """Вызов LLM с системным промптом и контекстом."""
        prompt = user_message
        if context:
            prompt = f"Context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\nTask:\n{user_message}"

        response = self.llm.generate_json(prompt, system=self.system_prompt)
        return response

    def _call_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a registered tool by name with given kwargs.

        Args:
            tool_name: Name of the tool to call.
            **kwargs: Arguments to pass to the tool function.

        Returns:
            Any: Result returned by the tool function.

        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not available for {self.name}")

        tool_func = self.tools[tool_name]
        logger.info(f"[{self.name}] Calling tool: {tool_name}({kwargs})")
        result = tool_func(**kwargs)
        logger.info(f"[{self.name}] Tool result: {str(result)[:200]}")
        return result

    def _format_message(self, msg_type: str, data: dict) -> dict:
        """Format a structured response message with type and agent name.

        Args:
            msg_type: The message type identifier.
            data: Dictionary of data to include in the message.

        Returns:
            dict: Formatted message dict with type, agent name, and data.

        """
        return {
            "type": msg_type,
            "agent": self.name,
            **data,
        }

    def log_action(self, input_data: dict, output_data: dict, tool_calls: list = None, action: str = "process"):
        """Log agent action to the database via tools.service.log_agent_action.

        Args:
            input_data: Input data received by the agent.
            output_data: Output data produced by the agent.
            tool_calls: List of tool calls made during processing. Defaults to None.
            action: Action name describing what was performed.

        """
        from tools.memory import log_agent_action
        log_agent_action(
            agent_name=self.name,
            action=action,
            input_data=input_data,
            output_data=output_data,
            tool_calls=tool_calls or [],
        )

    def _validate_ticker(self, ticker: str) -> str:
        """Validate and normalize a ticker string."""
        return validate_ticker(ticker)

    def _validate_positive(self, value, name: str) -> float:
        """Validate a positive number."""
        return validate_positive_number(value, name)

    def _validate_action(self, action: str) -> str:
        """Validate a trading action."""
        return validate_action(action)

    def _validate_side(self, side: str) -> str:
        """Validate an order side."""
        return validate_side(side)

    @abstractmethod
    def process(self, input_data: dict) -> dict:
        """Основной метод обработки. Каждый агент реализует свою логику."""
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"

"""Mock LLM client for testing."""

import json


class MockLLMClient:
    def __init__(self, response: str = None):
        self._response = response or json.dumps({"action": "HOLD", "confidence": 0.5, "rationale": "test"})
        self._available = True

    def is_available(self) -> bool:
        return self._available

    def set_available(self, available: bool):
        self._available = available

    def chat(self, messages: list, **kwargs) -> dict:
        return {"choices": [{"message": {"content": self._response}}]}

    def set_on_request(self, callback):
        pass

    def close(self):
        pass

"""LM Studio monitoring — speed, tokens, GPU metrics."""

import time
import logging
import subprocess
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMRequestResult:
    """Результат одного запроса к LLM."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed_time: float = 0.0
    tokens_per_sec: float = 0.0
    timestamp: float = 0.0


class LMStudioMonitor:
    """Трекинг метрик LM Studio: скорость, токены, GPU."""

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.history: deque[LLMRequestResult] = deque(maxlen=window_size)
        self.total_requests: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self._gpu_cache: dict = {}
        self._gpu_cache_time: float = 0
        self._gpu_cache_ttl: float = 5.0

    def record(self, response: dict, elapsed: float):
        """Записать результат запроса к LLM."""
        usage = response.get("usage", {})
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", prompt + completion)
        speed = completion / elapsed if elapsed > 0 else 0

        result = LLMRequestResult(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            elapsed_time=elapsed,
            tokens_per_sec=speed,
            timestamp=time.time(),
        )
        self.history.append(result)
        self.total_requests += 1
        self.total_prompt_tokens += prompt
        self.total_completion_tokens += completion

        logger.debug(
            f"LLM request: {completion} tokens in {elapsed:.2f}s "
            f"({speed:.1f} tok/s)"
        )

    def get_stats(self) -> dict:
        """Текущая статистика генерации."""
        if not self.history:
            return {
                "status": "no_data",
                "tokens_per_sec": 0,
                "avg_tokens_per_sec": 0,
                "min_tokens_per_sec": 0,
                "max_tokens_per_sec": 0,
                "last_prompt_tokens": 0,
                "last_completion_tokens": 0,
                "last_response_time": 0,
                "total_requests": self.total_requests,
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "speed_history": [],
            }

        speeds = [r.tokens_per_sec for r in self.history]
        last = self.history[-1]

        return {
            "status": "active",
            "tokens_per_sec": round(last.tokens_per_sec, 1),
            "avg_tokens_per_sec": round(sum(speeds) / len(speeds), 1),
            "min_tokens_per_sec": round(min(speeds), 1),
            "max_tokens_per_sec": round(max(speeds), 1),
            "last_prompt_tokens": last.prompt_tokens,
            "last_completion_tokens": last.completion_tokens,
            "last_response_time": round(last.elapsed_time, 2),
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "speed_history": [round(s, 1) for s in speeds],
        }

    def get_gpu_info(self) -> dict:
        """Получить информацию о GPU (NVIDIA или AMD)."""
        now = time.time()
        if now - self._gpu_cache_time < self._gpu_cache_ttl and self._gpu_cache:
            return self._gpu_cache

        gpu_info = self._try_nvidia_smi()
        if gpu_info:
            self._gpu_cache = gpu_info
            self._gpu_cache_time = now
            return self._gpu_cache

        gpu_info = self._try_wmi()
        if gpu_info:
            self._gpu_cache = gpu_info
            self._gpu_cache_time = now
            return self._gpu_cache

        return {
            "gpu_utilization": 0,
            "vram_used": 0,
            "vram_total": 0,
            "available": False,
        }

    def _try_nvidia_smi(self) -> Optional[dict]:
        """Попробовать получить GPU info через nvidia-smi (NVIDIA)."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 3:
                    return {
                        "gpu_utilization": int(parts[0]),
                        "vram_used": round(int(parts[1]) / 1024, 1),
                        "vram_total": round(int(parts[2]) / 1024, 1),
                        "available": True,
                    }
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"nvidia-smi failed: {e}")
        return None

    def _try_wmi(self) -> Optional[dict]:
        """Попробовать получить GPU info через WMI (AMD / Intel)."""
        try:
            script_path = Path(__file__).parent / "gpu_query.ps1"
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(script_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None

            vram_total = 0.0
            gpu_util = 0
            for line in result.stdout.strip().splitlines():
                if line.startswith("VRAM="):
                    vram_total = float(line.split("=", 1)[1])
                elif line.startswith("UTIL="):
                    gpu_util = int(line.split("=", 1)[1])

            if vram_total <= 0:
                return None

            return {
                "gpu_utilization": gpu_util,
                "vram_used": 0,
                "vram_total": vram_total,
                "available": True,
            }
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"WMI GPU query failed: {e}")
        return None

    def get_full_status(self, model: str = "unknown", is_online: bool = False) -> dict:
        """Полный статус LM Studio для WebSocket payload."""
        stats = self.get_stats()
        gpu = self.get_gpu_info()

        return {
            "status": "online" if is_online else "offline",
            "model": model,
            **stats,
            "gpu": gpu,
        }


# Глобальный экземпляр монитора
monitor = LMStudioMonitor()

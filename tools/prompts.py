"""Prompt loader — loads system prompts from config/prompts/*.md files."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "config" / "prompts"
_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt from config/prompts/{name}.md with caching."""
    if name not in _cache:
        path = PROMPTS_DIR / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        _cache[name] = path.read_text(encoding="utf-8").strip()
    return _cache[name]


def clear_cache() -> None:
    _cache.clear()

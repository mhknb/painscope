"""Topic configuration — multi-source scan config model and profile loader.

A "topic config" describes a named scan across multiple sources.
Built-in profiles ship with the package. Users can override or add
their own in ~/.painscope/profiles/.

Resolution order for `--profile tr`:
  1. ~/.painscope/profiles/tr.yaml  (user override)
  2. Built-in package profile        (default)
"""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# User-customizable profile directory
USER_PROFILES_DIR = Path.home() / ".painscope" / "profiles"


class SourceConfig(BaseModel):
    """A single source in a topic scan."""

    type: str = Field(description="Adapter name: reddit | youtube | hackernews | appstore | stackexchange | github")
    target: str = Field(description="Source-specific target. Reddit: subreddit name. YouTube: channel_id. App Store: app_id.")
    label: str | None = Field(default=None, description="Human-readable label for reports. Defaults to type:target.")
    language: str | None = Field(default=None, description="Override topic-level language for this source.")
    limit: int | None = Field(default=None, description="Override topic-level limit_per_source for this source.")

    @property
    def resolved_label(self) -> str:
        if self.label:
            return self.label
        if self.type == "reddit":
            return f"r/{self.target}"
        return f"{self.type}:{self.target}"


class TopicConfig(BaseModel):
    """Full configuration for a multi-source topic scan."""

    name: str
    description: str | None = None
    language: str = "tr"
    limit_per_source: int = 200
    top_n: int = 20
    scan_type: Literal["pain_points", "content_ideas"] = "pain_points"
    model: str | None = None
    sources: list[SourceConfig]

    def source_count(self) -> int:
        return len(self.sources)


def _load_yaml(path: Path) -> TopicConfig:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TopicConfig.model_validate(data)


def load_profile(name: str) -> TopicConfig:
    """Load a named profile. User profile overrides built-in if both exist."""

    # 1. User override
    user_path = USER_PROFILES_DIR / f"{name}.yaml"
    if user_path.exists():
        logger.info(f"Loading user profile: {user_path}")
        return _load_yaml(user_path)

    # 2. Built-in package profile (shipped in painscope/profiles/)
    try:
        pkg_files = importlib.resources.files("painscope.profiles")
        profile_file = pkg_files.joinpath(f"{name}.yaml")
        content = profile_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        logger.info(f"Loading built-in profile: {name}")
        return TopicConfig.model_validate(data)
    except (FileNotFoundError, TypeError):
        pass

    available = list_available_profiles()
    raise FileNotFoundError(
        f"Profile {name!r} not found. "
        f"Available built-in profiles: {available}. "
        f"Custom profiles go in: {USER_PROFILES_DIR}"
    )


def load_config_file(path: str | Path) -> TopicConfig:
    """Load a topic config from an arbitrary YAML file path."""
    return _load_yaml(Path(path))


def list_available_profiles() -> list[str]:
    """List available profile names (built-in + user)."""
    names: set[str] = set()

    # Built-in
    try:
        pkg_files = importlib.resources.files("painscope.profiles")
        for item in pkg_files.iterdir():
            if hasattr(item, "name") and item.name.endswith(".yaml"):
                names.add(item.name.removesuffix(".yaml"))
    except Exception:
        pass

    # User
    if USER_PROFILES_DIR.exists():
        for p in USER_PROFILES_DIR.glob("*.yaml"):
            names.add(p.stem)

    return sorted(names)


def save_user_profile(config: TopicConfig, name: str) -> Path:
    """Persist a TopicConfig as a user profile for reuse."""
    USER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_PROFILES_DIR / f"{name}.yaml"
    data = config.model_dump(exclude_none=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return path

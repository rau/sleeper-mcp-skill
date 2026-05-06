"""Runtime configuration for the Sleeper MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_SPORT = "nfl"
DEFAULT_CACHE_TTL_SECONDS = 60
PLAYERS_CACHE_TTL_SECONDS = 24 * 60 * 60


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class SleeperConfig:
    base_url: str
    default_sport: str
    default_user: str | None
    default_user_id: str | None
    default_league_id: str | None
    default_season: str | None
    cache_dir: Path | None
    timeout_seconds: float
    rate_limit_per_minute: int
    user_agent: str

    @classmethod
    def from_env(cls) -> SleeperConfig:
        cache_dir: Path | None
        if _env_bool("SLEEPER_DISABLE_CACHE"):
            cache_dir = None
        else:
            cache_dir = Path(
                os.getenv("SLEEPER_CACHE_DIR", "~/.cache/sleeper-mcp-skill")
            ).expanduser()

        return cls(
            base_url=os.getenv("SLEEPER_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            default_sport=os.getenv("SLEEPER_DEFAULT_SPORT", DEFAULT_SPORT),
            default_user=os.getenv("SLEEPER_DEFAULT_USER"),
            default_user_id=os.getenv("SLEEPER_DEFAULT_USER_ID"),
            default_league_id=os.getenv("SLEEPER_DEFAULT_LEAGUE_ID"),
            default_season=os.getenv("SLEEPER_DEFAULT_SEASON"),
            cache_dir=cache_dir,
            timeout_seconds=_env_float("SLEEPER_TIMEOUT_SECONDS", 20.0),
            rate_limit_per_minute=_env_int("SLEEPER_RATE_LIMIT_PER_MINUTE", 900),
            user_agent=os.getenv(
                "SLEEPER_USER_AGENT",
                "sleeper-mcp-skill/0.1.0 (+https://github.com/rau/sleeper-mcp-skill)",
            ),
        )

    def as_public_dict(self) -> dict[str, str | int | float | bool | None]:
        return {
            "base_url": self.base_url,
            "default_sport": self.default_sport,
            "default_user_set": self.default_user is not None,
            "default_user_id_set": self.default_user_id is not None,
            "default_league_id_set": self.default_league_id is not None,
            "default_season": self.default_season,
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
            "timeout_seconds": self.timeout_seconds,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "sleeper_auth": "not used; official Sleeper API is unauthenticated read-only",
        }

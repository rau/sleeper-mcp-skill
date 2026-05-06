"""Local-only helpers for storing Sleeper private API auth safely."""

from __future__ import annotations

import getpass
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_GRAPHQL_URL = "https://sleeper.com/graphql"
DEFAULT_TOKEN_SERVICE = "sleeper-mcp-skill-token"
DEFAULT_COOKIE_SERVICE = "sleeper-mcp-skill-cookie"
DEFAULT_CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "sleeper-mcp-skill" / "config.json"
)


class PrivateAuthError(RuntimeError):
    """Raised when private auth config or keychain access fails."""


@dataclass(frozen=True)
class PrivateAuthConfig:
    graphql_url: str = DEFAULT_GRAPHQL_URL
    keychain_account: str = ""
    keychain_token_service: str = DEFAULT_TOKEN_SERVICE
    keychain_cookie_service: str | None = DEFAULT_COOKIE_SERVICE
    user_id: str | None = None
    device_id: str | None = None
    enable_mutations: bool = False
    updated_at: str | None = None
    config_path: Path = DEFAULT_CONFIG_PATH

    @classmethod
    def load(cls, path: str | Path | None = None) -> PrivateAuthConfig:
        config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return cls(keychain_account=_default_account(), config_path=config_path)

        data = json.loads(config_path.read_text())
        return cls(
            graphql_url=data.get("graphql_url") or DEFAULT_GRAPHQL_URL,
            keychain_account=data.get("keychain_account") or _default_account(),
            keychain_token_service=data.get("keychain_token_service") or DEFAULT_TOKEN_SERVICE,
            keychain_cookie_service=data.get("keychain_cookie_service") or DEFAULT_COOKIE_SERVICE,
            user_id=data.get("user_id"),
            device_id=data.get("device_id"),
            enable_mutations=bool(data.get("enable_mutations", False)),
            updated_at=data.get("updated_at"),
            config_path=config_path,
        )

    def write(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        contents = json.dumps(self.as_file_dict(), indent=2, sort_keys=True) + "\n"
        self.config_path.write_text(contents)
        self.config_path.chmod(0o600)

    def as_file_dict(self) -> dict[str, Any]:
        return {
            "graphql_url": self.graphql_url,
            "keychain_account": self.keychain_account or _default_account(),
            "keychain_token_service": self.keychain_token_service,
            "keychain_cookie_service": self.keychain_cookie_service,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "enable_mutations": self.enable_mutations,
            "updated_at": self.updated_at,
        }

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "config_path": str(self.config_path),
            "config_exists": self.config_path.exists(),
            "graphql_url": self.graphql_url,
            "keychain_account": self.keychain_account or _default_account(),
            "keychain_token_service": self.keychain_token_service,
            "keychain_cookie_service": self.keychain_cookie_service,
            "user_id_set": self.user_id is not None,
            "device_id_set": self.device_id is not None,
            "enable_mutations": self.enable_mutations,
            "updated_at": self.updated_at,
        }

    def with_updates(
        self,
        *,
        user_id: str | None = None,
        device_id: str | None = None,
        updated_at: str | None = None,
        enable_mutations: bool | None = None,
    ) -> PrivateAuthConfig:
        return PrivateAuthConfig(
            graphql_url=self.graphql_url,
            keychain_account=self.keychain_account or _default_account(),
            keychain_token_service=self.keychain_token_service,
            keychain_cookie_service=self.keychain_cookie_service,
            user_id=self.user_id if user_id is None else user_id,
            device_id=self.device_id if device_id is None else device_id,
            enable_mutations=(
                self.enable_mutations if enable_mutations is None else enable_mutations
            ),
            updated_at=updated_at or self.updated_at,
            config_path=self.config_path,
        )


def private_auth_status(path: str | Path | None = None) -> dict[str, Any]:
    config = PrivateAuthConfig.load(path)
    token_present = keychain_has_secret(config.keychain_token_service, config.keychain_account)
    cookie_present = (
        keychain_has_secret(config.keychain_cookie_service, config.keychain_account)
        if config.keychain_cookie_service
        else False
    )
    return {
        **config.as_public_dict(),
        "token_present": token_present,
        "cookie_present": cookie_present,
        "secrets_redacted": True,
    }


def keychain_read(service: str, account: str | None = None) -> str | None:
    account = account or _default_account()
    result = subprocess.run(
        ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


def keychain_write(service: str, secret: str, account: str | None = None) -> None:
    account = account or _default_account()
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            account,
            "-s",
            service,
            "-U",
            "-w",
        ],
        input=f"{secret}\n",
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PrivateAuthError(result.stderr.strip() or "failed to write keychain item")


def keychain_has_secret(service: str, account: str | None = None) -> bool:
    return keychain_read(service, account) is not None


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _default_account() -> str:
    return os.getenv("USER") or getpass.getuser()

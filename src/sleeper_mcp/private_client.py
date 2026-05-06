"""Private Sleeper GraphQL client for local authenticated automation."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .private_auth import (
    PrivateAuthConfig,
    PrivateAuthError,
    keychain_read,
    keychain_write,
    now_iso,
)

JsonObject = dict[str, Any]


class SleeperPrivateAPIError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class SleeperPrivateGraphQLClient:
    def __init__(self, config: PrivateAuthConfig | None = None):
        self.config = config or PrivateAuthConfig.load()

    def graphql(
        self,
        query: str,
        variables: JsonObject | None = None,
        *,
        operation_name: str | None = None,
    ) -> JsonObject:
        token = keychain_read(self.config.keychain_token_service, self.config.keychain_account)
        if not token:
            raise PrivateAuthError("Sleeper private token is not configured")

        operation_name = operation_name or _operation_name(query)
        payload = {
            "operationName": operation_name,
            "variables": variables or {},
            "query": query.strip(),
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": token,
            "X-Sleeper-GraphQL-Op": operation_name or "",
        }
        if self.config.device_id:
            headers["X-Device-ID"] = self.config.device_id
        if self.config.keychain_cookie_service:
            cookie = keychain_read(
                self.config.keychain_cookie_service, self.config.keychain_account
            )
            if cookie:
                headers["Cookie"] = cookie

        request = Request(
            self.config.graphql_url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read().decode()
        except HTTPError as exc:
            body = exc.read().decode()
            data = _parse_json(body)
            replacement = _replacement_token(data)
            if replacement:
                self._persist_replacement_token(replacement)
            if exc.code == 401:
                raise SleeperPrivateAPIError("Sleeper private auth expired", status=401) from exc
            raise SleeperPrivateAPIError(body or str(exc), status=exc.code) from exc
        except URLError as exc:
            raise SleeperPrivateAPIError(str(exc)) from exc

        data = _parse_json(body)
        replacement = _replacement_token(data)
        if replacement:
            self._persist_replacement_token(replacement)
        return data

    def _persist_replacement_token(self, token: str) -> None:
        keychain_write(self.config.keychain_token_service, token, self.config.keychain_account)
        self.config = self.config.with_updates(updated_at=now_iso())
        self.config.write()


def _parse_json(body: str) -> JsonObject:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SleeperPrivateAPIError("Sleeper returned non-JSON private API response") from exc
    if not isinstance(data, dict):
        raise SleeperPrivateAPIError("Sleeper returned unexpected private API response")
    return data


def _replacement_token(data: JsonObject) -> str | None:
    token = data.get("token")
    if isinstance(token, str) and token:
        return token
    nested = data.get("data")
    if isinstance(nested, dict):
        token = nested.get("token")
        if isinstance(token, str) and token:
            return token
    return None


def _operation_name(query: str) -> str | None:
    words = query.replace("(", " ").split()
    for keyword in ("query", "mutation"):
        if keyword in words:
            index = words.index(keyword)
            if len(words) > index + 1:
                return words[index + 1]
    return None

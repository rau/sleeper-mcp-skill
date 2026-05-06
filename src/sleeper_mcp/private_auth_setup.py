"""Interactive setup for local Sleeper private auth."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .private_auth import (
    DEFAULT_GRAPHQL_URL,
    PrivateAuthConfig,
    keychain_write,
    now_iso,
    private_auth_status,
)

LOGIN_QUERY = """
query login_query(
  $email_or_phone_or_username: String!,
  $password: String,
  $captcha: String
) {
  login(
    email_or_phone_or_username: $email_or_phone_or_username,
    password: $password,
    captcha: $captcha
  ) {
    token
    cookies
    user_id
    display_name
    email
    phone
    verification
    data_updated
  }
}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure local Sleeper private auth.")
    parser.add_argument("--config", help="Config path; defaults to Application Support.")
    parser.add_argument("--graphql-url", default=DEFAULT_GRAPHQL_URL)
    parser.add_argument(
        "--manual-token",
        action="store_true",
        help="Prompt for an existing Sleeper token instead of logging in.",
    )
    parser.add_argument(
        "--cookie",
        action="store_true",
        help="Prompt for an optional Cookie header and store it in Keychain.",
    )
    parser.add_argument("--status", action="store_true", help="Print redacted auth status.")
    args = parser.parse_args(argv)

    config = PrivateAuthConfig.load(args.config)
    config = PrivateAuthConfig(
        graphql_url=args.graphql_url,
        keychain_account=config.keychain_account,
        keychain_token_service=config.keychain_token_service,
        keychain_cookie_service=config.keychain_cookie_service,
        user_id=config.user_id,
        device_id=config.device_id,
        enable_mutations=False,
        updated_at=config.updated_at,
        config_path=config.config_path,
    )

    if args.status:
        print(json.dumps(private_auth_status(config.config_path), indent=2, sort_keys=True))
        return 0

    if args.manual_token:
        token = getpass.getpass("Sleeper token (input hidden): ").strip()
        if not token:
            print("No token entered.", file=sys.stderr)
            return 2
        user_id = input("Sleeper user_id (optional): ").strip() or None
    else:
        identifier = input("Sleeper email/phone/username: ").strip()
        password = getpass.getpass("Sleeper password (input hidden): ")
        captcha = input("Captcha token if Sleeper required one, otherwise blank: ").strip() or None
        login = login_with_password(config.graphql_url, identifier, password, captcha)
        token = login["token"]
        user_id = login.get("user_id")
        display_name = login.get("display_name")
        if display_name:
            print(f"Logged in as {display_name}.")
        else:
            print("Sleeper login succeeded.")

    keychain_write(config.keychain_token_service, token, config.keychain_account)

    if args.cookie and config.keychain_cookie_service:
        cookie = getpass.getpass("Cookie header (optional, input hidden): ").strip()
        if cookie:
            keychain_write(config.keychain_cookie_service, cookie, config.keychain_account)

    config = config.with_updates(user_id=user_id, updated_at=now_iso(), enable_mutations=False)
    config.write()

    print("Sleeper private auth configured.")
    print(json.dumps(private_auth_status(config.config_path), indent=2, sort_keys=True))
    return 0


def login_with_password(
    graphql_url: str,
    identifier: str,
    password: str,
    captcha: str | None = None,
) -> dict[str, Any]:
    payload = {
        "operationName": "login_query",
        "variables": {
            "email_or_phone_or_username": identifier,
            "password": password,
            "captcha": captcha,
        },
        "query": LOGIN_QUERY,
    }
    request = Request(
        graphql_url,
        data=json.dumps(payload).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Sleeper-GraphQL-Op": "login_query",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode() or str(exc)
        raise RuntimeError(f"Sleeper login failed: {detail}") from exc
    except (URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Sleeper login failed: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Sleeper login returned unexpected response")
    errors = data.get("errors") or data.get("errors_with_code")
    if errors:
        raise RuntimeError(f"Sleeper login returned errors: {errors}")
    login = data.get("data", {}).get("login")
    if not isinstance(login, dict) or not login.get("token"):
        raise RuntimeError("Sleeper login did not return a token")
    return login


if __name__ == "__main__":
    raise SystemExit(main())

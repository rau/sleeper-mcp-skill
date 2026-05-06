"""Browser-assisted setup for local Sleeper private auth."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from .private_auth import (
    DEFAULT_GRAPHQL_URL,
    PrivateAuthConfig,
    keychain_write,
    now_iso,
    private_auth_status,
)


@dataclass
class CapturedAuth:
    token: str | None = None
    user_id: str | None = None
    display_name: str | None = None
    source: str | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Open an isolated browser login flow and store Sleeper auth in Keychain."
    )
    parser.add_argument("--config", help="Config path; defaults to Application Support.")
    parser.add_argument("--graphql-url", default=DEFAULT_GRAPHQL_URL)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless. This is only useful if Sleeper does not require manual login.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--channel",
        default="chrome",
        help='Playwright browser channel. Defaults to "chrome"; falls back to bundled Chromium.',
    )
    parser.add_argument(
        "--no-store-cookies",
        action="store_true",
        help="Do not store cookies from the isolated browser session.",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the browser open after auth is captured.",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            print(
                "Missing dependency: playwright. Install with `python3 -m pip install playwright`.",
                file=sys.stderr,
            )
            return 2
        raise


async def _main_async(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

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

    captured = CapturedAuth()
    captured_event = asyncio.Event()

    async with async_playwright() as playwright:
        browser = await _launch_browser(
            playwright,
            channel=args.channel,
            headless=args.headless,
        )
        context = await browser.new_context()
        page = await context.new_page()

        async def handle_response(response: Any) -> None:
            auth = await _auth_from_response(response)
            if not auth.token:
                return
            captured.token = auth.token
            captured.user_id = auth.user_id
            captured.display_name = auth.display_name
            captured.source = auth.source
            captured_event.set()

        page.on("response", lambda response: asyncio.create_task(handle_response(response)))

        await page.goto("https://sleeper.com/login", wait_until="domcontentloaded")
        if args.headless:
            print("Headless browser started. Waiting for Sleeper auth to appear...")
        else:
            print("Sleeper login browser opened.")
            print("Log in there; this script will store the token in Keychain once captured.")

        try:
            await asyncio.wait_for(captured_event.wait(), timeout=args.timeout_seconds)
        except TimeoutError:
            fallback = await _auth_from_page_storage(page)
            if fallback.token:
                captured = fallback
            else:
                print("Timed out before capturing Sleeper auth.", file=sys.stderr)
                await browser.close()
                return 1

        keychain_write(config.keychain_token_service, captured.token or "", config.keychain_account)

        cookie_count = 0
        if not args.no_store_cookies and config.keychain_cookie_service:
            cookie_header = await _cookie_header(context)
            if cookie_header:
                keychain_write(
                    config.keychain_cookie_service,
                    cookie_header,
                    config.keychain_account,
                )
                cookie_count = len(cookie_header.split("; "))

        config = config.with_updates(
            user_id=captured.user_id,
            updated_at=now_iso(),
            enable_mutations=False,
        )
        config.write()

        print("Sleeper private auth captured and stored.")
        if captured.display_name:
            print(f"Account: {captured.display_name}")
        print(f"Source: {captured.source or 'unknown'}")
        print(f"Stored cookies: {cookie_count}")
        print(json.dumps(private_auth_status(config.config_path), indent=2, sort_keys=True))

        if args.keep_open:
            print("Browser left open. Press Ctrl-C in this terminal when done.")
            await asyncio.Event().wait()
        else:
            await browser.close()
    return 0


async def _launch_browser(playwright: Any, *, channel: str, headless: bool) -> Any:
    try:
        return await playwright.chromium.launch(channel=channel, headless=headless)
    except Exception:
        return await playwright.chromium.launch(headless=headless)


async def _auth_from_response(response: Any) -> CapturedAuth:
    if "/graphql" not in response.url:
        return CapturedAuth()
    request = response.request
    post_data = request.post_data
    if not post_data:
        return CapturedAuth()
    try:
        payload = json.loads(post_data)
    except json.JSONDecodeError:
        return CapturedAuth()

    operation_name = payload.get("operationName")
    if operation_name not in {"login_query", "create_user"}:
        return CapturedAuth()

    try:
        data = await response.json()
    except Exception:
        return CapturedAuth()

    if not isinstance(data, dict):
        return CapturedAuth()
    login = _nested_dict(data, "data", "login")
    user = login or _nested_dict(data, "data", "user")
    if not user:
        return CapturedAuth()
    token = user.get("token")
    if not isinstance(token, str) or not token:
        return CapturedAuth()
    return CapturedAuth(
        token=token,
        user_id=_string_or_none(user.get("user_id")),
        display_name=_string_or_none(user.get("display_name")),
        source=f"graphql:{operation_name}",
    )


async def _auth_from_page_storage(page: Any) -> CapturedAuth:
    try:
        token = await page.evaluate("() => window.localStorage && localStorage.getItem('token')")
        user_id = await page.evaluate(
            "() => window.localStorage && localStorage.getItem('user_id')"
        )
    except Exception:
        return CapturedAuth()
    if not isinstance(token, str) or not token:
        return CapturedAuth()
    return CapturedAuth(
        token=token,
        user_id=_string_or_none(user_id),
        source="isolated-browser-local-storage",
    )


async def _cookie_header(context: Any) -> str:
    cookies = await context.cookies(["https://sleeper.com", "https://api.sleeper.com"])
    parts = []
    seen = set()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None or name in seen:
            continue
        seen.add(name)
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _nested_dict(data: dict[str, Any], *path: str) -> dict[str, Any] | None:
    node: Any = data
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


if __name__ == "__main__":
    raise SystemExit(main())

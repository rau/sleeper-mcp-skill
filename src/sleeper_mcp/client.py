"""Small, dependency-light Sleeper API client with caching and rate limiting."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import (
    DEFAULT_CACHE_TTL_SECONDS,
    PLAYERS_CACHE_TTL_SECONDS,
    SleeperConfig,
)

Json = dict[str, Any] | list[Any] | str | int | float | bool | None


class SleeperAPIError(RuntimeError):
    """Raised when Sleeper returns an HTTP or decoding error."""

    def __init__(self, message: str, *, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


@dataclass(frozen=True)
class CacheEntry:
    data: Json
    fetched_at: float
    ttl_seconds: int

    @property
    def expires_at(self) -> float:
        return self.fetched_at + self.ttl_seconds

    def is_fresh(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) < self.expires_at


class SleeperClient:
    def __init__(self, config: SleeperConfig | None = None):
        self.config = config or SleeperConfig.from_env()
        self._last_request_at = 0.0

    def request(
        self,
        path: str,
        *,
        params: Mapping[str, Any | None] | None = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        force_refresh: bool = False,
    ) -> Json:
        url = self._build_url(path, params)
        cache_key = self._cache_key(url)
        if not force_refresh:
            cached = self._read_cache(cache_key)
            if cached and cached.is_fresh():
                return cached.data

        self._rate_limit()
        data = self._fetch_json(url)
        self._write_cache(
            cache_key,
            CacheEntry(
                data=data,
                fetched_at=time.time(),
                ttl_seconds=cache_ttl_seconds,
            ),
        )
        return data

    def get_user(self, username_or_user_id: str | None = None) -> dict[str, Any]:
        identifier = self._require(
            username_or_user_id or self.config.default_user_id or self.config.default_user,
            "username_or_user_id",
        )
        return self._expect_dict(self.request(f"/user/{identifier}"))

    def get_avatar_urls(self, avatar_id: str) -> dict[str, str]:
        avatar_id = self._require(avatar_id, "avatar_id")
        return {
            "full": f"https://sleepercdn.com/avatars/{avatar_id}",
            "thumb": f"https://sleepercdn.com/avatars/thumbs/{avatar_id}",
        }

    def get_user_leagues(
        self,
        user_id: str | None = None,
        *,
        sport: str | None = None,
        season: str | int | None = None,
    ) -> list[dict[str, Any]]:
        user_id = self._resolve_user_id(user_id)
        sport = self._sport(sport)
        season = self._season(season)
        return self._expect_list(self.request(f"/user/{user_id}/leagues/{sport}/{season}"))

    def get_user_drafts(
        self,
        user_id: str | None = None,
        *,
        sport: str | None = None,
        season: str | int | None = None,
    ) -> list[dict[str, Any]]:
        user_id = self._resolve_user_id(user_id)
        sport = self._sport(sport)
        season = self._season(season)
        return self._expect_list(self.request(f"/user/{user_id}/drafts/{sport}/{season}"))

    def get_league(self, league_id: str | None = None) -> dict[str, Any]:
        league_id = self._league_id(league_id)
        return self._expect_dict(self.request(f"/league/{league_id}"))

    def get_league_rosters(self, league_id: str | None = None) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/rosters"))

    def get_league_users(self, league_id: str | None = None) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/users"))

    def get_league_matchups(
        self, league_id: str | None = None, *, week: int
    ) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/matchups/{week}"))

    def get_league_winners_bracket(self, league_id: str | None = None) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/winners_bracket"))

    def get_league_losers_bracket(self, league_id: str | None = None) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/losers_bracket"))

    def get_league_transactions(
        self, league_id: str | None = None, *, round_or_week: int
    ) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/transactions/{round_or_week}"))

    def get_league_traded_picks(self, league_id: str | None = None) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/traded_picks"))

    def get_league_drafts(self, league_id: str | None = None) -> list[dict[str, Any]]:
        league_id = self._league_id(league_id)
        return self._expect_list(self.request(f"/league/{league_id}/drafts"))

    def get_state(self, sport: str | None = None) -> dict[str, Any]:
        sport = self._sport(sport)
        return self._expect_dict(self.request(f"/state/{sport}", cache_ttl_seconds=30))

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        draft_id = self._require(draft_id, "draft_id")
        return self._expect_dict(self.request(f"/draft/{draft_id}"))

    def get_draft_picks(self, draft_id: str) -> list[dict[str, Any]]:
        draft_id = self._require(draft_id, "draft_id")
        return self._expect_list(self.request(f"/draft/{draft_id}/picks"))

    def get_draft_traded_picks(self, draft_id: str) -> list[dict[str, Any]]:
        draft_id = self._require(draft_id, "draft_id")
        return self._expect_list(self.request(f"/draft/{draft_id}/traded_picks"))

    def get_players(
        self, sport: str | None = None, *, force_refresh: bool = False
    ) -> dict[str, dict[str, Any]]:
        sport = self._sport(sport)
        data = self.request(
            f"/players/{sport}",
            cache_ttl_seconds=PLAYERS_CACHE_TTL_SECONDS,
            force_refresh=force_refresh,
        )
        if not isinstance(data, dict):
            raise SleeperAPIError("Expected players response to be an object")
        return {str(player_id): self._expect_dict(player) for player_id, player in data.items()}

    def get_trending_players(
        self,
        sport: str | None = None,
        *,
        trend_type: str = "add",
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        sport = self._sport(sport)
        if trend_type not in {"add", "drop"}:
            raise ValueError('trend_type must be "add" or "drop"')
        return self._expect_list(
            self.request(
                f"/players/{sport}/trending/{trend_type}",
                params={"lookback_hours": lookback_hours, "limit": limit},
                cache_ttl_seconds=60,
            )
        )

    def search_players(
        self,
        *,
        sport: str | None = None,
        query: str | None = None,
        player_ids: Iterable[str] | None = None,
        positions: Iterable[str] | None = None,
        teams: Iterable[str] | None = None,
        active_only: bool = False,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        players = self.get_players(sport)
        normalized_query = _searchable(query)
        position_set = {p.upper() for p in positions or []}
        team_set = {t.upper() for t in teams or []}
        id_set = {str(player_id) for player_id in player_ids or []}

        results: list[dict[str, Any]] = []
        for player_id, player in players.items():
            if id_set and player_id not in id_set:
                continue
            if normalized_query and normalized_query not in _player_search_blob(player):
                continue
            if position_set and not (set(_player_positions(player)) & position_set):
                continue
            if team_set and str(player.get("team", "")).upper() not in team_set:
                continue
            if active_only and str(player.get("status", "")).lower() != "active":
                continue
            enriched = {"player_id": player_id, **player}
            results.append(enriched)

        results.sort(key=_player_sort_key)
        return results[: _bounded_limit(limit)]

    def get_free_agents(
        self,
        league_id: str | None = None,
        *,
        sport: str | None = None,
        positions: Iterable[str] | None = None,
        teams: Iterable[str] | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rostered = {
            str(player_id)
            for roster in self.get_league_rosters(league_id)
            for player_id in roster.get("players") or []
        }
        return [
            player
            for player in self.search_players(
                sport=sport,
                positions=positions,
                teams=teams,
                active_only=active_only,
                limit=max(_bounded_limit(limit), 100),
            )
            if str(player.get("player_id")) not in rostered
        ][: _bounded_limit(limit)]

    def get_league_snapshot(
        self,
        league_id: str | None = None,
        *,
        week: int | None = None,
        include_drafts: bool = True,
    ) -> dict[str, Any]:
        league_id = self._league_id(league_id)
        snapshot: dict[str, Any] = {
            "league": self.get_league(league_id),
            "users": self.get_league_users(league_id),
            "rosters": self.get_league_rosters(league_id),
            "traded_picks": self.get_league_traded_picks(league_id),
        }
        if week is not None:
            snapshot["matchups"] = self.get_league_matchups(league_id, week=week)
            snapshot["transactions"] = self.get_league_transactions(
                league_id, round_or_week=week
            )
        if include_drafts:
            snapshot["drafts"] = self.get_league_drafts(league_id)
        return snapshot

    def get_standings(self, league_id: str | None = None) -> list[dict[str, Any]]:
        users_by_id = {user.get("user_id"): user for user in self.get_league_users(league_id)}
        standings: list[dict[str, Any]] = []
        for roster in self.get_league_rosters(league_id):
            settings = roster.get("settings") or {}
            owner_id = roster.get("owner_id")
            user = users_by_id.get(owner_id, {})
            standings.append(
                {
                    "roster_id": roster.get("roster_id"),
                    "owner_id": owner_id,
                    "display_name": user.get("display_name") or user.get("username"),
                    "team_name": (user.get("metadata") or {}).get("team_name"),
                    "wins": settings.get("wins", 0),
                    "losses": settings.get("losses", 0),
                    "ties": settings.get("ties", 0),
                    "points_for": _points(settings, "fpts"),
                    "points_against": _points(settings, "fpts_against"),
                    "waiver_position": settings.get("waiver_position"),
                    "waiver_budget_used": settings.get("waiver_budget_used"),
                    "total_moves": settings.get("total_moves"),
                }
            )
        standings.sort(
            key=lambda row: (
                row["wins"] or 0,
                row["ties"] or 0,
                row["points_for"] or 0,
            ),
            reverse=True,
        )
        return standings

    def get_matchups_detailed(
        self,
        league_id: str | None = None,
        *,
        week: int,
        include_player_details: bool = False,
        sport: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.get_league_matchups(league_id, week=week)
        users_by_roster = self._users_by_roster(league_id)
        players = self.get_players(sport) if include_player_details else {}

        by_matchup: dict[Any, list[dict[str, Any]]] = {}
        for row in rows:
            by_matchup.setdefault(row.get("matchup_id"), []).append(row)

        detailed = []
        for row in rows:
            roster_id = row.get("roster_id")
            opponents = [
                member.get("roster_id")
                for member in by_matchup.get(row.get("matchup_id"), [])
                if member.get("roster_id") != roster_id
            ]
            detailed.append(
                {
                    **row,
                    "team": users_by_roster.get(roster_id),
                    "opponent_roster_ids": opponents,
                    "starters_detail": _pick_players(players, row.get("starters") or []),
                    "players_detail": _pick_players(players, row.get("players") or []),
                }
            )
        return detailed

    def get_roster_snapshot(
        self,
        league_id: str | None = None,
        *,
        roster_id: int,
        week: int | None = None,
        include_player_details: bool = True,
        sport: str | None = None,
    ) -> dict[str, Any]:
        roster = next(
            (
                row
                for row in self.get_league_rosters(league_id)
                if row.get("roster_id") == roster_id
            ),
            None,
        )
        if not roster:
            raise SleeperAPIError(f"Roster {roster_id} was not found")

        users_by_roster = self._users_by_roster(league_id)
        players = self.get_players(sport) if include_player_details else {}
        snapshot: dict[str, Any] = {
            "roster": roster,
            "team": users_by_roster.get(roster_id),
            "starters_detail": _pick_players(players, roster.get("starters") or []),
            "players_detail": _pick_players(players, roster.get("players") or []),
        }
        if week is not None:
            snapshot["matchup"] = next(
                (
                    row
                    for row in self.get_matchups_detailed(
                        league_id,
                        week=week,
                        include_player_details=include_player_details,
                        sport=sport,
                    )
                    if row.get("roster_id") == roster_id
                ),
                None,
            )
        return snapshot

    def get_draft_board(
        self,
        draft_id: str,
        *,
        include_player_details: bool = True,
        sport: str | None = None,
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        picks = self.get_draft_picks(draft_id)
        traded_picks = self.get_draft_traded_picks(draft_id)
        players = self.get_players(sport or draft.get("sport")) if include_player_details else {}
        return {
            "draft": draft,
            "picks": [
                {**pick, "player": players.get(str(pick.get("player_id")))}
                for pick in sorted(picks, key=lambda row: row.get("pick_no") or 0)
            ],
            "traded_picks": traded_picks,
        }

    def _users_by_roster(self, league_id: str | None = None) -> dict[int, dict[str, Any]]:
        users_by_id = {user.get("user_id"): user for user in self.get_league_users(league_id)}
        out: dict[int, dict[str, Any]] = {}
        for roster in self.get_league_rosters(league_id):
            roster_id = roster.get("roster_id")
            if roster_id is None:
                continue
            user = users_by_id.get(roster.get("owner_id"), {})
            out[int(roster_id)] = {
                "roster_id": roster_id,
                "owner_id": roster.get("owner_id"),
                "username": user.get("username"),
                "display_name": user.get("display_name"),
                "team_name": (user.get("metadata") or {}).get("team_name"),
            }
        return out

    def _build_url(self, path: str, params: Mapping[str, Any | None] | None = None) -> str:
        normalized_path = "/" + path.lstrip("/")
        query = ""
        if params:
            cleaned = {key: value for key, value in params.items() if value is not None}
            if cleaned:
                query = "?" + urlencode(cleaned)
        return f"{self.config.base_url}{normalized_path}{query}"

    def _fetch_json(self, url: str) -> Json:
        request = Request(url, headers={"User-Agent": self.config.user_agent})
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SleeperAPIError(
                f"Sleeper API returned HTTP {exc.code}: {body[:500]}",
                status=exc.code,
                url=url,
            ) from exc
        except URLError as exc:
            raise SleeperAPIError(f"Sleeper API request failed: {exc.reason}", url=url) from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SleeperAPIError("Sleeper API returned invalid JSON", url=url) from exc

    def _rate_limit(self) -> None:
        if self.config.rate_limit_per_minute <= 0:
            return
        min_interval = 60.0 / self.config.rate_limit_per_minute
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _cache_key(self, url: str) -> str:
        return sha256(url.encode("utf-8")).hexdigest() + ".json"

    def _cache_path(self, cache_key: str) -> Path | None:
        if self.config.cache_dir is None:
            return None
        return self.config.cache_dir / cache_key

    def _read_cache(self, cache_key: str) -> CacheEntry | None:
        path = self._cache_path(cache_key)
        if path is None or not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return CacheEntry(
                data=payload["data"],
                fetched_at=float(payload["fetched_at"]),
                ttl_seconds=int(payload["ttl_seconds"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache(self, cache_key: str, entry: CacheEntry) -> None:
        path = self._cache_path(cache_key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "data": entry.data,
                        "fetched_at": entry.fetched_at,
                        "ttl_seconds": entry.ttl_seconds,
                    },
                    handle,
                    sort_keys=True,
                )
        except OSError:
            return

    def _resolve_user_id(self, user_id: str | None) -> str:
        if user_id:
            return user_id
        if self.config.default_user_id:
            return self.config.default_user_id
        user = self.get_user(self.config.default_user)
        return str(user["user_id"])

    def _league_id(self, league_id: str | None) -> str:
        return self._require(league_id or self.config.default_league_id, "league_id")

    def _sport(self, sport: str | None) -> str:
        return self._require(sport or self.config.default_sport, "sport").lower()

    def _season(self, season: str | int | None) -> str:
        if season is not None:
            return str(season)
        if self.config.default_season:
            return self.config.default_season
        return str(self.get_state().get("league_season") or self.get_state().get("season"))

    def _require(self, value: str | None, name: str) -> str:
        if value is None or str(value).strip() == "":
            raise ValueError(f"{name} is required")
        return str(value)

    def _expect_dict(self, value: Json) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SleeperAPIError(f"Expected object response, got {type(value).__name__}")
        return value

    def _expect_list(self, value: Json) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise SleeperAPIError(f"Expected list response, got {type(value).__name__}")
        return [self._expect_dict(item) for item in value]


def _bounded_limit(limit: int, maximum: int = 250) -> int:
    return max(1, min(int(limit), maximum))


def _searchable(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _player_search_blob(player: Mapping[str, Any]) -> str:
    parts = [
        player.get("full_name"),
        player.get("first_name"),
        player.get("last_name"),
        player.get("search_full_name"),
        player.get("search_first_name"),
        player.get("search_last_name"),
        player.get("hashtag"),
        player.get("team"),
        player.get("position"),
    ]
    return _searchable(" ".join(str(part) for part in parts if part))


def _player_positions(player: Mapping[str, Any]) -> list[str]:
    fantasy_positions = player.get("fantasy_positions")
    if isinstance(fantasy_positions, list):
        return [str(position).upper() for position in fantasy_positions]
    position = player.get("position")
    return [str(position).upper()] if position else []


def _player_sort_key(player: Mapping[str, Any]) -> tuple[int, str]:
    rank = player.get("search_rank")
    try:
        normalized_rank = int(rank)
    except (TypeError, ValueError):
        normalized_rank = 999999
    return normalized_rank, str(player.get("search_full_name") or player.get("full_name") or "")


def _pick_players(
    players: Mapping[str, Mapping[str, Any]], player_ids: Iterable[Any]
) -> list[dict[str, Any]]:
    return [
        {"player_id": str(player_id), **players[str(player_id)]}
        for player_id in player_ids
        if str(player_id) in players
    ]


def _points(settings: Mapping[str, Any], prefix: str) -> float:
    whole = settings.get(prefix) or 0
    decimal = settings.get(f"{prefix}_decimal") or 0
    try:
        return float(whole) + float(decimal) / 100
    except (TypeError, ValueError):
        return 0.0

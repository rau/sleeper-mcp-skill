from __future__ import annotations

from pathlib import Path
from typing import Any

from sleeper_mcp.client import SleeperClient
from sleeper_mcp.config import SleeperConfig


class FakeSleeperClient(SleeperClient):
    def __init__(self, responses: dict[str, Any], tmp_path: Path):
        super().__init__(
            SleeperConfig(
                base_url="https://api.test/v1",
                default_sport="nfl",
                default_user=None,
                default_user_id=None,
                default_league_id="L1",
                default_season="2026",
                cache_dir=tmp_path,
                timeout_seconds=1.0,
                rate_limit_per_minute=0,
                user_agent="test",
            )
        )
        self.responses = responses
        self.fetches: list[str] = []

    def _fetch_json(self, url: str):
        self.fetches.append(url)
        path_and_query = url.removeprefix("https://api.test/v1")
        return self.responses[path_and_query]


def test_builds_user_leagues_url(tmp_path: Path) -> None:
    client = FakeSleeperClient({"/user/U1/leagues/nfl/2026": []}, tmp_path)

    assert client.get_user_leagues("U1", sport="nfl", season=2026) == []
    assert client.fetches == ["https://api.test/v1/user/U1/leagues/nfl/2026"]


def test_uses_cache_for_repeated_request(tmp_path: Path) -> None:
    client = FakeSleeperClient({"/league/L1": {"league_id": "L1"}}, tmp_path)

    assert client.get_league("L1") == {"league_id": "L1"}
    assert client.get_league("L1") == {"league_id": "L1"}
    assert client.fetches == ["https://api.test/v1/league/L1"]


def test_search_players_filters_and_sorts(tmp_path: Path) -> None:
    client = FakeSleeperClient(
        {
            "/players/nfl": {
                "1": {
                    "first_name": "Ja'Marr",
                    "last_name": "Chase",
                    "search_full_name": "jamarrchase",
                    "fantasy_positions": ["WR"],
                    "team": "CIN",
                    "status": "Active",
                    "search_rank": 4,
                },
                "2": {
                    "first_name": "Joe",
                    "last_name": "Burrow",
                    "search_full_name": "joeburrow",
                    "fantasy_positions": ["QB"],
                    "team": "CIN",
                    "status": "Active",
                    "search_rank": 10,
                },
                "3": {
                    "first_name": "Inactive",
                    "last_name": "Receiver",
                    "search_full_name": "inactivereceiver",
                    "fantasy_positions": ["WR"],
                    "team": "CIN",
                    "status": "Inactive",
                    "search_rank": 1,
                },
            }
        },
        tmp_path,
    )

    results = client.search_players(query="chase", positions=["WR"], active_only=True)

    assert [row["player_id"] for row in results] == ["1"]


def test_standings_join_users_to_rosters(tmp_path: Path) -> None:
    client = FakeSleeperClient(
        {
            "/league/L1/users": [
                {
                    "user_id": "U1",
                    "username": "alpha",
                    "display_name": "Alpha",
                    "metadata": {"team_name": "A Team"},
                }
            ],
            "/league/L1/rosters": [
                {
                    "roster_id": 1,
                    "owner_id": "U1",
                    "settings": {
                        "wins": 2,
                        "losses": 1,
                        "ties": 0,
                        "fpts": 100,
                        "fpts_decimal": 75,
                    },
                }
            ],
        },
        tmp_path,
    )

    assert client.get_standings("L1") == [
        {
            "roster_id": 1,
            "owner_id": "U1",
            "display_name": "Alpha",
            "team_name": "A Team",
            "wins": 2,
            "losses": 1,
            "ties": 0,
            "points_for": 100.75,
            "points_against": 0.0,
            "waiver_position": None,
            "waiver_budget_used": None,
            "total_moves": None,
        }
    ]


def test_free_agents_are_players_not_on_rosters(tmp_path: Path) -> None:
    client = FakeSleeperClient(
        {
            "/league/L1/rosters": [{"players": ["1"]}],
            "/players/nfl": {
                "1": {
                    "first_name": "Rostered",
                    "last_name": "Player",
                    "fantasy_positions": ["RB"],
                    "status": "Active",
                    "search_rank": 1,
                },
                "2": {
                    "first_name": "Free",
                    "last_name": "Agent",
                    "fantasy_positions": ["RB"],
                    "status": "Active",
                    "search_rank": 2,
                },
            },
        },
        tmp_path,
    )

    assert [row["player_id"] for row in client.get_free_agents("L1", positions=["RB"])] == ["2"]

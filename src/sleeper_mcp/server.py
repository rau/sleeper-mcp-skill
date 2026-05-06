"""MCP server exposing Sleeper fantasy sports data."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import SleeperClient
from .config import SleeperConfig
from .private_auth import private_auth_status as get_private_auth_status

mcp = FastMCP("Sleeper Fantasy Sports")
client = SleeperClient()


@mcp.resource("sleeper://api-summary")
def api_summary() -> str:
    return (
        "Sleeper's official API is a read-only HTTP API. It provides users, leagues, "
        "rosters, matchups, transactions, drafts, player metadata, trending players, "
        "avatars, and sport state. No Sleeper API token is required or sent."
    )


@mcp.resource("sleeper://config")
def config() -> dict[str, Any]:
    return SleeperConfig.from_env().as_public_dict()


@mcp.resource("sleeper://private-auth-status")
def private_auth_status_resource() -> dict[str, Any]:
    return get_private_auth_status()


@mcp.tool()
def private_auth_status(config_path: str | None = None) -> dict[str, Any]:
    """Return redacted Sleeper private auth status without exposing secrets."""
    return get_private_auth_status(config_path)


@mcp.tool()
def get_user(username_or_user_id: str | None = None) -> dict[str, Any]:
    """Get a Sleeper user by username or user id."""
    return client.get_user(username_or_user_id)


@mcp.tool()
def get_avatar_urls(avatar_id: str) -> dict[str, str]:
    """Return full-size and thumbnail URLs for a Sleeper avatar id."""
    return client.get_avatar_urls(avatar_id)


@mcp.tool()
def get_user_leagues(
    user_id: str | None = None, sport: str | None = None, season: str | int | None = None
) -> list[dict[str, Any]]:
    """Get all leagues for a user in a sport/season."""
    return client.get_user_leagues(user_id, sport=sport, season=season)


@mcp.tool()
def get_user_drafts(
    user_id: str | None = None, sport: str | None = None, season: str | int | None = None
) -> list[dict[str, Any]]:
    """Get all drafts for a user in a sport/season."""
    return client.get_user_drafts(user_id, sport=sport, season=season)


@mcp.tool()
def get_league(league_id: str | None = None) -> dict[str, Any]:
    """Get a Sleeper league by id."""
    return client.get_league(league_id)


@mcp.tool()
def get_league_rosters(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get all rosters in a league."""
    return client.get_league_rosters(league_id)


@mcp.tool()
def get_league_users(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get all users in a league."""
    return client.get_league_users(league_id)


@mcp.tool()
def get_league_matchups(week: int, league_id: str | None = None) -> list[dict[str, Any]]:
    """Get raw matchup rows for a league week."""
    return client.get_league_matchups(league_id, week=week)


@mcp.tool()
def get_league_winners_bracket(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get a league winners bracket."""
    return client.get_league_winners_bracket(league_id)


@mcp.tool()
def get_league_losers_bracket(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get a league losers bracket."""
    return client.get_league_losers_bracket(league_id)


@mcp.tool()
def get_league_transactions(
    round_or_week: int, league_id: str | None = None
) -> list[dict[str, Any]]:
    """Get league transactions for a week/round."""
    return client.get_league_transactions(league_id, round_or_week=round_or_week)


@mcp.tool()
def get_league_traded_picks(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get traded future picks for a league."""
    return client.get_league_traded_picks(league_id)


@mcp.tool()
def get_league_drafts(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get drafts associated with a league."""
    return client.get_league_drafts(league_id)


@mcp.tool()
def get_state(sport: str | None = None) -> dict[str, Any]:
    """Get current state for a sport, such as nfl."""
    return client.get_state(sport)


@mcp.tool()
def get_draft(draft_id: str) -> dict[str, Any]:
    """Get a draft by id."""
    return client.get_draft(draft_id)


@mcp.tool()
def get_draft_picks(draft_id: str) -> list[dict[str, Any]]:
    """Get all picks in a draft."""
    return client.get_draft_picks(draft_id)


@mcp.tool()
def get_draft_traded_picks(draft_id: str) -> list[dict[str, Any]]:
    """Get all traded picks in a draft."""
    return client.get_draft_traded_picks(draft_id)


@mcp.tool()
def refresh_players_cache(sport: str | None = None, force_refresh: bool = True) -> dict[str, Any]:
    """Fetch player metadata into the local cache and return a count."""
    players = client.get_players(sport, force_refresh=force_refresh)
    return {"sport": sport or client.config.default_sport, "player_count": len(players)}


@mcp.tool()
def get_player(player_id: str, sport: str | None = None) -> dict[str, Any] | None:
    """Get one player by Sleeper player id."""
    return client.get_players(sport).get(str(player_id))


@mcp.tool()
def search_players(
    query: str | None = None,
    sport: str | None = None,
    player_ids: list[str] | None = None,
    positions: list[str] | None = None,
    teams: list[str] | None = None,
    active_only: bool = False,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Search or filter Sleeper player metadata."""
    return client.search_players(
        sport=sport,
        query=query,
        player_ids=player_ids,
        positions=positions,
        teams=teams,
        active_only=active_only,
        limit=limit,
    )


@mcp.tool()
def get_trending_players(
    sport: str | None = None,
    trend_type: str = "add",
    lookback_hours: int = 24,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Get trending adds or drops."""
    return client.get_trending_players(
        sport, trend_type=trend_type, lookback_hours=lookback_hours, limit=limit
    )


@mcp.tool()
def get_league_snapshot(
    league_id: str | None = None, week: int | None = None, include_drafts: bool = True
) -> dict[str, Any]:
    """Get league info, users, rosters, picks, and optional week-specific data."""
    return client.get_league_snapshot(league_id, week=week, include_drafts=include_drafts)


@mcp.tool()
def get_standings(league_id: str | None = None) -> list[dict[str, Any]]:
    """Get league standings joined to user/team names."""
    return client.get_standings(league_id)


@mcp.tool()
def get_matchups_detailed(
    week: int,
    league_id: str | None = None,
    include_player_details: bool = False,
    sport: str | None = None,
) -> list[dict[str, Any]]:
    """Get matchups joined to team names and optionally player metadata."""
    return client.get_matchups_detailed(
        league_id, week=week, include_player_details=include_player_details, sport=sport
    )


@mcp.tool()
def get_roster_snapshot(
    roster_id: int,
    league_id: str | None = None,
    week: int | None = None,
    include_player_details: bool = True,
    sport: str | None = None,
) -> dict[str, Any]:
    """Get one roster joined to user and optional player/matchup details."""
    return client.get_roster_snapshot(
        league_id,
        roster_id=roster_id,
        week=week,
        include_player_details=include_player_details,
        sport=sport,
    )


@mcp.tool()
def get_draft_board(
    draft_id: str, include_player_details: bool = True, sport: str | None = None
) -> dict[str, Any]:
    """Get a draft, picks, traded picks, and optional player metadata."""
    return client.get_draft_board(
        draft_id, include_player_details=include_player_details, sport=sport
    )


@mcp.tool()
def get_free_agents(
    league_id: str | None = None,
    sport: str | None = None,
    positions: list[str] | None = None,
    teams: list[str] | None = None,
    active_only: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Compute unrostered players in a league from roster and player metadata."""
    return client.get_free_agents(
        league_id,
        sport=sport,
        positions=positions,
        teams=teams,
        active_only=active_only,
        limit=limit,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

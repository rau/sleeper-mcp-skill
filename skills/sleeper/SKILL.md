# Sleeper

Use this skill when the user asks for Sleeper fantasy sports data, Sleeper league analysis, rosters, matchups, drafts, transactions, traded picks, standings, waiver/free-agent context, or player lookup.

## Contract

- Sleeper's official API is read-only and unauthenticated.
- Do not ask the user for a Sleeper API token for public API reads.
- Do not scrape Chrome cookies/local storage or print tokens. If private auth is explicitly needed, use the repo's Keychain-backed setup path and `private_auth_status`; keep secrets out of chat and tool results.
- Do not use private web endpoints or write actions unless the user explicitly asks for non-official experimentation and accepts the risk.
- Treat `SLEEPER_DEFAULT_USER`, `SLEEPER_DEFAULT_USER_ID`, `SLEEPER_DEFAULT_LEAGUE_ID`, `SLEEPER_DEFAULT_SPORT`, and `SLEEPER_DEFAULT_SEASON` as convenience defaults, not secrets.
- Player metadata is large. Prefer `search_players`, `get_player`, or `refresh_players_cache` before broad player-data workflows.

## Preferred MCP Tools

Use the `sleeper` MCP server from this repo when available.

- User context: `get_user`, `get_user_leagues`, `get_user_drafts`
- League context: `get_league`, `get_league_snapshot`, `get_standings`
- Weekly context: `get_league_matchups`, `get_matchups_detailed`, `get_league_transactions`
- Roster context: `get_league_rosters`, `get_roster_snapshot`
- Draft context: `get_league_drafts`, `get_draft`, `get_draft_board`, `get_draft_picks`, `get_draft_traded_picks`
- Player context: `get_player`, `search_players`, `get_trending_players`, `get_free_agents`
- Private auth status: `private_auth_status`
- Misc: `get_state`, `get_avatar_urls`

## Workflow

1. If the user gives a username, call `get_user`, then use the stable `user_id`.
2. If the user gives only a user and season, call `get_user_leagues` and ask only if multiple leagues need disambiguation.
3. If the user gives a league id, use it directly.
4. For weekly analysis, call `get_state` when the week is omitted, then use `display_week` or `week` based on the user's wording.
5. For names/team labels, join rosters to users with `get_standings`, `get_matchups_detailed`, or `get_roster_snapshot` instead of hand-joining raw responses.
6. For free agents, explain that availability is computed from Sleeper's player metadata minus current league rosters.

## Setup

MCP clients can run the server over stdio:

```json
{
  "mcpServers": {
    "sleeper": {
      "command": "sleeper-mcp",
      "env": {
        "SLEEPER_DEFAULT_SPORT": "nfl",
        "SLEEPER_DEFAULT_LEAGUE_ID": "your_league_id"
      }
    }
  }
}
```

From a local checkout:

```bash
python3 -m pip install -e .
```

Private auth setup, when explicitly requested:

```bash
python3 scripts/setup_private_auth.py
python3 scripts/setup_private_auth.py --status
```

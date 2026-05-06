# Sleeper MCP Skill

A comprehensive local MCP server plus a Codex skill for the public Sleeper fantasy sports API.

## What Exists Elsewhere

There are already a few public Sleeper MCP projects, including:

- `sourknives/sleeper-mcp-server`
- `FloSchl8/sleeper-mcp`
- `einreke/sleeper-scraper-mcp`
- `GregBaugues/tokenbowl-mcp`

This repo is intentionally narrower on auth and broader on reusable API coverage: it exposes the official read-only Sleeper API, adds safe caching and higher-level league helpers, and includes a Codex skill entrypoint.

## Authentication

Sleeper's official API is read-only and does not require an API token. This server does not ask for or store Sleeper credentials.

Supported configuration is identity/context, not auth:

- `SLEEPER_DEFAULT_USER` - default username or user id for tools that accept a user.
- `SLEEPER_DEFAULT_USER_ID` - explicit default user id.
- `SLEEPER_DEFAULT_LEAGUE_ID` - default league id.
- `SLEEPER_DEFAULT_SPORT` - default sport, `nfl` unless set.
- `SLEEPER_DEFAULT_SEASON` - default season for user league/draft tools.
- `SLEEPER_CACHE_DIR` - cache directory, default `~/.cache/sleeper-mcp-skill`.
- `SLEEPER_DISABLE_CACHE=1` - disables filesystem caching.
- `SLEEPER_RATE_LIMIT_PER_MINUTE` - client-side request ceiling, default `900`.
- `SLEEPER_TIMEOUT_SECONDS` - HTTP timeout, default `20`.
- `SLEEPER_BASE_URL` - override the API base URL for tests or proxies.

No bearer token is sent to Sleeper. If Sleeper adds official authenticated endpoints later, add a separate opt-in transport path rather than reusing app cookies or scraped private endpoints.

## Installation

From a checkout:

```bash
python3 -m pip install -e .
```

From GitHub:

```bash
python3 -m pip install "git+https://github.com/rau/sleeper-mcp-skill.git"
```

## MCP Configuration

Claude Desktop, Cursor, and other MCP clients can run the server over stdio:

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

If you prefer not to install an entrypoint, point at the module:

```json
{
  "mcpServers": {
    "sleeper": {
      "command": "python3",
      "args": ["-m", "sleeper_mcp.server"]
    }
  }
}
```

## Tools

Core API tools:

- `get_user`
- `get_avatar_urls`
- `get_user_leagues`
- `get_user_drafts`
- `get_league`
- `get_league_rosters`
- `get_league_users`
- `get_league_matchups`
- `get_league_winners_bracket`
- `get_league_losers_bracket`
- `get_league_transactions`
- `get_league_traded_picks`
- `get_league_drafts`
- `get_state`
- `get_draft`
- `get_draft_picks`
- `get_draft_traded_picks`
- `refresh_players_cache`
- `get_player`
- `search_players`
- `get_trending_players`

Higher-level helpers:

- `get_league_snapshot`
- `get_standings`
- `get_matchups_detailed`
- `get_roster_snapshot`
- `get_draft_board`
- `get_free_agents`

Resources:

- `sleeper://api-summary`
- `sleeper://config`

## Local Skill

The Codex skill lives at `skills/sleeper/SKILL.md`. To install it into Codex manually:

```bash
mkdir -p ~/.codex/skills/sleeper
cp skills/sleeper/SKILL.md ~/.codex/skills/sleeper/SKILL.md
```

The skill tells Codex when to use the MCP server and how to stay inside Sleeper's read-only/auth constraints.

## Development

This repo has no build step. Syntax and unit checks:

```bash
python3 -m compileall src tests
pytest
```

`pytest` exercises URL construction, caching, filtering, and higher-level data shaping without calling the live Sleeper API.

## API Coverage Notes

Sleeper asks clients to keep calls under 1000 requests per minute. This client defaults below that and caches player metadata because the `/players/<sport>` response is large and should generally be fetched no more than daily.

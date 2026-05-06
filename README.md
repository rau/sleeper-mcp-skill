# Sleeper Internal Fantasy API Field Guide

This repo contains a local Sleeper MCP server and Codex skill, but this README is now the working field guide for Sleeper's web app APIs. It is based on:

- Live Chrome network capture from the logged-in Sleeper web app on 2026-05-06.
- Static inspection of the current web bundle: `https://sleepercdn.com/js/bundle-2c19b9545a99dcdaa566da8383b30d2c.js?vsn=d`.
- The public official Sleeper API used by the MCP server.

Scope is fantasy/dynasty only: leagues, rosters, players, waivers, trades, draft picks, drafts, matchup state, settings, and league chat only where it affects fantasy workflows. Gambling, DFS, contests, marketplace, and unrelated social surfaces are intentionally omitted.

## Safety Rules

The private API is authenticated by the logged-in browser session. Do not commit or print cookies, session values, CSRF tokens, or full authenticated headers.

Operation classes:

- `READ`: safe for status discovery, waiver/player availability, rosters, standings, drafts, transaction history, and settings.
- `APP-AUTO WRITE`: state-changing calls the web app triggers during normal viewing, such as invite link creation or read receipts.
- `USER WRITE`: changes a fantasy object and must not be submitted without explicit user confirmation.
- `ADMIN WRITE`: changes league/admin state and must not be submitted without explicit user confirmation.

For this investigation, state-changing operations were documented from the bundle and captured UI setup flows, but final mutation submissions were not executed.

## Transports

Sleeper uses three relevant transports.

### Private GraphQL

Base URL:

```text
POST https://sleeper.com/graphql
```

The web app sends JSON:

```json
{
  "operationName": "get_league_detail",
  "variables": {},
  "query": "query get_league_detail { ... }"
}
```

Authentication is via browser cookies on `sleeper.com`. The current app did not expose a separate official bearer-token API for team management, waivers, or trades.

### Web Data REST

Base URL:

```text
https://api.sleeper.com
```

This is used by the web app for large public-ish data such as stats, projections, player metadata, trending adds/drops, schedule, and research.

### Official Public REST

Base URL:

```text
https://api.sleeper.app/v1
```

This is the documented read-only public API used by the MCP server in this repo. It does not authenticate and does not support sending trades, accepting trades, adding/dropping players, or changing lineups.

## Shared Encodings

The private GraphQL API often encodes maps as parallel key/value arrays.

Adds/drops:

```graphql
$k_adds: [String]
$v_adds: [Int]
$k_drops: [String]
$v_drops: [Int]
```

The app builds these from maps like:

```json
{
  "adds": { "player_id": roster_id },
  "drops": { "player_id": roster_id }
}
```

Settings and metadata use the same pattern:

```graphql
$k_settings: [String]
$v_settings: [Float]
$k_metadata: [String]
$v_metadata: [String]
```

Examples:

```json
{
  "k_adds": ["player_id_to_add"],
  "v_adds": [1],
  "k_drops": ["player_id_to_drop"],
  "v_drops": [1]
}
```

## Core Schemas

### League

Common fields returned by `get_league`, `league_update_*`, and league creation/update mutations:

```graphql
company_id
draft_id
last_message_attachment
last_message_id
last_message_time
league_id
metadata
previous_league_id
roster_positions
scoring_settings
season
status
name
avatar
season_type
settings
sport
total_rosters
```

### Roster

Common fields from `league_rosters`, roster update mutations, and user roster reads:

```graphql
league_id
metadata
owner_id
co_owners
players
player_map
roster_id
settings
starters
keepers
reserve
taxi
```

### League User

Common fields:

```graphql
avatar
user_id
league_id
metadata
settings
display_name
is_owner
is_bot
```

### Transaction

Core response shape for trades, waivers, adds/drops, and transaction filters:

```graphql
adds
consenter_ids
created
creator
draft_picks
drops
league_id
leg
metadata
roster_ids
settings
status
status_updated
transaction_id
type
player_map
waiver_budget
```

Observed high-value statuses:

- `pending`
- `proposed`
- Completed/history statuses are returned by unfiltered transaction reads, but the captured active-trade read filtered only `pending` and `proposed`.

Observed high-value transaction types:

- `trade`
- `waiver`
- `free_agent`
- Commissioner/admin transaction types appear in history and are handled by the same transaction schema.

### Draft Pick Asset

Fields from `roster_draft_picks` and `roster_draft_picks_by_draft`:

```graphql
roster_id
season
round
owner_id
```

Trade and draft mutations pass richer `draft_picks` objects, but the visible roster-pick read model uses the fields above.

### League Player Status

Fields returned by trade block, like, and note mutations:

```graphql
player_id
league_id
metadata
settings
```

This object stores per-league player state such as trade block, likes/interests, and notes.

### Matchup Leg

Common fields from matchup reads and forced updates:

```graphql
league_id
leg
matchup_id
roster_id
round
starters
players
player_map
points
proj_points
max_points
custom_points
starters_games
subs
```

### Player News

Fields from `get_player_news`:

```graphql
metadata
player_id
published
source
source_key
sport
```

## Captured Page Flows

### App Initialization

Opening a logged-in league page triggers:

- `initialize_app`
- `create_invite_link` (`APP-AUTO WRITE`)
- `metadata(type: "league_history", key: league_id)`
- `requests`
- `watched_players`
- `teams`
- `league_players`
- `get_league_detail`
- `messages`
- `league_users`
- `get_draft`
- `user_drafts_by_draft`
- `draft_picks`
- `league_transactions_filtered`
- `create_receipt` / `create_read_receipt` field (`APP-AUTO WRITE`)

### League Detail

Captured operation:

```graphql
query get_league_detail {
  league_rosters(league_id: "<league_id>") { ...Roster }
  league_users(league_id: "<league_id>") { ...LeagueUser }
  league_transactions_filtered(
    league_id: "<league_id>",
    roster_id_filters: [],
    type_filters: [],
    leg_filters: [],
    status_filters: ["pending", "proposed"]
  ) { ...Transaction }
  matchup_legs_<round>: matchup_legs(league_id: "<league_id>", round: <round>) { ...MatchupLeg }
  league_playoff_bracket(league_id: "<league_id>") { ... }
}
```

Purpose: hydrate the league page with rosters, users, active transactions, matchup legs, and optional playoff brackets.

### Team Tab

Captured:

- `roster_draft_picks(league_id)`
- `matchup_legs`
- `GET https://api.sleeper.com/players/nfl/research/regular/{season}/{week}?league_type={league_type}`

Purpose: display roster, draft capital, current matchup/status, and market/research context.

### League Tab

Captured:

- `league_transactions_filtered`

Purpose: transaction feed, league activity, and filtered history.

### Players Tab

Captured:

- `league_players(league_id)`
- `batch_scores`
- `get_player_news_for_ids`
- `league_transactions_by_player`
- `get_player_news`
- `GET https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular&position[]=QB&position[]=RB&position[]=TE&position[]=WR&order_by=pts_ppr`

Clicking a free-agent plus opened a player card and loaded player context. It did not submit an add/drop by itself.

### Trend Tab

Captured:

- `league_players(league_id)`
- `batch_scores`
- `GET https://api.sleeper.com/players/nfl/trending/add?limit=50`
- `GET https://api.sleeper.com/players/nfl/trending/drop?limit=50`
- `GET https://api.sleeper.com/players/nfl/research/regular/{season}/{week}?league_type={league_type}`

Purpose: trending adds/drops, player availability context, and recent market movement.

### Trades Tab

Captured:

- `get_draft`
- `league_players`
- `league_transactions_filtered`
- `roster_draft_picks`

Opening "Propose a Trade" loaded roster assets and trade block state. No trade was submitted.

### Scores Tab

Captured:

- `scores`
- `GET https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=off&position=QB&order_by=pts_ppr`
- `GET https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=off&position=RB&order_by=pts_ppr`
- `GET https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=off&position=WR&order_by=pts_ppr`
- `GET https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=off&position=TE&order_by=pts_ppr`
- Matching `projections` URLs for QB/RB/WR/TE.

### Draft / Predraft Tab

Captured:

- `league_users`
- `get_draft`
- `user_drafts_by_draft`
- `draft_picks`
- `league_transactions_filtered`

Purpose: draft state, current picks, draft users, and draft-related transactions.

## Fantasy GraphQL Reads

### `initialize_app`

Class: `READ`

Purpose: bootstrap current user and global app state.

Captured subfields:

```graphql
me { ... }
my_channels { ... }
recommended_channels { ... }
my_leagues(exclude_archived: false) { ...League }
sport_info { ... }
```

### `get_league`

Class: `READ`

Purpose: fetch one league and its core settings.

Shape:

```graphql
query get_league {
  get_league(league_id: "<league_id>") {
    ...League
  }
}
```

### `get_league_detail`

Class: `READ`

Purpose: combined league page hydration. See "League Detail" above.

### `league_rosters`

Class: `READ`

Purpose: fetch all roster objects in a league.

```graphql
query league_rosters {
  league_rosters(league_id: "<league_id>") {
    league_id
    metadata
    owner_id
    co_owners
    players
    player_map
    roster_id
    settings
    starters
    keepers
    reserve
    taxi
  }
}
```

### `league_users`

Class: `READ`

Purpose: fetch all user objects in a league.

```graphql
query league_users {
  league_users(league_id: "<league_id>") {
    avatar
    user_id
    league_id
    metadata
    settings
    display_name
    is_owner
    is_bot
  }
}
```

### `league_user_by_user`

Class: `READ`

Purpose: fetch one league user row by Sleeper user id.

Parameters:

- `league_id`
- `user_id`

### `owned_leagues`

Class: `READ`

Purpose: list leagues owned by the current user.

### `user_rosters`

Class: `READ`

Purpose: list rosters owned by a user.

### `rosters_by_user`

Class: `READ`

Purpose: fetch a user's rosters for a season/sport.

Parameters observed in bundle:

- `season`
- `season_type`
- `sport`
- `user_id`

### `roster_standings`

Class: `READ`

Purpose: read standings data for league rosters.

### `league_playoff_bracket`

Class: `READ`

Purpose: fetch playoff and loser-bracket state.

### `league_transactions_filtered`

Class: `READ`

Purpose: fetch active, historical, or filtered transactions.

```graphql
query league_transactions_filtered {
  league_transactions_filtered(
    league_id: "<league_id>",
    roster_id_filters: [<roster_id>],
    type_filters: ["trade", "waiver", "free_agent"],
    leg_filters: [<leg>],
    status_filters: ["pending", "proposed"],
    limit: <optional_limit>
  ) {
    ...Transaction
  }
}
```

All filter arrays can be empty. The web app uses empty arrays for broad reads.

### `league_transactions_by_player`

Class: `READ`

Purpose: fetch transaction history involving one player.

```graphql
query league_transactions_by_player {
  league_transactions_by_player(
    league_id: "<league_id>",
    player_id: "<player_id>"
  ) {
    ...Transaction
  }
}
```

### `league_players`

Class: `READ`

Purpose: fetch per-league player status records, including trade block, likes, notes, and league-specific metadata/settings.

```graphql
query league_players {
  league_players(league_id: "<league_id>") {
    league_id
    metadata
    player_id
    settings
  }
}
```

### `matchup_legs`

Class: `READ`

Purpose: fetch matchup leg data for one league round/week.

Parameters:

- `league_id`
- `round`

### `get_multiple_matchup_legs`

Class: `READ`

Purpose: batch multiple `matchup_legs` aliases into one query.

### `get_all_matchup_legs`

Class: `READ`

Purpose: fetch all matchup legs for a league.

### `matchup_legs_related_to_roster`

Class: `READ`

Purpose: fetch matchup legs for one roster across a round range.

```graphql
query matchup_legs_related_to_roster {
  matchup_legs_related_to_roster(
    roster_id: <roster_id>,
    league_id: "<league_id>",
    start_round: <start_round>,
    end_round: <end_round>
  ) {
    league_id
    leg
    matchup_id
    player_map
    players
    points
    custom_points
    proj_points
    roster_id
    round
    starters
    starters_games
    subs
  }
}
```

### `roster_draft_picks`

Class: `READ`

Purpose: fetch dynasty draft capital by roster.

```graphql
query roster_draft_picks {
  roster_draft_picks(league_id: "<league_id>") {
    roster_id
    season
    round
    owner_id
  }
}
```

### `roster_draft_picks_by_draft`

Class: `READ`

Purpose: fetch draft-pick ownership for a specific draft.

Parameters:

- `draft_id`

### `metadata`

Class: `READ`

Purpose: generic key/value metadata reads. Captured for league history:

```graphql
metadata(type: "league_history", key: "<league_id>") { ... }
```

### `requests` and `type_data`

Class: `READ`

Purpose: fetch pending requests, including friend, league, DM, and co-owner request state.

## Player, Scores, And News GraphQL Reads

### `get_active_players`

Class: `READ`

Purpose: active player search/listing by sport.

### `search_players`

Class: `READ`

Purpose: prefix search.

```graphql
query search_players {
  search_players(sport: "nfl", prefix: "<query>") {
    player_id
    first_name
    last_name
    position
    team
  }
}
```

### `get_players`

Class: `READ`

Purpose: batch player lookup by ids.

```graphql
query get_players {
  get_player_<player_id>: get_player(sport: "nfl", player_id: "<player_id>") {
    player_id
    team
    number
    position
    first_name
    last_name
    age
    height
    injury_status
    injury_start_date
    injury_notes
    injury_body_part
    weight
    years_exp
    college
  }
}
```

### `get_player_news`

Class: `READ`

Purpose: player news feed.

```graphql
query get_player_news {
  get_player_news(sport: "nfl", player_id: "<player_id>", limit: 10) {
    metadata
    player_id
    published
    source
    source_key
    sport
  }
}
```

### `get_player_news_for_ids`

Class: `READ`

Purpose: batch one latest news item per player using aliases.

### `get_player_outlook`

Class: `READ`

Purpose: player outlook/editorial data.

### `get_player_score_and_projections_batch`

Class: `READ`

Purpose: batch player scores/projections.

### `get_player_stats`

Class: `READ`

Purpose: player stat/projection lookup.

Observed args include:

- `player_id`
- `sport`
- `season`
- `category` (`proj` or `stat`)
- `season_type`
- `week`

### `get_weekly_stats_for_players`

Class: `READ`

Purpose: weekly stats by player batch.

### `weekly_stats`

Class: `READ`

Purpose: weekly aggregate stats.

### `scores`

Class: `READ`

Purpose: game/schedule score state.

Captured alias pattern:

```graphql
query batch_scores {
  nfl__regular__2026__1: scores(
    sport: "nfl",
    season_type: "regular",
    season: "2026",
    week: 1
  ) {
    date
    game_id
    metadata
    season
    season_type
    sport
    status
    week
    start_time
  }
}
```

### `batch_scores`

Class: `READ`

Purpose: app-level batched score aliases.

### `game_stats`

Class: `READ`

Purpose: stats for a game.

```graphql
query game_stats {
  game_stats(
    sport: "nfl",
    season_type: "regular",
    season: "<season>",
    category: "stat",
    game_id: "<game_id>",
    order_by: "<stat_key>",
    positions: ["QB", "RB", "WR", "TE"]
  ) {
    player
    player_id
    season_type
    season
    week
    category
    sport
    stats
    team
  }
}
```

### `plays`

Class: `READ`

Purpose: play-by-play events.

```graphql
query plays {
  plays(
    sport: "nfl",
    season_type: "regular",
    season: "<season>",
    game_id: "<game_id>"
  ) {
    play_id
    game_id
    sequence
    week
    sport
    season
    season_type
    metadata
    play_stats {
      stats
      player
    }
  }
}
```

## Waivers, Adds, Drops, And Trades

All operations in this section are `USER WRITE` unless marked as read. They change rosters, transaction state, or league assets.

### `league_create_transaction`

Class: `USER WRITE`

Purpose: submit instant add/drop style transactions. The app function around it is named `addAndDropPlayers`; the `type` argument is passed separately and is expected to include values such as `free_agent`.

```graphql
mutation league_create_transaction(
  $k_adds: [String],
  $v_adds: [Int],
  $k_drops: [String],
  $v_drops: [Int]
) {
  league_create_transaction(
    league_id: "<league_id>",
    type: "<transaction_type>",
    k_adds: $k_adds,
    v_adds: $v_adds,
    k_drops: $k_drops,
    v_drops: $v_drops
  ) {
    adds
    consenter_ids
    created
    creator
    drops
    league_id
    leg
    metadata
    roster_ids
    settings
    status
    status_updated
    transaction_id
    type
    player_map
  }
}
```

### `submit_waiver_claim`

Class: `USER WRITE`

Purpose: submit a waiver claim, including optional bid/priority settings.

```graphql
mutation submit_waiver_claim(
  $k_adds: [String],
  $v_adds: [Int],
  $k_drops: [String],
  $v_drops: [Int],
  $k_settings: [String],
  $v_settings: [Int]
) {
  submit_waiver_claim(
    league_id: "<league_id>",
    k_adds: $k_adds,
    v_adds: $v_adds,
    k_drops: $k_drops,
    v_drops: $v_drops,
    k_settings: $k_settings,
    v_settings: $v_settings
  ) {
    ...Transaction
  }
}
```

### `cancel_waiver_claim`

Class: `USER WRITE`

Purpose: cancel an existing waiver claim.

Parameters:

- `league_id`
- `leg`
- `transaction_id`

Returns: `Transaction`.

### `update_waiver_claim`

Class: `USER WRITE`

Purpose: update settings on an existing waiver claim.

Parameters:

- `league_id`
- `transaction_id`
- `leg`
- `k_settings`
- `v_settings`

Returns: `Transaction`.

### `propose_trade`

Class: `USER WRITE`

Purpose: submit a trade proposal.

```graphql
mutation propose_trade(
  $k_adds: [String],
  $v_adds: [Int],
  $k_drops: [String],
  $v_drops: [Int]
) {
  propose_trade(
    league_id: "<league_id>",
    draft_picks: <draft_picks>,
    k_adds: $k_adds,
    v_adds: $v_adds,
    k_drops: $k_drops,
    v_drops: $v_drops,
    waiver_budget: <waiver_budget>,
    expires_at: <optional_timestamp>,
    reject_transaction_id: <optional_transaction_id>,
    reject_transaction_leg: <optional_leg>
  ) {
    adds
    consenter_ids
    created
    creator
    draft_picks
    drops
    league_id
    leg
    metadata
    roster_ids
    settings
    status
    status_updated
    transaction_id
    type
    player_map
    waiver_budget
  }
}
```

Notes:

- `adds` and `drops` are roster-id maps keyed by player id.
- `draft_picks` carries dynasty pick assets.
- `waiver_budget` can be included in trade assets when league settings support it.
- `reject_transaction_id` and `reject_transaction_leg` support counteroffer style flows.

### `accept_trade`

Class: `USER WRITE`

Purpose: accept a proposed trade.

Parameters:

- `league_id`
- `transaction_id`
- `leg`

Returns: `Transaction`.

### `reject_trade`

Class: `USER WRITE`

Purpose: reject a proposed trade.

Parameters:

- `league_id`
- `transaction_id`
- `leg`

Returns: `Transaction`.

### `force_cancel_transaction`

Class: `ADMIN WRITE`

Purpose: force-cancel a transaction.

Parameters:

- `league_id`
- `transaction_id`
- `leg`

Returns: `Transaction`.

### `process_transaction`

Class: `ADMIN WRITE`

Purpose: commissioner/admin processing of a transaction.

Parameters:

- `league_id`
- `transaction_id`
- `leg`

Returns: `Transaction`.

## Trade Block, Likes, Notes, Watchlist

### `add_league_player_trade_block`

Class: `USER WRITE`

Purpose: place a player or pick on the league trade block.

```graphql
mutation add_league_player_trade_block {
  add_league_player_trade_block(
    league_id: "<league_id>",
    player_id: "<player_id_or_pick_id>"
  ) {
    player_id
    league_id
    metadata
    settings
  }
}
```

### `remove_league_player_trade_block`

Class: `USER WRITE`

Purpose: remove a player or pick from the league trade block.

Same args and return shape as `add_league_player_trade_block`.

### `like_league_player`

Class: `USER WRITE`

Purpose: mark interest/like on a league player or pick.

Same args and return shape as trade block operations.

### `unlike_league_player`

Class: `USER WRITE`

Purpose: remove interest/like from a league player or pick.

### `add_league_player_note`

Class: `USER WRITE`

Purpose: save a private/user note on a league player.

```graphql
mutation add_league_player_note($note: String) {
  add_league_player_note(
    league_id: "<league_id>",
    player_id: "<player_id>",
    note: $note
  ) {
    league_id
    metadata
    player_id
    settings
  }
}
```

### `remove_league_player_note`

Class: `USER WRITE`

Purpose: delete a player note.

Parameters:

- `league_id`
- `player_id`

### `watch_player`

Class: `USER WRITE`

Purpose: add a player to the user's global watchlist.

### `unwatch_player`

Class: `USER WRITE`

Purpose: remove a player from the user's global watchlist.

### `unwatch_all_players`

Class: `USER WRITE`

Purpose: clear watched players.

### `watched_players`

Class: `READ`

Purpose: list watched players.

## Roster Management

All roster-management mutations are `USER WRITE` or `ADMIN WRITE` depending on league role and target roster.

### `roster_update_starters`

Class: `USER WRITE`

Purpose: set the starting lineup.

```graphql
mutation roster_update_starters {
  roster_update_starters(
    league_id: "<league_id>",
    roster_id: <roster_id>,
    starters: ["<player_id>", ...]
  ) {
    league_id
    co_owners
    metadata
    owner_id
    players
    player_map
    roster_id
    reserve
    taxi
    settings
    starters
  }
}
```

### `roster_update_reserve`

Class: `USER WRITE`

Purpose: update injured/reserve slot membership.

Args:

- `league_id`
- `roster_id`
- `reserve`

Returns: `Roster`.

### `roster_update_taxi`

Class: `USER WRITE`

Purpose: update taxi squad membership.

Args:

- `league_id`
- `roster_id`
- `taxi`
- optional `force: true`

Returns: `Roster`.

### `roster_update_settings`

Class: `ADMIN WRITE`

Purpose: update roster numeric settings.

```graphql
mutation roster_update_settings($k_settings: [String], $v_settings: [Int]) {
  roster_update_settings(
    league_id: "<league_id>",
    roster_id: <roster_id>,
    k_settings: $k_settings,
    v_settings: $v_settings
  ) {
    league_id
    metadata
    owner_id
    players
    roster_id
    reserve
    settings
    starters
    player_map
  }
}
```

### `roster_update_metadata`

Class: `ADMIN WRITE`

Purpose: update roster metadata.

```graphql
mutation roster_update_metadata($k_metadata: [String], $v_metadata: [String]) {
  roster_update_metadata(
    league_id: "<league_id>",
    roster_id: <roster_id>,
    k_metadata: $k_metadata,
    v_metadata: $v_metadata
  ) {
    league_id
    metadata
    owner_id
    players
    roster_id
    reserve
    taxi
    settings
    starters
    player_map
  }
}
```

### `roster_set_keepers`

Class: `USER WRITE`

Purpose: set keeper players for a roster.

### `create_roster` / `delete_roster`

Class: `ADMIN WRITE`

Purpose: add or remove league rosters.

### `create_user_roster` / `delete_user_roster`

Class: `USER WRITE`

Purpose: user roster creation/removal surfaces.

### `update_user_roster_players`

Class: `USER WRITE`

Purpose: update players on a user roster.

### `roster_change_owner`

Class: `ADMIN WRITE`

Purpose: transfer roster ownership.

### `remove_co_owner`

Class: `ADMIN WRITE`

Purpose: remove a co-owner from a roster/league user relationship.

## Matchup And Scoring Writes

### `add_matchup_leg_pick`

Class: `USER WRITE`

Purpose: tournament/pick-style matchup selection.

### `add_matchup_leg_ban`

Class: `USER WRITE`

Purpose: matchup ban selection.

### `update_matchup_leg`

Class: `ADMIN WRITE`

Purpose: update matchup leg state.

### `force_update_matchup_leg`

Class: `ADMIN WRITE`

Purpose: force update a matchup leg.

### `update_matchup_leg_custom_points`

Class: `ADMIN WRITE`

Purpose: set custom points for a matchup leg.

### `recalculate_matchup_scoring`

Class: `ADMIN WRITE`

Purpose: trigger scoring recalculation.

## Drafts And Dynasty Picks

### Draft Reads

`get_draft`

Class: `READ`

Purpose: draft room metadata/settings/state.

`draft_picks`

Class: `READ`

Purpose: picks already made in a draft. Captured as a field in the draft page flow.

`user_drafts`

Class: `READ`

Purpose: current user's drafts.

`user_drafts_by_status`

Class: `READ`

Purpose: drafts filtered by status.

`user_drafts_by_league_mock`

Class: `READ`

Purpose: mock drafts associated with a league.

`user_drafts_by_draft`

Class: `READ`

Purpose: users for a draft, captured in predraft.

`drafts_by_league_id`

Class: `READ`

Purpose: all drafts for a league.

`draft_queue`

Class: `READ`

Purpose: current user's queued draft players.

`draft_autopickers`

Class: `READ`

Purpose: users currently marked for autopick.

`draft_offers`

Class: `READ`

Purpose: auction/offering state in auction drafts.

`get_user_draft_settings`

Class: `READ`

Purpose: per-user draft preferences/settings.

### Draft Writes

`create_draft`

Class: `ADMIN WRITE`

Purpose: create a draft.

`clone_draft`

Class: `ADMIN WRITE`

Purpose: clone an existing draft.

`delete_draft`

Class: `ADMIN WRITE`

Purpose: delete a draft.

`update_draft_settings`

Class: `ADMIN WRITE`

Purpose: update draft settings.

`update_draft_metadata`

Class: `ADMIN WRITE`

Purpose: update draft metadata.

`update_draft_order`

Class: `ADMIN WRITE`

Purpose: set draft order.

`randomize_draft_order`

Class: `ADMIN WRITE`

Purpose: randomize draft order.

`update_draft_type`

Class: `ADMIN WRITE`

Purpose: change draft type.

`update_draft_status`

Class: `ADMIN WRITE`

Purpose: change draft status.

`update_draft_start_time`

Class: `ADMIN WRITE`

Purpose: change scheduled draft start.

`join_draft`

Class: `USER WRITE`

Purpose: join a draft.

`leave_draft`

Class: `USER WRITE`

Purpose: leave a draft.

`claim_draft_slot`

Class: `USER WRITE`

Purpose: claim a draft slot.

`draft_pick_player`

Class: `USER WRITE`

Purpose: make a player pick.

`draft_remove_pick`

Class: `ADMIN WRITE`

Purpose: remove a pick.

`draft_cpu_pick_player`

Class: `ADMIN WRITE`

Purpose: force a CPU/autopick.

`react_to_draft_pick`

Class: `USER WRITE`

Purpose: react to a draft pick.

`draft_set_keeper`

Class: `USER WRITE`

Purpose: mark/set a keeper in draft context.

`update_user_draft_settings`

Class: `USER WRITE`

Purpose: save personal draft settings.

`update_draft_queue`

Class: `USER WRITE`

Purpose: update queued draft players.

`put_user_on_autopick`

Class: `ADMIN WRITE`

Purpose: force a user onto autopick.

`remove_user_from_autopick`

Class: `ADMIN WRITE`

Purpose: remove autopick state.

`draft_make_offer`

Class: `USER WRITE`

Purpose: submit an auction draft offer/bid.

`draft_hover_player`

Class: `USER WRITE`

Purpose: broadcast draft-room hover/presence around a player.

`draft_nominate_player`

Class: `USER WRITE`

Purpose: nominate a player in auction draft.

`draft_force_auction_pick`

Class: `ADMIN WRITE`

Purpose: force an auction pick.

`draft_set_nominator`

Class: `ADMIN WRITE`

Purpose: set auction nominator.

`draft_end_phase`

Class: `ADMIN WRITE`

Purpose: end a draft/auction phase.

`draft_pass_offering`

Class: `USER WRITE`

Purpose: pass an auction offering.

`draft_resume_offering`

Class: `ADMIN WRITE`

Purpose: resume an offering.

`draft_clear_afk_rounds`

Class: `ADMIN WRITE`

Purpose: clear AFK round tracking.

### Dynasty Pick Writes

`assign_roster_draft_pick`

Class: `ADMIN WRITE`

Purpose: assign a draft pick asset.

```graphql
mutation assign_roster_draft_pick {
  assign_roster_draft_pick(
    league_id: "<league_id>",
    draft_pick: <draft_pick_object>
  ) {
    league_id
  }
}
```

`unassign_roster_draft_pick`

Class: `ADMIN WRITE`

Purpose: unassign a draft pick asset.

Args:

- `league_id`
- `roster_id`
- `season`
- `round`

`create_supplemental_draft`

Class: `ADMIN WRITE`

Purpose: create a supplemental draft.

`reset_to_startup_draft`

Class: `ADMIN WRITE`

Purpose: reset league to startup draft state.

## League Admin And Settings

Most operations in this section are `ADMIN WRITE`.

### Scoring And Settings

`league_update_scoring_settings`

Purpose: update scoring keys.

```graphql
mutation league_update_scoring_settings(
  $k_scoring_settings: [String],
  $v_scoring_settings: [Float]
) {
  league_update_scoring_settings(
    league_id: "<league_id>",
    k_scoring_settings: $k_scoring_settings,
    v_scoring_settings: $v_scoring_settings
  ) {
    ...League
  }
}
```

`league_update_settings`

Purpose: update numeric/general league settings.

```graphql
mutation league_update_settings($k_settings: [String], $v_settings: [Float]) {
  league_update_settings(
    league_id: "<league_id>",
    k_settings: $k_settings,
    v_settings: $v_settings
  ) {
    ...League
  }
}
```

`league_update_metadata`

Purpose: update string metadata.

```graphql
mutation league_update_metadata($k_metadata: [String], $v_metadata: [String]) {
  league_update_metadata(
    league_id: "<league_id>",
    k_metadata: $k_metadata,
    v_metadata: $v_metadata
  ) {
    ...League
  }
}
```

`update_league_user_metadata`

Class: `USER WRITE`

Purpose: update a user's per-league metadata/preferences.

### League Identity And Structure

`league_update_name`

Purpose: rename a league.

`league_update_avatar`

Purpose: update league avatar.

`league_update_roster_positions`

Purpose: update roster slot structure.

`league_update_display_order`

Purpose: update league display order.

`league_update_custom_standings`

Purpose: update custom standings.

`league_update_owners`

Purpose: update owner mapping.

`league_remove_user`

Purpose: remove a user from a league.

`configure_divisions`

Purpose: configure divisions.

`remove_divisions`

Purpose: remove divisions.

`update_opponents`

Purpose: update schedule/opponent mapping.

`import_league_users`

Purpose: import users into a league.

`continue_league`

Purpose: continue/roll league forward.

`create_league`

Purpose: create a league.

`delete_league`

Purpose: delete a league.

`leave_league`

Class: `USER WRITE`

Purpose: leave a league.

`join_public_league`

Class: `USER WRITE`

Purpose: join a public league.

### Mascot And Cosmetic

`set_league_mascot`

Class: `USER WRITE`

Purpose: set league mascot.

`set_league_mascot_message`

Class: `USER WRITE`

Purpose: set mascot message.

`set_league_mascot_emotion`

Class: `USER WRITE`

Purpose: set mascot emotion.

## League Sync

These are likely import/sync workflows for external leagues. Treat all as sensitive because they can connect accounts or create leagues.

`league_sync_login`

Class: `USER WRITE`

Purpose: authenticate/login to a league sync provider.

`league_sync_get_mask`

Class: `READ`

Purpose: fetch sync masking/config state.

`league_sync_send_recovery_code`

Class: `USER WRITE`

Purpose: send a recovery code.

`league_sync_use_recovery_code`

Class: `USER WRITE`

Purpose: use a recovery code.

`league_sync_list_leagues`

Class: `READ`

Purpose: list leagues available to import/sync.

`league_sync_create_league`

Class: `ADMIN WRITE`

Purpose: create a Sleeper league from synced external data.

## Public Web Data REST

Captured from `https://api.sleeper.com`.

### Player Metadata

```text
GET /players/nfl
```

Purpose: full player metadata map.

### Trending Adds/Drops

```text
GET /players/nfl/trending/add?limit=50
GET /players/nfl/trending/drop?limit=50
```

Purpose: trending player adds and drops.

### Research

```text
GET /players/nfl/research/regular/{season}/{week}?league_type={league_type}
```

Purpose: market/research data for players.

### Stats

```text
GET /stats/nfl/{season}/{week}?season_type=regular&position[]=QB&position[]=RB&position[]=TE&position[]=WR&order_by=pts_ppr
GET /stats/nfl/{season}/{week}?season_type=off&position[]=QB&position[]=RB&position[]=TE&position[]=WR&order_by=pts_ppr
GET /stats/nfl/{season}?season_type=regular&position=TEAM&order_by=
GET /stats/nfl/{season}?season_type=regular&position=DEF&order_by=fan_pts_allow
GET /stats/nfl/{season}?season_type=regular&position[]=TEAM&order_by=pts_std
```

Purpose: fantasy scoring stats, team stats, and defense points allowed.

### Projections

```text
GET /projections/nfl/{season}/{week}?season_type=regular&position[]=QB&position[]=RB&position[]=TE&position[]=WR&order_by=pts_ppr
GET /projections/nfl/{season}/{week}?season_type=off&position=QB&order_by=pts_ppr
GET /projections/nfl/{season}/{week}?season_type=off&position=RB&order_by=pts_ppr
GET /projections/nfl/{season}/{week}?season_type=off&position=WR&order_by=pts_ppr
GET /projections/nfl/{season}/{week}?season_type=off&position=TE&order_by=pts_ppr
```

Purpose: player fantasy projections.

### Schedule

```text
GET /schedule/nfl/regular/{season}
```

Purpose: NFL schedule for fantasy week mapping.

## Official Public REST Used By This MCP

Base URL:

```text
https://api.sleeper.app/v1
```

These are read-only and unauthenticated.

```text
GET /user/{username_or_user_id}
GET /user/{user_id}/leagues/{sport}/{season}
GET /user/{user_id}/drafts/{sport}/{season}
GET /league/{league_id}
GET /league/{league_id}/rosters
GET /league/{league_id}/users
GET /league/{league_id}/matchups/{week}
GET /league/{league_id}/winners_bracket
GET /league/{league_id}/losers_bracket
GET /league/{league_id}/transactions/{round_or_week}
GET /league/{league_id}/traded_picks
GET /league/{league_id}/drafts
GET /state/{sport}
GET /draft/{draft_id}
GET /draft/{draft_id}/picks
GET /draft/{draft_id}/traded_picks
GET /players/{sport}
GET /players/{sport}/trending/{add_or_drop}?lookback_hours={hours}&limit={limit}
```

## Fantasy/Dynasty Operation Inventory

This is the relevant operation set found in the current web bundle. `READ` operations can be used for documentation/status. `USER WRITE` and `ADMIN WRITE` require explicit confirmation before sending.

### League Reads

- `get_league`
- `get_league_detail`
- `league_rosters`
- `league_users`
- `league_user_by_user`
- `owned_leagues`
- `user_rosters`
- `rosters_by_user`
- `roster_standings`
- `league_playoff_bracket`
- `league_transactions_filtered`
- `league_transactions_by_player`
- `league_players`
- `metadata`
- `sport_info`
- `sync_local_data`
- `teams`
- `requests`
- `type_data`

### Roster And Matchup Reads

- `matchup_legs`
- `matchup_legs_related_to_roster`
- `get_multiple_matchup_legs`
- `get_all_matchup_legs`
- `scores`
- `batch_scores`
- `game_stats`
- `plays`

### Player Reads

- `get_active_players`
- `search_players`
- `get_players`
- `get_player_news`
- `get_player_news_for_ids`
- `get_player_outlook`
- `get_player_score_and_projections_batch`
- `get_player_stats`
- `get_weekly_stats_for_players`
- `weekly_stats`
- `watched_players`

### Draft And Pick Reads

- `get_draft`
- `user_drafts`
- `user_drafts_by_status`
- `user_drafts_by_league_mock`
- `drafts_by_league_id`
- `draft_queue`
- `draft_autopickers`
- `draft_offers`
- `get_user_draft_settings`
- `roster_draft_picks`
- `roster_draft_picks_by_draft`

### Waiver, Add/Drop, And Trade Writes

- `league_create_transaction`
- `submit_waiver_claim`
- `cancel_waiver_claim`
- `update_waiver_claim`
- `propose_trade`
- `accept_trade`
- `reject_trade`
- `force_cancel_transaction`
- `process_transaction`

### Trade Block, Watchlist, And Player Status Writes

- `add_league_player_trade_block`
- `remove_league_player_trade_block`
- `like_league_player`
- `unlike_league_player`
- `add_league_player_note`
- `remove_league_player_note`
- `watch_player`
- `unwatch_player`
- `unwatch_all_players`

### Roster Writes

- `roster_update_starters`
- `roster_update_reserve`
- `roster_update_taxi`
- `roster_update_settings`
- `roster_update_metadata`
- `roster_set_keepers`
- `create_roster`
- `delete_roster`
- `create_user_roster`
- `delete_user_roster`
- `update_user_roster_players`
- `roster_change_owner`
- `remove_co_owner`

### Matchup And Scoring Writes

- `add_matchup_leg_pick`
- `add_matchup_leg_ban`
- `update_matchup_leg`
- `force_update_matchup_leg`
- `update_matchup_leg_custom_points`
- `recalculate_matchup_scoring`

### Draft Writes

- `create_draft`
- `clone_draft`
- `delete_draft`
- `update_draft_settings`
- `update_draft_metadata`
- `update_draft_order`
- `randomize_draft_order`
- `update_draft_type`
- `update_draft_status`
- `update_draft_start_time`
- `join_draft`
- `leave_draft`
- `claim_draft_slot`
- `draft_pick_player`
- `draft_remove_pick`
- `draft_cpu_pick_player`
- `react_to_draft_pick`
- `draft_set_keeper`
- `update_user_draft_settings`
- `update_draft_queue`
- `put_user_on_autopick`
- `remove_user_from_autopick`
- `draft_make_offer`
- `draft_hover_player`
- `draft_nominate_player`
- `draft_force_auction_pick`
- `draft_set_nominator`
- `draft_end_phase`
- `draft_pass_offering`
- `draft_resume_offering`
- `draft_clear_afk_rounds`

### Dynasty Pick Writes

- `assign_roster_draft_pick`
- `unassign_roster_draft_pick`
- `create_supplemental_draft`
- `reset_to_startup_draft`

### League Admin Writes

- `league_update_scoring_settings`
- `league_update_settings`
- `league_update_metadata`
- `update_league_user_metadata`
- `league_update_name`
- `league_update_avatar`
- `league_update_roster_positions`
- `league_update_display_order`
- `league_update_custom_standings`
- `league_update_owners`
- `league_remove_user`
- `configure_divisions`
- `remove_divisions`
- `update_opponents`
- `import_league_users`
- `continue_league`
- `create_league`
- `delete_league`
- `leave_league`
- `join_public_league`
- `set_league_mascot`
- `set_league_mascot_message`
- `set_league_mascot_emotion`

### League Sync

- `league_sync_login`
- `league_sync_get_mask`
- `league_sync_send_recovery_code`
- `league_sync_use_recovery_code`
- `league_sync_list_leagues`
- `league_sync_create_league`

### League Chat/Receipt Operations Seen During Fantasy Pages

These are not core fantasy roster APIs, but they are triggered by league pages.

- `messages`
- `create_message`
- `change_message_text`
- `delete_message`
- `pinned_messages`
- `pin_message`
- `unpin_message`
- `create_reaction`
- `delete_reaction`
- `messages_by_reaction`
- `create_receipt` / `create_read_receipt` field
- `read_receipts`
- `mentions`
- `mark_mention_as_read`
- `clear_unread_mentions`
- `typing_on_league`

## Auth Handling For A Future Private MCP

The official MCP in this repo intentionally uses only the public read-only API. A private API MCP would need a separate transport and stricter auth handling.

Recommended model:

1. Do not store Sleeper credentials in the repo.
2. Do not copy cookies from Chrome storage.
3. For local-only use, allow the user to provide a short-lived `Cookie` header via an environment variable or OS keychain item.
4. Redact `cookie`, `authorization`, CSRF, and token-like values from logs and MCP tool results.
5. Split tools into `read_*` and `mutate_*` namespaces.
6. Require an explicit confirmation gate for every mutation tool.
7. Dry-run every trade/waiver mutation by rendering the exact assets, roster ids, player names, picks, waiver budget, and action before sending.

Possible environment variables for a private transport:

```text
SLEEPER_PRIVATE_GRAPHQL_URL=https://sleeper.com/graphql
SLEEPER_PRIVATE_COOKIE=<redacted browser cookie header>
SLEEPER_PRIVATE_ENABLE_MUTATIONS=0
```

Default should be read-only. `SLEEPER_PRIVATE_ENABLE_MUTATIONS=1` should still require per-call confirmation in the host agent.

## MCP Server In This Repo

The committed MCP server currently targets the official public read-only API. It is safe for unauthenticated fantasy research and league inspection.

### Installation

From a checkout:

```bash
python3 -m pip install -e .
```

From GitHub:

```bash
python3 -m pip install "git+https://github.com/rau/sleeper-mcp-skill.git"
```

### MCP Configuration

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

Module entrypoint:

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

### Public MCP Tools

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

### Local Codex Skill

The Codex skill lives at `skills/sleeper/SKILL.md`.

Manual install:

```bash
mkdir -p ~/.codex/skills/sleeper
cp skills/sleeper/SKILL.md ~/.codex/skills/sleeper/SKILL.md
```

### Development

This repo has no build step. Syntax and unit checks:

```bash
python3 -m compileall src tests
pytest
```

Sleeper asks clients to keep calls under 1000 requests per minute. This client defaults below that and caches player metadata because `/players/{sport}` is large.

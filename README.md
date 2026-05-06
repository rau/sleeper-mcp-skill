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
- `AUTH WRITE`: logs in, logs out, verifies contact info, changes credentials, or otherwise affects account auth state.
- `DANGEROUS AUTH WRITE`: destructive account-auth operation, such as account deletion.

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

Authentication is via the web app's saved auth token plus normal browser cookies on `sleeper.com`. The current app did not expose a separate official OAuth-style bearer-token API for team management, waivers, or trades.

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

## Auth And Session Preservation

This section is based on static bundle inspection, not by dumping the active browser session.

### Request Auth Mechanics

The web GraphQL wrapper posts to relative `/graphql`, which resolves to:

```text
POST https://sleeper.com/graphql
```

The same code path can resolve to `https://api.sleeper.com/graphql` in mobile/native-style environments.

GraphQL requests include:

```text
Content-Type: application/json
Accept: application/json
X-Sleeper-GraphQL-Op: <operationName>
Authorization: <stored token>
X-Device-ID: <deviceUniqueId, if known>
```

The `Authorization` header value is the raw token string returned by Sleeper login/signup flows. The bundle does not prepend `Bearer`.

The request interceptor only adds `Authorization` for relative URLs or allowlisted Sleeper domains:

```text
sleeperbot
sleeper.com
sleeper.app
sleeper.im
sleeper.dev
blitzchat
:4000
```

Cookies are still part of the browser session. Logout explicitly calls a cookie-aware endpoint with `credentials: "include"`.

### Local Auth State

On startup, the web app reads:

```text
token
key
```

from its client storage wrapper. Login and signup persist:

```text
token
user_id
```

Logout removes:

```text
token
user_id
blocked_users_data
blockers_data
preferences_data
bans_data
```

### Refresh Behavior

No explicit `refresh_token` string and no standalone refresh endpoint were found in the current web bundle.

Instead, the app has an opportunistic token replacement path:

1. A GraphQL or REST response can contain a replacement `token`.
2. On API/GraphQL errors, if the response data contains `token`, the app stores that new token.
3. The app dispatches an internal `API_ERROR_401_REFRESH` action for that replacement path.
4. If a 401 has no replacement token, the app removes `token` and `user_id` and treats auth as invalid.

For an MCP or agent, mirror this behavior:

```text
load token before each request
send Authorization: <token>
send Cookie header only from a local secret store or cookie jar
after every response, check for top-level token or data.token
if a replacement token appears, atomically update the auth store
if 401 without replacement token, mark auth invalid and ask for login
```

### Recommended Private MCP Auth Store

Do not put Sleeper auth in the repo, README, skill prompt, or MCP tool output.

For local-only use, use one of:

- macOS Keychain item, preferred.
- A `0600` JSON file outside the repo, for example under `~/.cache/sleeper-mcp-skill/private-auth.json`.
- Explicit environment variables for a one-off session.

Suggested private auth shape:

```json
{
  "token": "<redacted>",
  "user_id": "<redacted>",
  "device_id": "<optional redacted>",
  "cookies": "<optional redacted Cookie header or cookie-jar reference>",
  "updated_at": "2026-05-06T00:00:00Z"
}
```

Suggested environment variables:

```text
SLEEPER_PRIVATE_GRAPHQL_URL=https://sleeper.com/graphql
SLEEPER_PRIVATE_TOKEN=<redacted token>
SLEEPER_PRIVATE_COOKIE=<redacted cookie header>
SLEEPER_PRIVATE_DEVICE_ID=<optional redacted device id>
SLEEPER_PRIVATE_AUTH_FILE=~/.cache/sleeper-mcp-skill/private-auth.json
SLEEPER_PRIVATE_ENABLE_MUTATIONS=0
```

The private MCP should default to read-only even when authenticated. `SLEEPER_PRIVATE_ENABLE_MUTATIONS=1` should only unlock mutation tools after the host agent also asks for per-call confirmation.

### Local Setup Script

This repo includes a local setup script that stores secrets in macOS Keychain and writes only redacted/non-secret config to:

```text
~/Library/Application Support/sleeper-mcp-skill/config.json
```

From a checkout:

```bash
python3 scripts/setup_private_auth.py
```

It prompts for Sleeper email/phone/username and password in the terminal, calls the private GraphQL `login_query`, stores the returned token in Keychain, and writes config with `enable_mutations: false`.

If you already have a token and do not want the script to perform login:

```bash
python3 scripts/setup_private_auth.py --manual-token
```

If cookies become necessary for a specific private endpoint, store a cookie header separately:

```bash
python3 scripts/setup_private_auth.py --manual-token --cookie
```

Check redacted status:

```bash
python3 scripts/setup_private_auth.py --status
```

Installed entrypoint:

```bash
sleeper-private-auth --status
```

The script never prints the token or cookie. It uses:

```text
security add-generic-password ... -w
```

with the secret passed through stdin instead of a command-line argument.

### Agent Preservation Model

For a Codex skill or agent, the clean boundary is:

1. The skill tells the agent to call the local MCP.
2. The MCP owns auth loading, request headers, token refresh updates, and redaction.
3. MCP tools never return the token, cookie, or full request headers.
4. Read tools can run directly.
5. Mutation tools return a dry-run plan first and require explicit confirmation before sending.

This preserves auth across agent turns without pasting credentials into the chat context.

## Auth GraphQL And Web Endpoints

### `login_context_by_email_or_phone_or_username`

Class: `READ`

Purpose: inspect what login methods exist for an identifier.

```graphql
query login_context_by_email_or_phone_or_username {
  login_context_by_email_or_phone_or_username(
    email_or_phone_or_username: "<identifier>"
  )
}
```

Observed returned fields in the app state mapping:

```graphql
has_password
has_email
has_phone
user_id
display_name
avatar
real_name
masked_email
masked_phone
```

### `login_query` / `login`

Class: `AUTH WRITE`

Purpose: password login.

```graphql
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
    avatar
    cookies
    created
    display_name
    real_name
    email
    notifications
    phone
    user_id
    verification
    data_updated
  }
}
```

On success, the web app stores `token` and `user_id`.

### Logout

Class: `AUTH WRITE`

Transport: web REST, not GraphQL.

```text
POST /web-api/auth/logout
credentials: include
```

Purpose: invalidate/clear browser auth. The app then clears local auth-related storage.

### `create_user`

Class: `AUTH WRITE`

Purpose: signup.

The bundle names the mutation `create_user` but calls the GraphQL field `user`.

```graphql
mutation create_user($password: String, $captcha: String) {
  user(
    display_name: "<username>",
    email_or_phone: "<email_or_phone>",
    code: "<verification_code>",
    avatar_url: "<optional_avatar_url>",
    password: $password,
    captcha: $captcha
  ) {
    avatar
    created
    display_name
    real_name
    email
    notifications
    phone
    token
    user_id
    verification
  }
}
```

On success, the web app stores `token` and `user_id`.

### `request_verification`

Class: `AUTH WRITE`

Purpose: send verification for email or phone, with optional captcha.

```graphql
mutation request_verification($captcha: String) {
  request_verification(
    email_or_phone: "<email_or_phone>",
    captcha: $captcha
  )
}
```

### `create_verification_code`

Class: `AUTH WRITE`

Purpose: request a verification code for signup/contact verification.

```graphql
mutation create_verification_code($captcha: String) {
  create_verification_code(
    email_or_phone: "<email_or_phone>",
    captcha: $captcha
  )
}
```

### `verify_verification_code`

Class: `AUTH WRITE`

Purpose: validate an email/phone verification code.

```graphql
mutation verify_verification_code {
  verify_verification_code(
    email_or_phone: "<email_or_phone>",
    code: "<code>"
  )
}
```

### `create_phone_code`

Class: `AUTH WRITE`

Purpose: request a phone code.

```graphql
mutation create_phone_code {
  create_phone_code(phone: "<phone>")
}
```

### `verify_phone_code`

Class: `AUTH WRITE`

Purpose: verify a phone code.

```graphql
mutation verify_phone_code {
  verify_phone_code(
    phone: "<phone>",
    code: "<code>"
  )
}
```

### `verify_contact_update`

Class: `AUTH WRITE`

Purpose: complete a contact-info update verification.

```graphql
mutation verify_contact_update {
  verify_contact_update(code: "<code>") {
    avatar
    created
    display_name
    real_name
    email
    notifications
    phone
    token
    user_id
    verification
  }
}
```

This can return a new `token`; persist it if present.

### `request_password_reset`

Class: `AUTH WRITE`

Purpose: request password reset.

```graphql
mutation request_password_reset($captcha: String) {
  request_password_reset(
    email_or_phone: "<email_or_phone>",
    captcha: $captcha
  )
}
```

### `reset_password`

Class: `AUTH WRITE`

Purpose: reset password using a reset code.

```graphql
mutation reset_password {
  reset_password(
    code: "<code>",
    password: "<new_password>"
  )
}
```

### `reset_password_with_code`

Class: `AUTH WRITE`

Purpose: reset password with email/phone plus code.

```graphql
mutation reset_password_with_code(
  $email_or_phone: String!,
  $password: String!,
  $code: String!
) {
  reset_password_with_code(
    email_or_phone: $email_or_phone,
    password: $password,
    code: $code
  )
}
```

### `change_password`

Class: `AUTH WRITE`

Purpose: change password for an authenticated user.

```graphql
mutation change_password {
  change_password(
    password: "<new_password>",
    old_password: "<old_password>"
  )
}
```

### `update_user_display_name`

Class: `USER WRITE`

Purpose: update account display name.

```graphql
mutation updateUserDisplayName {
  update_user_display_name(display_name: "<display_name>") {
    avatar
    created
    display_name
    real_name
    email
    notifications
    phone
    token
    user_id
    verification
  }
}
```

### `update_user_avatar_url`

Class: `USER WRITE`

Purpose: update account avatar.

```graphql
mutation updateUserAvatar {
  update_user_avatar_url(avatar_url: "<avatar_url>") {
    avatar
    created
    display_name
    real_name
    email
    notifications
    phone
    token
    user_id
    verification
  }
}
```

### `delete_user`

Class: `DANGEROUS AUTH WRITE`

Purpose: delete account. Do not expose as an agent tool without a hard deny or multi-step manual confirmation.

```graphql
mutation delete_user {
  delete_user(
    email_or_phone_or_username: "<identifier>",
    password: "<password>"
  ) {
    user_id
  }
}
```

### `update_preferences`

Class: `USER WRITE`

Purpose: update user/app preference rows.

```graphql
mutation update_preferences {
  update_preferences(
    names: ["<name>"],
    values: ["<value>"],
    type_id: "<type_id>"
  )
}
```

### `app_info`

Class: `READ`

Purpose: fetch app info/config.

```graphql
query app_info {
  app_info
}
```

### Invite Codes Adjacent To Auth

These are not auth tokens, but they are involved in signup/join flows.

`create_invite_link`

Class: `APP-AUTO WRITE` or `USER WRITE`

```graphql
mutation create_invite_link {
  create_invite_link(
    type: "<invite_type>",
    type_id: "<type_id>",
    expires_at: <optional_timestamp>,
    uses_remaining: <optional_count>,
    code: "<optional_custom_code>"
  ) {
    code
    expires_at
    metadata
    type
    type_id
    uses_remaining
  }
}
```

`get_code`

Class: `READ`

```graphql
query get_code {
  get_code(code: "<invite_code>") {
    code
    expires_at
    metadata
    type
    type_id
    uses_remaining
  }
}
```

`use_code`

Class: `USER WRITE`

```graphql
mutation use_code {
  use_code(code: "<invite_code>") {
    code
    expires_at
    metadata
    type
    type_id
    uses_remaining
  }
}
```

### SMS Download Link

`send_download_link`

Class: `AUTH WRITE`

Purpose: send an app download link to a phone number.

```graphql
mutation send_download_link {
  send_download_link(phone: "<phone>")
}
```

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

### Evidence Level

Live network capture covered read/setup flows:

- Opening the trade center loaded `roster_draft_picks` and `league_players`.
- Opening player/free-agent detail loaded `league_transactions_by_player`, `get_player_news_for_ids`, and `get_player_news`.
- League and trade pages loaded `league_transactions_filtered`.

The final submit mutations below were recovered from the web bundle, not executed against the logged-in account:

- `propose_trade`
- `accept_trade`
- `reject_trade`
- `force_cancel_transaction`
- `process_transaction`
- `league_create_transaction`
- `submit_waiver_claim`
- `cancel_waiver_claim`
- `update_waiver_claim`

### Map Direction For Player Assets

The app flattens selected assets into player-id-to-roster-id maps before calling GraphQL:

```js
adds[player_id] = Number(roster_id)
drops[player_id] = Number(roster_id)
```

For a two-team player trade, model both sides explicitly:

```json
{
  "adds": {
    "player_from_roster_1": 2,
    "player_from_roster_2": 1
  },
  "drops": {
    "player_from_roster_1": 1,
    "player_from_roster_2": 2
  }
}
```

In words: `adds` maps each player to the roster receiving that player; `drops` maps the same player to the roster giving that player up. For free-agent and waiver claims, `adds` is the claiming roster and `drops` is the roster dropping the player.

For a private MCP, the safe dry-run should render the resolved player names and roster names from both maps before sending anything.

### Send Trade Cookbook

Operation: `propose_trade`

Inputs:

- `league_id`
- `adds`: player id to destination roster id map
- `drops`: player id to source roster id map
- `draft_picks`: array of selected dynasty pick assets
- `waiver_budget`: array of selected FAAB/waiver-budget assets
- optional `expires_at`: Unix timestamp seconds
- optional `reject_transaction_id` and `reject_transaction_leg` for counteroffers

The web UI builds this call from:

```js
proposeTrade(
  leagueId,
  adds,
  drops,
  draftPicks,
  waiverBudget,
  expiresAt,
  rejectTransactionId,
  rejectTransactionLeg
)
```

GraphQL:

```graphql
mutation propose_trade(
  $k_adds: [String],
  $v_adds: [Int],
  $k_drops: [String],
  $v_drops: [Int]
) {
  propose_trade(
    league_id: "<league_id>",
    draft_picks: <draft_picks_array>,
    k_adds: $k_adds,
    v_adds: $v_adds,
    k_drops: $k_drops,
    v_drops: $v_drops,
    waiver_budget: <waiver_budget_array>,
    expires_at: <optional_unix_seconds>,
    reject_transaction_id: "<optional_transaction_id>",
    reject_transaction_leg: <optional_leg>
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
    draft_picks
    type
    player_map
    waiver_budget
  }
}
```

Variables for the two-team example above:

```json
{
  "k_adds": ["player_from_roster_1", "player_from_roster_2"],
  "v_adds": [2, 1],
  "k_drops": ["player_from_roster_1", "player_from_roster_2"],
  "v_drops": [1, 2]
}
```

Exploding offer expiration options observed in the UI:

- `1hour`: current time plus 1 hour
- `today`: end of current day
- `24hours`: current time plus 24 hours
- `2days`: current time plus 2 days
- `1week`: current time plus 1 week
- `2weeks`: current time plus 2 weeks

Draft-pick and waiver-budget asset arrays are inserted directly into the GraphQL document as JSON-like values by the bundle. Before sending real pick/FAAB trades from an MCP, capture or build those asset objects from the same trade UI model and print the dry-run, because the read-only `roster_draft_picks` shape is only:

```graphql
roster_id
season
round
owner_id
```

### Waiver Claim Cookbook

Operation: `submit_waiver_claim`

Inputs:

- `league_id`
- `adds`: player id to claiming roster id map
- `drops`: player id to dropping roster id map
- optional `settings`: string/int map, used for bid/priority settings

GraphQL:

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

Claim one player and drop one player:

```json
{
  "k_adds": ["free_agent_player_id"],
  "v_adds": [1],
  "k_drops": ["dropped_player_id"],
  "v_drops": [1],
  "k_settings": ["waiver_bid"],
  "v_settings": [7]
}
```

The exact setting key for FAAB should be confirmed from the claim modal capture for the target league before sending, because settings can vary by league configuration. The bundle confirms that waiver settings are passed as `$k_settings: [String]` and `$v_settings: [Int]`.

### Instant Free-Agent Add/Drop Cookbook

Operation: `league_create_transaction`

Purpose: instant add/drop when a player is not subject to waiver processing.

Inputs:

- `league_id`
- `type`, expected to include `free_agent` for normal instant add/drop flows
- `adds`: player id to roster id map
- `drops`: player id to roster id map

GraphQL:

```graphql
mutation league_create_transaction(
  $k_adds: [String],
  $v_adds: [Int],
  $k_drops: [String],
  $v_drops: [Int]
) {
  league_create_transaction(
    league_id: "<league_id>",
    type: "free_agent",
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

Add one free agent and drop one rostered player:

```json
{
  "k_adds": ["free_agent_player_id"],
  "v_adds": [1],
  "k_drops": ["dropped_player_id"],
  "v_drops": [1]
}
```

Drop-only and add-only transactions are represented by leaving the other map empty.

### Cancel Or Update Waiver Claim Cookbook

Cancel:

```graphql
mutation cancel_waiver_claim {
  cancel_waiver_claim(
    league_id: "<league_id>",
    leg: <leg>,
    transaction_id: "<transaction_id>"
  ) {
    ...Transaction
  }
}
```

Update:

```graphql
mutation update_waiver_claim($k_settings: [String], $v_settings: [Int]) {
  update_waiver_claim(
    league_id: "<league_id>",
    transaction_id: "<transaction_id>",
    leg: <leg>,
    k_settings: $k_settings,
    v_settings: $v_settings
  ) {
    ...Transaction
  }
}
```

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

### Auth And Account Operations

- `login_context_by_email_or_phone_or_username`
- `login_query` / `login`
- `create_user`
- `request_verification`
- `create_verification_code`
- `verify_verification_code`
- `create_phone_code`
- `verify_phone_code`
- `verify_contact_update`
- `request_password_reset`
- `reset_password`
- `reset_password_with_code`
- `change_password`
- `update_user_display_name`
- `update_user_avatar_url`
- `delete_user`
- `update_preferences`
- `app_info`
- `send_download_link`

### Invite Code Operations Adjacent To Auth

- `create_invite_link`
- `get_code`
- `use_code`
- `invite_friends`

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

The official MCP in this repo intentionally uses only the public read-only API. A private API MCP should use the auth model documented in "Auth And Session Preservation":

- Store the returned Sleeper `token` outside the repo.
- Send it as raw `Authorization: <token>`.
- Optionally keep a local cookie jar or `Cookie` header outside the repo.
- Persist replacement tokens returned in response bodies.
- Treat 401 without a replacement token as expired auth.
- Keep all mutation tools behind explicit confirmation.

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
- `sleeper://private-auth-status`

Private auth status:

- `private_auth_status`

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

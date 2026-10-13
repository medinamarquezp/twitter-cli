# Structured output contract

Every command prints a JSON or YAML envelope with `--json` or `--yaml`, and also when stdout is not a terminal (YAML by default; set `OUTPUT=json` to change it). The shapes are defined in [`schema/twitter-cli.schema.json`](schema/twitter-cli.schema.json) (JSON Schema 2020-12) and checked by `tests/test_json_contract.py`, including tweets parsed from recorded X responses.

## Envelopes

Success:

```json
{ "ok": true, "schema_version": "1", "data": ..., "pagination": { "nextCursor": "..." } }
```

`pagination` is present only when there is a next page. Pass its `nextCursor` to the same command with `--cursor` to continue.

Failure (exit code 1):

```json
{ "ok": false, "schema_version": "1", "error": { "code": "not_authenticated", "message": "...", "details": {} } }
```

| `error.code` | Meaning |
|---|---|
| `not_authenticated` | Missing, expired or rejected session (HTTP 401/403) |
| `rate_limited` | HTTP 429 after the built-in retries |
| `not_found` | User or tweet not found |
| `network_error` | Network failure |
| `query_id_error` | No GraphQL query ID could be resolved; try `refresh-query-ids` |
| `media_upload_error` | Image upload failed |
| `invalid_input` | Invalid argument |
| `api_error` | Any other X error |

Only stdout carries the contract. Structured mode prints no progress messages on stderr, and `-c/--compact` output is a separate, unversioned format.

## Commands

| Command | Schema definition | `data` |
|---|---|---|
| `feed`, `list`, `bookmarks`, `bookmarks folders ID`, `user-posts`, `search`, `likes`, `mentions`, `conversation`, `quotes` | `TweetPage` | `Tweet[]`, with `pagination` |
| `tweet`, `show` | `TweetPage` | `Tweet[]`, the requested tweet first |
| `article` | `TweetResponse` | `Tweet` with `articleTitle` and `articleText` |
| `user` | `UserResponse` | `User` |
| `status` | `StatusResponse` | `{ "authenticated": true, "user": AccountUser }` |
| `whoami` | `WhoamiResponse` | `{ "user": AccountUser }` |
| `followers`, `following`, `retweeters`, `list-members` | `UserPage` | `User[]`, with `pagination` |
| `lists` | `ListPage` | `TwitterList[]`, with `pagination` |
| `bookmarks folders` | `BookmarkFolderList` | `BookmarkFolder[]` |
| `scheduled` | `ScheduledTweetList` | `ScheduledTweet[]`, soonest first |
| `post`, `reply`, `quote`, `delete`, `like`, `unlike`, `retweet`, `unretweet`, `bookmark`, `unbookmark`, `favorite`, `unfavorite`, `follow`, `unfollow`, `schedule`, `unschedule` | `WriteResponse` | One of the write results below |
| `refresh-query-ids` | `RefreshResponse` | `RefreshResult` |

List commands return whole pages: `--max` is the minimum number of results to collect, and `nextCursor` resumes right after the last item returned. Pages can repeat a few items (X groups conversations), so deduplicate by `id`.

## Data types

All IDs are strings. Counts are non-negative integers. Every field listed here is always present; nullable fields are `null` when they do not apply.

**Tweet**

| Field | Type | Notes |
|---|---|---|
| `id`, `text` | string | `text` is the full text, also for long posts; replies start with their leading mentions |
| `author` | Author | `id`, `name`, `screenName`, `profileImageUrl`, `verified`, `followers`, `following` |
| `metrics` | Metrics | `likes`, `retweets`, `replies`, `quotes`, `views`, `bookmarks` |
| `createdAt` | string | X format, `Mon Oct 13 08:00:00 +0000 2026`; for a retweet, the original post time |
| `createdAtISO` | string | ISO 8601 in UTC |
| `createdAtLocal` | string | `YYYY-MM-DD HH:MM` in the machine's time zone |
| `media` | Media[] | `type` (`photo`, `video`, `animated_gif`), `url`, `width` and `height` (integer or null) |
| `urls`, `mentions`, `hashtags` | string[] | Expanded URLs, mentioned handles without `@`, hashtags without `#` |
| `isRetweet` | boolean | |
| `retweetedBy`, `retweetedAt`, `retweetedAtISO` | string or null | Who retweeted it and when; null for original posts |
| `inReplyToId`, `inReplyToUser` | string or null | Tweet and handle this one replies to |
| `conversationId` | string or null | ID of the conversation root |
| `lang` | string | Language code detected by X |
| `score` | number or null | Only set with `--filter` |
| `isSubscriberOnly`, `isPromoted` | boolean | Promoted tweets are dropped unless the command asks for them |
| `isPinned` | boolean | The profile's pinned tweet, which `user-posts` lists first on the first page; false everywhere else |
| `articleTitle`, `articleText` | string or null | X Articles only |
| `quotedTweet` | QuotedTweet or null | `id`, `text`, `author` (`id`, `screenName`, `name`), `metrics`, `createdAt`, `createdAtISO` |

**User**: `id`, `name`, `screenName`, `bio`, `location`, `url`, `followers`, `following`, `tweets`, `likes` (likes given), `verified`, `profileImageUrl`, `createdAt`, `createdAtISO`. **AccountUser** adds `username`, equal to `screenName`.

**TwitterList**: `id`, `name`, `description`, `memberCount`, `subscriberCount`, `isPrivate`, `ownerScreenName`, `createdAt`.

**ScheduledTweet**: `id`, `text`, `executeAt` (Unix seconds), `executeAtISO`, `executeAtLocal`, `state`, `mediaIds`.

**BookmarkFolder**: `id`, `name`.

**Write results** (`success` is always `true`):

| Actions | Fields |
|---|---|
| `post` | `id`, `url` |
| `reply` | `id`, `replyTo`, `url` |
| `quote` | `id`, `quotedId`, `url` |
| `delete`, `like`, `unlike`, `retweet`, `unretweet`, `bookmark`, `unbookmark`, `unschedule` | `id` |
| `follow`, `unfollow` | `screenName`, `userId` |
| `schedule` | `id` (scheduled post), `executeAt`, `executeAtISO`, `executeAtLocal` |

**RefreshResult**: `scannedScripts`, `availableChunks`, `found`, `changed` (built-in operations whose web ID differs), `missing` (built-in operations not found).

## Versioning

- `schema_version` stays `"1"` for additive changes: new commands, new fields or new enum values. Every such change updates the schema, this file and the contract tests in the same commit; the schema forbids unknown fields so that no change slips through unnoticed.
- Renaming or removing a field, or changing its type or meaning, bumps `schema_version` to `"2"`.
- Consumers should ignore fields they do not know.

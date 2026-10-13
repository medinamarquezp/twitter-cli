# twitter-cli fork

This fork of [public-clis/twitter-cli](https://github.com/public-clis/twitter-cli) tracks upstream and integrates fixes that are still open as upstream pull requests.

## Branches and tags

- `main` mirrors `upstream/main` and carries no fork-specific commits.
- `integration` is upstream `main` plus the pull requests listed below, each merged with `--no-ff` so it can be reverted on its own, plus the fork's own work.
- Releases are tagged `v<upstream version>-fork.<n>`, and the package version is `<upstream version>+fork.<n>`.

## Install

```bash
uv tool install git+https://github.com/medinamarquezp/twitter-cli@v0.8.6-fork.7
```

## Integrated upstream pull requests

| PR | Change | Notes |
|---|---|---|
| [#93](https://github.com/public-clis/twitter-cli/pull/93) | Bootstrap `x-client-transaction-id` from `x.com/home` with the session cookie and require `xclienttransaction>=1.0.3` | Fixes search, followers, following and likes returning HTTP 404 since the September 2026 X web rebuild |
| [#75](https://github.com/public-clis/twitter-cli/pull/75) | Reject incomplete `TweetDetail` responses | |
| [#57](https://github.com/public-clis/twitter-cli/pull/57) | Add author follower and following counts to serialized tweets | |
| [#77](https://github.com/public-clis/twitter-cli/pull/77) | Retry `Query: Unspecified` GraphQL errors with live query IDs | |
| [#82](https://github.com/public-clis/twitter-cli/pull/82) | Refresh fallback query IDs from twitter-openapi (2026-08-09) | Conflict with #77 resolved in favour of the newer IDs |
| [#64](https://github.com/public-clis/twitter-cli/pull/64) | Premium long-form posts through `CreateNoteTweet`, using twitter-text v3 weighting | Chosen over #60, whose weighting counts accented Latin characters as two |

## Reviewed and not integrated

| PR | Reason |
|---|---|
| [#83](https://github.com/public-clis/twitter-cli/pull/83) | Overwrites GraphQL feature flags with a third-party GitHub file and makes network calls at import time. Its x-web bundle scan is already covered by #93 |
| [#60](https://github.com/public-clis/twitter-cli/pull/60) | Superseded by #64 |
| #74, #79, #84, #86, #89, #90, #91 | Alternative fixes for the `ClientTransaction` bootstrap issue that #93 already solves |

## Fork changes

| Since | Change |
|---|---|
| `0.8.6+fork.2` | No startup cookie check: its two endpoints answer HTTP 404, so it cost two failed requests per run, and it re-read browser cookies even when they came from environment variables. Expired sessions still fail as `not_authenticated` on the first real request |
| `0.8.6+fork.2` | No progress lines on stderr with `--json` or `--yaml` |
| `0.8.6+fork.2` | Live-resolved GraphQL query IDs are kept for 30 days in `~/.twitter-cli/query_ids.json`, and a stale ID is retried whenever a different live ID can be resolved |
| `0.8.6+fork.2` | `~/.twitter-cli` is `0700` and its files `0600` |
| `0.8.6+fork.2` | Tweets expose `inReplyToId`, `inReplyToUser`, `conversationId`, `mentions`, `hashtags`, `retweetedAt` and `retweetedAtISO`; quoted tweets include the author id, metrics and creation time |
| `0.8.6+fork.2` | `user-posts --with-replies` reads the replies tab (`UserTweetsAndReplies`) |
| `0.8.6+fork.2` | List commands return whole pages: `--max` sets how many results to collect at least, and `pagination.nextCursor` resumes right after the last one returned. Before, pages were trimmed to `--max` while the cursor pointed past the whole page, so every continuation skipped results (X ignores the requested count: the following feed returns about 100 tweets per page and follower lists about 50 users). `bookmarks`, `user-posts`, `search`, `likes`, `followers` and `following` gained `--cursor`, which also lets follower lists go past the per-call cap across several calls |
| `0.8.6+fork.2` | Promoted tweets are dropped unless they are requested |
| `0.8.6+fork.3` | `mentions [SCREEN_NAME]`: latest posts mentioning a user, without the user's own (search `@handle -from:handle`); defaults to the logged-in account |
| `0.8.6+fork.3` | `conversation TWEET_ID`: a tweet and its replies, newest replies first, through `TweetDetail` with cursors. A `conversation_id:` search returned nothing for a conversation that has replies |
| `0.8.6+fork.3` | `quotes TWEET_ID`: posts quoting a tweet, through a `quoted_tweet_id:` search |
| `0.8.6+fork.3` | `retweeters TWEET_ID` and `list-members LIST_ID`, with cursors |
| `0.8.6+fork.3` | `lists [SCREEN_NAME]`: lists a user owns, through the 1.1 `lists/ownerships.json` endpoint. `CombinedLists`, `ListsManagementPageTimeline` and `ListOwnerships` answer `DecodeException` for an account that owns a list, even with the web's feature flags |
| `0.8.6+fork.3` | Handles, tweet IDs and list IDs are validated before they are used, so arguments cannot inject search operators |
| `0.8.6+fork.3` | A Bottom cursor nested inside a timeline item is now followed |
| `0.8.6+fork.4` | Native scheduling: `schedule TEXT --at TIME [-i IMAGE]` (`CreateScheduledTweet`; X publishes the post even when this machine is off), `scheduled` (`FetchScheduledTweets`) and `unschedule ID` (`DeleteScheduledTweet`). `--at` takes ISO 8601, local time without an offset, at least five minutes ahead. `scheduled` is verified against X; `schedule` and `unschedule` are covered by tests but not yet exercised against a live account |
| `0.8.6+fork.5` | `refresh-query-ids [--quick]`: scans the logged-in x.com web build (`main.js`, `vendor.js` and about 540 on-demand chunks, about 25 seconds) and saves every operation found to `~/.twitter-cli/web_query_ids.json`; `--quick` stops once the fork's operations are found. These IDs are used only for operations without a built-in ID or after an ID is rejected, so working IDs are never replaced, and a rejected ID is never handed back |
| `0.8.6+fork.5` | The automatic bundle scan reads the cached logged-in page (`main.js` and `vendor.js`) instead of the logged-out shell, which links no operation, and keeps its findings apart from the main cache |
| `0.8.6+fork.6` | Stable structured output: [`schema/twitter-cli.schema.json`](schema/twitter-cli.schema.json) (JSON Schema 2020-12) and [`SCHEMA.md`](SCHEMA.md) describe every command's envelope, checked by contract tests that also validate tweets parsed from recorded X responses |
| `0.8.6+fork.6` | Tweets always include `articleTitle`, `articleText` and `quotedTweet` (null when absent); `status` and `whoami` return the full user object plus `username`; write commands report the command name as `action` (`like`, `unretweet`, …) instead of a progress phrase (`liking_tweet`) |
| `0.8.6+fork.7` | The `x.com/home` request that bootstraps `x-client-transaction-id` keeps curl_cffi's own Chrome headers. The fixed Chrome 127 on Windows headers from `x_client_transaction` now get an interactive Cloudflare challenge (HTTP 403), which left search, followers, following and likes without the header. The `ondemand.s` download no longer sends the session cookie to `abs.twimg.com` |
| `0.8.6+fork.7` | If that bootstrap fails, the last snapshot up to a day old is used and the refresh is retried after 15 minutes instead of on every run; the warning names the cause, such as a Cloudflare challenge |
| `0.8.6+fork.7` | `user-posts` includes the profile's pinned tweet, first and flagged `isPinned`. X sends it in a separate `TimelinePinEntry` instruction and leaves it out of the timeline entries, so it was missing |

Live web IDs also explained the list `DecodeException`: the twitter-openapi IDs for `CombinedLists`, `ListsManagementPageTimeline` and `ListOwnerships` no longer match the ones the web uses.

## Planned fork work

- Nothing scheduled. `schedule`, `unschedule` and long posts still need a check against a live account.

## Testing

```bash
TWITTER_AUTH_TOKEN=dummy TWITTER_CT0=dummy uv run pytest -q --ignore=tests/test_smoke.py
```

The dummy credentials keep any accidental client construction away from real browser cookies. Smoke tests (`uv run pytest -m smoke`) call the live API with your browser session and are only run on purpose.

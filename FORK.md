# twitter-cli fork

This fork of [public-clis/twitter-cli](https://github.com/public-clis/twitter-cli) tracks upstream and integrates fixes that are still open as upstream pull requests.

## Branches and tags

- `main` mirrors `upstream/main` and carries no fork-specific commits.
- `integration` is upstream `main` plus the pull requests listed below, each merged with `--no-ff` so it can be reverted on its own, plus the fork's own work.
- Releases are tagged `v<upstream version>-fork.<n>`, and the package version is `<upstream version>+fork.<n>`.

## Install

```bash
uv tool install git+https://github.com/medinamarquezp/twitter-cli@v0.8.6-fork.2
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

## Planned fork work

- New commands: mentions, full conversations, quotes and retweeters of a tweet, your lists and their members.
- Native scheduling through `CreateScheduledTweet`: schedule, list and cancel posts.
- A stable JSON schema for every command.

## Testing

```bash
TWITTER_AUTH_TOKEN=dummy TWITTER_CT0=dummy uv run pytest -q --ignore=tests/test_smoke.py
```

The dummy credentials keep any accidental client construction away from real browser cookies. Smoke tests (`uv run pytest -m smoke`) call the live API with your browser session and are only run on purpose.

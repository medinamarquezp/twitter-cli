# twitter-cli fork

This fork of [public-clis/twitter-cli](https://github.com/public-clis/twitter-cli) tracks upstream and integrates fixes that are still open as upstream pull requests.

## Branches and tags

- `main` mirrors `upstream/main` and carries no fork-specific commits.
- `integration` is upstream `main` plus the pull requests listed below, each merged with `--no-ff` so it can be reverted on its own, plus the fork's own work.
- Releases are tagged `v<upstream version>-fork.<n>`, and the package version is `<upstream version>+fork.<n>`.

## Install

```bash
uv tool install git+https://github.com/medinamarquezp/twitter-cli@v0.8.6-fork.1
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

## Planned fork work

- Skip the startup cookie check, whose two endpoints now return HTTP 404, and never fall back to browser cookies when they come from environment variables.
- Persist resolved GraphQL query IDs on disk, so stale fallback IDs do not cause a failed request on every start.
- Create `~/.twitter-cli` and its files readable by the owner only.
- Keep structured output clean: no progress messages on stderr with `--json` or `--yaml`.
- Expose reply, conversation, mention, hashtag and retweet time fields on every tweet.
- Read a user's replies tab (`UserTweetsAndReplies`).
- Return resumable cursors from every list command without dropping items, and lift the follower pagination limit.
- Filter promoted tweets unless they are requested.
- New commands: mentions, full conversations, quotes and retweeters of a tweet, your lists and their members.
- Native scheduling through `CreateScheduledTweet`: schedule, list and cancel posts.
- A stable JSON schema for every command.

## Testing

```bash
TWITTER_AUTH_TOKEN=dummy TWITTER_CT0=dummy uv run pytest -q --ignore=tests/test_smoke.py
```

The dummy credentials keep any accidental client construction away from real browser cookies. Smoke tests (`uv run pytest -m smoke`) call the live API with your browser session and are only run on purpose.

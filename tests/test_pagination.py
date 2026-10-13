from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from twitter_cli.cli import cli
from twitter_cli.client import TwitterClient
from twitter_cli.models import UserProfile


def _client() -> TwitterClient:
    client = TwitterClient.__new__(TwitterClient)
    client._request_delay = 0.0
    client._max_count = 200
    return client


def _page(*ids: str, promoted: tuple[str, ...] = ()) -> list[MagicMock]:
    return [MagicMock(id=tweet_id, is_promoted=tweet_id in promoted) for tweet_id in ids]


def _user_list_response(user_id: str, next_cursor: str) -> dict[str, Any]:
    entries = [
        {
            "content": {
                "entryType": "TimelineTimelineItem",
                "itemContent": {"user_results": {"result": {"id": user_id}}},
            }
        },
        {"content": {"entryType": "TimelineTimelineCursor", "cursorType": "Bottom", "value": next_cursor}},
    ]
    return {"data": {"user": {"result": {"timeline": {"timeline": {"instructions": [{"entries": entries}]}}}}}}


def test_fetch_timeline_with_cursor_returns_the_whole_last_page() -> None:
    client = _client()
    client._graphql_get = lambda *args, **kwargs: {}

    with patch("twitter_cli.client.parse_timeline_response", return_value=(_page("1", "2", "3", "4", "5"), "next")):
        tweets, cursor = client._fetch_timeline("HomeLatestTimeline", 3, lambda data: data, return_cursor=True)

    assert [tweet.id for tweet in tweets] == ["1", "2", "3", "4", "5"]
    assert cursor == "next"


def test_fetch_timeline_without_cursor_still_caps_results() -> None:
    client = _client()
    client._graphql_get = lambda *args, **kwargs: {}

    with patch("twitter_cli.client.parse_timeline_response", return_value=(_page("1", "2", "3", "4", "5"), None)):
        tweets = client._fetch_timeline("HomeLatestTimeline", 3, lambda data: data)

    assert [tweet.id for tweet in tweets] == ["1", "2", "3"]


def test_fetch_timeline_drops_promoted_tweets_unless_requested() -> None:
    client = _client()
    client._graphql_get = lambda *args, **kwargs: {}
    page = (_page("1", "ad", "2", promoted=("ad",)), None)

    with patch("twitter_cli.client.parse_timeline_response", return_value=page):
        without_ads = client._fetch_timeline("HomeLatestTimeline", 10, lambda data: data)
        with_ads = client._fetch_timeline("HomeLatestTimeline", 10, lambda data: data, include_promoted=True)

    assert [tweet.id for tweet in without_ads] == ["1", "2"]
    assert [tweet.id for tweet in with_ads] == ["1", "ad", "2"]


def test_user_lists_start_from_a_cursor_and_return_the_next_one() -> None:
    client = _client()
    calls = []

    def graphql_post(operation_name, variables, features=None):
        calls.append(variables.copy())
        return _user_list_response("u1", "next")

    client._graphql_post = graphql_post

    with patch(
        "twitter_cli.client.parse_user_result",
        side_effect=lambda result: UserProfile(id=result["id"], name="A", screen_name="a"),
    ):
        users, cursor = client.fetch_followers("42", 1, cursor="previous", return_cursor=True)

    assert [user.id for user in users] == ["u1"]
    assert cursor == "next"
    assert calls[0]["cursor"] == "previous"


def test_user_tweets_can_read_the_replies_tab() -> None:
    client = _client()
    operations = []

    def graphql_get(operation_name, variables, features, field_toggles=None):
        operations.append((operation_name, variables.copy()))
        return {}

    client._graphql_get = graphql_get

    with patch("twitter_cli.client.parse_timeline_response", return_value=([], None)):
        client.fetch_user_tweets("42", 5, with_replies=True)
        client.fetch_user_tweets("42", 5)

    assert operations[0][0] == "UserTweetsAndReplies"
    assert operations[0][1]["withCommunity"] is True
    assert operations[1][0] == "UserTweets"


def test_user_posts_passes_cursor_and_replies_flag_and_emits_next_cursor(monkeypatch, tweet_factory) -> None:
    captured = {}

    class FakeClient:
        def fetch_user(self, screen_name):
            return UserProfile(id="42", name="Alice", screen_name=screen_name)

        def fetch_user_tweets(self, user_id, count, cursor=None, return_cursor=False, with_replies=False):
            captured.update(user_id=user_id, cursor=cursor, return_cursor=return_cursor, with_replies=with_replies)
            return [tweet_factory("1")], "next"

    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: FakeClient())

    result = CliRunner().invoke(cli, ["user-posts", "alice", "--cursor", "previous", "--with-replies", "--json"])

    assert result.exit_code == 0, result.output
    assert captured == {"user_id": "42", "cursor": "previous", "return_cursor": True, "with_replies": True}
    assert json.loads(result.output)["pagination"]["nextCursor"] == "next"


def test_followers_command_emits_next_cursor(monkeypatch) -> None:
    class FakeClient:
        def fetch_user(self, screen_name):
            return UserProfile(id="42", name="Alice", screen_name=screen_name)

        def fetch_followers(self, user_id, count, cursor=None, return_cursor=False):
            assert cursor == "previous"
            assert return_cursor is True
            return [UserProfile(id="7", name="Bob", screen_name="bob")], "next"

    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: FakeClient())

    result = CliRunner().invoke(cli, ["followers", "alice", "--cursor", "previous", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"][0]["screenName"] == "bob"
    assert payload["pagination"]["nextCursor"] == "next"

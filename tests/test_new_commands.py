from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from twitter_cli.cli import cli
from twitter_cli.client import TwitterClient
from twitter_cli.models import TwitterList, UserProfile
from twitter_cli.parser import _extract_cursor, parse_list_result


def _client() -> TwitterClient:
    client = TwitterClient.__new__(TwitterClient)
    client._request_delay = 0.0
    client._max_count = 200
    return client


def _user(rest_id: str, screen_name: str) -> dict[str, Any]:
    return {"rest_id": rest_id, "core": {"screen_name": screen_name, "name": screen_name}, "legacy": {}}


def _user_entry(rest_id: str, screen_name: str) -> dict[str, Any]:
    return {
        "content": {
            "entryType": "TimelineTimelineItem",
            "itemContent": {"user_results": {"result": _user(rest_id, screen_name)}},
        }
    }


def _cursor_entry(value: str) -> dict[str, Any]:
    return {"content": {"entryType": "TimelineTimelineCursor", "cursorType": "Bottom", "value": value}}


def _list_data(list_id: str, name: str, mode: str) -> dict[str, Any]:
    return {
        "id_str": list_id,
        "name": name,
        "description": "Cuentas del nicho",
        "member_count": 12,
        "subscriber_count": 3,
        "mode": mode,
        "created_at": 1760000000000,
        "user_results": {"result": _user("1", "alice")},
    }


def test_search_based_reads_build_safe_queries() -> None:
    client = _client()
    client.fetch_search = MagicMock(return_value=([], None))

    client.fetch_mentions("alice", 5, cursor="c1", return_cursor=True)
    client.fetch_quotes("456", 5)

    calls = client.fetch_search.call_args_list
    assert calls[0].args == ("@alice -from:alice", 5, "Latest")
    assert calls[0].kwargs == {"cursor": "c1", "return_cursor": True}
    assert calls[1].args == ("quoted_tweet_id:456", 5, "Latest")


def test_conversation_reads_the_tweet_detail_newest_first() -> None:
    client = _client()
    calls = []

    def graphql_get(operation_name, variables, features, field_toggles=None):
        calls.append((operation_name, variables.copy()))
        return {}

    client._graphql_get = graphql_get

    with patch("twitter_cli.client.parse_timeline_response", return_value=([], None)):
        tweets, cursor = client.fetch_conversation("123", 5, cursor="prev", return_cursor=True)

    assert (tweets, cursor) == ([], None)
    assert calls[0][0] == "TweetDetail"
    assert calls[0][1]["focalTweetId"] == "123"
    assert calls[0][1]["rankingMode"] == "Recency"
    assert calls[0][1]["cursor"] == "prev"


def test_tweet_detail_cursor_can_sit_inside_the_item() -> None:
    content = {
        "entryType": "TimelineTimelineItem",
        "itemContent": {"itemType": "TimelineTimelineCursor", "cursorType": "Bottom", "value": "more"},
    }

    assert _extract_cursor(content) == "more"
    assert _extract_cursor({"entryType": "TimelineTimelineItem", "itemContent": {}}) is None


def test_retweeters_and_list_members_read_user_timelines() -> None:
    client = _client()
    calls = []
    responses = {
        "Retweeters": {
            "data": {
                "retweeters_timeline": {
                    "timeline": {"instructions": [{"entries": [_user_entry("7", "bob"), _cursor_entry("next")]}]}
                }
            }
        },
        "ListMembers": {
            "data": {
                "list": {
                    "members_timeline": {
                        "timeline": {"instructions": [{"entries": [_user_entry("8", "carol"), _cursor_entry("more")]}]}
                    }
                }
            }
        },
    }

    def graphql_get(operation_name, variables, features):
        calls.append((operation_name, variables.copy()))
        return responses[operation_name]

    client._graphql_get = graphql_get

    retweeters, retweeters_cursor = client.fetch_retweeters("123", 1, cursor="prev", return_cursor=True)
    members, members_cursor = client.fetch_list_members("456", 1, return_cursor=True)

    assert [user.screen_name for user in retweeters] == ["bob"]
    assert retweeters_cursor == "next"
    assert calls[0][1]["tweetId"] == "123"
    assert calls[0][1]["cursor"] == "prev"
    assert [user.screen_name for user in members] == ["carol"]
    assert members_cursor == "more"
    assert calls[1][1]["listId"] == "456"


def test_users_inside_timeline_modules_are_read() -> None:
    client = _client()
    module = {
        "content": {
            "entryType": "TimelineTimelineModule",
            "items": [{"item": {"itemContent": {"user_results": {"result": _user("9", "dave")}}}}],
        }
    }
    client._graphql_get = lambda operation_name, variables, features: {
        "data": {"list": {"members_timeline": {"timeline": {"instructions": [{"entries": [module]}]}}}}
    }

    members = client.fetch_list_members("456", 5)

    assert [user.screen_name for user in members] == ["dave"]


def test_lists_are_read_from_the_rest_ownerships_endpoint() -> None:
    client = _client()
    urls = []
    rest_list = {
        "id_str": "10",
        "name": "Referentes",
        "member_count": 12,
        "mode": "private",
        "user": {"screen_name": "alice"},
    }

    def api_get(url):
        urls.append(url)
        return {"lists": [rest_list], "next_cursor_str": "0" if "cursor=" in url else "77"}

    client._api_get = api_get

    first, first_cursor = client.fetch_lists("1", 10, return_cursor=True)
    second, second_cursor = client.fetch_lists("1", 10, cursor="77", return_cursor=True)

    assert [item.name for item in first] == ["Referentes"]
    assert first[0].is_private is True
    assert first[0].owner_screen_name == "alice"
    assert first_cursor == "77"
    assert second_cursor is None
    assert "lists/ownerships.json?user_id=1&count=10" in urls[0]
    assert "cursor=77" in urls[1]


def test_parse_list_result_reads_counts_privacy_and_owner() -> None:
    item = parse_list_result(_list_data("10", "Referentes", "Private"))

    assert item == TwitterList(
        id="10",
        name="Referentes",
        description="Cuentas del nicho",
        member_count=12,
        subscriber_count=3,
        is_private=True,
        owner_screen_name="alice",
        created_at="1760000000000",
    )
    assert parse_list_result({"name": "sin id"}) is None
    assert parse_list_result(None) is None


class FakeClient:
    def __init__(self, tweet_factory) -> None:
        self.tweet_factory = tweet_factory
        self.calls: list[tuple[str, Any]] = []

    def fetch_me(self) -> UserProfile:
        return UserProfile(id="42", name="Me", screen_name="me")

    def fetch_user(self, screen_name: str) -> UserProfile:
        return UserProfile(id="7", name=screen_name, screen_name=screen_name)

    def _tweets(self, name: str, subject: str, cursor: str | None) -> tuple[list[Any], str]:
        self.calls.append((name, subject))
        return [self.tweet_factory("1")], "next"

    def fetch_mentions(self, screen_name, count, cursor=None, return_cursor=False):
        return self._tweets("mentions", screen_name, cursor)

    def fetch_conversation(self, tweet_id, count, cursor=None, return_cursor=False):
        return self._tweets("conversation", tweet_id, cursor)

    def fetch_quotes(self, tweet_id, count, cursor=None, return_cursor=False):
        return self._tweets("quotes", tweet_id, cursor)

    def fetch_retweeters(self, tweet_id, count, cursor=None, return_cursor=False):
        self.calls.append(("retweeters", tweet_id))
        return [UserProfile(id="9", name="Bob", screen_name="bob")], "next"

    def fetch_list_members(self, list_id, count, cursor=None, return_cursor=False):
        self.calls.append(("list-members", list_id))
        return [UserProfile(id="9", name="Bob", screen_name="bob")], None

    def fetch_lists(self, user_id, count, cursor=None, return_cursor=False):
        self.calls.append(("lists", user_id))
        return [TwitterList(id="10", name="Referentes", is_private=True)], None


def _invoke(monkeypatch, fake: FakeClient, *args: str):
    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: fake)
    return CliRunner().invoke(cli, [*args, "--json"])


def test_mentions_default_to_the_logged_in_account(monkeypatch, tweet_factory) -> None:
    fake = FakeClient(tweet_factory)

    explicit = _invoke(monkeypatch, fake, "mentions", "@alice")
    implicit = _invoke(monkeypatch, fake, "mentions")

    assert explicit.exit_code == 0, explicit.output
    assert implicit.exit_code == 0, implicit.output
    assert fake.calls == [("mentions", "alice"), ("mentions", "me")]
    assert json.loads(explicit.output)["pagination"]["nextCursor"] == "next"


def test_mentions_reject_handles_that_could_inject_search_operators(monkeypatch, tweet_factory) -> None:
    fake = FakeClient(tweet_factory)

    result = _invoke(monkeypatch, fake, "mentions", "alice OR from:bob")

    assert result.exit_code != 0
    assert fake.calls == []


def test_conversation_and_quotes_accept_urls(monkeypatch, tweet_factory) -> None:
    fake = FakeClient(tweet_factory)

    conversation = _invoke(monkeypatch, fake, "conversation", "https://x.com/alice/status/123")
    quotes = _invoke(monkeypatch, fake, "quotes", "456")

    assert conversation.exit_code == 0, conversation.output
    assert quotes.exit_code == 0, quotes.output
    assert fake.calls == [("conversation", "123"), ("quotes", "456")]


def test_retweeters_and_list_members_emit_users(monkeypatch, tweet_factory) -> None:
    fake = FakeClient(tweet_factory)

    retweeters = _invoke(monkeypatch, fake, "retweeters", "123")
    members = _invoke(monkeypatch, fake, "list-members", "https://x.com/i/lists/456")

    assert retweeters.exit_code == 0, retweeters.output
    assert members.exit_code == 0, members.output
    assert json.loads(retweeters.output)["data"][0]["screenName"] == "bob"
    assert json.loads(retweeters.output)["pagination"]["nextCursor"] == "next"
    assert fake.calls == [("retweeters", "123"), ("list-members", "456")]


def test_lists_default_to_the_logged_in_account(monkeypatch, tweet_factory) -> None:
    fake = FakeClient(tweet_factory)

    result = _invoke(monkeypatch, fake, "lists")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"][0]["name"] == "Referentes"
    assert payload["data"][0]["isPrivate"] is True
    assert fake.calls == [("lists", "42")]

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from click.testing import CliRunner

from twitter_cli.cli import cli
from twitter_cli.client import TwitterClient
from twitter_cli.models import TwitterList, UserProfile
from twitter_cli.parser import parse_list_result


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
    client.fetch_conversation("123", 5)
    client.fetch_quotes("456", 5)

    calls = client.fetch_search.call_args_list
    assert calls[0].args == ("@alice -from:alice", 5, "Latest")
    assert calls[0].kwargs == {"cursor": "c1", "return_cursor": True}
    assert calls[1].args == ("conversation_id:123", 5, "Latest")
    assert calls[2].args == ("quoted_tweet_id:456", 5, "Latest")


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


def test_lists_are_read_from_items_and_modules() -> None:
    client = _client()
    entries = [
        {
            "content": {
                "entryType": "TimelineTimelineItem",
                "itemContent": {"itemType": "TimelineTwitterList", "list": _list_data("10", "Referentes", "Private")},
            }
        },
        {
            "content": {
                "entryType": "TimelineTimelineModule",
                "items": [{"item": {"itemContent": {"list": _list_data("11", "Pares", "Public")}}}],
            }
        },
    ]
    client._graphql_get = lambda operation_name, variables, features: {
        "data": {"user": {"result": {"timeline": {"timeline": {"instructions": [{"entries": entries}]}}}}}
    }

    items, cursor = client.fetch_lists("1", 10, return_cursor=True)

    assert [item.name for item in items] == ["Referentes", "Pares"]
    assert [item.is_private for item in items] == [True, False]
    assert cursor is None


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

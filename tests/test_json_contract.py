from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from jsonschema import Draft202012Validator, ValidationError

from twitter_cli.cli import cli
from twitter_cli.exceptions import AuthenticationError
from twitter_cli.models import (
    Author,
    BookmarkFolder,
    Metrics,
    ScheduledTweet,
    Tweet,
    TweetMedia,
    TwitterList,
    UserProfile,
)
from twitter_cli.output import success_payload
from twitter_cli.parser import _deep_get, parse_timeline_response
from twitter_cli.serialization import tweets_to_data, users_to_data

SCHEMA = json.loads((Path(__file__).parent.parent / "schema" / "twitter-cli.schema.json").read_text(encoding="utf-8"))
PROFILE = UserProfile(
    id="42",
    name="Alice",
    screen_name="alice",
    bio="Hola",
    followers_count=10,
    created_at="Sat Nov 07 17:56:10 +0000 2009",
)


def _validate(instance: Any, definition: str) -> None:
    Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/%s" % definition}).validate(instance)


def _invoke(monkeypatch, client: Any, *args: str) -> Any:
    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: client)
    result = CliRunner().invoke(cli, [*args, "--json"])
    return json.loads(result.output)


def _rich_tweet() -> Tweet:
    quoted = Tweet(
        id="30",
        text="citado",
        author=Author(id="9", name="Dave", screen_name="dave"),
        metrics=Metrics(likes=4),
        created_at="Sun Oct 12 08:00:00 +0000 2026",
    )
    return Tweet(
        id="20",
        text="hola @bob #IA",
        author=Author(id="2", name="Bob", screen_name="bob", verified=True, followers_count=7),
        metrics=Metrics(likes=1, retweets=2, replies=3, quotes=4, views=5, bookmarks=6),
        created_at="Mon Oct 13 08:00:00 +0000 2026",
        media=[TweetMedia(type="photo", url="https://pbs.twimg.com/media/a.jpg", width=10, height=None)],
        urls=["https://example.com"],
        is_retweet=True,
        lang="es",
        retweeted_by="carol",
        quoted_tweet=quoted,
        score=1.5,
        article_title="Título",
        article_text="Texto",
        in_reply_to_id="10",
        in_reply_to_user="alice",
        conversation_id="10",
        mentions=["bob"],
        hashtags=["IA"],
        retweeted_at="Mon Oct 13 09:00:00 +0000 2026",
    )


def test_schema_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    ("fixture", "path"),
    [
        ("home_timeline.json", ("data", "home", "home_timeline_urt", "instructions")),
        ("list_timeline.json", ("data", "list", "tweets_timeline", "timeline", "instructions")),
        ("search_timeline.json", ("data", "search_by_raw_query", "search_timeline", "timeline", "instructions")),
        ("tweet_detail.json", ("data", "threaded_conversation_with_injections_v2", "instructions")),
    ],
)
def test_tweets_parsed_from_x_responses_match_the_schema(fixture_loader, fixture, path) -> None:
    tweets, cursor = parse_timeline_response(fixture_loader(fixture), lambda data: _deep_get(data, *path))
    payload = success_payload(tweets_to_data(tweets))
    if cursor:
        payload["pagination"] = {"nextCursor": cursor}

    assert tweets
    _validate(payload, "TweetPage")


def test_every_tweet_field_matches_the_schema() -> None:
    payload = success_payload(tweets_to_data([_rich_tweet()]))

    _validate(payload, "TweetPage")
    assert set(payload["data"][0]) == set(SCHEMA["$defs"]["Tweet"]["required"])


def test_user_lists_match_the_schema() -> None:
    _validate(dict(success_payload(users_to_data([PROFILE])), pagination={"nextCursor": "c"}), "UserPage")


def test_read_commands_match_their_envelopes(monkeypatch, tweet_factory) -> None:
    client = MagicMock()
    client.fetch_following_feed.return_value = ([_rich_tweet(), tweet_factory("1")], "next")
    client.fetch_user.return_value = PROFILE
    client.fetch_me.return_value = PROFILE
    client.fetch_followers.return_value = ([PROFILE], "next")
    client.fetch_lists.return_value = ([TwitterList(id="10", name="Referentes", is_private=True)], None)
    client.fetch_scheduled_tweets.return_value = [ScheduledTweet(id="900", text="hola", execute_at=1893492000)]
    client.fetch_bookmark_folders.return_value = [BookmarkFolder(id="5", name="Leer")]

    _validate(_invoke(monkeypatch, client, "feed", "-t", "following"), "TweetPage")
    _validate(_invoke(monkeypatch, client, "user", "alice"), "UserResponse")
    _validate(_invoke(monkeypatch, client, "status"), "StatusResponse")
    _validate(_invoke(monkeypatch, client, "whoami"), "WhoamiResponse")
    _validate(_invoke(monkeypatch, client, "followers", "alice"), "UserPage")
    _validate(_invoke(monkeypatch, client, "lists"), "ListPage")
    _validate(_invoke(monkeypatch, client, "scheduled"), "ScheduledTweetList")
    _validate(_invoke(monkeypatch, client, "bookmarks", "folders"), "BookmarkFolderList")


def test_write_commands_match_the_write_envelope(monkeypatch) -> None:
    client = MagicMock()
    client.create_tweet.return_value = "77"
    client.quote_tweet.return_value = "78"
    client.resolve_user_id.return_value = "42"
    client.schedule_tweet.return_value = "900"

    for args in (
        ("post", "hola"),
        ("reply", "10", "hola"),
        ("quote", "10", "hola"),
        ("like", "10"),
        ("unretweet", "10"),
        ("bookmark", "10"),
        ("follow", "alice"),
        ("schedule", "hola", "--at", "2030-01-01T10:00+00:00"),
        ("unschedule", "900"),
    ):
        _validate(_invoke(monkeypatch, client, *args), "WriteResponse")


def test_errors_match_the_error_envelope(monkeypatch) -> None:
    client = MagicMock()
    client.fetch_user.side_effect = AuthenticationError("session expired")

    payload = _invoke(monkeypatch, client, "user", "alice")

    _validate(payload, "ErrorEnvelope")
    assert payload["error"]["code"] == "not_authenticated"


def test_missing_or_unexpected_fields_break_the_contract() -> None:
    missing = success_payload(tweets_to_data([_rich_tweet()]))
    del missing["data"][0]["mentions"]
    unexpected = success_payload(tweets_to_data([_rich_tweet()]))
    unexpected["data"][0]["newField"] = 1

    with pytest.raises(ValidationError):
        _validate(missing, "TweetPage")
    with pytest.raises(ValidationError):
        _validate(unexpected, "TweetPage")

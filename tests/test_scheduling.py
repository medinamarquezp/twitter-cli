from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from twitter_cli.cli import _parse_schedule_time, cli
from twitter_cli.client import TwitterClient
from twitter_cli.exceptions import TwitterAPIError
from twitter_cli.models import ScheduledTweet
from twitter_cli.parser import parse_scheduled_tweet
from twitter_cli.serialization import scheduled_tweet_to_dict


def _client() -> TwitterClient:
    client = TwitterClient.__new__(TwitterClient)
    client._write_delay = lambda: None
    return client


def test_schedule_tweet_sends_the_web_payload() -> None:
    client = _client()
    calls = []

    def graphql_post(operation_name, variables, features=None):
        calls.append((operation_name, variables))
        return {"data": {"tweet": {"rest_id": "900"}}}

    client._graphql_post = graphql_post

    scheduled_id = client.schedule_tweet("hola", 1800000000, media_ids=["m1"])

    assert scheduled_id == "900"
    assert calls == [
        (
            "CreateScheduledTweet",
            {
                "post_tweet_request": {
                    "auto_populate_reply_metadata": False,
                    "status": "hola",
                    "exclude_reply_user_ids": [],
                    "media_ids": ["m1"],
                },
                "execute_at": 1800000000,
            },
        )
    ]


def test_schedule_tweet_fails_without_an_id() -> None:
    client = _client()
    client._graphql_post = lambda operation_name, variables, features=None: {"data": {}}

    with pytest.raises(TwitterAPIError):
        client.schedule_tweet("hola", 1800000000)


def test_fetch_scheduled_tweets_parses_items() -> None:
    client = _client()
    client._graphql_get = lambda operation_name, variables, features: {
        "data": {
            "viewer": {
                "scheduled_tweet_list": [
                    {
                        "rest_id": "900",
                        "scheduling_info": {"execute_at": 1800000000000, "state": "Scheduled"},
                        "tweet_create_request": {"status": "hola", "media_ids": ["m1"]},
                    },
                    {"without": "id"},
                ]
            }
        }
    }

    items = client.fetch_scheduled_tweets()

    assert items == [ScheduledTweet(id="900", text="hola", execute_at=1800000000, state="Scheduled", media_ids=["m1"])]


def test_delete_scheduled_tweet_requires_confirmation() -> None:
    client = _client()
    client._graphql_post = lambda operation_name, variables, features=None: {"data": {"scheduledtweet_delete": "Done"}}
    assert client.delete_scheduled_tweet("900") is True

    client._graphql_post = lambda operation_name, variables, features=None: {"data": {}}
    with pytest.raises(TwitterAPIError):
        client.delete_scheduled_tweet("900")


def test_parse_scheduled_tweet_keeps_seconds() -> None:
    item = parse_scheduled_tweet({"rest_id": "1", "scheduling_info": {"execute_at": 1800000000}})

    assert item is not None
    assert item.execute_at == 1800000000
    assert parse_scheduled_tweet({"scheduling_info": {}}) is None


def test_scheduled_tweet_serialization_adds_iso_time() -> None:
    data = scheduled_tweet_to_dict(ScheduledTweet(id="1", text="hola", execute_at=1800000000, state="Scheduled"))

    assert data["executeAtISO"] == "2027-01-15T08:00:00+00:00"
    assert data["state"] == "Scheduled"


def test_parse_schedule_time_accepts_offsets_and_local_time() -> None:
    assert _parse_schedule_time("2030-01-01T10:00+00:00") == 1893492000
    in_an_hour = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 3600))
    assert abs(_parse_schedule_time(in_an_hour) - (time.time() + 3600)) < 61


def test_parse_schedule_time_rejects_past_and_unparseable_times() -> None:
    with pytest.raises(click.BadParameter):
        _parse_schedule_time("2020-01-01T10:00+00:00")
    with pytest.raises(click.BadParameter):
        _parse_schedule_time("mañana")


def test_schedule_command_returns_id_and_time(monkeypatch) -> None:
    fake = MagicMock()
    fake.schedule_tweet.return_value = "900"
    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: fake)

    result = CliRunner().invoke(cli, ["schedule", "hola", "--at", "2030-01-01T10:00+00:00", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)["data"]
    assert payload["id"] == "900"
    assert payload["executeAt"] == 1893492000
    fake.schedule_tweet.assert_called_once_with("hola", 1893492000, media_ids=None)


def test_unschedule_rejects_non_numeric_ids(monkeypatch) -> None:
    fake = MagicMock()
    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: fake)

    result = CliRunner().invoke(cli, ["unschedule", "abc", "--json"])

    assert result.exit_code != 0
    fake.delete_scheduled_tweet.assert_not_called()


def test_scheduled_command_lists_items(monkeypatch) -> None:
    fake = MagicMock()
    fake.fetch_scheduled_tweets.return_value = [ScheduledTweet(id="900", text="hola", execute_at=1893492000)]
    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: fake)

    result = CliRunner().invoke(cli, ["scheduled", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"][0]["id"] == "900"

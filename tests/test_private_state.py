from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from twitter_cli import cache, graphql
from twitter_cli.client import TwitterClient
from twitter_cli.exceptions import TwitterAPIError
from twitter_cli.graphql import FEATURES
from twitter_cli.private_files import write_private_text


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_write_private_text_restricts_new_and_existing_files(tmp_path: Path) -> None:
    target = tmp_path / "private" / "data.json"

    write_private_text(target, "{}")
    assert _mode(target) == 0o600
    assert _mode(target.parent) == 0o700

    target.chmod(0o644)
    write_private_text(target, "[]")
    assert target.read_text(encoding="utf-8") == "[]"
    assert _mode(target) == 0o600


def test_tweet_cache_is_private(tweet_factory) -> None:
    cache.save_tweet_cache([tweet_factory("1")])

    assert _mode(cache._CACHE_FILE) == 0o600


def test_transaction_cache_is_private() -> None:
    client = TwitterClient.__new__(TwitterClient)

    client._save_ct_cache("<html></html>", "ondemand")

    assert _mode(Path(TwitterClient._ct_cache_path())) == 0o600


def test_live_query_ids_survive_a_new_process(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    graphql._remember_live_query_id("UserTweets", "live-user-tweets")

    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    monkeypatch.setattr(graphql, "_persisted_query_ids", None)

    assert graphql._resolve_query_id("UserTweets") == "live-user-tweets"
    assert _mode(graphql.QUERY_ID_CACHE_FILE) == 0o600


def test_expired_query_ids_are_ignored(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    expired = time.time() - graphql.QUERY_ID_CACHE_TTL - 60
    write_private_text(
        graphql.QUERY_ID_CACHE_FILE,
        json.dumps({"UserTweets": {"queryId": "expired-id", "resolvedAt": expired}}),
    )

    assert graphql._resolve_query_id("UserTweets") == graphql.FALLBACK_QUERY_IDS["UserTweets"]


def test_invalidated_query_ids_are_dropped_from_disk(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    graphql._remember_live_query_id("UserTweets", "live-user-tweets")

    graphql._invalidate_query_id("UserTweets")

    assert "UserTweets" not in json.loads(graphql.QUERY_ID_CACHE_FILE.read_text(encoding="utf-8"))


def test_graphql_get_retries_a_stale_persisted_query_id() -> None:
    client = TwitterClient.__new__(TwitterClient)
    urls = []

    def api_get(url):
        urls.append(url)
        if len(urls) == 1:
            raise TwitterAPIError(404, "stale")
        return {"data": {}}

    client._api_get = api_get

    with (
        patch("twitter_cli.client._resolve_query_id", side_effect=["persisted-id", "live-id"]),
        patch("twitter_cli.client._invalidate_query_id") as invalidate,
    ):
        assert client._graphql_get("UserTweets", {}, FEATURES) == {"data": {}}

    assert "persisted-id" in urls[0]
    assert "live-id" in urls[1]
    invalidate.assert_called_once_with("UserTweets")


def test_graphql_get_does_not_retry_when_the_live_query_id_is_unchanged() -> None:
    client = TwitterClient.__new__(TwitterClient)
    urls = []

    def api_get(url):
        urls.append(url)
        raise TwitterAPIError(404, "missing")

    client._api_get = api_get

    with (
        patch("twitter_cli.client._resolve_query_id", side_effect=["same-id", "same-id"]),
        patch("twitter_cli.client._invalidate_query_id"),
        pytest.raises(TwitterAPIError),
    ):
        client._graphql_get("UserTweets", {}, FEATURES)

    assert len(urls) == 1

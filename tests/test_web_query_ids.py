from __future__ import annotations

import json
import stat
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from twitter_cli import graphql
from twitter_cli.cli import cli
from twitter_cli.exceptions import QueryIdError

BASE = "https://abs.twimg.com/responsive-web/client-web/"
HOME_HTML = (
    '<script src="%svendor.aaa111.js"></script>'
    '<script src="%smain.bbb222.js"></script>'
    '<script>window.n={1:"bundle.ComposeGrokMedia",2:"bundle.Explore",3:"bundle.UserLists"};'
    'window.h={1:"c0ffee1",2:"d00d002",3:"abc1234"}</script>'
) % (BASE, BASE)
SCRIPTS = {
    BASE + "main.bbb222.js": (
        'a={queryId:"web-user-tweets",operationName:"UserTweets"};'
        'b={queryId:"web-brand-new",operationName:"BrandNewTimeline"}'
    ),
    BASE + "vendor.aaa111.js": "",
    BASE + "bundle.ComposeGrokMedia.c0ffee1a.js": 'b={queryId:"web-create",operationName:"CreateScheduledTweet"}',
    BASE + "bundle.Explore.d00d002a.js": 'c={queryId:"web-explore",operationName:"ExplorePage"}',
    BASE + "bundle.UserLists.abc1234a.js": 'd={queryId:"web-members",operationName:"ListMembers"}',
}


def _fetcher(fetched: list[str]):
    def fetch(url: str) -> str:
        fetched.append(url)
        return SCRIPTS[url]

    return fetch


def test_web_bundle_urls_reads_entries_and_the_chunk_map() -> None:
    entries, chunks = graphql.web_bundle_urls(HOME_HTML)

    assert entries == [BASE + "main.bbb222.js", BASE + "vendor.aaa111.js"]
    assert chunks["bundle.UserLists"] == BASE + "bundle.UserLists.abc1234a.js"
    assert len(chunks) == 3


def test_chunks_sharing_words_with_missing_operations_go_first() -> None:
    _, chunks = graphql.web_bundle_urls(HOME_HTML)

    ordered = graphql.prioritized_chunk_urls(chunks, ["ListMembers"])

    assert ordered[0] == BASE + "bundle.UserLists.abc1234a.js"


def test_refresh_stops_once_every_wanted_operation_is_found() -> None:
    fetched: list[str] = []

    result = graphql.refresh_web_query_ids(HOME_HTML, _fetcher(fetched), ["UserTweets", "ListMembers"], quick=True)

    assert result["queryIds"]["UserTweets"] == "web-user-tweets"
    assert result["queryIds"]["ListMembers"] == "web-members"
    assert result["missing"] == []
    assert BASE + "bundle.Explore.d00d002a.js" not in fetched
    saved = json.loads(graphql.WEB_QUERY_ID_FILE.read_text(encoding="utf-8"))
    assert saved["queryIds"]["ListMembers"] == "web-members"
    assert stat.S_IMODE(graphql.WEB_QUERY_ID_FILE.stat().st_mode) == 0o600


def test_refresh_scans_every_chunk_by_default_and_reports_missing() -> None:
    fetched: list[str] = []

    result = graphql.refresh_web_query_ids(HOME_HTML, _fetcher(fetched), ["UserTweets", "Unknown"])

    assert len(fetched) == len(SCRIPTS)
    assert result["queryIds"]["ExplorePage"] == "web-explore"
    assert result["missing"] == ["Unknown"]


def test_refresh_needs_the_logged_in_page() -> None:
    with pytest.raises(QueryIdError):
        graphql.refresh_web_query_ids("<html></html>", _fetcher([]), ["UserTweets"])


def test_web_ids_serve_operations_without_a_built_in_id(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    graphql.save_web_query_ids({"BrandNewOperation": "web-new"})

    assert graphql._resolve_query_id("BrandNewOperation") == "web-new"


def test_web_ids_do_not_replace_working_built_in_ids(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    graphql.save_web_query_ids({"UserTweets": "web-user-tweets"})

    assert graphql._resolve_query_id("UserTweets") == graphql.FALLBACK_QUERY_IDS["UserTweets"]


def test_a_rejected_id_falls_back_to_the_web_id_and_is_never_retried(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    graphql.save_web_query_ids({"UserTweets": "web-user-tweets"})
    built_in = graphql._resolve_query_id("UserTweets")

    graphql._invalidate_query_id("UserTweets")
    refreshed = graphql._resolve_query_id("UserTweets", prefer_fallback=False)

    assert refreshed == "web-user-tweets"
    graphql._invalidate_query_id("UserTweets")
    assert graphql._resolve_query_id("UserTweets", prefer_fallback=False) == built_in


def test_automatic_scan_reads_the_cached_logged_in_page(monkeypatch) -> None:
    monkeypatch.setattr(graphql, "_cached_query_ids", {})
    graphql.TRANSACTION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    graphql.TRANSACTION_CACHE_FILE.write_text(json.dumps({"home_html": HOME_HTML}), encoding="utf-8")
    monkeypatch.setattr(graphql, "_fetch_from_github", lambda url_fetch_fn, operation_name: None)
    fetched: list[str] = []

    query_id = graphql._resolve_query_id("BrandNewTimeline", url_fetch_fn=lambda url, headers=None: _fetcher(fetched)(url))

    assert query_id == "web-brand-new"
    assert fetched == [BASE + "main.bbb222.js", BASE + "vendor.aaa111.js"]
    assert graphql._scanned_query_ids["UserTweets"] == "web-user-tweets"
    assert "UserTweets" not in graphql._cached_query_ids


def test_refresh_command_reports_changed_and_missing_ids(monkeypatch) -> None:
    fake = MagicMock()
    fake.cached_home_html.return_value = HOME_HTML
    monkeypatch.setattr("twitter_cli.cli._get_client", lambda config=None, quiet=False: fake)
    monkeypatch.setattr("twitter_cli.cli._url_fetch", _fetcher([]))

    result = CliRunner().invoke(cli, ["refresh-query-ids", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)["data"]
    assert "UserTweets" in payload["changed"]
    assert "ListMembers" in payload["changed"]
    assert payload["found"] == 5

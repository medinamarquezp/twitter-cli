from __future__ import annotations

from typing import Any

from twitter_cli.parser import parse_timeline_response, parse_tweet_result
from twitter_cli.serialization import tweet_from_dict, tweet_to_dict


def _user(user_id: str, screen_name: str) -> dict[str, Any]:
    return {"rest_id": user_id, "core": {"screen_name": screen_name, "name": screen_name}, "legacy": {}}


def _result(rest_id: str, user: dict[str, Any], legacy: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "__typename": "Tweet",
        "rest_id": rest_id,
        "core": {"user_results": {"result": user}},
        "legacy": {"created_at": "Mon Oct 13 08:00:00 +0000 2026", "full_text": "hola", **legacy},
        **extra,
    }


def _reply_legacy() -> dict[str, Any]:
    return {
        "in_reply_to_status_id_str": "10",
        "in_reply_to_screen_name": "alice",
        "conversation_id_str": "10",
        "entities": {"user_mentions": [{"screen_name": "alice"}], "hashtags": [{"text": "IA"}]},
    }


def test_reply_and_conversation_fields_are_parsed() -> None:
    tweet = parse_tweet_result(_result("20", _user("2", "bob"), _reply_legacy()))

    assert tweet is not None
    assert tweet.in_reply_to_id == "10"
    assert tweet.in_reply_to_user == "alice"
    assert tweet.conversation_id == "10"
    assert tweet.mentions == ["alice"]
    assert tweet.hashtags == ["IA"]
    assert tweet.retweeted_at is None


def test_original_posts_have_no_reply_fields() -> None:
    tweet = parse_tweet_result(_result("10", _user("1", "alice"), {"conversation_id_str": "10"}))

    assert tweet is not None
    assert tweet.in_reply_to_id is None
    assert tweet.in_reply_to_user is None
    assert tweet.conversation_id == "10"
    assert tweet.mentions == []


def test_retweets_keep_the_retweet_time() -> None:
    original = _result("10", _user("1", "alice"), {"created_at": "Sun Oct 12 08:00:00 +0000 2026"})
    retweet = _result(
        "30",
        _user("3", "carol"),
        {"created_at": "Mon Oct 13 09:30:00 +0000 2026", "retweeted_status_result": {"result": original}},
    )

    tweet = parse_tweet_result(retweet)

    assert tweet is not None
    assert tweet.is_retweet is True
    assert tweet.created_at == "Sun Oct 12 08:00:00 +0000 2026"
    assert tweet.retweeted_at == "Mon Oct 13 09:30:00 +0000 2026"
    assert tweet_to_dict(tweet)["retweetedAtISO"] == "2026-10-13T09:30:00+00:00"


def test_long_posts_take_mentions_and_hashtags_from_the_note() -> None:
    note = {
        "note_tweet_results": {
            "result": {
                "text": "texto largo",
                "entity_set": {"user_mentions": [{"screen_name": "bob"}], "hashtags": [{"text": "dev"}]},
            }
        }
    }

    tweet = parse_tweet_result(
        _result("40", _user("1", "alice"), {"entities": {"user_mentions": [], "hashtags": []}}, note_tweet=note)
    )

    assert tweet is not None
    assert tweet.text == "texto largo"
    assert tweet.mentions == ["bob"]
    assert tweet.hashtags == ["dev"]


def test_new_fields_round_trip_through_json() -> None:
    quoted = _result("5", _user("9", "dave"), {"favorite_count": 7})
    tweet = parse_tweet_result(
        _result("20", _user("2", "bob"), _reply_legacy(), quoted_status_result={"result": quoted})
    )
    assert tweet is not None

    data = tweet_to_dict(tweet)
    assert data["inReplyToId"] == "10"
    assert data["conversationId"] == "10"
    assert data["mentions"] == ["alice"]
    assert data["quotedTweet"]["author"]["id"] == "9"
    assert data["quotedTweet"]["metrics"]["likes"] == 7

    restored = tweet_from_dict(data)
    assert restored.in_reply_to_id == "10"
    assert restored.in_reply_to_user == "alice"
    assert restored.conversation_id == "10"
    assert restored.mentions == ["alice"]
    assert restored.hashtags == ["IA"]
    assert restored.quoted_tweet is not None
    assert restored.quoted_tweet.metrics.likes == 7


def _entry(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "entryId": "tweet-%s" % result["rest_id"],
        "content": {"entryType": "TimelineTimelineItem", "itemContent": {"tweet_results": {"result": result}}},
    }


def test_pinned_tweet_is_flagged_listed_first_and_not_repeated() -> None:
    alice = _user("1", "alice")
    instructions = [
        {"type": "TimelineClearCache"},
        {"type": "TimelineAddEntries", "entries": [_entry(_result("9", alice, {})), _entry(_result("5", alice, {}))]},
        {"type": "TimelinePinEntry", "entry": _entry(_result("5", alice, {}))},
    ]

    tweets, _ = parse_timeline_response({}, lambda data: instructions)

    assert [(tweet.id, tweet.is_pinned) for tweet in tweets] == [("5", True), ("9", False)]
    assert tweet_to_dict(tweets[0])["isPinned"] is True
    assert tweet_to_dict(tweets[1])["isPinned"] is False
    assert tweet_from_dict(tweet_to_dict(tweets[0])).is_pinned is True


def test_timelines_without_a_pin_entry_flag_nothing() -> None:
    alice = _user("1", "alice")
    instructions = [{"type": "TimelineAddEntries", "entries": [_entry(_result("9", alice, {}))]}]

    tweets, _ = parse_timeline_response({}, lambda data: instructions)

    assert [tweet.is_pinned for tweet in tweets] == [False]

"""Serialization helpers for Tweet and UserProfile models."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from .models import Author, BookmarkFolder, Metrics, Tweet, TweetMedia, TwitterList, UserProfile
from .timeutil import format_iso8601, format_local_time


def tweet_to_dict(tweet: Tweet) -> Dict[str, Any]:
    """Convert a Tweet dataclass into a JSON-safe dict."""
    data = {
        "id": tweet.id,
        "text": tweet.text,
        "author": {
            "id": tweet.author.id,
            "name": tweet.author.name,
            "screenName": tweet.author.screen_name,
            "profileImageUrl": tweet.author.profile_image_url,
            "verified": tweet.author.verified,
            "followers": tweet.author.followers_count,
            "following": tweet.author.following_count,
        },
        "metrics": _metrics_to_dict(tweet.metrics),
        "createdAt": tweet.created_at,
        "createdAtLocal": format_local_time(tweet.created_at),
        "createdAtISO": format_iso8601(tweet.created_at),
        "media": [
            {
                "type": media.type,
                "url": media.url,
                "width": media.width,
                "height": media.height,
            }
            for media in tweet.media
        ],
        "urls": list(tweet.urls),
        "mentions": list(tweet.mentions),
        "hashtags": list(tweet.hashtags),
        "isRetweet": tweet.is_retweet,
        "retweetedBy": tweet.retweeted_by,
        "retweetedAt": tweet.retweeted_at,
        "retweetedAtISO": format_iso8601(tweet.retweeted_at) if tweet.retweeted_at else None,
        "inReplyToId": tweet.in_reply_to_id,
        "inReplyToUser": tweet.in_reply_to_user,
        "conversationId": tweet.conversation_id,
        "lang": tweet.lang,
        "score": tweet.score,
        "isSubscriberOnly": tweet.is_subscriber_only,
        "isPromoted": tweet.is_promoted,
    }
    if tweet.article_title is not None:
        data["articleTitle"] = tweet.article_title
    if tweet.article_text is not None:
        data["articleText"] = tweet.article_text
    if tweet.quoted_tweet:
        data["quotedTweet"] = {
            "id": tweet.quoted_tweet.id,
            "text": tweet.quoted_tweet.text,
            "author": {
                "id": tweet.quoted_tweet.author.id,
                "screenName": tweet.quoted_tweet.author.screen_name,
                "name": tweet.quoted_tweet.author.name,
            },
            "metrics": _metrics_to_dict(tweet.quoted_tweet.metrics),
            "createdAt": tweet.quoted_tweet.created_at,
            "createdAtISO": format_iso8601(tweet.quoted_tweet.created_at),
        }
    return data


def _metrics_to_dict(metrics: Metrics) -> Dict[str, int]:
    return {
        "likes": metrics.likes,
        "retweets": metrics.retweets,
        "replies": metrics.replies,
        "quotes": metrics.quotes,
        "views": metrics.views,
        "bookmarks": metrics.bookmarks,
    }


def _metrics_from_dict(data: Dict[str, Any]) -> Metrics:
    return Metrics(
        likes=int(data.get("likes") or 0),
        retweets=int(data.get("retweets") or 0),
        replies=int(data.get("replies") or 0),
        quotes=int(data.get("quotes") or 0),
        views=int(data.get("views") or 0),
        bookmarks=int(data.get("bookmarks") or 0),
    )


def tweet_from_dict(data: Dict[str, Any]) -> Tweet:
    """Convert a dict into a Tweet dataclass."""
    author_data = data.get("author") or {}
    metrics_data = data.get("metrics") or {}
    media_data = data.get("media") or []
    quoted_data = data.get("quotedTweet")

    quoted_tweet = None  # type: Optional[Tweet]
    if isinstance(quoted_data, dict):
        quoted_author = quoted_data.get("author") or {}
        quoted_tweet = Tweet(
            id=str(quoted_data.get("id") or ""),
            text=str(quoted_data.get("text") or ""),
            author=Author(
                id=str(quoted_author.get("id") or ""),
                name=str(quoted_author.get("name") or ""),
                screen_name=str(quoted_author.get("screenName") or ""),
            ),
            metrics=_metrics_from_dict(quoted_data.get("metrics") or {}),
            created_at=str(quoted_data.get("createdAt") or ""),
        )

    return Tweet(
        id=str(data.get("id") or ""),
        text=str(data.get("text") or ""),
        author=Author(
            id=str(author_data.get("id") or ""),
            name=str(author_data.get("name") or ""),
            screen_name=str(author_data.get("screenName") or ""),
            profile_image_url=str(author_data.get("profileImageUrl") or ""),
            verified=bool(author_data.get("verified", False)),
        ),
        metrics=_metrics_from_dict(metrics_data),
        created_at=str(data.get("createdAt") or ""),
        media=[
            TweetMedia(
                type=str(item.get("type") or ""),
                url=str(item.get("url") or ""),
                width=_optional_int(item.get("width")),
                height=_optional_int(item.get("height")),
            )
            for item in media_data
            if isinstance(item, dict)
        ],
        urls=[str(url) for url in (data.get("urls") or [])],
        is_retweet=bool(data.get("isRetweet", False)),
        lang=str(data.get("lang") or ""),
        retweeted_by=_optional_str(data.get("retweetedBy")),
        quoted_tweet=quoted_tweet,
        score=float(data["score"]) if data.get("score") is not None else None,
        article_title=_optional_str(data.get("articleTitle")),
        article_text=_optional_str(data.get("articleText")),
        is_subscriber_only=bool(data.get("isSubscriberOnly", False)),
        is_promoted=bool(data.get("isPromoted", False)),
        in_reply_to_id=_optional_str(data.get("inReplyToId")),
        in_reply_to_user=_optional_str(data.get("inReplyToUser")),
        conversation_id=_optional_str(data.get("conversationId")),
        mentions=[str(item) for item in (data.get("mentions") or [])],
        hashtags=[str(item) for item in (data.get("hashtags") or [])],
        retweeted_at=_optional_str(data.get("retweetedAt")),
    )


def tweets_from_json(raw: str) -> List[Tweet]:
    """Parse a JSON string into Tweet objects."""
    payload = json.loads(raw)
    if isinstance(payload, dict) and payload.get("ok") is True and isinstance(payload.get("data"), list):
        payload = payload["data"]
    if not isinstance(payload, list):
        raise ValueError("Tweet JSON payload must be a list")
    return [tweet_from_dict(item) for item in payload if isinstance(item, dict)]


def tweets_to_json(tweets: Iterable[Tweet]) -> str:
    """Serialize Tweet objects to pretty JSON."""
    return json.dumps([tweet_to_dict(tweet) for tweet in tweets], ensure_ascii=False, indent=2)


def tweets_to_data(tweets: Iterable[Tweet]) -> List[Dict[str, Any]]:
    """Serialize Tweet objects to Python dicts."""
    return [tweet_to_dict(tweet) for tweet in tweets]


def tweet_to_compact_dict(tweet: Tweet) -> Dict[str, Any]:
    """Convert a Tweet into a compact dict with minimal fields for LLM consumption."""
    text = tweet.text.replace("\n", " ").strip()
    if len(text) > 140:
        text = text[:137] + "..."
    # Short time: "Mar 07 05:51" from "Sat Mar 07 05:51:02 +0000 2026"
    parts = tweet.created_at.split()
    if len(parts) >= 4:
        time_str = "%s %s %s" % (parts[1], parts[2], parts[3][:5])
    else:
        time_str = tweet.created_at
    return {
        "id": tweet.id,
        "author": "@%s" % tweet.author.screen_name,
        "text": text,
        "likes": tweet.metrics.likes,
        "rts": tweet.metrics.retweets,
        "time": time_str,
    }


def tweets_to_compact_json(tweets: Iterable[Tweet]) -> str:
    """Serialize Tweet objects to compact JSON (minimal fields for LLM/pipe usage)."""
    return json.dumps(
        [tweet_to_compact_dict(tweet) for tweet in tweets],
        ensure_ascii=False,
        indent=2,
    )


def bookmark_folder_to_dict(folder: BookmarkFolder) -> Dict[str, Any]:
    """Convert a BookmarkFolder dataclass into a JSON-safe dict."""
    return {
        "id": folder.id,
        "name": folder.name,
    }


def bookmark_folders_to_data(folders: Iterable[BookmarkFolder]) -> List[Dict[str, Any]]:
    """Serialize BookmarkFolder objects to Python dicts."""
    return [bookmark_folder_to_dict(f) for f in folders]


def user_profile_to_dict(user: UserProfile) -> Dict[str, Any]:
    """Convert a UserProfile dataclass into a JSON-safe dict."""
    return {
        "id": user.id,
        "name": user.name,
        "screenName": user.screen_name,
        "bio": user.bio,
        "location": user.location,
        "url": user.url,
        "followers": user.followers_count,
        "following": user.following_count,
        "tweets": user.tweets_count,
        "likes": user.likes_count,
        "verified": user.verified,
        "profileImageUrl": user.profile_image_url,
        "createdAt": user.created_at,
        "createdAtISO": format_iso8601(user.created_at),
    }


def users_to_json(users: Iterable[UserProfile]) -> str:
    """Serialize UserProfile objects to pretty JSON."""
    return json.dumps(
        [user_profile_to_dict(user) for user in users],
        ensure_ascii=False,
        indent=2,
    )


def users_to_data(users: Iterable[UserProfile]) -> List[Dict[str, Any]]:
    """Serialize UserProfile objects to Python dicts."""
    return [user_profile_to_dict(user) for user in users]


def twitter_list_to_dict(item: TwitterList) -> Dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "memberCount": item.member_count,
        "subscriberCount": item.subscriber_count,
        "isPrivate": item.is_private,
        "ownerScreenName": item.owner_screen_name,
        "createdAt": item.created_at,
    }


def twitter_lists_to_data(items: Iterable[TwitterList]) -> List[Dict[str, Any]]:
    return [twitter_list_to_dict(item) for item in items]


def _optional_int(value: Any) -> Optional[int]:
    """Parse an optional integer value."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> Optional[str]:
    """Parse an optional string value."""
    if value is None:
        return None
    text = str(value)
    return text if text else None

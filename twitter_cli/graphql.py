"""GraphQL infrastructure for Twitter API.

Handles queryId resolution, URL building, JS bundle scanning,
and feature flag management.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple  # noqa: F401

from .exceptions import QueryIdError
from .private_files import STATE_DIR, write_private_text
from .text import CREATE_NOTE_TWEET_OPERATION, CREATE_TWEET_OPERATION

logger = logging.getLogger(__name__)

# ── Community OpenAPI queryId source ─────────────────────────────────────
TWITTER_OPENAPI_URL = (
    "https://raw.githubusercontent.com/fa0311/"
    "twitter-openapi/refs/heads/main/src/config/placeholder.json"
)

# ── Fallback (hardcoded) queryIds ────────────────────────────────────────
# NOTE: refreshed against twitter-openapi placeholder.json on 2026-08-09.
# X rotates these IDs regularly; refresh by fetching
# https://raw.githubusercontent.com/fa0311/twitter-openapi/refs/heads/main/src/config/placeholder.json
# and updating any value that drifted.
FALLBACK_QUERY_IDS = {
    "HomeTimeline": "7zlnp2TxC044W4C1ZUJMHw",
    "HomeLatestTimeline": "0dateTVgvXjpkf7kyBZy0g",
    "UserByScreenName": "IGgvgiOx4QZndDHuD3x9TQ",
    "UserTweets": "36rb3Xj3iJ64Q-9wKDjCcQ",
    "TweetDetail": "oCon7R-cgWRFy6EfZjaKfg",
    "Likes": "rk2aeVVvKsyUdG3jf5uiLw",
    "SearchTimeline": "Yw6L66Pw54NHKuq4Dp7b4Q",
    "Bookmarks": "XD0ViOeSOW4YoeNTGjVaYw",
    "ListLatestTweetsTimeline": "FVWmROVvhgjRPC-4jAUh8A",
    "Followers": "_orfRBQae57vylFPH0Huhg",
    "Following": "F42cDX8PDFxkbjjq6JrM2w",
    CREATE_TWEET_OPERATION: "5CdvsV_zjv4L64XFifAglw",
    CREATE_NOTE_TWEET_OPERATION: "dAlh5Gh9rR5pKk4HU4vW8g",
    "DeleteTweet": "VaenaVgh5q5ih7kvyVjgtg",
    "FavoriteTweet": "lI07N6Otwv1PhnEgXILM7A",
    "UnfavoriteTweet": "ZYKSe-w7KEslx3JhSIk5LA",
    "CreateRetweet": "mbRO74GrOvSfRcJnlMapnQ",
    "DeleteRetweet": "ZyZigVsNiFO6v1dEks1eWg",
    "CreateBookmark": "aoDbu3RHznuiSkQ9aNM67Q",
    "DeleteBookmark": "Wlmlj2-xzyS1GN3a6cj-mQ",
    "TweetResultByRestId": "tCVRZ3WCvoj0BVO7BKnL-Q",
    "BookmarkFoldersSlice": "i78YDd0Tza-dV4SYs58kRg",
    "BookmarkFolderTimeline": "hNY7X2xE2N7HVF6Qb_mu6w",
    "UserTweetsAndReplies": "D5eKzDa5ZoJuC1TCeAXbWA",
    "Retweeters": "TZsWuSj7vGmncVnq7KWDUQ",
    "ListMembers": "oIetCo19avgStX4mOnGsPg",
    "CreateScheduledTweet": "LCVzRQGxOaGnOnYH01NQXg",
    "FetchScheduledTweets": "H2elmT2R9DLhWoo0DZFNkA",
    "DeleteScheduledTweet": "CTOVqej0JBXAZSwkp1US0g",
}

# ── Default feature flags ────────────────────────────────────────────────
_DEFAULT_FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "responsive_web_media_download_video_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "responsive_web_enhance_cards_enabled": False,
}

# Features dict that gets updated dynamically from x.com JS bundles
FEATURES = dict(_DEFAULT_FEATURES)

# Extra composer flags belong only on CreateNoteTweet. Merging at call time
# preserves any live updates made to the shared base feature set.
NOTE_TWEET_FEATURES = {
    "longform_notetweets_creation_enabled": True,
    "longform_notetweets_richtext_consumption_enabled": True,
    "articles_preview_enabled": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
}

# Module-level caches (not thread-safe — CLI is single-threaded)
_cached_query_ids: Dict[str, str] = {}
_scanned_query_ids: Dict[str, str] = {}
_rejected_query_ids: Dict[str, Set[str]] = {}
_bundles_scanned = False

QUERY_ID_CACHE_FILE = STATE_DIR / "query_ids.json"
QUERY_ID_CACHE_TTL = 30 * 24 * 3600
_persisted_query_ids: Optional[Dict[str, Dict[str, Any]]] = None

WEB_QUERY_ID_FILE = STATE_DIR / "web_query_ids.json"
TRANSACTION_CACHE_FILE = STATE_DIR / "transaction_cache.json"
_web_query_ids: Optional[Dict[str, str]] = None

_OPERATION_PATTERN = re.compile(r'queryId:\s*"([A-Za-z0-9_-]+)"[^}]{0,200}operationName:\s*"([^"]+)"')
_WEB_ENTRY_PATTERN = re.compile(r"https://abs\.twimg\.com/responsive-web/client-web/(?:main|vendor)\.[0-9a-f]+\.js")
_CHUNK_ENTRY_PATTERN = re.compile(r'[,{](\d+):"([A-Za-z0-9_.~\-]+)"')
_CHUNK_URL = "https://abs.twimg.com/responsive-web/client-web/%s.%sa.js"
WEB_SCAN_CHUNK_LIMIT = 150


def find_query_ids(script: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for query_id, operation_name in _OPERATION_PATTERN.findall(script):
        found.setdefault(operation_name, query_id)
    return found


def web_bundle_urls(home_html: str) -> Tuple[List[str], Dict[str, str]]:
    entries = sorted(set(_WEB_ENTRY_PATTERN.findall(home_html)), key=lambda url: "/main." not in url)
    names: Dict[str, str] = {}
    hashes: Dict[str, str] = {}
    for chunk_id, value in _CHUNK_ENTRY_PATTERN.findall(home_html):
        if re.fullmatch(r"[0-9a-f]{6,}", value):
            hashes[chunk_id] = value
        else:
            names[chunk_id] = value
    chunks = {names[key]: _CHUNK_URL % (names[key], hashes[key]) for key in names if key in hashes}
    return entries, chunks


def prioritized_chunk_urls(chunks: Dict[str, str], wanted: Iterable[str]) -> List[str]:
    words = {word for name in wanted for word in re.findall(r"[A-Z][a-z]+", name) if len(word) > 3}

    def rank(name: str) -> Tuple[int, str]:
        return (-sum(1 for word in words if word in name), name)

    return [chunks[name] for name in sorted(chunks, key=rank)]


def _load_web_query_ids() -> Dict[str, str]:
    global _web_query_ids
    if _web_query_ids is not None:
        return _web_query_ids
    _web_query_ids = {}
    try:
        payload = json.loads(WEB_QUERY_ID_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _web_query_ids
    query_ids = payload.get("queryIds") if isinstance(payload, dict) else None
    if isinstance(query_ids, dict):
        _web_query_ids.update(
            {name: value for name, value in query_ids.items() if isinstance(name, str) and isinstance(value, str) and value}
        )
    return _web_query_ids


def save_web_query_ids(query_ids: Dict[str, str]) -> None:
    global _web_query_ids
    payload = {"scannedAt": time.time(), "queryIds": dict(sorted(query_ids.items()))}
    write_private_text(WEB_QUERY_ID_FILE, json.dumps(payload, indent=2))
    _web_query_ids = dict(query_ids)


def refresh_web_query_ids(
    home_html: str,
    url_fetch_fn: Callable[[str], str],
    wanted: Iterable[str],
    quick: bool = False,
    chunk_limit: int = WEB_SCAN_CHUNK_LIMIT,
) -> Dict[str, Any]:
    entries, chunks = web_bundle_urls(home_html)
    if not entries:
        raise QueryIdError("The logged-in x.com page links no web build; renew the session and retry")
    wanted_set = set(wanted)
    found: Dict[str, str] = {}
    scanned = 0
    for url in entries:
        for name, query_id in find_query_ids(url_fetch_fn(url)).items():
            found.setdefault(name, query_id)
        scanned += 1
    scanned_chunks = 0
    for url in prioritized_chunk_urls(chunks, wanted_set - set(found)):
        if quick and (wanted_set <= set(found) or scanned_chunks >= chunk_limit):
            break
        try:
            script = url_fetch_fn(url)
        except Exception as exc:
            logger.debug("Skipping chunk %s: %s", url, exc)
            continue
        scanned_chunks += 1
        for name, query_id in find_query_ids(script).items():
            found.setdefault(name, query_id)
    save_web_query_ids(found)
    return {
        "scannedScripts": scanned + scanned_chunks,
        "availableChunks": len(chunks),
        "queryIds": found,
        "missing": sorted(wanted_set - set(found)),
    }


def _cached_home_html() -> str:
    try:
        cache = json.loads(TRANSACTION_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    home_html = cache.get("home_html") if isinstance(cache, dict) else None
    return home_html if isinstance(home_html, str) else ""


def _load_persisted_query_ids() -> Dict[str, Dict[str, Any]]:
    global _persisted_query_ids
    if _persisted_query_ids is not None:
        return _persisted_query_ids
    _persisted_query_ids = {}
    try:
        payload = json.loads(QUERY_ID_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _persisted_query_ids
    if not isinstance(payload, dict):
        return _persisted_query_ids
    now = time.time()
    for operation_name, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        query_id = entry.get("queryId")
        resolved_at = entry.get("resolvedAt")
        if not isinstance(query_id, str) or not query_id:
            continue
        if not isinstance(resolved_at, (int, float)) or now - resolved_at > QUERY_ID_CACHE_TTL:
            continue
        _persisted_query_ids[operation_name] = {"queryId": query_id, "resolvedAt": resolved_at}
    return _persisted_query_ids


def _write_persisted_query_ids(entries: Dict[str, Dict[str, Any]]) -> None:
    try:
        write_private_text(QUERY_ID_CACHE_FILE, json.dumps(entries, sort_keys=True))
    except OSError as exc:
        logger.debug("Failed to persist query IDs: %s", exc)


def _remember_live_query_id(operation_name: str, query_id: str) -> str:
    _cached_query_ids[operation_name] = query_id
    entries = _load_persisted_query_ids()
    entries[operation_name] = {"queryId": query_id, "resolvedAt": time.time()}
    _write_persisted_query_ids(entries)
    return query_id


def operation_features(operation_name):
    # type: (str) -> Dict[str, Any]
    """Return base features plus overrides scoped to one operation."""
    if operation_name == CREATE_NOTE_TWEET_OPERATION:
        return dict(FEATURES, **NOTE_TWEET_FEATURES)
    return FEATURES


def _build_graphql_url(query_id, operation_name, variables, features, field_toggles=None):
    # type: (str, str, Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]]) -> str
    """Build GraphQL GET URL with encoded variables/features/fieldToggles.

    Only includes True-valued feature flags in the URL to avoid 414 URI Too Long.
    Twitter's API defaults missing features to False.
    """
    # Compact features: omit False values to keep URL under server limits
    compact_features = {k: v for k, v in features.items() if v is not False}
    url = "https://x.com/i/api/graphql/%s/%s?variables=%s&features=%s" % (
        query_id,
        operation_name,
        urllib.parse.quote(json.dumps(variables, separators=(",", ":"))),
        urllib.parse.quote(json.dumps(compact_features, separators=(",", ":"))),
    )
    if field_toggles:
        url += "&fieldToggles=%s" % urllib.parse.quote(
            json.dumps(field_toggles, separators=(",", ":"))
        )
    return url


def _scan_bundles(url_fetch_fn, home_html=""):
    # type: (Any, str) -> None
    """Scan Twitter JS bundles and cache queryId mappings.

    Args:
        url_fetch_fn: Function to fetch URLs (injected to avoid circular import).
    """
    global _bundles_scanned
    if _bundles_scanned:
        return
    _bundles_scanned = True

    entries, _ = web_bundle_urls(home_html) if home_html else ([], {})
    if entries:
        for url in entries:
            try:
                for name, query_id in find_query_ids(url_fetch_fn(url)).items():
                    _scanned_query_ids.setdefault(name, query_id)
            except Exception as exc:
                logger.debug("Failed to scan %s: %s", url, exc)
        logger.info("Scanned %d logged-in web bundles, found %d query IDs", len(entries), len(_scanned_query_ids))
        return

    try:
        from .constants import get_user_agent
        html = url_fetch_fn("https://x.com", {"user-agent": get_user_agent()})
        # Match both the legacy responsive-web/client-web layout and the new
        # x-web/x-web layout (X moved the web build to /x-web/ in 2026).
        script_pattern = re.compile(
            r'(?:src|href)=["\']'
            r'(https://abs\.twimg\.com/(?:responsive-web/client-web|x-web/x-web)[^"\']+'
            r'\.js)'
            r'["\']'
        )
        script_urls = script_pattern.findall(html)
        # The x-web entry bundle references its code as relative ./assets/*.js
        # chunks — follow those so any queryId/operationName pairs stay
        # reachable as the build layout evolves.
        if script_urls:
            try:
                from curl_cffi import requests as _cc_requests

                _sess: Any = _cc_requests.Session(impersonate="chrome")
                for script_url in list(script_urls):
                    if "/x-web/x-web/" not in script_url:
                        continue
                    entry = _sess.get(script_url, timeout=20).text
                    for rel in re.findall(
                        r'["\']\./assets/([a-zA-Z0-9._\-]+\.js)["\']', entry
                    ):
                        full = script_url.rsplit("/", 1)[0] + "/" + rel
                        if full not in script_urls:
                            script_urls.append(full)
            except Exception as _exc:
                logger.debug("x-web asset follow-up scan failed: %s", _exc)
    except Exception as exc:  # pragma: no cover - network-dependent branch
        logger.warning("Failed to scan JS bundles: %s", exc)
        return

    for script_url in script_urls:
        try:
            for operation_name, query_id in find_query_ids(url_fetch_fn(script_url)).items():
                _scanned_query_ids.setdefault(operation_name, query_id)
        except Exception:
            continue

    logger.info("Scanned %d JS bundles, found %d query IDs", len(script_urls), len(_scanned_query_ids))


def _update_features_from_html(html):
    # type: (str) -> None
    """Extract live feature flags from x.com HTML and update the global FEATURES dict.

    Twitter embeds feature switch config in inline scripts on the homepage.
    We parse these to keep FEATURES in sync with the current frontend.
    Only UPDATES existing keys — never adds new ones to avoid URL bloat.
    """
    try:
        feature_pattern = re.compile(
            r'"([a-z][a-z0-9_]+)":\s*\{\s*"value"\s*:\s*(true|false)',
            re.IGNORECASE,
        )
        found = 0
        for match in feature_pattern.finditer(html):
            key = match.group(1)
            value = match.group(2).lower() == "true"
            # Only update keys already in FEATURES — never add new ones
            # Adding new keys inflates URL length, causing 414/431 errors
            if key in FEATURES and FEATURES[key] != value:
                logger.debug("Feature flag updated: %s = %s -> %s", key, FEATURES[key], value)
                FEATURES[key] = value
                found += 1
        if found:
            logger.info("Updated %d feature flags from x.com", found)
    except Exception as exc:
        logger.debug("Feature extraction from HTML failed: %s", exc)


def _fetch_from_github(url_fetch_fn, operation_name):
    # type: (Any, str) -> Optional[str]
    """Fetch queryId from community-maintained twitter-openapi file."""
    try:
        payload = url_fetch_fn(TWITTER_OPENAPI_URL)
        parsed = json.loads(payload)
        operation = parsed.get(operation_name, {})
        query_id = operation.get("queryId")
        if isinstance(query_id, str) and query_id:
            return query_id
    except Exception as exc:  # pragma: no cover - network-dependent branch
        logger.debug("GitHub queryId lookup failed: %s", exc)
    return None


def _invalidate_query_id(operation_name):
    # type: (str) -> None
    """Remove a cached queryId for an operation."""
    rejected = _cached_query_ids.pop(operation_name, None)
    if rejected:
        _rejected_query_ids.setdefault(operation_name, set()).add(rejected)
    entries = _load_persisted_query_ids()
    if entries.pop(operation_name, None) is not None:
        _write_persisted_query_ids(entries)


def _resolve_query_id(operation_name, prefer_fallback=True, url_fetch_fn=None):
    # type: (str, bool, Any) -> str
    """Resolve queryId using cache, remote sources, and fallback constants."""
    cached = _cached_query_ids.get(operation_name)
    if cached:
        return cached

    rejected = _rejected_query_ids.get(operation_name, set())
    persisted = _load_persisted_query_ids().get(operation_name)
    if persisted and persisted["queryId"] not in rejected:
        _cached_query_ids[operation_name] = persisted["queryId"]
        return persisted["queryId"]

    fallback = FALLBACK_QUERY_IDS.get(operation_name)
    if prefer_fallback and fallback and fallback not in rejected:
        _cached_query_ids[operation_name] = fallback
        return fallback

    web_query_id = _load_web_query_ids().get(operation_name)
    if web_query_id and web_query_id not in rejected:
        return _remember_live_query_id(operation_name, web_query_id)

    if url_fetch_fn:
        github_query_id = _fetch_from_github(url_fetch_fn, operation_name)
        if github_query_id and github_query_id not in rejected:
            return _remember_live_query_id(operation_name, github_query_id)

        _scan_bundles(url_fetch_fn, _cached_home_html())
        scanned = _scanned_query_ids.get(operation_name)
        if scanned and scanned not in rejected:
            return _remember_live_query_id(operation_name, scanned)

    if fallback:
        _cached_query_ids[operation_name] = fallback
        return fallback

    raise QueryIdError('Cannot resolve queryId for "%s"' % operation_name)

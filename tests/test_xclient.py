"""Tests for XTimelineClient._parse_single_tweet using real-payload fixtures.

Fixtures are minimal slices of the actual API response captured 2026-04-01.
Key structure change vs legacy: user identity fields moved out of result.legacy
into result.core (name, screen_name) and result.avatar (image_url).
"""

from unittest.mock import patch

import pytest

from xclient import XTimelineClient, expand_tco_urls

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_node(name: str, screen_name: str, image_url: str = "") -> dict:
    """Build a minimal user_results.result node using the new API shape."""
    return {
        "__typename": "User",
        "core": {"name": name, "screen_name": screen_name},
        "avatar": {"image_url": image_url},
        "legacy": {},
    }


def _wrap_user(name: str, screen_name: str, image_url: str = "") -> dict:
    return {"user_results": {"result": _user_node(name, screen_name, image_url)}}


# ---------------------------------------------------------------------------
# Fixtures — minimal slices of the 2026-04-01 real payload
# ---------------------------------------------------------------------------

PLAIN_TWEET: dict = {
    "__typename": "Tweet",
    "rest_id": "2039421316445724961",
    "core": _wrap_user(
        "First Squawk",
        "FirstSquawk",
        "https://pbs.twimg.com/profile_images/squawk_normal.jpg",
    ),
    "legacy": {
        "id_str": "2039421316445724961",
        "full_text": "US CONGRESS GOP LEADERS: TO ADVANCE BILLS TO FULLY FUND HOMELAND SECURITY PROGRAMS",
        "entities": {"hashtags": [], "symbols": []},
    },
}

QUOTE_TWEET: dict = {
    "__typename": "Tweet",
    "rest_id": "2039421494527160688",
    "core": _wrap_user(
        "TraderSZ",
        "trader1sz",
        "https://pbs.twimg.com/profile_images/tradersz_normal.jpg",
    ),
    "legacy": {
        "id_str": "2039421494527160688",
        "full_text": "$ETHBTC breaking out? https://t.co/JeAapElptJ",
        "entities": {
            "symbols": [{"text": "ETHBTC", "indices": [0, 7]}],
            "hashtags": [],
        },
    },
    "quoted_status_result": {
        "result": {
            "__typename": "Tweet",
            "rest_id": "2037910161172377806",
            "core": _wrap_user("TraderSZ", "trader1sz"),
            "legacy": {
                "id_str": "2037910161172377806",
                "full_text": "$ETHBTC doesnt look too bad here",
                "entities": {
                    "symbols": [{"text": "ETHBTC", "indices": [0, 7]}],
                    "hashtags": [],
                },
            },
        }
    },
}

RETWEET: dict = {
    "__typename": "Tweet",
    "rest_id": "2039421365132906855",
    "core": _wrap_user(
        "TraderSZ",
        "trader1sz",
        "https://pbs.twimg.com/profile_images/tradersz_normal.jpg",
    ),
    "legacy": {
        "id_str": "2039421365132906855",
        "full_text": "RT @CryptoJelleNL: Many of you will remember my bull run plan...",
        "entities": {"hashtags": [], "symbols": []},
        "retweeted_status_result": {
            "result": {
                "__typename": "Tweet",
                "rest_id": "2038894508343963755",
                "core": _wrap_user(
                    "Jelle",
                    "CryptoJelleNL",
                    "https://pbs.twimg.com/profile_images/jelle_normal.jpg",
                ),
                "legacy": {
                    "id_str": "2038894508343963755",
                    "full_text": "Many of you will remember my bull run plan.",
                    "entities": {"hashtags": [], "symbols": []},
                },
            }
        },
    },
}

TWEET_WITH_MEDIA: dict = {
    "__typename": "Tweet",
    "rest_id": "2039000000000000001",
    "core": _wrap_user("TraderSZ", "trader1sz"),
    "legacy": {
        "id_str": "2039000000000000001",
        "full_text": "Chart attached https://t.co/abc123",
        "entities": {"hashtags": [], "symbols": []},
        "extended_entities": {
            "media": [
                {
                    "media_url_https": "https://pbs.twimg.com/media/photo.jpg",
                    "type": "photo",
                }
            ]
        },
    },
}

TWEET_WITH_METRICS: dict = {
    "__typename": "Tweet",
    "rest_id": "2039000000000000003",
    "core": _wrap_user("Someone", "someone"),
    "views": {"count": "24248", "state": "Enabled"},
    "legacy": {
        "id_str": "2039000000000000003",
        "full_text": "Some tweet",
        "created_at": "Wed Apr 01 19:15:49 +0000 2026",
        "favorite_count": 120,
        "retweet_count": 45,
        "reply_count": 10,
        "entities": {"hashtags": [], "symbols": []},
    },
}

TWEET_WITH_TICKERS_AND_HASHTAGS: dict = {
    "__typename": "Tweet",
    "rest_id": "2039000000000000002",
    "core": _wrap_user("Someone", "someone"),
    "legacy": {
        "id_str": "2039000000000000002",
        "full_text": "$BTC #Bitcoin looking good",
        "entities": {
            "symbols": [{"text": "BTC", "indices": [0, 4]}],
            "hashtags": [{"text": "Bitcoin", "indices": [5, 13]}],
        },
    },
}

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> XTimelineClient:
    with (
        patch.object(XTimelineClient, "_load_curl"),
        patch.object(XTimelineClient, "_load_last_id"),
    ):
        c = XTimelineClient(curl_path="nonexistent.txt")
        c.debug_http = False
        return c


def _parse(client: XTimelineClient, tw: dict) -> object:
    return client._parse_single_tweet(tw, allow_update_last_id=False)


# ---------------------------------------------------------------------------
# User field extraction
# ---------------------------------------------------------------------------

class TestUserField:
    def test_name_from_result_core(self, client):
        assert client._user_field(PLAIN_TWEET, "name") == "First Squawk"

    def test_screen_name_from_result_core(self, client):
        assert client._user_field(PLAIN_TWEET, "screen_name") == "FirstSquawk"

    def test_profile_image_from_result_avatar(self, client):
        assert client._user_field(PLAIN_TWEET, "profile_image_url_https") == (
            "https://pbs.twimg.com/profile_images/squawk_normal.jpg"
        )

    def test_missing_user_returns_empty_string(self, client):
        tw = {"__typename": "Tweet", "rest_id": "1", "core": {}, "legacy": {"id_str": "1", "full_text": "", "entities": {}}}
        assert client._user_field(tw, "name") == ""

    def test_legacy_stat_field_still_works(self, client):
        tw = {
            "core": {
                "user_results": {
                    "result": {
                        "__typename": "User",
                        "core": {},
                        "avatar": {},
                        "legacy": {"followers_count": 42},
                    }
                }
            }
        }
        assert client._user_field(tw, "followers_count") == 42


# ---------------------------------------------------------------------------
# Plain tweet
# ---------------------------------------------------------------------------

class TestPlainTweet:
    def test_id(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.id == 2039421316445724961

    def test_user_name(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.user_name == "First Squawk"

    def test_user_screen_name(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.user_screen_name == "FirstSquawk"

    def test_user_img(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.user_img == "https://pbs.twimg.com/profile_images/squawk_normal.jpg"

    def test_title(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.title == "First Squawk tweeted"

    def test_text(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert "HOMELAND SECURITY" in t.text

    def test_url(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.url == "https://twitter.com/user/status/2039421316445724961"


# ---------------------------------------------------------------------------
# Quote tweet
# ---------------------------------------------------------------------------

class TestQuoteTweet:
    def test_outer_user(self, client):
        t = _parse(client, QUOTE_TWEET)
        assert t.user_name == "TraderSZ"
        assert t.user_screen_name == "trader1sz"

    def test_title_includes_quoted_user(self, client):
        t = _parse(client, QUOTE_TWEET)
        assert "quote tweeted" in t.title
        assert "TraderSZ" in t.title

    def test_quoted_text_appended(self, client):
        t = _parse(client, QUOTE_TWEET)
        assert "doesnt look too bad" in t.text

    def test_tickers_merged(self, client):
        t = _parse(client, QUOTE_TWEET)
        assert "ETHBTC" in t.tickers


# ---------------------------------------------------------------------------
# Retweet
# ---------------------------------------------------------------------------

class TestRetweet:
    def test_outer_user(self, client):
        t = _parse(client, RETWEET)
        assert t.user_name == "TraderSZ"

    def test_title_includes_retweeted_user(self, client):
        t = _parse(client, RETWEET)
        assert "retweeted" in t.title
        assert "Jelle" in t.title

    def test_text_is_original(self, client):
        t = _parse(client, RETWEET)
        assert t.text == "Many of you will remember my bull run plan."


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

class TestMedia:
    def test_photo_parsed(self, client):
        t = _parse(client, TWEET_WITH_MEDIA)
        assert len(t.media) == 1
        assert t.media[0].url == "https://pbs.twimg.com/media/photo.jpg"
        assert t.media[0].type == "photo"

    def test_media_types_mirror_media(self, client):
        t = _parse(client, TWEET_WITH_MEDIA)
        assert t.media_types == ["photo"]


# ---------------------------------------------------------------------------
# Tickers and hashtags
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_created_at_parsed_to_iso(self, client):
        t = _parse(client, TWEET_WITH_METRICS)
        assert t.created_at == "2026-04-01T19:15:49Z"

    def test_likes(self, client):
        t = _parse(client, TWEET_WITH_METRICS)
        assert t.likes == 120

    def test_retweets(self, client):
        t = _parse(client, TWEET_WITH_METRICS)
        assert t.retweets == 45

    def test_replies(self, client):
        t = _parse(client, TWEET_WITH_METRICS)
        assert t.replies == 10

    def test_views(self, client):
        t = _parse(client, TWEET_WITH_METRICS)
        assert t.views == 24248

    def test_missing_metrics_default_to_zero(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.likes == 0
        assert t.retweets == 0
        assert t.views == 0

    def test_missing_created_at_defaults_to_empty(self, client):
        t = _parse(client, PLAIN_TWEET)
        assert t.created_at == ""


TWEET_WITH_URL: dict = {
    "__typename": "Tweet",
    "rest_id": "2039000000000000004",
    "core": _wrap_user("FlappyBert", "flappybert"),
    "legacy": {
        "id_str": "2039000000000000004",
        "full_text": "Play now 👉 https://t.co/tOjx6u4o0o",
        "entities": {
            "hashtags": [],
            "symbols": [],
            "urls": [
                {
                    "url": "https://t.co/tOjx6u4o0o",
                    "expanded_url": "http://t.me/FlappyBertBot",
                    "display_url": "t.me/FlappyBertBot",
                }
            ],
        },
    },
}

TWEET_WITH_MEDIA_URL: dict = {
    "__typename": "Tweet",
    "rest_id": "2039000000000000005",
    "core": _wrap_user("Someone", "someone"),
    "legacy": {
        "id_str": "2039000000000000005",
        "full_text": "Check this out https://t.co/medialink",
        # media t.co links are NOT in entities.urls — only in entities.media
        "entities": {"hashtags": [], "symbols": [], "urls": []},
        "extended_entities": {
            "media": [
                {"media_url_https": "https://pbs.twimg.com/media/photo.jpg", "type": "photo"}
            ]
        },
    },
}


LONG_TWEET: dict = {
    "__typename": "Tweet",
    "rest_id": "2039000000000000006",
    "core": _wrap_user("Trader", "trader"),
    "note_tweet": {
        "is_expandable": True,
        "note_tweet_results": {
            "result": {
                "text": "Full long text that goes well beyond 280 chars. " * 10,
                "entity_set": {
                    "symbols": [{"text": "BTC", "indices": [0, 4]}],
                    "hashtags": [{"text": "Trading", "indices": [5, 13]}],
                    "urls": [],
                },
            }
        },
    },
    "legacy": {
        "id_str": "2039000000000000006",
        "full_text": "Full long text that goes well beyond 280 chars. Full long text t…",
        "entities": {"hashtags": [], "symbols": [], "urls": []},
    },
}


class TestLongTweet:
    def test_full_text_used_over_truncated_legacy(self, client):
        t = _parse(client, LONG_TWEET)
        assert not t.text.endswith("…")
        assert len(t.text) > 280

    def test_tickers_from_note_entity_set(self, client):
        t = _parse(client, LONG_TWEET)
        assert "BTC" in t.tickers

    def test_hashtags_from_note_entity_set(self, client):
        t = _parse(client, LONG_TWEET)
        assert "TRADING" in t.hashtags


class TestUrlExpansion:
    def test_tco_replaced_with_expanded(self, client):
        t = _parse(client, TWEET_WITH_URL)
        assert "http://t.me/FlappyBertBot" in t.text
        assert "t.co" not in t.text

    def test_media_tco_still_stripped(self, client):
        # media t.co has no entities.urls entry, so strip_trailing_tco removes it
        t = _parse(client, TWEET_WITH_MEDIA_URL)
        assert "t.co" not in t.text

    def test_expand_tco_urls_replaces_all_occurrences(self):
        entities = [{"url": "https://t.co/abc", "expanded_url": "https://example.com"}]
        result = expand_tco_urls("see https://t.co/abc and https://t.co/abc", entities)
        assert result == "see https://example.com and https://example.com"

    def test_expand_tco_urls_ignores_missing_fields(self):
        entities = [{"url": "", "expanded_url": "https://example.com"}, {"url": "https://t.co/abc"}]
        # should not raise, text unchanged for invalid entries
        result = expand_tco_urls("https://t.co/abc", entities)
        assert result == "https://t.co/abc"


class TestEntities:
    def test_ticker_uppercased(self, client):
        t = _parse(client, TWEET_WITH_TICKERS_AND_HASHTAGS)
        assert "BTC" in t.tickers

    def test_hashtag_uppercased(self, client):
        t = _parse(client, TWEET_WITH_TICKERS_AND_HASHTAGS)
        assert "BITCOIN" in t.hashtags

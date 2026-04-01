"""Tests for XTimelineClient._parse_single_tweet using real-payload fixtures.

Fixtures are minimal slices of the actual API response captured 2026-04-01.
Key structure change vs legacy: user identity fields moved out of result.legacy
into result.core (name, screen_name) and result.avatar (image_url).
"""

from unittest.mock import patch

import pytest

from xclient import XTimelineClient

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

class TestEntities:
    def test_ticker_uppercased(self, client):
        t = _parse(client, TWEET_WITH_TICKERS_AND_HASHTAGS)
        assert "BTC" in t.tickers

    def test_hashtag_uppercased(self, client):
        t = _parse(client, TWEET_WITH_TICKERS_AND_HASHTAGS)
        assert "BITCOIN" in t.hashtags

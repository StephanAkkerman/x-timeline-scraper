import json
from urllib.request import Request

import pytest

from xquik import (
    build_xquik_request,
    build_xquik_search_url,
    search_xquik,
    tweet_from_xquik,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_build_xquik_search_url_includes_source_truth_params():
    url = build_xquik_search_url("agent search", cursor="next", limit=25)

    assert url == (
        "https://xquik.com/api/v1/x/tweets/search?"
        "q=agent+search&queryType=Latest&cursor=next&limit=25"
    )


def test_build_xquik_request_uses_api_key_header():
    request = build_xquik_request("https://example.test/search", "test-key")

    assert isinstance(request, Request)
    assert request.headers["X-api-key"] == "test-key"
    assert "Authorization" not in request.headers
    assert request.headers["Accept"] == "application/json"


def test_tweet_from_xquik_maps_known_fields():
    tweet = tweet_from_xquik(
        {
            "id": "2039000000000000001",
            "text": "hello",
            "createdAt": "2026-06-30T00:00:00.000Z",
            "likeCount": "4",
            "retweetCount": 3,
            "replyCount": True,
            "views": "10",
            "author": {"username": "xquik", "name": "Xquik"},
        }
    )

    assert tweet is not None
    assert tweet.id == 2039000000000000001
    assert tweet.text == "hello"
    assert tweet.user_screen_name == "xquik"
    assert tweet.user_name == "Xquik"
    assert tweet.likes == 4
    assert tweet.retweets == 3
    assert tweet.replies == 1
    assert tweet.views == 10


def test_tweet_from_xquik_preserves_zero_metric_values():
    tweet = tweet_from_xquik(
        {
            "id": "2039000000000000002",
            "text": "zero metrics",
            "likeCount": 0,
            "likes": 9,
            "retweetCount": "0.0",
            "retweets": 8,
            "replyCount": 0.0,
            "replies": 7,
            "viewCount": "0",
            "views": 6,
            "author": {"username": "xquik", "name": "Xquik"},
        }
    )

    assert tweet is not None
    assert tweet.likes == 0
    assert tweet.retweets == 0
    assert tweet.replies == 0
    assert tweet.views == 0


def test_search_xquik_uses_injected_opener():
    captured = {}

    def fake_opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["api_key"] = request.headers["X-api-key"]
        captured["timeout"] = timeout
        return FakeResponse({"tweets": [{"id": "1", "text": "one"}]})

    tweets = search_xquik("mcp", api_key="test-key", opener=fake_opener)

    assert len(tweets) == 1
    assert tweets[0].id == 1
    assert captured == {
        "url": "https://xquik.com/api/v1/x/tweets/search?q=mcp&queryType=Latest",
        "api_key": "test-key",
        "timeout": 30,
    }


def test_search_xquik_rejects_non_object_response():
    def fake_opener(_request, *, timeout):
        return FakeResponse(["not-object"])

    with pytest.raises(TypeError, match="JSON object"):
        search_xquik("mcp", api_key="test-key", opener=fake_opener)

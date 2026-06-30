from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tweet import Tweet

XQUIK_SEARCH_URL = "https://xquik.com/api/v1/x/tweets/search"


def build_xquik_search_url(
    query: str,
    *,
    query_type: str = "Latest",
    cursor: str | None = None,
    limit: int | None = None,
    base_url: str = XQUIK_SEARCH_URL,
) -> str:
    params: dict[str, str] = {"q": query, "queryType": query_type}
    if cursor:
        params["cursor"] = cursor
    if limit is not None:
        params["limit"] = str(limit)
    return f"{base_url}?{urlencode(params)}"


def build_xquik_request(url: str, api_key: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return 0
    return 0


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def tweet_from_xquik(raw: Mapping[str, Any]) -> Tweet | None:
    tweet_id = _as_int(
        _first_not_none(raw.get("id"), raw.get("tweet_id"), raw.get("rest_id"))
    )
    if tweet_id <= 0:
        return None

    author = raw.get("author")
    if not isinstance(author, Mapping):
        author = {}
    username = str(
        author.get("username") or author.get("screen_name") or raw.get("username") or ""
    ).lstrip("@")
    display_name = str(author.get("name") or raw.get("name") or username)
    text = str(raw.get("text") or raw.get("full_text") or "")

    return Tweet(
        id=tweet_id,
        text=text,
        user_name=display_name,
        user_screen_name=username,
        user_img=str(
            author.get("profile_image_url")
            or author.get("profile_image_url_https")
            or ""
        ),
        url=str(raw.get("url") or f"https://x.com/{username}/status/{tweet_id}"),
        media=[],
        tickers=[],
        hashtags=[],
        title=f"{display_name} tweeted",
        media_types=[],
        created_at=str(raw.get("createdAt") or raw.get("created_at") or ""),
        likes=_as_int(_first_not_none(raw.get("likeCount"), raw.get("likes"))),
        retweets=_as_int(_first_not_none(raw.get("retweetCount"), raw.get("retweets"))),
        replies=_as_int(_first_not_none(raw.get("replyCount"), raw.get("replies"))),
        views=_as_int(_first_not_none(raw.get("viewCount"), raw.get("views"))),
    )


def search_xquik(
    query: str,
    *,
    api_key: str,
    query_type: str = "Latest",
    cursor: str | None = None,
    limit: int | None = None,
    opener: Callable[..., Any] = urlopen,
) -> list[Tweet]:
    url = build_xquik_search_url(
        query,
        query_type=query_type,
        cursor=cursor,
        limit=limit,
    )
    request = build_xquik_request(url, api_key)
    with opener(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Xquik search response must be a JSON object")

    raw_tweets = payload.get("tweets") or payload.get("data") or []
    if not isinstance(raw_tweets, list):
        return []
    tweets: list[Tweet] = []
    for raw in raw_tweets:
        if isinstance(raw, Mapping):
            tweet = tweet_from_xquik(raw)
            if tweet is not None:
                tweets.append(tweet)
    return tweets

import asyncio
import datetime as dt
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Iterable

import aiohttp
import uncurl

from tweet import MediaItem, Tweet

logger = logging.getLogger(__file__)


def get_in(obj: Any, path: list[str] | tuple[str, ...], default: Any = None) -> Any:
    """Safe nested get: get_in(d, ['a','b','c'])."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def is_promoted_entry(entry: dict) -> bool:
    """Detect ads/promoted units."""
    eid = entry.get("entryId", "")
    if eid.startswith(("promoted-", "advertiser-")):
        return True
    content = entry.get("content", {})
    item = content.get("itemContent", {})
    return "promotedMetadata" in item or "promotedMetadata" in content


def is_tweet_item(entry: dict) -> bool:
    """Detect timeline items that actually contain tweets."""
    content = entry.get("content", {})
    if content.get("entryType") != "TimelineTimelineItem":
        return False
    item = content.get("itemContent", {})
    return item.get("itemType") == "TimelineTweet" and "tweet_results" in item


def normalize_tweet_result(tweet_results: dict) -> dict | None:
    """
    Normalize GraphQL result:
    - 'Tweet' -> as-is
    - 'TweetWithVisibilityResults' -> unwrap '.tweet'
    """
    result = tweet_results.get("result")
    if not isinstance(result, dict):
        return None
    tname = result.get("__typename")
    if tname == "Tweet":
        return result
    if tname == "TweetWithVisibilityResults":
        inner = result.get("tweet")
        return inner if isinstance(inner, dict) else None
    return None


def unescape_entities(text: str) -> str:
    """Unescape a minimal set of HTML entities that appear in tweet text."""
    return text.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")


_RE_TRAILING_TCO = re.compile(r"(https?://t\.co/\S+)$")
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "x-csrf-token",
    "x-guest-token",
    "x-twitter-auth-type",
    "ct0",
    "auth_token",
}


def _mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def _redact_mapping(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    out: dict[str, Any] = {}
    for k, v in data.items():
        key_l = str(k).lower()
        if key_l in _SENSITIVE_KEYS or "token" in key_l or "auth" in key_l:
            out[str(k)] = _mask_secret(str(v))
        else:
            out[str(k)] = v
    return out


def _preview_json(value: Any, limit: int = 1000) -> str:
    try:
        txt = json.dumps(value, ensure_ascii=False)
    except Exception:
        txt = str(value)
    return txt[:limit]


def _parse_cookie_string(cookie_blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in cookie_blob.split(";"):
        token = part.strip()
        if not token or "=" not in token:
            continue
        k, v = token.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def _extract_cookies_from_curl(raw_curl: str) -> dict[str, str]:
    collapsed = re.sub(r"\\\s*\n", " ", raw_curl)
    out: dict[str, str] = {}
    patterns = [
        r"(?:^|\s)-b\s+'([^']+)'",
        r'(?:^|\s)-b\s+"([^"]+)"',
        r"(?:^|\s)--cookie\s+'([^']+)'",
        r'(?:^|\s)--cookie\s+"([^"]+)"',
    ]
    for pat in patterns:
        for m in re.finditer(pat, collapsed):
            out.update(_parse_cookie_string(m.group(1)))
    return out


def strip_trailing_tco(text: str) -> str:
    return _RE_TRAILING_TCO.sub("", text)


class XTimelineClient:
    """
    Minimal client for polling an X/Twitter timeline endpoint described by a cURL.

    Parameters
    ----------
    curl_path : str
        Path to a text file containing a single cURL command.
    timeout_s : float
        Per-request timeout in seconds.
    persist_last_id_path : str | None
        Optional path to persist last seen tweet id between runs.
    """

    def __init__(
        self,
        curl_path: str = "curl.txt",
        timeout_s: float = 30.0,
        persist_last_id_path: str | None = None,
        debug_http: bool | None = None,
    ) -> None:
        self.curl_path = Path(curl_path)
        self.timeout_s = timeout_s
        self._session: aiohttp.ClientSession | None = None
        self._req: dict[str, Any] = {}
        self._last_tweet_id: int = 0
        self.debug_http = (
            (os.getenv("XCLIENT_DEBUG_HTTP", "").lower() in {"1", "true", "yes"})
            if debug_http is None
            else debug_http
        )
        self.persist_last_id_path = (
            Path(persist_last_id_path) if persist_last_id_path else None
        )
        self._load_curl()
        self._load_last_id()

    # ---------- lifecycle ----------

    def _load_curl(self) -> None:
        """Parse the cURL file into url/headers/cookies/json payload."""
        try:
            raw = self.curl_path.read_text(encoding="utf-8")
            ctx = uncurl.parse_context(
                "".join(line.strip() for line in raw.splitlines())
            )
            parsed_cookies = dict(ctx.cookies) if ctx.cookies else {}
            if not parsed_cookies:
                parsed_cookies = _extract_cookies_from_curl(raw)
            self._req = {
                "url": ctx.url,
                "headers": dict(ctx.headers) if ctx.headers else {},
                "cookies": parsed_cookies,
                "json": json.loads(ctx.data) if ctx.data else None,
                "method": ctx.method.upper(),
            }
            self._log_request_health_hint()
            if self.debug_http:
                logger.warning(
                    "Loaded cURL: method=%s url=%s headers=%s cookies=%s has_json=%s",
                    self._req["method"],
                    self._req["url"],
                    sorted(_redact_mapping(self._req["headers"]).keys()),
                    sorted(_redact_mapping(self._req["cookies"]).keys()),
                    self._req["json"] is not None,
                )
        except Exception as e:
            logger.critical("Error reading %s: %s", self.curl_path, e)
            self._req = {}

    def _log_request_health_hint(self) -> None:
        headers = {str(k).lower(): str(v) for k, v in self._req.get("headers", {}).items()}
        cookies = {str(k).lower(): str(v) for k, v in self._req.get("cookies", {}).items()}
        warnings: list[str] = []

        if "authorization" not in headers:
            warnings.append("missing authorization header")
        if "x-csrf-token" not in headers:
            warnings.append("missing x-csrf-token header")
        if "auth_token" not in cookies:
            warnings.append("missing auth_token cookie")
        if "ct0" not in cookies:
            warnings.append("missing ct0 cookie")

        if warnings:
            logger.warning("Request auth hints: %s", "; ".join(warnings))

    def _log_request_debug(self, *, url: str, method: str, json_payload: Any) -> None:
        if not self.debug_http:
            return
        logger.warning(
            "HTTP request %s %s\nheaders=%s\ncookies=%s\njson=%s",
            method,
            url,
            _redact_mapping(self._req.get("headers")),
            _redact_mapping(self._req.get("cookies")),
            _preview_json(json_payload),
        )

    def _save_http_error_snapshot(
        self,
        *,
        status: int,
        url: str,
        body: str,
        response_headers: dict[str, str],
        request_payload: Any,
    ) -> Path | None:
        Path("logs").mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = Path("logs") / f"http_error_{status}_{ts}.json"
        payload = {
            "timestamp": dt.datetime.now().isoformat(),
            "status": status,
            "url": url,
            "request": {
                "method": self._req.get("method", "GET"),
                "headers": _redact_mapping(self._req.get("headers")),
                "cookies": _redact_mapping(self._req.get("cookies")),
                "json": request_payload,
            },
            "response": {
                "headers": response_headers,
                "body": body,
            },
        }
        try:
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return out_path
        except Exception as e:
            logger.warning("Could not save HTTP error snapshot: %s", e)
            return None

    def _load_last_id(self) -> None:
        """Load last tweet id from disk (if configured)."""
        if not self.persist_last_id_path:
            return
        try:
            self._last_tweet_id = int(
                self.persist_last_id_path.read_text().strip() or "0"
            )
        except FileNotFoundError:
            self._last_tweet_id = 0
        except Exception as e:
            logger.warning("Could not read last id file: %s", e)

    def _store_last_id(self) -> None:
        """Persist last tweet id to disk (if configured)."""
        if not self.persist_last_id_path:
            return
        try:
            self.persist_last_id_path.parent.mkdir(parents=True, exist_ok=True)
            self.persist_last_id_path.write_text(
                str(self._last_tweet_id), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Could not write last id file: %s", e)

    async def __aenter__(self) -> "XTimelineClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _ensure_session(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_s)
            self._session = aiohttp.ClientSession(
                headers=self._req.get("headers"),
                cookies=self._req.get("cookies"),
                timeout=timeout,
            )

    # ---------- HTTP ----------

    async def fetch_raw(self, *, text: bool = False) -> dict | str:
        """
        Perform a single GET call using the cURL details.

        Parameters
        ----------
        text : bool
            If True, return raw text; else parse JSON.

        Returns
        -------
        dict | str
            Parsed JSON (dict) or raw text.
        """
        if not self._req:
            logger.critical("No cURL loaded. Aborting fetch.")
            return "" if text else {}

        await self._ensure_session()
        assert self._session is not None
        url = self._req["url"]
        method = self._req.get("method", "GET")
        json_payload = self._req.get("json")
        self._log_request_health_hint()
        self._log_request_debug(url=url, method=method, json_payload=json_payload)

        try:
            async with self._session.request(method, url, json=json_payload) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    resp_headers = {k: v for k, v in resp.headers.items()}
                    snapshot = self._save_http_error_snapshot(
                        status=resp.status,
                        url=url,
                        body=body,
                        response_headers=resp_headers,
                        request_payload=json_payload,
                    )
                    logger.error(
                        "HTTP %s for %s\nResponse headers: %s\nResponse: %s\nSnapshot: %s",
                        resp.status,
                        url,
                        resp_headers,
                        body[:2000],
                        snapshot,
                    )
                    return "" if text else {}

                if text:
                    return await resp.text()

                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    raw = await resp.text()
                    logger.error("Non-JSON response from %s\nBody: %s", url, raw[:2000])
                    return {}
                except json.JSONDecodeError as e:
                    raw = await resp.text()
                    logger.error("JSON decode error: %s\nBody: %s", e, raw[:2000])
                    return {}
        except aiohttp.ClientError as e:
            logger.error("Network error for %s: %s", url, e)
        except asyncio.TimeoutError:
            logger.error("Timeout after %ss for %s", self.timeout_s, url)
        return "" if text else {}

    # ---------- extraction ----------

    @staticmethod
    def _get_entries(payload: dict) -> list[dict]:
        """
        Extract raw timeline entries (not yet filtered/normalized).

        Returns
        -------
        list[dict]
            Entries inside TimelineAddEntries.
        """
        instructions = get_in(
            payload, ["data", "home", "home_timeline_urt", "instructions"], []
        )
        if not isinstance(instructions, list):
            return []
        for inst in instructions:
            if inst.get("type") == "TimelineAddEntries":
                entries = inst.get("entries", [])
                return entries if isinstance(entries, list) else []
        return []

    def _iter_entry_tweets(self, entries: list[dict]) -> Iterable[dict]:
        """
        Yield normalized tweet dicts from raw entries, skipping promoted & non-tweet items.
        """
        for entry in entries:
            if not is_tweet_item(entry):
                continue
            if is_promoted_entry(entry):
                continue
            item = entry["content"]["itemContent"]
            twr = item.get("tweet_results", {})
            tw = normalize_tweet_result(twr)
            if not tw:
                continue
            yield tw

    # ---------- parsing ----------

    def _save_errored_tweet(self, tweet: dict, error_msg: str) -> None:
        logger.error(error_msg)
        ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        Path("logs").mkdir(parents=True, exist_ok=True)
        (Path("logs") / f"error_tweet_{ts}.json").write_text(
            json.dumps(tweet, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    def _user_field(self, tweet: dict, key: str) -> str:
        result = (
            tweet.get("core", {})
            .get("user_results", {})
            .get("result", {})
        )
        # New API shape: name/screen_name live in result.core; image in result.avatar
        if key in ("name", "screen_name", "created_at"):
            value = result.get("core", {}).get(key, "")
        elif key == "profile_image_url_https":
            value = result.get("avatar", {}).get("image_url", "")
        else:
            value = result.get("legacy", {}).get(key, "")
        return value

    def _entities(self, tweet: dict, key: str) -> list[str]:
        legacy = tweet.get("legacy", {})
        entities = legacy.get("entities", {}).get(key)
        if not entities:
            return []
        return [
            e.get("text", "") for e in entities if isinstance(e, dict) and "text" in e
        ]

    def _collect_media(self, tweet: dict) -> tuple[list[MediaItem], list[str]]:
        legacy = tweet.get("legacy", {})
        ext = legacy.get("extended_entities", {})
        media_items: list[MediaItem] = []
        media_types: list[str] = []
        if "media" in ext:
            for m in ext["media"]:
                if not isinstance(m, dict):
                    continue
                url = m.get("media_url_https") or m.get("media_url") or ""
                mtype = m.get("type", "")
                if url:
                    media_items.append(MediaItem(url=url, type=mtype))
                    media_types.append(mtype)
        # dedupe by URL
        seen = set()
        uniq_items: list[MediaItem] = []
        uniq_types: list[str] = []
        for mi, mt in zip(media_items, media_types):
            if mi.url in seen:
                continue
            seen.add(mi.url)
            uniq_items.append(mi)
            uniq_types.append(mt)
        return uniq_items, uniq_types

    def _tweet_url(self, tweet_id: int) -> str:
        return f"https://twitter.com/user/status/{tweet_id}"

    def _parse_single_tweet(
        self, tw: dict, *, allow_update_last_id: bool
    ) -> Tweet | None:
        """
        Parse a normalized Tweet GraphQL node into a Tweet object.

        Parameters
        ----------
        tw : dict
            GraphQL 'Tweet' node (already normalized).
        allow_update_last_id : bool
            If True, update last seen id and skip older/equal.

        Returns
        -------
        Tweet | None
            Parsed Tweet or None if filtered/invalid.
        """
        # Prefer legacy.id_str; fallback to rest_id
        try:
            tid = int(tw.get("legacy", {}).get("id_str") or tw.get("rest_id") or 0)
        except Exception:
            tid = 0
        if tid <= 0:
            self._save_errored_tweet(tw, "Missing tweet id")
            return None

        # last-id gate
        if allow_update_last_id:
            if tid <= self._last_tweet_id:
                return None
            self._last_tweet_id = tid
            self._store_last_id()

        # text & entities
        legacy = tw.get("legacy", {})
        text = legacy.get("full_text", "")
        text = unescape_entities(strip_trailing_tco(text))

        tickers = [t.upper() for t in self._entities(tw, "symbols") if t]
        hashtags = [
            h.upper()
            for h in self._entities(tw, "hashtags")
            if h and h.upper() != "CRYPTO"
        ]

        # user info
        user_name = self._user_field(tw, "name")
        user_screen = self._user_field(tw, "screen_name")
        user_img = self._user_field(tw, "profile_image_url_https")
        url = self._tweet_url(tid)

        # media
        media_items, media_types = self._collect_media(tw)

        # reply/quote/retweet handling (best-effort)
        title = f"{user_name} tweeted"
        quoted = tw.get("quoted_status_result") or None
        retweeted = tw.get("legacy", {}).get("retweeted_status_result") or None

        # For replies, X often embeds it differently; handle when present
        # We try to reuse this parser recursively on embedded nodes.
        def _parse_nested(n: dict) -> Tweet | None:
            # n may already be the normalized 'Tweet' or wrapped
            if "result" in n:
                inner = (
                    normalize_tweet_result(n)
                    if "tweet" in n.get("result", {})
                    else n.get("result")
                )
            else:
                inner = normalize_tweet_result({"result": n}) or n
            if not isinstance(inner, dict):
                return None
            # don't update last_id for nested
            return self._parse_single_tweet(inner, allow_update_last_id=False)

        nested: Tweet | None = None
        if quoted:
            nested = _parse_nested(quoted)
            if nested:
                title = f"{user_name} quote tweeted {nested.user_name}"
                q_text = "\n".join("> " + line for line in nested.text.splitlines())
                text = f"{text}\n\n> [@{nested.user_screen_name}](https://twitter.com/{nested.user_screen_name}):\n{q_text}"
                # Merge entities/media
                media_items += nested.media
                media_types += nested.media_types
                tickers = sorted(set(tickers) | set(nested.tickers))
                hashtags = sorted(set(hashtags) | set(nested.hashtags))

        if retweeted:
            nested = _parse_nested(retweeted)
            if nested:
                title = f"{user_name} retweeted {nested.user_name}"
                # Use the full RT text
                text = nested.text
                media_items += nested.media
                media_types += nested.media_types
                tickers = sorted(set(tickers) | set(nested.tickers))
                hashtags = sorted(set(hashtags) | set(nested.hashtags))

        # replies can show up as composite timeline items; handled in entry stage usually
        # If you later surface reply threads, add that here.

        # dedupe media again after merges
        uniq_media: list[MediaItem] = []
        seen_urls = set()
        for m in media_items:
            if m.url and m.url not in seen_urls:
                uniq_media.append(m)
                seen_urls.add(m.url)

        return Tweet(
            id=tid,
            text=text,
            user_name=user_name,
            user_screen_name=user_screen,
            user_img=user_img,
            url=url,
            media=uniq_media,
            tickers=sorted(set(tickers)),
            hashtags=sorted(set(hashtags)),
            title=title,
            media_types=[m.type for m in uniq_media],
        )

    # ---------- public APIs ----------

    async def fetch_tweets(self, *, update_last_id: bool = False) -> list[Tweet]:
        """
        Fetch entries and parse into `Tweet` objects.

        Parameters
        ----------
        update_last_id : bool
            If True, update the client's last-seen tweet id (skip older/equal).

        Returns
        -------
        list[Tweet]
            Parsed tweets (ads removed, deduped).
        """
        payload = await self.fetch_raw(text=False)
        if not isinstance(payload, dict) or not payload:
            return []

        if self.debug_http:
            Path("logs").mkdir(parents=True, exist_ok=True)
            ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            dump_path = Path("logs") / f"raw_payload_{ts}.json"
            dump_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.warning("Raw payload saved to %s", dump_path)

        out: list[Tweet] = []
        seen: set[int] = set()
        for tw in self._iter_entry_tweets(self._get_entries(payload)):
            parsed = self._parse_single_tweet(tw, allow_update_last_id=update_last_id)
            if not parsed:
                continue
            if parsed.id in seen:
                continue
            seen.add(parsed.id)
            out.append(parsed)
        return out

    async def stream(self, interval_s: float = 5.0) -> AsyncIterator[Tweet]:
        """
        Async generator that yields new tweets forever.

        Parameters
        ----------
        interval_s : float
            Polling interval in seconds.

        Yields
        ------
        Tweet
            Each new parsed Tweet.
        """
        while True:
            try:
                for tw in await self.fetch_tweets(update_last_id=True):
                    yield tw
            except Exception as e:
                logger.error("stream() iteration error: %s", e)
            await asyncio.sleep(interval_s)


async def _example_once():
    async with XTimelineClient(
        "curl.txt", persist_last_id_path="state/last_id.txt"
    ) as xc:
        tweets = await xc.fetch_tweets(update_last_id=False)
        for t in tweets:
            print(t)


async def _example_stream():
    async with XTimelineClient(
        "curl.txt", persist_last_id_path="state/last_id.txt"
    ) as xc:
        async for tweet in xc.stream(interval_s=5.0):
            print(tweet.id, tweet.text)


if __name__ == "__main__":
    # asyncio.run(_example_stream())
    # Set os env XCLIENT_DEBUG_HTTP
    # os.environ["XCLIENT_DEBUG_HTTP"] = "1"
    asyncio.run(_example_once())

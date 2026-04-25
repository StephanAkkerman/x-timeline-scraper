# X-Timeline Scraper
A Python client to scrape tweets from X (formerly Twitter) timelines using a cURL command.

<!-- Add a banner here like: https://github.com/StephanAkkerman/fintwit-bot/blob/main/img/logo/fintwit-banner.png -->

---
<!-- Adjust the link of the second badge to your own repo -->
<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-blue.svg" alt="Supported versions">
  <img src="https://img.shields.io/github/license/StephanAkkerman/x-timeline-scraper.svg?color=brightgreen" alt="License">
  <a href="https://github.com/psf/black"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

## Introduction

This project provides a Python client to scrape tweets from X (formerly Twitter) timelines using a cURL command. It leverages asynchronous programming for efficient data retrieval and includes features for parsing tweet data.

## Table of Contents 🗂

- [Installation](#installation)
- [Usage](#usage)
- [Citation](#citation)
- [Contributing](#contributing)
- [License](#license)

## Installation ⚙️
<!-- Adjust the link of the second command to your own repo -->

To install the X-Timeline Scraper, you can use pip:

```bash
pip install xtimeline
```

## Usage ⌨️

To use the X-Timeline Scraper, you need to provide a cURL command that accesses the desired X timeline. The instructions can be found in [curl_example.txt](curl_example.txt). Then, you can use the `XTimelineClient` class to fetch and parse tweets.

### Fetching tweets once

```python
import asyncio
from xclient import XTimelineClient

async def main():
    async with XTimelineClient("curl.txt") as xc:
        tweets = await xc.fetch_tweets()
        for t in tweets:
            print(t.to_markdown())

asyncio.run(main())
```

### Streaming new tweets

```python
import asyncio
from xclient import XTimelineClient

async def main():
    async with XTimelineClient(
        "curl.txt", persist_last_id_path="state/last_id.txt"
    ) as xc:
        async for t in xc.stream():
            print(t.to_markdown())

asyncio.run(main())
```

By default, `stream()` now polls every ~30 seconds with built-in jitter (fuzzy interval) so requests do not follow an identical cadence.

```python
# 30s base with +-20% jitter (default)
async for t in xc.stream():
    process(t)

# Custom base interval and jitter
async for t in xc.stream(interval_s=45.0, jitter_ratio=0.15):
    process(t)

# Disable jitter if you need a fixed cadence
async for t in xc.stream(interval_s=30.0, jitter_ratio=0.0):
    process(t)
```

### Fetch modes

Both `fetch_tweets()` and `stream()` accept a `mode` parameter that controls which tweets are returned:

| Mode | Behaviour |
|---|---|
| `"new_only"` (default) | Only returns tweets newer than the last-seen cursor. The cursor advances so the same tweet is never emitted twice. |
| `"all"` | Returns every tweet in each response. Nothing is filtered. Useful when your own store (e.g. a SQLite database) handles deduplication. |
| `"with_updates"` | Returns new tweets **and** re-emits previously seen tweets whenever their metrics change (likes, retweets, views). Re-emitted tweets have `is_update=True`. |

```python
# Hand all deduplication to your own store
async for t in xc.stream(mode="all"):
    upsert_to_db(t)

# Only new tweets, cursor persisted across restarts
async with XTimelineClient(
    "curl.txt", persist_last_id_path="state/last_id.txt"
) as xc:
    async for t in xc.stream(mode="new_only"):
        process(t)

# New tweets + engagement updates
async for t in xc.stream(mode="with_updates"):
    if t.is_update:
        update_metrics_in_db(t)
    else:
        insert_new_tweet(t)
```

### Tweet fields

Each `Tweet` object contains:

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Tweet ID |
| `text` | `str` | Full text, HTML entities unescaped, t.co links expanded, long-form tweets supported |
| `user_name` | `str` | Display name |
| `user_screen_name` | `str` | @handle (without @) |
| `user_img` | `str` | Profile image URL |
| `url` | `str` | Canonical tweet URL |
| `created_at` | `str` | Post time in ISO 8601 format (`2026-04-01T19:15:49Z`) |
| `likes` | `int` | Like count |
| `retweets` | `int` | Retweet count |
| `replies` | `int` | Reply count |
| `views` | `int` | View count |
| `media` | `list[MediaItem]` | Attached photos/videos |
| `tickers` | `list[str]` | Uppercased `$TICKER` symbols |
| `hashtags` | `list[str]` | Uppercased hashtags |
| `title` | `str` | Human-readable summary, e.g. `"TraderSZ retweeted Jelle"` |
| `is_update` | `bool` | `True` if this tweet was seen in a previous fetch this session |

## Citation ✍️
<!-- Be sure to adjust everything here so it matches your name and repo -->
If you use this project in your research, please cite as follows:

```bibtex
@misc{project_name,
  author  = {Stephan Akkerman},
  title   = {X-Timeline Scraper},
  year    = {2025},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/StephanAkkerman/x-timeline-scraper}}
}
```

## Contributing 🛠
<!-- Be sure to adjust the repo name here for both the URL and GitHub link -->
Contributions are welcome! If you have a feature request, bug report, or proposal for code refactoring, please feel free to open an issue on GitHub. We appreciate your help in improving this project.\
![https://github.com/StephanAkkerman/x-timeline-scraper/graphs/contributors](https://contributors-img.firebaseapp.com/image?repo=StephanAkkerman/x-timeline-scraper)

## License 📜

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

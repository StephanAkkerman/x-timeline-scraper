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

The required packages to run this code can be found in the requirements.txt file. To run this file, execute the following code block after cloning the repository:

```bash
pip install .
```

or

```bash
pip install git+https://github.com/StephanAkkerman/x-timeline-scraper.git
```

## Usage ⌨️

To use the X-Timeline Scraper, you need to provide a cURL command that accesses the desired X timeline. The instructions can be found in [curl_example.txt](curl_example.txt). Then, you can use the `XTimelineClient` class to fetch and parse tweets.

Here's a simple example of how to use the client:

```python
import asyncio
from src.xclient import XTimelineClient

async with XTimelineClient(
        "curl.txt", persist_last_id_path="state/last_id.txt"
    ) as xc:
        tweets = await xc.fetch_tweets(update_last_id=False)
        for t in tweets:
            print(t.to_markdown())
```

You can also stream new tweets in real-time:

```python
import asyncio
from src.xclient import XTimelineClient
async with XTimelineClient(
        "curl.txt", persist_last_id_path="state/last_id.txt"
    ) as xc:
        async for t in xc.stream(interval_s=5.0):
            print(t.to_markdown())
```

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

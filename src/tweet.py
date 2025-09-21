import logging
from dataclasses import asdict, dataclass

logger = logging.getLogger(__file__)


@dataclass(frozen=True, slots=True)
class MediaItem:
    """Single media attachment."""

    url: str
    type: str  # e.g. "photo", "video"


@dataclass(slots=True)
class Tweet:
    """
    Normalized tweet.

    Attributes
    ----------
    id : int
        Tweet rest_id as int.
    text : str
        Full text, HTML entities unescaped and trailing t.co removed.
    user_name : str
        Display name.
    user_screen_name : str
        @handle (without @).
    user_img : str
        Profile image URL.
    url : str
        Canonical tweet URL.
    media : list[MediaItem]
        Unique media attachments.
    tickers : list[str]
        Uppercased $SYMBOLS.
    hashtags : list[str]
        Uppercased hashtags (CRYPTO excluded).
    title : str
        A short human-readable title (“X retweeted Y”, etc.).
    media_types : list[str]
        Mirrors the attachment types for convenience.
    """

    id: int
    text: str
    user_name: str
    user_screen_name: str
    user_img: str
    url: str
    media: list[MediaItem]
    tickers: list[str]
    hashtags: list[str]
    title: str
    media_types: list[str]

    def to_dict(self) -> dict:
        """Serialize to a plain dict safe for JSON."""
        d = asdict(self)
        d["media"] = [asdict(m) for m in self.media]
        return d

    def to_markdown(self) -> str:
        """Compact markdown rendering."""
        md = f"**{self.user_name}** ([@{self.user_screen_name}])\n\n{self.text}\n\n{self.url}"
        if self.tickers:
            md += f"\n\n**Tickers:** {', '.join(self.tickers)}"
        if self.hashtags:
            md += f"\n**Hashtags:** {', '.join(self.hashtags)}"
        return md

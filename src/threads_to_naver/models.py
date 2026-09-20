from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Media:
    kind: str
    url: str
    thumbnail_url: str | None = None


@dataclass(frozen=True)
class ThreadPost:
    id: str
    text: str
    timestamp: datetime
    permalink: str
    media_type: str
    is_reply: bool = False
    is_repost: bool = False
    media: tuple[Media, ...] = field(default_factory=tuple)

    @property
    def title(self) -> str:
        """Return a mechanical title without rewriting the source text."""
        first_nonempty = next(
            (line.strip() for line in self.text.splitlines() if line.strip()), ""
        )
        if first_nonempty:
            return first_nonempty[:100]
        return f"Threads {self.timestamp:%Y-%m-%d %H:%M} ({self.id})"

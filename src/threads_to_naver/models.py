from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo

DATED_SERIES_TITLE = "직접 쓰는 AI교양"


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
    title_override: str | None = None
    source_name: str = "Threads"

    @property
    def source_title(self) -> str:
        if self.title_override is not None:
            return self.title_override.strip()
        return next(
            (line.strip() for line in self.text.splitlines() if line.strip()), ""
        )

    def title_for_timezone(self, timezone: tzinfo) -> str:
        """Return a mechanical title without rewriting the source text."""
        first_nonempty = self.source_title
        if first_nonempty:
            if first_nonempty == DATED_SERIES_TITLE:
                local_date = self.timestamp.astimezone(timezone)
                return f"{first_nonempty} – {local_date:%Y.%m.%d}"
            return first_nonempty[:100]
        return f"{self.source_name} {self.timestamp:%Y-%m-%d %H:%M} ({self.id})"

    @property
    def title(self) -> str:
        timezone = self.timestamp.tzinfo
        if timezone is None:
            raise ValueError("ThreadPost.timestamp must include a timezone.")
        return self.title_for_timezone(timezone)

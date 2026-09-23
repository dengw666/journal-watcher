from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class PaperCandidate:
    title: str
    url: str
    journal: str
    publisher: str
    source_type: str
    discovered_at: datetime
    doi: Optional[str] = None
    authors: Optional[list[str]] = None
    abstract: Optional[str] = None
    article_type: Optional[str] = None
    published_online: Optional[datetime] = None
    issn: Optional[str] = None
    keywords_matched: list[str] = field(default_factory=list)
    raw_tags: Optional[list[str]] = None
    parser_name: str = ""

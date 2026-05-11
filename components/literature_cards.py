# components/literature_cards.py
# ──────────────────────────────────────────────────────────────
# PaperCard dataclass — typed literature result for Web UI rendering
# PROJ-145 (Dilraj Singh)
# ──────────────────────────────────────────────────────────────

from dataclasses import dataclass, field


@dataclass
class PaperCard:
    """Typed representation of a single academic paper result."""
    title:     str
    authors:   str       = ""
    year:      str       = ""
    abstract:  str       = ""
    citations: int       = 0
    url:       str       = ""
    source:    str       = "arxiv"
    doi:       str       = ""
    keywords:  list      = field(default_factory=list)

    def truncate_abstract(self, max_chars: int = 300) -> str:
        if len(self.abstract) <= max_chars:
            return self.abstract
        return self.abstract[:max_chars].rstrip() + "..."

    def to_dict(self) -> dict:
        return {
            "title":     self.title,
            "authors":   self.authors,
            "year":      self.year,
            "abstract":  self.truncate_abstract(),
            "citations": self.citations,
            "url":       self.url,
            "source":    self.source,
            "doi":       self.doi,
        }

    def to_html_card(self) -> str:
        url_attr   = f'href="{self.url}"' if self.url else 'href="#"'
        source_tag = self.source.replace("_", " ").upper()
        abstract   = self.truncate_abstract(280)
        citation_badge = (
            f'<span class="card-citations" data-citations="{self.citations}">'
            f'📚 {self.citations:,} citations</span>'
            if self.citations else ""
        )
        return f"""<div class="card paper-card" data-citations="{self.citations}">
  <div class="card-source-tag">{source_tag}</div>
  <div class="card-body">
    <a {url_attr} target="_blank" class="card-title">{self.title}</a>
    <div class="card-meta">
      <span class="card-authors">{self.authors}</span>
      {f'<span class="card-year">({self.year})</span>' if self.year else ""}
      {citation_badge}
    </div>
    <p class="card-abstract">{abstract}</p>
  </div>
</div>"""

    @classmethod
    def from_skill_result(cls, raw: dict) -> "PaperCard":
        title     = raw.get("title", "Untitled Paper")
        authors   = raw.get("authors", raw.get("author", ""))
        year      = str(raw.get("year", raw.get("published", "")) or "")
        abstract  = raw.get("abstract", raw.get("summary", ""))
        citations = int(raw.get("citations", raw.get("citation_count", 0)) or 0)
        url       = raw.get("url", raw.get("link", raw.get("arxiv_url", "")))
        doi       = raw.get("doi", "")
        if "arxiv" in url.lower():
            source = "arxiv"
        elif "semanticscholar" in url.lower() or raw.get("source") == "semantic_scholar":
            source = "semantic_scholar"
        elif "pubmed" in url.lower() or raw.get("source") == "pubmed":
            source = "pubmed"
        else:
            source = raw.get("source", "arxiv")
        return cls(title=title, authors=authors, year=year[:4] if len(year) >= 4 else year,
                   abstract=abstract, citations=citations, url=url, source=source, doi=doi)

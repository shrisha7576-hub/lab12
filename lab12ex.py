"""
ISOM3400 Business Applications Development in Python
Individual Assignment: Wikipedia Article Extractor (logic layer)
Filename: wikipedia_extractor_core.py

Pure logic for the Streamlit web app. This module contains NO calls to
input() or print(). The UI layer is responsible for all user interaction
and for delivering the report (e.g. via st.download_button).

Requires:  requests, beautifulsoup4
"""

import re
import textwrap
from datetime import datetime
from urllib.parse import quote, unquote

import requests
from bs4 import BeautifulSoup, Tag


# ============================================================================
# Custom Exceptions
# ============================================================================
class WikipediaError(Exception):
    """Base exception for Wikipedia extractor errors."""


class ArticleNotFoundError(WikipediaError):
    """Raised when no matching Wikipedia article is found."""


class DisambiguationError(WikipediaError):
    """Raised when a topic matches a disambiguation page."""

    def __init__(self, message, suggestions=None):
        super().__init__(message)
        self.suggestions = suggestions or []


class FetchError(WikipediaError):
    """Raised on network or HTTP errors."""


class ParseError(WikipediaError):
    """Raised when article HTML cannot be parsed as expected."""


# ============================================================================
# WikipediaExtractor Class
# ============================================================================
class WikipediaExtractor:
    """Fetches, parses, and formats sections from an English Wikipedia article."""

    BASE_URL = "https://en.wikipedia.org/wiki/"
    SEARCH_URL = "https://en.wikipedia.org/wiki/Special:Search"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 ISOM3400Assignment/1.0"
        )
    }
    TIMEOUT = 10
    WRAP_WIDTH = 88

    IGNORED_TITLES = {
        "contents", "see also", "references", "external links",
        "further reading", "notes", "notes and references", "footnotes",
        "navigation menu", "bibliography", "sources", "citations",
    }

    JUNK_SELECTORS = [
        "sup.reference", "sup.noprint", "span.mw-editsection", "style", "script",
        "figure", "div.thumb", "div.navbox", "div.hatnote", "div.reflist",
        "div.refbegin", "div.toc", "div#toc", "div.sidebar",
        "div.shortdescription", "div.metadata", "span.noprint", "div.gallery",
        "div.mw-references-wrap", "ol.references", "span[style*='display:none']",
    ]

    def __init__(self, topic: str):
        self.error = None  # Last error message (str) set by fetch_and_parse, else None
        self.topic = topic.strip()
        self.url = ""
        self.soup = None
        self.article_title = ""
        self.sections = []  # List of dicts: {"id": int, "title": str, "lines": list[str]}

    def _get(self, url, params=None):
        """Perform an HTTP GET and translate request errors into FetchError."""
        try:
            return requests.get(
                url,
                params=params,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
        except requests.exceptions.Timeout:
            raise FetchError("Request timed out while connecting to Wikipedia.")
        except requests.exceptions.ConnectionError:
            raise FetchError("Network connection error. Please check your internet connection.")
        except requests.exceptions.RequestException as exc:
            raise FetchError(f"Network error: {exc}") from exc

    def _download(self):
        """Download the Wikipedia article, falling back to Go search for casing/redirects."""
        slug = quote(self.topic.replace(" ", "_"))
        response = self._get(self.BASE_URL + slug)

        if response.status_code == 404:
            response = self._get(
                self.SEARCH_URL,
                params={"search": self.topic, "go": "Go"},
            )
            if "Special:Search" in unquote(response.url):
                raise ArticleNotFoundError(
                    f"Article not found for '{self.topic}'. Please check spelling or try another topic."
                )

        if response.status_code == 429:
            raise FetchError("Wikipedia rate limit reached (HTTP 429). Please wait and try again.")

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise FetchError(f"Wikipedia returned HTTP status {response.status_code}.") from exc

        return response

    def fetch_and_parse(self):
        """
        Fetch the article HTML and parse top-level sections.

        On failure the message is stored in self.error and the original
        WikipediaError subclass is re-raised so the UI can choose how to react.
        """
        self.error = None
        try:
            self._fetch_and_parse()
        except WikipediaError as exc:
            self.error = str(exc)
            raise

    def _fetch_and_parse(self):
        response = self._download()
        response.encoding = "utf-8"
        self.url = response.url

        self.soup = BeautifulSoup(response.text, "html.parser")
        heading = self.soup.find("h1", id="firstHeading")
        self.article_title = (
            heading.get_text(strip=True) if heading else self.topic.title()
        )

        if self.soup.find("div", id="mw-content-text") is None:
            raise ParseError("Could not locate main article content on the page.")

        self._check_disambiguation()

        try:
            self._parse_sections()
        except Exception as exc:
            raise ParseError(f"Failed to parse article structure ({exc}).") from exc

        if not self.sections:
            raise ParseError("No readable sections found on this article.")

    def _check_disambiguation(self):
        """Raise DisambiguationError if the page is a disambiguation page."""
        is_disambig = self.soup.select_one("#disambigbox, .dmbox-disambig") is not None
        if not is_disambig:
            catlinks = self.soup.find("div", id="mw-normal-catlinks")
            if catlinks is not None:
                is_disambig = any(
                    a.get_text(strip=True).lower().endswith("disambiguation pages")
                    for a in catlinks.find_all("a")
                )
        if is_disambig:
            raise DisambiguationError(
                f"'{self.topic}' is a disambiguation page with multiple possible articles.",
                self._disambiguation_suggestions(),
            )

    def _disambiguation_suggestions(self, limit=6):
        """Return up to `limit` suggested article titles from a disambiguation page."""
        suggestions = []
        content = self.soup.find("div", id="mw-content-text")
        if content is None:
            return suggestions
        for li in content.find_all("li"):
            link = li.find("a", href=True)
            title = link.get("title", "").strip() if link else ""
            if title and ":" not in title and title not in suggestions:
                suggestions.append(title)
            if len(suggestions) >= limit:
                break
        return suggestions

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove citation markers like [1] or [citation needed] and normalize spacing."""
        cleaned = re.sub(
            r"\[\s*(\d+\vert{}citation needed\vert{}note \d+\vert{}[a-z])\s*\]",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _heading_level(node):
        """Return heading level 2..6 for h2-h6 or mw-heading wrappers, else None."""
        if not isinstance(node, Tag):
            return None
        if re.fullmatch(r"h[2-6]", node.name or ""):
            return int(node.name[1])
        if node.name == "div" and "mw-heading" in node.get("class", []):
            inner = node.find(re.compile(r"^h[2-6]$"))
            if inner:
                return int(inner.name[1])
        return None

    @staticmethod
    def _heading_text(node) -> str:
        """Extract clean heading text without edit links."""
        heading = node if re.fullmatch(r"h[2-6]", node.name or "") else node.find(re.compile(r"^h[2-6]$"))
        for edit_span in heading.select("span.mw-editsection"):
            edit_span.decompose()
        return WikipediaExtractor._clean_text(heading.get_text())

    def _list_to_lines(self, list_node, depth=0) -> list:
        """Convert <ul> or <ol> elements (including nested lists) into wrapped lines."""
        lines = []
        is_ordered = list_node.name == "ol"
        indent = "    " * depth
        for idx, li in enumerate(list_node.find_all("li", recursive=False), start=1):
            parts = []
            for child in li.children:
                if isinstance(child, Tag) and child.name in ("ul", "ol"):
                    continue
                parts.append(child.get_text() if isinstance(child, Tag) else str(child))
            item_text = self._clean_text("".join(parts))
            bullet = f"{idx}." if is_ordered else "-"
            if item_text:
                lines.append(
                    textwrap.fill(
                        f"{bullet} {item_text}",
                        self.WRAP_WIDTH,
                        initial_indent=indent + "  ",
                        subsequent_indent=indent + "    ",
                    )
                )
            for sub_list in li.find_all(["ul", "ol"], recursive=False):
                lines.extend(self._list_to_lines(sub_list, depth + 1))
        return lines

    def _table_to_lines(self, table) -> list:
        """Convert a data table into readable ' | ' separated rows."""
        rows = []
        for tr in table.find_all("tr"):
            if tr.find_parent("table") is not table:
                continue
            cells = [
                self._clean_text(cell.get_text())
                for cell in tr.find_all(["th", "td"], recursive=False)
            ]
            if any(cells):
                rows.append(" | ".join(cells))
        if not rows:
            return []
        caption = table.find("caption")
        caption_text = self._clean_text(caption.get_text()) if caption else ""
        label = f"[Table: {caption_text}]" if caption_text else "[Table]"
        return [label] + rows

    def _walk(self, parent):
        """Yield headings and content blocks in document order."""
        for node in parent.children:
            if not isinstance(node, Tag):
                continue
            if self._heading_level(node) is not None:
                yield node
            elif node.name in ("p", "ul", "ol", "dl", "blockquote"):
                yield node
            elif node.name == "table" and "wikitable" in node.get("class", []):
                yield node
            elif node.name in ("div", "section", "article", "main"):
                yield from self._walk(node)

    def _add_section(self, title: str, lines: list, collecting: bool):
        """Append a non-ignored, non-empty section to self.sections."""
        if collecting and any(line.strip() for line in lines):
            self.sections.append(

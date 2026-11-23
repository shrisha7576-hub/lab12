"""
ISOM3400 Business Applications Development in Python
Lab 12: Wikipedia Article Extractor - Logic Layer (wikipedia_extractor_core.py)

Pure logic with NO calls to input() or print() and NO disk writes.
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
            r"\[\s*(\d+|citation needed|note \d+|[a-z])\s*\]",
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
                {
                    "id": len(self.sections) + 1,
                    "title": title,
                    "lines": lines,
                }
            )

    def _parse_sections(self):
        """Parse top-level sections starting with 'About' (lead) and each H2 heading."""
        self.sections = []

        candidates = self.soup.find_all("div", class_="mw-parser-output")
        content = (
            max(candidates, key=lambda div: len(div.find_all("p")))
            if candidates
            else (self.soup.find("div", id="mw-content-text") or self.soup)
        )

        for selector in self.JUNK_SELECTORS:
            for el in content.select(selector):
                el.decompose()
        for br in content.find_all("br"):
            br.replace_with(" ")

        current_title = "About"
        current_lines = []
        collecting = True

        for node in self._walk(content):
            level = self._heading_level(node)
            if level == 2:
                self._add_section(current_title, current_lines, collecting)
                current_title = self._heading_text(node)
                current_lines = []
                collecting = current_title.lower() not in self.IGNORED_TITLES
                continue

            if level is not None:
                if collecting:
                    sub_title = self._heading_text(node)
                    current_lines.extend(["", f"  [{sub_title}]", ""])
                continue

            if not collecting:
                continue

            if node.name == "p":
                text = self._clean_text(node.get_text())
                if text:
                    current_lines.extend([textwrap.fill(text, self.WRAP_WIDTH), ""])
            elif node.name in ("ul", "ol"):
                current_lines.extend(self._list_to_lines(node))
                current_lines.append("")
            elif node.name == "table":
                table_lines = self._table_to_lines(node)
                if table_lines:
                    current_lines.extend(table_lines)
                    current_lines.append("")
            elif node.name in ("dl", "blockquote"):
                text = self._clean_text(node.get_text())
                if text:
                    current_lines.extend([textwrap.fill(text, self.WRAP_WIDTH), ""])

        self._add_section(current_title, current_lines, collecting)

    def format_selected_sections(self, indices: list) -> str:
        """Format chosen 1-based section indices into a clean report body."""
        blocks = []
        for idx in indices:
            sec = self.sections[idx - 1]
            heading_line = f"{idx}. {sec['title']}"
            underline = "-" * len(heading_line)
            body = "\n".join(sec["lines"]).strip()
            body = re.sub(r"\n{3,}", "\n\n", body)
            blocks.append(f"{heading_line}\n{underline}\n\n{body}\n")
        return "\n".join(blocks).strip() + "\n"


# ============================================================================
# Pure Helpers (no I/O, no printing)
# ============================================================================
def validate_topic(topic: str):
    """Return an error string if topic is invalid, else None."""
    if not topic:
        return "Topic cannot be empty. Please enter a Wikipedia topic."
    if len(topic) > 200:
        return "Topic is too long (maximum 200 characters)."
    if re.search(r"[<>\[\]{}|#]", topic):
        return "Topic contains invalid characters (< > [ ] { } | #). Please try again."
    return None


def safe_filename(article_title: str) -> str:
    """
    Naming convention: <Article_Title>_extracted.txt, with spaces replaced by
    underscores and filesystem-unsafe characters removed. Returns a bare
    file name (no folder), suitable for st.download_button's file_name.
    """
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", article_title)
    safe_title = re.sub(r"\s+", "_", safe_title).strip("._ ")
    safe_title = safe_title[:80] or "wikipedia_article"
    return f"{safe_title}_extracted.txt"


def numbered_filename(filename: str, existing_names: list) -> str:
    """Return a non-colliding filename using (2), (3), ... against existing_names."""
    existing = set(existing_names)
    if filename not in existing:
        return filename
    stem, ext = (filename.rsplit(".", 1) + [""])[:2]
    suffix = f".{ext}" if ext else ""
    counter = 2
    while True:
        candidate = f"{stem} ({counter}){suffix}"
        if candidate not in existing:
            return candidate
        counter += 1


def build_report_text(article_title: str, source_url: str, body: str) -> str:
    """Return the full report (header + body + end marker) as a string."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    border = "=" * 64
    header = (
        f"{border}\n"
        f"{article_title}\n"
        f"{border}\n"
        f"Source    : {source_url}\n"
        f"Extracted : {timestamp}\n"
        f"License   : Content from Wikipedia, CC BY-SA 4.0\n"
        f"            https://creativecommons.org/licenses/by-sa/4.0/\n"
        f"{border}\n\n"
    )
    footer = f"\n{border}\nEND OF DOCUMENT\n{border}\n"
    return header + body + footer


def format_txt(article_title: str, article_url: str, sections: list) -> str:
    """Format extracted section dicts into the complete report string in memory."""
    blocks = []
    for sec in sections:
        idx = sec.get("id", len(blocks) + 1)
        heading_line = f"{idx}. {sec['title']}"
        underline = "-" * len(heading_line)
        body = "\n".join(sec.get("lines", [])).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        blocks.append(f"{heading_line}\n{underline}\n\n{body}\n")
    formatted_body = "\n".join(blocks).strip() + "\n" if blocks else ""
    return build_report_text(article_title, article_url, formatted_body)

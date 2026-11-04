#!/usr/bin/env python3
"""Shared paper discovery / digest / note pipeline for lark-bot.

This module is intentionally backend-agnostic: codex, omp and Claude instances
all import it from ``bridge.py``.  Runtime data lives in a *shared* directory
(``PAPER_HOME``, default ``~/.agents/papers``) so multiple bots do not push the
same paper twice and can reuse downloaded full texts.

Layout::

    $PAPER_HOME/papers.db          shared SQLite store
    $PAPER_HOME/topics.json        interests shared by all instances
    $PAPER_HOME/library/<id>/      metadata + pdf + fulltext
    $PAPER_HOME/digests/           candidate packs / digest drafts
    $PAPER_HOME/notes/             deep-reading notes before Feishu upload

Only the Python standard library is used.  PDF text extraction degrades to
``pdftotext`` / PyMuPDF / pypdf when available, then to arXiv HTML, then to the
abstract.  The agent is always told which coverage level it got.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - very old Python
    ZoneInfo = None  # type: ignore[assignment]

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_ABS = "https://arxiv.org/abs/{id}"
ARXIV_PDF = "https://arxiv.org/pdf/{id}"
ARXIV_HTML = "https://arxiv.org/html/{id}"
ARXIV_LIST = "https://arxiv.org/list/{category}/new"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
USER_AGENT = "lark-bot-paper/1.0 (+https://arxiv.org/help/api)"
MAX_FULLTEXT_CHARS = 250_000
MAX_PDF_BYTES = 40 * 1024 * 1024

DEFAULT_TOPICS: dict[str, Any] = {
    "categories": ["cs.RO", "cs.CV", "cs.AI", "cs.LG"],
    "keywords": [
        "robot", "robotics", "embodied", "manipulation", "navigation",
        "vision-language-action", "vla", "world model", "sim2real",
        "reinforcement learning", "policy learning", "locomotion",
        "mobile robot", "slam", "imitation learning",
    ],
    "negative_keywords": ["survey", "review", "position paper"],
    "category_limit": 3,
    "max_results_per_category": 50,
}

VENUE_RE = re.compile(
    r"\b(cvpr|iccv|eccv|neurips|nips|iclr|icml|corl|rss|icra|iros|aaai|ijcai|"
    r"acl|emnlp|naacl|siggraph|tmlr|tpami|tro|ijrr|jmlr|colt)\b",
    re.I,
)
HONOR_RE = re.compile(r"\b(oral|spotlight|best paper|award|highlight)\b", re.I)
CODE_RE = re.compile(
    r"(github\.com|gitlab\.com|huggingface\.co|code (?:is )?available|"
    r"project page|open[- ]source)",
    re.I,
)
CODEX_PAPER_HINT = re.compile(
    r"论文|paper|arxiv|精读|细读|综述|survey|benchmark|gap|研究空白|文献|复现",
    re.I,
)

ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?",
    re.I,
)
ARXIV_LEGACY_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html)/([a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?",
    re.I,
)
ARXIV_BARE_RE = re.compile(r"\b([0-9]{4}\.[0-9]{4,5})(v\d+)?\b")
NOTE_PATH_RE = re.compile(r"^\s*(?:NOTE_PATH|DIGEST_PATH)\s*=\s*(.+?)\s*$", re.M)
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")

# HTML fallbacks (used when the arXiv API is rate limited or unavailable).
LIST_ENTRY_RE = re.compile(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S | re.I)
SUBJECT_CODE_RE = re.compile(r"\(([a-z\-]+(?:\.[A-Za-z]{2,4})?)\)")


def _div_text(raw: str, class_name: str) -> str:
    """Return the cleaned text of the first ``div`` carrying ``class_name``."""
    match = re.search(
        r"<div[^>]*class=['\"][^'\"]*" + re.escape(class_name) + r"[^'\"]*['\"][^>]*>(.*?)</div>",
        raw,
        re.S | re.I,
    )
    if not match:
        return ""
    text = _strip_html(match.group(1))
    return re.sub(
        r"^(?:Title|Authors|Comments|Subjects|Journal reference):\s*",
        "",
        text,
        flags=re.I,
    )


def _subject_codes(text: str) -> list[str]:
    seen: list[str] = []
    for code in SUBJECT_CODE_RE.findall(text or ""):
        code = code.strip()
        if code and code not in seen:
            seen.append(code)
    return seen


class _MetaParser(HTMLParser):
    """Collect ``<meta name=... content=...>`` pairs and the page title."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            data = {key.lower(): (value or "") for key, value in attrs}
            name = (data.get("name") or "").lower()
            if name and data.get("content"):
                self.meta.setdefault(name, []).append(data["content"])
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)

    def first(self, name: str) -> str:
        values = self.meta.get(name) or [""]
        return _clean(values[0])


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clip(value: str, limit: int) -> str:
    value = _clean(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_time(value: str) -> datetime | None:
    value = _clean(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|nav|header|footer)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    text = html_lib.unescape(raw)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# arXiv client
# ---------------------------------------------------------------------------

class ArxivFetcher:
    def __init__(self, timeout: int = 25, delay: float = 3.0):
        self.timeout = max(5, int(timeout))
        self.delay = max(0.0, float(delay))
        self._lock = threading.Lock()
        self._last_call = 0.0

    def _request(self, url: str, timeout: int | None = None,
                 retries: int = 4) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        retries = max(1, int(retries))
        with self._lock:
            wait = self.delay - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                for attempt in range(retries):
                    try:
                        with urllib.request.urlopen(
                            req, timeout=timeout or self.timeout
                        ) as resp:
                            return resp.read()
                    except urllib.error.HTTPError as exc:
                        if exc.code not in (429, 500, 502, 503, 504) or attempt >= retries - 1:
                            raise
                        backoff = (5, 15, 30)[min(attempt, 2)]
                        logging.warning("arXiv API HTTP %s，%ss 后重试", exc.code, backoff)
                        time.sleep(backoff)
                raise RuntimeError("arXiv 请求重试失败")
            finally:
                self._last_call = time.monotonic()

    def _entries(self, query: str, max_results: int,
                 retries: int = 4) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({
            "search_query": query,
            "start": 0,
            "max_results": max(1, min(200, int(max_results))),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        raw = self._request(f"{ARXIV_API}?{params}", retries=retries)
        root = ET.fromstring(raw)
        papers: list[dict[str, Any]] = []
        for entry in root.findall(f"{ATOM_NS}entry"):
            paper = self._parse_entry(entry)
            if paper:
                papers.append(paper)
        return papers

    @staticmethod
    def _parse_entry(entry: ET.Element) -> dict[str, Any] | None:
        raw_id = _clean(entry.findtext(f"{ATOM_NS}id", default=""))
        arxiv_id = ""
        match = re.search(r"/abs/(.+?)(?:v\d+)?$", raw_id)
        if match:
            arxiv_id = re.sub(r"v\d+$", "", match.group(1))
        if not arxiv_id:
            return None
        title = _clean(entry.findtext(f"{ATOM_NS}title", default=""))
        if not title or title.lower() == "error":
            return None
        authors = [
            _clean(node.findtext(f"{ATOM_NS}name", default=""))
            for node in entry.findall(f"{ATOM_NS}author")
        ]
        categories = [
            _clean(node.get("term", ""))
            for node in entry.findall(f"{ATOM_NS}category")
            if node.get("term")
        ]
        links = {str(node.get("title") or node.get("rel") or ""): node.get("href", "")
                 for node in entry.findall(f"{ATOM_NS}link")}
        return {
            "id": arxiv_id,
            "title": title,
            "abstract": _clean(entry.findtext(f"{ATOM_NS}summary", default="")),
            "authors": [a for a in authors if a],
            "categories": categories,
            "published": _clean(entry.findtext(f"{ATOM_NS}published", default="")),
            "updated": _clean(entry.findtext(f"{ATOM_NS}updated", default="")),
            "comment": _clean(entry.findtext(f"{ARXIV_NS}comment", default="")),
            "journal_ref": _clean(entry.findtext(f"{ARXIV_NS}journal_ref", default="")),
            "url": ARXIV_ABS.format(id=arxiv_id),
            "pdf_url": links.get("pdf") or ARXIV_PDF.format(id=arxiv_id),
            "html_url": ARXIV_HTML.format(id=arxiv_id),
        }

    def fetch_category(self, category: str, max_results: int) -> list[dict[str, Any]]:
        try:
            papers = self._entries(f"cat:{category}", max_results, retries=2)
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                "arXiv API 分类 %s 获取失败（%s），改用列表页", category, exc
            )
            papers = []
        if not papers:
            papers = self.fetch_category_html(category, max_results)
        return papers

    def fetch_category_html(self, category: str,
                            max_results: int) -> list[dict[str, Any]]:
        """Fallback: parse ``/list/<category>/new`` (no API quota needed).

        The listing page carries title, authors, comments, subjects and the
        full abstract, so the digest pipeline keeps working when the export
        API answers 429/5xx.
        """
        try:
            raw = self._request(
                ARXIV_LIST.format(category=category), timeout=self.timeout
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning("arXiv 列表页 %s 获取失败: %s", category, exc)
            return []
        text = raw.decode("utf-8", "ignore")
        start = text.find("<dl id='articles'>")
        if start < 0:
            start = text.find('<dl id="articles">')
        if start >= 0:
            end = text.find("</dl>", start)
            if end > 0:
                text = text[start:end]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        papers: list[dict[str, Any]] = []
        for head, body in LIST_ENTRY_RE.findall(text):
            match = re.search(r"href\s*=\s*[\"']/abs/([^\"']+)", head, re.I)
            if not match:
                continue
            arxiv_id = re.sub(r"v\d+$", "", html_lib.unescape(match.group(1)))
            title = _div_text(body, "list-title")
            if not title:
                continue
            abstract = ""
            paragraph = re.search(
                r"<p[^>]*class=['\"][^'\"]*mathjax[^'\"]*['\"][^>]*>(.*?)</p>",
                body,
                re.S | re.I,
            )
            if paragraph:
                abstract = _strip_html(paragraph.group(1))
            authors_text = _div_text(body, "list-authors")
            authors = [a.strip() for a in re.split(r",\s*", authors_text) if a.strip()]
            comment = _div_text(body, "list-comments")
            journal_ref = _div_text(body, "list-journal-ref")
            categories = _subject_codes(_div_text(body, "list-subjects"))
            if not categories:
                categories = [category]
            papers.append({
                "id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "published": now,
                "updated": now,
                "comment": comment,
                "journal_ref": journal_ref,
                "url": ARXIV_ABS.format(id=arxiv_id),
                "pdf_url": ARXIV_PDF.format(id=arxiv_id),
                "html_url": ARXIV_HTML.format(id=arxiv_id),
            })
            if len(papers) >= max(1, int(max_results)):
                break
        return papers

    def fetch_by_ids(self, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        wanted = [
            re.sub(r"v\d+$", "", x)
            for x in dict.fromkeys(_clean(i) for i in ids)
            if x
        ]
        if not wanted:
            return {}
        result: dict[str, dict[str, Any]] = {}
        params = urllib.parse.urlencode({
            "id_list": ",".join(wanted),
            "max_results": len(wanted),
        })
        try:
            raw = self._request(f"{ARXIV_API}?{params}")
            root = ET.fromstring(raw)
            for entry in root.findall(f"{ATOM_NS}entry"):
                paper = self._parse_entry(entry)
                if paper:
                    result[paper["id"]] = paper
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                "arXiv API 元数据获取失败（%s），改用 abs 页面", exc
            )
        missing = [x for x in wanted if x not in result or not result[x].get("title")]
        # Bound the fallback burst; metadata is only needed for a handful of
        # papers per message/digest anyway.
        for arxiv_id in missing[:20]:
            paper = self.fetch_abs_metadata(arxiv_id)
            if not paper:
                continue
            result[paper["id"]] = paper
            result.setdefault(arxiv_id, paper)
        return result

    def fetch_abs_metadata(self, arxiv_id: str) -> dict[str, Any] | None:
        """Fallback metadata from an abstract page's citation_* meta tags."""
        try:
            raw = self._request(ARXIV_ABS.format(id=arxiv_id), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            logging.debug("arXiv abs 页面获取失败 %s: %s", arxiv_id, exc)
            return None
        text = raw.decode("utf-8", "ignore")
        parser = _MetaParser()
        try:
            parser.feed(text)
        except Exception:  # noqa: BLE001 - malformed page should not crash
            pass
        title = parser.first("citation_title") or _clean(" ".join(parser.title_parts))
        title = re.sub(r"\s*[|\-]\s*arXiv.*$", "", title, flags=re.I)
        if not title or re.search(r"not found|page not found", title, re.I):
            return None
        abstract = parser.first("citation_abstract")
        if not abstract:
            block = re.search(
                r"<blockquote[^>]*class=['\"][^'\"]*abstract[^'\"]*['\"][^>]*>(.*?)</blockquote>",
                text,
                re.S | re.I,
            )
            if block:
                abstract = re.sub(
                    r"^Abstract:\s*", "", _strip_html(block.group(1)), flags=re.I
                )
        authors = [
            _clean(value) for value in parser.meta.get("citation_author", [])
            if _clean(value)
        ]
        published = ""
        date = parser.first("citation_date") or parser.first("citation_online_date")
        if date:
            for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
                try:
                    published = datetime.strptime(date, fmt).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                    break
                except ValueError:
                    continue
        subjects_match = re.search(
            r"class=['\"][^'\"]*subjects[^'\"]*['\"][^>]*>(.*?)</td>",
            text,
            re.S | re.I,
        )
        categories = _subject_codes(
            _strip_html(subjects_match.group(1)) if subjects_match else ""
        )
        comments_match = re.search(
            r"class=['\"][^'\"]*comments[^'\"]*['\"][^>]*>(.*?)</td>",
            text,
            re.S | re.I,
        )
        comment = (
            _strip_html(comments_match.group(1)) if comments_match else ""
        )
        meta_id = re.sub(r"v\d+$", "", parser.first("citation_arxiv_id") or arxiv_id)
        return {
            "id": meta_id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "categories": categories,
            "published": published,
            "updated": published,
            "comment": comment,
            "journal_ref": "",
            "url": ARXIV_ABS.format(id=meta_id),
            "pdf_url": parser.first("citation_pdf_url")
            or ARXIV_PDF.format(id=meta_id),
            "html_url": ARXIV_HTML.format(id=meta_id),
        }

    def fetch_html_text(self, arxiv_id: str) -> str:
        try:
            raw = self._request(ARXIV_HTML.format(id=arxiv_id), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            logging.debug("arXiv HTML 获取失败 %s: %s", arxiv_id, exc)
            return ""
        text = _strip_html(raw.decode("utf-8", "ignore"))
        if len(text) < 1500 or re.search(r"article not found|page not found", text[:3000], re.I):
            return ""
        return text[:MAX_FULLTEXT_CHARS]

    def download_pdf(self, arxiv_id: str, dest: Path) -> bool:
        try:
            req = urllib.request.Request(
                ARXIV_PDF.format(id=arxiv_id), headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=max(30, self.timeout)) as resp:
                data = resp.read(MAX_PDF_BYTES + 1)
        except Exception as exc:  # noqa: BLE001
            logging.debug("PDF 下载失败 %s: %s", arxiv_id, exc)
            return False
        if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
            return False
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        except OSError as exc:
            logging.warning("PDF 写入失败 %s: %s", dest, exc)
            return False
        return True


def extract_pdf_text(path: Path) -> str:
    """Best-effort PDF text extraction using whatever is installed."""
    tool = shutil.which("pdftotext")
    if tool:
        try:
            proc = subprocess.run(
                [tool, "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=90,
            )
            if proc.returncode == 0 and len(proc.stdout.strip()) > 200:
                return proc.stdout[:MAX_FULLTEXT_CHARS]
        except Exception:  # noqa: BLE001
            logging.debug("pdftotext 失败", exc_info=True)
    try:  # optional PyMuPDF
        import fitz  # type: ignore

        with fitz.open(str(path)) as doc:
            text = "\n".join(page.get_text() for page in doc)
        if len(text.strip()) > 200:
            return text[:MAX_FULLTEXT_CHARS]
    except Exception:  # noqa: BLE001
        pass
    try:  # optional pypdf
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if len(text.strip()) > 200:
            return text[:MAX_FULLTEXT_CHARS]
    except Exception:  # noqa: BLE001
        pass
    return ""


# ---------------------------------------------------------------------------
# Shared SQLite store
# ---------------------------------------------------------------------------

class PaperStore:
    def __init__(self, home: Path):
        self.home = home
        self.home.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(home / "papers.db"), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init()

    def _init(self) -> None:
        with self.lock, self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    arxiv_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL DEFAULT '[]',
                    abstract TEXT NOT NULL DEFAULT '',
                    categories TEXT NOT NULL DEFAULT '[]',
                    published TEXT NOT NULL DEFAULT '',
                    updated TEXT NOT NULL DEFAULT '',
                    comment TEXT NOT NULL DEFAULT '',
                    journal_ref TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    pdf_url TEXT NOT NULL DEFAULT '',
                    html_url TEXT NOT NULL DEFAULT '',
                    score REAL NOT NULL DEFAULT 0,
                    signals TEXT NOT NULL DEFAULT '[]',
                    fetched_at INTEGER NOT NULL,
                    pushed_at INTEGER,
                    digest_date TEXT
                );
                CREATE TABLE IF NOT EXISTS digest_runs (
                    date TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    instance TEXT NOT NULL DEFAULT '',
                    claimed_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    message TEXT NOT NULL DEFAULT '',
                    paper_ids TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    path TEXT PRIMARY KEY,
                    kind TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    doc_token TEXT NOT NULL DEFAULT '',
                    doc_url TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_todo (
                    source TEXT PRIMARY KEY,
                    note TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
        self.add_todo(
            "semantic_scholar",
            "TODO: 需要 S2 API key；未配置时直接调用会返回 429。"
            "配置 PAPER_S2_API_KEY 后启用引用数/会议等质量信号。",
        )
        self.add_todo(
            "huggingface",
            "TODO: 本机直连 huggingface.co 被拒；需代理或镜像。"
            "配置 PAPER_HF_ENABLED=1 与代理后启用 HF Daily Papers 源。",
        )

    @staticmethod
    def _row_to_paper(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        paper = dict(row)
        for key in ("authors", "categories", "signals"):
            try:
                paper[key] = json.loads(paper.get(key) or "[]")
            except ValueError:
                paper[key] = []
        return paper

    def upsert_paper(self, paper: dict[str, Any], score: float = 0.0,
                     signals: list[str] | None = None) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO papers(arxiv_id, title, authors, abstract, categories,
                                   published, updated, comment, journal_ref, url,
                                   pdf_url, html_url, score, signals, fetched_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(arxiv_id) DO UPDATE SET
                    title=excluded.title, authors=excluded.authors,
                    abstract=excluded.abstract, categories=excluded.categories,
                    published=excluded.published, updated=excluded.updated,
                    comment=excluded.comment, journal_ref=excluded.journal_ref,
                    url=excluded.url, pdf_url=excluded.pdf_url,
                    html_url=excluded.html_url, score=excluded.score,
                    signals=excluded.signals, fetched_at=excluded.fetched_at
                """,
                (
                    paper["id"], paper["title"],
                    json.dumps(paper.get("authors") or [], ensure_ascii=False),
                    paper.get("abstract") or "",
                    json.dumps(paper.get("categories") or [], ensure_ascii=False),
                    paper.get("published") or "", paper.get("updated") or "",
                    paper.get("comment") or "", paper.get("journal_ref") or "",
                    paper.get("url") or "", paper.get("pdf_url") or "",
                    paper.get("html_url") or "", float(score),
                    json.dumps(signals or [], ensure_ascii=False), _now_ms(),
                ),
            )

    def get_paper(self, arxiv_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()
        return self._row_to_paper(row)

    def pushed_ids(self) -> set[str]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT arxiv_id FROM papers WHERE pushed_at IS NOT NULL"
            ).fetchall()
        return {str(row["arxiv_id"]) for row in rows}

    def claim_digest(self, date: str, instance: str,
                     stale_seconds: int = 3 * 3600) -> bool:
        """Atomically claim one daily digest across all lark-bot instances."""
        now = _now_ms()
        stale_before = now - max(60, stale_seconds) * 1000
        with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                row = self.conn.execute(
                    "SELECT * FROM digest_runs WHERE date = ?", (date,)
                ).fetchone()
                if row is None:
                    self.conn.execute(
                        "INSERT INTO digest_runs(date, status, instance, claimed_at) "
                        "VALUES(?, 'claimed', ?, ?)",
                        (date, instance, now),
                    )
                    self.conn.commit()
                    return True
                status = str(row["status"])
                claimed_at = int(row["claimed_at"] or 0)
                retryable = (
                    status == "failed" and claimed_at < now - 1800 * 1000
                ) or (status == "claimed" and claimed_at < stale_before)
                if not retryable:
                    self.conn.commit()
                    return False
                self.conn.execute(
                    "UPDATE digest_runs SET status='claimed', instance=?, claimed_at=?, "
                    "finished_at=NULL, message='' WHERE date=?",
                    (instance, now, date),
                )
                self.conn.commit()
                return True
            except Exception:
                self.conn.rollback()
                raise

    def digest_row(self, date: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM digest_runs WHERE date = ?", (date,)
            ).fetchone()
        return dict(row) if row else None

    def finish_digest(self, date: str, status: str, message: str = "",
                      paper_ids: list[str] | None = None) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE digest_runs SET status=?, finished_at=?, message=?, "
                "paper_ids=COALESCE(?, paper_ids) WHERE date=?",
                (
                    status, _now_ms(), _clip(message, 2000),
                    json.dumps(paper_ids, ensure_ascii=False) if paper_ids is not None else None,
                    date,
                ),
            )

    def set_digest_papers(self, date: str, paper_ids: list[str]) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE digest_runs SET paper_ids=? WHERE date=?",
                (json.dumps(paper_ids, ensure_ascii=False), date),
            )

    def digest_papers(self, date: str) -> list[str]:
        row = self.digest_row(date)
        if not row:
            return []
        try:
            values = json.loads(row.get("paper_ids") or "[]")
        except ValueError:
            return []
        return [str(x) for x in values if x]

    def mark_pushed(self, paper_ids: Iterable[str], date: str) -> None:
        ids = [x for x in dict.fromkeys(paper_ids) if x]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self.lock, self.conn:
            self.conn.execute(
                f"UPDATE papers SET pushed_at=?, digest_date=? "
                f"WHERE arxiv_id IN ({placeholders})",
                (_now_ms(), date, *ids),
            )

    def recent_papers(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM papers WHERE pushed_at IS NOT NULL "
                "ORDER BY pushed_at DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [p for p in (self._row_to_paper(row) for row in rows) if p]

    def count_papers(self) -> dict[str, int]:
        with self.lock:
            total = int(self.conn.execute("SELECT COUNT(*) AS n FROM papers").fetchone()["n"])
            pushed = int(self.conn.execute(
                "SELECT COUNT(*) AS n FROM papers WHERE pushed_at IS NOT NULL"
            ).fetchone()["n"])
        return {"total": total, "pushed": pushed}

    def get_artifact(self, path: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM artifacts WHERE path = ?", (str(path),)
            ).fetchone()
        return dict(row) if row else None

    def save_artifact(self, path: str, kind: str, title: str,
                      doc_token: str, doc_url: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO artifacts(path, kind, title, doc_token, doc_url, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET kind=excluded.kind, title=excluded.title, "
                "doc_token=excluded.doc_token, doc_url=excluded.doc_url",
                (str(path), kind, title, doc_token, doc_url, _now_ms()),
            )

    def add_todo(self, source: str, note: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO source_todo(source, note, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET note=excluded.note, "
                "updated_at=excluded.updated_at",
                (source, note, _now_ms()),
            )

    def todos(self) -> list[dict[str, str]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT source, note FROM source_todo ORDER BY source"
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self.lock:
            self.conn.close()


# ---------------------------------------------------------------------------
# Digest plan
# ---------------------------------------------------------------------------

@dataclass
class DigestPlan:
    date: str
    pack_path: Path
    paper_ids: list[str]
    prompt: str
    candidates: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PaperService:
    def __init__(self, cfg: Any, fetcher: Any | None = None,
                 store: PaperStore | None = None):
        self.cfg = cfg
        raw_home = getattr(cfg, "paper_home", None)
        self.home = Path(raw_home).expanduser() if raw_home else Path.home() / ".agents" / "papers"
        self.home.mkdir(parents=True, exist_ok=True)
        self.library = self.home / "library"
        self.digests = self.home / "digests"
        self.notes = self.home / "notes"
        for path in (self.library, self.digests, self.notes):
            path.mkdir(parents=True, exist_ok=True)
        self.store = store or PaperStore(self.home)
        self.fetcher = fetcher or ArxivFetcher(
            timeout=int(getattr(cfg, "paper_http_timeout", 25))
        )
        raw_skills = getattr(cfg, "paper_skills_dir", None)
        self.skills_dir = Path(
            raw_skills or Path(__file__).resolve().parent / "skills"
        ).expanduser()
        self.instance = str(getattr(cfg, "instance_name", cfg.home.name))
        self.env = cfg.feishu_env() if hasattr(cfg, "feishu_env") else os.environ.copy()
        self.lark_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
        self.fulltext_fetcher: Callable[[str], str] | None = None

    # -- topics ---------------------------------------------------------
    @property
    def topics_file(self) -> Path:
        raw = getattr(self.cfg, "paper_topics_file", None)
        return Path(raw).expanduser() if raw else self.home / "topics.json"

    def topics(self) -> dict[str, Any]:
        path = self.topics_file
        data: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError) as exc:
                logging.warning("读取 topics.json 失败，使用默认值: %s", exc)
        topics = dict(DEFAULT_TOPICS)
        for key in ("categories", "keywords", "negative_keywords"):
            if isinstance(data.get(key), list):
                topics[key] = [_clean(x) for x in data[key] if _clean(x)]
        for key in ("category_limit", "max_results_per_category"):
            try:
                topics[key] = int(data.get(key, topics[key]))
            except (TypeError, ValueError):
                pass
        # Explicit config values win over topics.json (handy for per-instance
        # tuning without touching the shared interest file).
        for key, attr in (
            ("category_limit", "paper_category_limit"),
            ("max_results_per_category", "paper_max_results_per_category"),
        ):
            override = getattr(self.cfg, attr, None)
            if override:
                topics[key] = int(override)
        # Env overrides are handy for one-off deployments/tests.
        for key, env_name in (
            ("categories", "PAPER_CATEGORIES"),
            ("keywords", "PAPER_KEYWORDS"),
            ("negative_keywords", "PAPER_NEGATIVE_KEYWORDS"),
        ):
            raw = os.environ.get(env_name, "")
            if raw.strip():
                topics[key] = [x.strip() for x in raw.split(",") if x.strip()]
        if not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(topics, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        return topics

    def topics_summary(self) -> str:
        topics = self.topics()
        categories = ", ".join(topics.get("categories") or []) or "无"
        keywords = ", ".join(topics.get("keywords") or []) or "无"
        return f"分类：{categories}\n关键词：{keywords}"

    # -- time -----------------------------------------------------------
    def _tz(self):
        name = str(getattr(self.cfg, "paper_timezone", "") or "").strip()
        if name and ZoneInfo is not None:
            try:
                return ZoneInfo(name)
            except Exception:  # noqa: BLE001
                logging.warning("未知时区 %s，使用系统本地时区", name)
        return None

    def now(self) -> datetime:
        tz = self._tz()
        return datetime.now(tz) if tz else datetime.now()

    @property
    def push_time(self) -> str:
        raw = str(getattr(self.cfg, "paper_push_time", "08:30") or "08:30").strip()
        return raw if re.fullmatch(r"\d{2}:\d{2}", raw) else "08:30"

    def should_push_now(self) -> bool:
        return self.now().strftime("%H:%M") >= self.push_time

    # -- scoring --------------------------------------------------------
    @staticmethod
    def _kw_hit(keyword: str, text: str) -> bool:
        keyword = keyword.lower()
        if not keyword:
            return False
        if re.search(r"[^\x00-\x7f]", keyword):
            return keyword in text
        return re.search(
            r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text
        ) is not None

    def score(self, paper: dict[str, Any], topics: dict[str, Any]) -> tuple[float, list[str]]:
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        comment = (paper.get("comment") or "").lower()
        journal = (paper.get("journal_ref") or "").lower()
        extra = f"{comment} {journal}"
        signals: list[str] = []
        value = 0.0

        for keyword in topics.get("keywords") or []:
            title_hit = self._kw_hit(keyword, title)
            abstract_hit = self._kw_hit(keyword, abstract)
            if title_hit:
                value += 6
                signals.append(f"标题:{keyword}")
            elif abstract_hit:
                value += 2
                signals.append(f"摘要:{keyword}")

        categories = paper.get("categories") or []
        if categories:
            value += 1
            signals.append(f"分类:{categories[0]}")

        venue = VENUE_RE.search(extra)
        if venue:
            value += 10
            signals.append(f"venue:{venue.group(1)}")
        honor = HONOR_RE.search(extra)
        if honor:
            value += 6
            signals.append(f"荣誉:{honor.group(1)}")
        if re.search(r"\baccepted\b|\baccept\b", extra):
            value += 4
            signals.append("已接收")
        if CODE_RE.search(f"{abstract} {extra}"):
            value += 5
            signals.append("开源/项目页")

        negative_hits = [kw for kw in (topics.get("negative_keywords") or [])
                         if self._kw_hit(kw, title)]
        if negative_hits:
            value -= 8
            signals.append("排除:" + ",".join(negative_hits))
        if len(abstract) < 400:
            value -= 2
            signals.append("摘要偏短")

        published = _parse_time(paper.get("published") or "")
        if published is not None:
            age = datetime.now(timezone.utc) - published
            if age <= timedelta(days=1):
                value += 2
                signals.append("24h 内")
            elif age <= timedelta(days=7):
                value += 1
                signals.append("7 天内")
        return round(value, 2), signals

    def _select(self, candidates: list[dict[str, Any]],
                topics: dict[str, Any]) -> list[dict[str, Any]]:
        ranked = sorted(
            candidates,
            key=lambda p: (float(p.get("score") or 0), p.get("published") or ""),
            reverse=True,
        )
        limit = max(8, int(getattr(self.cfg, "paper_max", 8)) * 2)
        category_limit = max(1, int(topics.get("category_limit") or 3))
        chosen: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for paper in ranked:
            primary = (paper.get("categories") or ["?"])[0]
            if counts.get(primary, 0) >= category_limit:
                continue
            chosen.append(paper)
            counts[primary] = counts.get(primary, 0) + 1
            if len(chosen) >= limit:
                break
        minimum = max(1, int(getattr(self.cfg, "paper_min", 4)))
        if len(chosen) < minimum:
            for paper in ranked:
                if paper not in chosen:
                    chosen.append(paper)
                if len(chosen) >= minimum:
                    break
        return chosen

    # -- fetch ----------------------------------------------------------
    def fetch_candidates(self) -> list[dict[str, Any]]:
        topics = self.topics()
        lookback = max(1, int(getattr(self.cfg, "paper_lookback_hours", 96)))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback)
        per_category = max(10, int(topics.get("max_results_per_category") or 50))
        categories = topics.get("categories") or []
        keywords = topics.get("keywords") or []
        merged: dict[str, dict[str, Any]] = {}

        requests: list[list[dict[str, Any]]] = []
        if categories:
            for category in categories:
                try:
                    requests.append(self.fetcher.fetch_category(category, per_category))
                except Exception as exc:  # noqa: BLE001
                    logging.warning("arXiv 分类 %s 获取失败: %s", category, exc)
        elif keywords:
            try:
                requests.append(self.fetcher.fetch_keywords(keywords, per_category))
            except Exception as exc:  # noqa: BLE001
                logging.warning("arXiv 关键词获取失败: %s", exc)

        pushed = self.store.pushed_ids()
        for papers in requests:
            for paper in papers:
                if paper["id"] in pushed or paper["id"] in merged:
                    continue
                published = _parse_time(paper.get("published") or "")
                if published is not None and published < cutoff:
                    continue
                merged[paper["id"]] = paper

        scored: list[dict[str, Any]] = []
        for paper in merged.values():
            value, signals = self.score(paper, topics)
            paper["score"] = value
            paper["signals"] = signals
            self.store.upsert_paper(paper, value, signals)
            scored.append(paper)
        return self._select(scored, topics)

    # -- digest ---------------------------------------------------------
    def _write_pack(self, date: str, candidates: list[dict[str, Any]]) -> Path:
        path = self.digests / f"{date}-candidates.md"
        lines = [
            f"# 候选论文 {date}",
            "",
            f"共 {len(candidates)} 篇（按规则打分排序）。请从中选出 "
            f"{int(getattr(self.cfg, 'paper_min', 4))}～"
            f"{int(getattr(self.cfg, 'paper_max', 8))} 篇高质量论文。",
            "",
        ]
        for index, paper in enumerate(candidates, 1):
            authors = ", ".join(paper.get("authors") or [])
            lines += [
                f"## {index}. {paper.get('title', '')}",
                f"- arXiv: {paper.get('id')}",
                f"- 链接: {paper.get('url')}",
                f"- PDF: {paper.get('pdf_url')}",
                f"- 分类: {', '.join(paper.get('categories') or [])}",
                f"- 作者: {_clip(authors, 300)}",
                f"- 发布: {paper.get('published', '')}",
                f"- Comment: {paper.get('comment', '') or '未知'}",
                f"- Journal ref: {paper.get('journal_ref', '') or '未知'}",
                f"- 规则分: {paper.get('score')}（{', '.join(paper.get('signals') or []) or '无'}）",
                "",
                "摘要：",
                _clip(paper.get("abstract", ""), 2400),
                "",
            ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def build_plan(self, date: str) -> DigestPlan | None:
        candidates = self.fetch_candidates()
        if not candidates:
            return None
        pack = self._write_pack(date, candidates)
        min_docs = int(getattr(self.cfg, "paper_min", 4))
        max_docs = int(getattr(self.cfg, "paper_max", 8))
        digest_path = self.digests / f"{date}-digest.md"
        skill = self.skills_dir / "paper-digest" / "SKILL.md"
        prompt = (
            "[每日论文速递任务]\n"
            f"日期: {date}\n"
            f"候选素材: {pack}\n"
            f"技能说明（先读）: {skill}\n\n"
            f"请从候选中挑选 {min_docs}～{max_docs} 篇高质量、与主人方向最相关的论文，"
            "宁缺毋滥。先用规则分做初筛，再结合摘要质量、会议/期刊、开源情况判断；"
            "需要核实会议或开源状态时可以联网搜索。\n\n"
            "输出要求：\n"
            "1. 全中文，按质量从高到低排序。\n"
            "2. 每篇包含：标题（附 arXiv 链接）、一句话结论、核心贡献、"
            "为什么值得读、质量依据（会议/代码/开源等；没有就写“未知”）。\n"
            "3. 明确区分“论文明确说”“合理推断”“未支撑”，不得编造实验数字、"
            "数据集细节或开源状态。\n"
            "4. 把完整速递 Markdown 写入：\n"
            f"   {digest_path}\n"
            "   并在最终答复末尾单独一行输出：\n"
            f"   DIGEST_PATH={digest_path}\n"
            "5. 最终答复本身也要完整可读，不要只说“已写入文件”。\n"
        )
        return DigestPlan(
            date=date,
            pack_path=pack,
            paper_ids=[p["id"] for p in candidates],
            prompt=prompt,
            candidates=candidates,
        )

    def try_start_digest(self, state: Any) -> str:
        """Called by the scheduler; returns a short status string."""
        if not self.is_enabled(
            state, bool(getattr(self.cfg, "paper_enabled_default", False))
        ):
            return "disabled"
        if not self.should_push_now():
            return "not_yet"
        date = self.now().strftime("%Y-%m-%d")
        if not self.store.claim_digest(date, self.instance):
            return "already_claimed"
        try:
            plan = self.build_plan(date)
            if plan is None:
                self.store.finish_digest(date, "failed", "没有抓取到候选论文")
                return "no_candidates"
            self.store.set_digest_papers(date, plan.paper_ids)
            event = {
                "message_id": f"paper-digest-{date}",
                "chat_id": str(getattr(self.cfg, "owner_id", "")),
                "chat_type": "p2p",
                "sender_id": str(getattr(self.cfg, "owner_id", "")),
                "sender_type": "user",
                "message_type": "text",
                "content": plan.prompt,
                "create_time": str(_now_ms()),
                "mentions": [],
            }
            task_id = state.requeue_task(
                f"paper-digest-{date}",
                f"paper-digest:{date}",
                str(getattr(self.cfg, "owner_id", "")),
                plan.prompt,
                json.dumps(event, ensure_ascii=False),
                str(self.home),
            )
            if task_id <= 0:
                self.store.finish_digest(date, "failed", "任务入队失败")
                return "enqueue_failed"
            self.store.finish_digest(date, "queued", "已入队", plan.paper_ids)
            logging.info("论文速递已入队 date=%s task=%s papers=%s",
                         date, task_id, len(plan.paper_ids))
            return f"queued:{task_id}"
        except Exception as exc:  # noqa: BLE001
            logging.exception("生成论文速递失败")
            self.store.finish_digest(date, "failed", str(exc))
            return f"error:{exc}"

    def mark_digest_done(self, date: str, message: str = "") -> None:
        ids = self.store.digest_papers(date)
        known = set(ids)
        # Prefer the arXiv links actually present in the digest so candidates
        # the agent rejected stay eligible for tomorrow.
        chosen = [x for x in self.extract_ids(message) if x in known]
        pushed = chosen or ids
        self.store.mark_pushed(pushed, date)
        self.store.finish_digest(date, "done", message or "已发送", pushed)

    def mark_digest_failed(self, date: str, error: str) -> None:
        self.store.finish_digest(date, "failed", error)

    # -- on-demand material --------------------------------------------
    @staticmethod
    def extract_ids(text: str) -> list[str]:
        ids: list[str] = []
        for pattern in (ARXIV_ID_RE, ARXIV_LEGACY_RE):
            ids.extend(m.group(1) for m in pattern.finditer(text))
        # Bare IDs are only trusted when the message is explicitly about arXiv.
        if re.search(r"arxiv|论文|paper", text, re.I):
            for match in ARXIV_BARE_RE.finditer(text):
                candidate = match.group(1)
                # Avoid years and common decimal numbers.
                if candidate[:4].isdigit() and 1000 <= int(candidate[:4]) <= 3000:
                    ids.append(candidate)
        cleaned = []
        for value in ids:
            value = re.sub(r"v\d+$", "", value.strip())
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    def _material_dir(self, arxiv_id: str) -> Path:
        return self.library / re.sub(r"[^A-Za-z0-9._-]", "_", arxiv_id.replace("/", "_"))

    def _fetch_fulltext(self, arxiv_id: str, directory: Path) -> tuple[str, str]:
        """Return (text, coverage). coverage = html/pdf/abstract."""
        fulltext = directory / "fulltext.txt"
        if fulltext.exists():
            try:
                text = fulltext.read_text(encoding="utf-8")
                if len(text.strip()) > 200:
                    return text, "cached"
            except OSError:
                pass

        text = ""
        if self.fulltext_fetcher is not None:
            text = self.fulltext_fetcher(arxiv_id)
        if not text:
            text = self.fetcher.fetch_html_text(arxiv_id)
        coverage = "html" if text else ""
        if not text:
            pdf = directory / "paper.pdf"
            if not pdf.exists():
                self.fetcher.download_pdf(arxiv_id, pdf)
            if pdf.exists():
                text = extract_pdf_text(pdf)
                coverage = "pdf" if text else ""
        return text, coverage

    def ensure_material(self, arxiv_id: str) -> dict[str, Any] | None:
        paper = self.store.get_paper(arxiv_id)
        if paper is None:
            try:
                found = self.fetcher.fetch_by_ids([arxiv_id])
            except Exception as exc:  # noqa: BLE001
                logging.warning("获取论文元数据失败 %s: %s", arxiv_id, exc)
                found = {}
            paper = found.get(arxiv_id)
            if paper is None:
                return None
            value, signals = self.score(paper, self.topics())
            paper["score"] = value
            paper["signals"] = signals
            self.store.upsert_paper(paper, value, signals)

        directory = self._material_dir(arxiv_id)
        directory.mkdir(parents=True, exist_ok=True)
        meta_path = directory / "meta.json"
        try:
            meta_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        text, coverage = self._fetch_fulltext(arxiv_id, directory)
        if text:
            try:
                (directory / "fulltext.txt").write_text(text, encoding="utf-8")
            except OSError:
                pass
        pdf = directory / "paper.pdf"
        paper = dict(paper)
        paper["material_dir"] = str(directory)
        paper["fulltext_path"] = str(directory / "fulltext.txt") if text else ""
        paper["pdf_path"] = str(pdf) if pdf.exists() else ""
        paper["coverage"] = "fulltext" if text else "abstract"
        paper["coverage_source"] = coverage or "abstract"
        return paper

    def prepare_text(self, text: str) -> str:
        ids = self.extract_ids(text)
        blocks: list[str] = []
        for arxiv_id in ids[: max(1, int(getattr(self.cfg, "paper_max_attach", 3)))]:
            try:
                paper = self.ensure_material(arxiv_id)
            except Exception as exc:  # noqa: BLE001
                logging.warning("预取论文素材失败 %s: %s", arxiv_id, exc)
                paper = None
            if paper is None:
                blocks.append(f"### {arxiv_id}\n- 元数据获取失败，请联网核实：{ARXIV_ABS.format(id=arxiv_id)}")
                continue
            note = self.notes / f"{re.sub(r'[^A-Za-z0-9._-]', '_', arxiv_id)}.md"
            coverage = (
                f"全文已获取（来源: {paper.get('coverage_source')}）"
                if paper.get("fulltext_path")
                else "仅摘要/元数据，未获取到全文"
            )
            blocks.append(
                "\n".join([
                    f"### {paper.get('id')} {paper.get('title')}",
                    f"- 作者: {_clip(', '.join(paper.get('authors') or []), 400)}",
                    f"- 分类: {', '.join(paper.get('categories') or [])}",
                    f"- arXiv: {paper.get('url')}",
                    f"- PDF: {paper.get('pdf_path') or paper.get('pdf_url')}",
                    f"- 全文文本: {paper.get('fulltext_path') or '无'}",
                    f"- 素材目录: {paper.get('material_dir')}",
                    f"- 覆盖范围: {coverage}",
                    f"- 摘要: {_clip(paper.get('abstract', ''), 2200)}",
                    f"- 笔记输出: {note}",
                ])
            )

        hints: list[str] = []
        if ids or CODEX_PAPER_HINT.search(text):
            for name, purpose in (
                ("paper-reading", "决定值不值得读/复现"),
                ("paper-deep-note", "结构化精读笔记"),
                ("paper-benchmark", "多篇实验设置对比"),
                ("research-gap-finder", "找研究空白"),
                ("paper-digest", "每日速递"),
            ):
                skill = self.skills_dir / name / "SKILL.md"
                if skill.exists():
                    hints.append(f"- {purpose}: {skill}")
        if not blocks and not hints:
            return text
        parts = [text, "", "[bridge 论文上下文]"]
        if blocks:
            parts.append("用户消息包含 arXiv 论文，以下素材已由 bridge 预取：")
            parts.extend(blocks)
            parts += [
                "",
                "要求：",
                "- 有全文时基于全文；没有全文时必须显式写“仅基于摘要判断”。",
                "- 不得编造实验数字、数据集细节、消融结论或开源状态；未知就写“未知”。",
                "- 若用户要精读/笔记，把 Markdown 笔记写入上面给出的“笔记输出”路径，"
                "并在最终答复末尾单独一行输出 NOTE_PATH=<该绝对路径>。",
                "- 若用户要比较多篇，请先分别抽取各篇的实验设置，再给对比表。",
            ]
        if hints:
            parts.append("")
            parts.append("相关技能说明（按任务先读对应文件）：")
            parts.extend(hints)
        return "\n".join(parts)

    # -- Feishu docs ----------------------------------------------------
    def _lark_base(self, profile: str) -> list[str]:
        base = [str(getattr(self.cfg, "lark_cli_bin", "lark-cli"))]
        if profile:
            base += ["--profile", profile]
        return base

    @staticmethod
    def _find_url(value: Any) -> str:
        if isinstance(value, str):
            match = URL_RE.search(value)
            return match.group(0) if match else ""
        if isinstance(value, dict):
            for key in ("url", "document_url", "doc_url", "link", "web_url"):
                if isinstance(value.get(key), str) and value[key].startswith("http"):
                    return value[key]
            for item in value.values():
                found = PaperService._find_url(item)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = PaperService._find_url(item)
                if found:
                    return found
        return ""

    @staticmethod
    def _find_token(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("document_id", "doc_token", "document_token", "token", "node_token"):
                if isinstance(value.get(key), str) and value[key]:
                    return value[key]
            for item in value.values():
                found = PaperService._find_token(item)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = PaperService._find_token(item)
                if found:
                    return found
        return ""

    @staticmethod
    def _doc_parent_token(value: str) -> str:
        """Accept a folder/wiki token or a Feishu doc/wiki URL."""
        value = _clean(value)
        if not value:
            return ""
        match = re.search(r"/(?:wiki|docx|docs|drive/folder)/([A-Za-z0-9]+)", value)
        return match.group(1) if match else value

    @staticmethod
    def _json_output(stdout: str) -> dict[str, Any]:
        """Parse lark-cli JSON output (single object or NDJSON)."""
        text = (stdout or "").strip()
        if not text:
            return {}
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {}
        except ValueError:
            pass
        for line in reversed(text.splitlines()):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
        return {}

    def _doc_profile(self) -> str:
        return str(
            getattr(self.cfg, "paper_doc_profile", "")
            or getattr(self.cfg, "lark_profile", "")
            or ""
        ).strip()

    def _fetch_doc_markdown(self, token: str, profile: str) -> tuple[str | None, str]:
        args = self._lark_base(profile) + [
            "docs", "+fetch", "--as", "user", "--doc", token,
            "--doc-format", "markdown",
        ]
        proc = self.lark_runner(
            args, capture_output=True, text=True, env=self.env, timeout=120,
        )
        output = f"{proc.stdout}\n{proc.stderr}".strip()
        if proc.returncode != 0:
            return None, output
        payload = self._json_output(proc.stdout)
        document = payload.get("data", {}).get("document", {})
        content = document.get("content") if isinstance(document, dict) else None
        if not isinstance(content, str):
            return "", ""
        return content, ""

    @staticmethod
    def _digest_index_entries(path: Path | None) -> list[dict[str, Any]]:
        """Extract paper title/URL/summary/priority from a digest markdown."""
        if path is None:
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in text.splitlines():
            heading = re.match(r"^##\s+(?:\d+[.、]\s*)?(.+?)\s*$", line)
            if heading:
                if current and current.get("url"):
                    entries.append(current)
                current = {
                    "title": _clean(heading.group(1)),
                    "url": "",
                    "summary": "",
                    "priority": "",
                }
                continue
            if current is None:
                continue
            arxiv = re.match(r"^-\s*arXiv:\s*(\S+)", line)
            if arxiv and not current["url"]:
                current["url"] = arxiv.group(1)
                continue
            # Digests generated interactively may use plain list items
            # ("- 一句话结论：...") instead of bold labels.
            summary = re.match(
                r"^(?:-\s*)?(?:\*\*)?一句话结论(?:\*\*)?[：:]\s*(.+)$", line
            )
            if summary and not current["summary"]:
                current["summary"] = _clean(summary.group(1))
                continue
            priority = re.match(
                r"^(?:-\s*)?(?:\*\*)?阅读优先级(?:\*\*)?[：:]\s*(.+)$", line
            )
            if priority and not current["priority"]:
                current["priority"] = _clean(priority.group(1))
        if current and current.get("url"):
            entries.append(current)
        for entry in entries:
            primary = re.split(r"[；;，,。]", entry["priority"], maxsplit=1)[0]
            if "精读" in primary:
                entry["rank"] = 1
            elif "速读" in primary:
                entry["rank"] = 2
            elif "暂缓" in primary:
                entry["rank"] = 3
            else:
                entry["rank"] = 4
        entries.sort(key=lambda item: item["rank"])
        return entries

    def append_digest_index(self, title: str, url: str,
                            path: Path | None = None) -> str:
        """Append a month → day → paper outline to the parent wiki doc."""
        parent = self._doc_parent_token(
            str(getattr(self.cfg, "paper_doc_folder", "") or "")
        )
        if not parent or not url:
            return ""
        profile = self._doc_profile()
        content, error = self._fetch_doc_markdown(parent, profile)
        if content is None:
            logging.warning("读取父文档目录失败: %s", _clip(error, 300))
            return ""
        child_token = self._doc_parent_token(url)
        if url in content or (child_token and child_token in content):
            return ""
        if title in content:
            return ""
        month = self.now().strftime("%Y-%m")
        month_heading = f"{month} 论文速递"
        body = ""
        if month_heading not in content:
            body += f"<h2>{html_lib.escape(month_heading)}</h2>"
        body += f"<h3>{html_lib.escape(title)}</h3>"
        body += (
            f'<p><a href="{html_lib.escape(url, quote=True)}">'
            "📄 打开当日速递</a></p>"
        )
        for entry in self._digest_index_entries(path):
            summary = entry["summary"].replace("**", "").replace("`", "")
            item = (
                f'P{entry["rank"]} · <a href="'
                f'{html_lib.escape(entry["url"], quote=True)}">'
                f'{html_lib.escape(entry["title"])}</a>'
            )
            if summary:
                item += f"：{html_lib.escape(summary)}"
            body += f'<checkbox done="false">{item}</checkbox>'
        args = self._lark_base(profile) + [
            "docs", "+update", "--as", "user", "--doc", parent,
            "--command", "append", "--doc-format", "xml",
            "--content", "-",
        ]
        proc = self.lark_runner(
            args, capture_output=True, text=True, env=self.env, timeout=120,
            input=body,
        )
        if proc.returncode != 0:
            output = f"{proc.stdout}\n{proc.stderr}".strip()
            logging.warning("更新父文档目录失败: %s", _clip(output, 300))
            return ""
        return "ok"

    def _create_doc(self, path: Path, title: str, identity: str,
                    profile: str) -> tuple[str, str, str]:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return "", "", f"读取文档内容失败: {exc}"
        args = self._lark_base(profile) + [
            "docs", "+create", "--as", identity,
            "--doc-format", "markdown", "--title", title,
            # lark-cli only accepts --content files under cwd, /tmp or ~/files;
            # pipe the digest from PAPER_HOME through stdin instead.
            "--content", "-",
        ]
        folder = self._doc_parent_token(
            str(getattr(self.cfg, "paper_doc_folder", "") or "")
        )
        if folder:
            args += ["--parent-token", folder]
        else:
            args += ["--parent-position", "my_library"]
        proc = self.lark_runner(
            args, capture_output=True, text=True, env=self.env, timeout=120,
            input=content,
        )
        output = f"{proc.stdout}\n{proc.stderr}".strip()
        if proc.returncode != 0:
            return "", "", output
        url = ""
        token = ""
        for line in reversed(proc.stdout.strip().splitlines()):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            url = self._find_url(payload)
            token = self._find_token(payload)
            if url:
                break
        if not url:
            match = URL_RE.search(proc.stdout)
            url = match.group(0) if match else ""
        if not url and not token:
            return "", "", f"无法解析 docs +create 输出: {_clip(output, 500)}"
        return url, token, ""

    def publish_markdown(self, path: Path, title: str, kind: str = "") -> tuple[str, str]:
        """Create a Feishu doc in the user's cloud space. Returns (url, error)."""
        path = path.expanduser().resolve()
        if not path.is_file():
            return "", f"文件不存在: {path}"
        artifact = self.store.get_artifact(str(path))
        if artifact and artifact.get("doc_url"):
            return str(artifact["doc_url"]), ""
        title = _clean(title)[:80] or path.stem
        profile = self._doc_profile()
        url, token, error = self._create_doc(path, title, "user", profile)
        if not url and not token:
            logging.warning("以用户身份创建飞书文档失败，尝试机器人身份: %s", _clip(error, 300))
            url, token, error = self._create_doc(path, title, "bot", profile)
            if url:
                logging.warning("飞书文档创建于机器人空间（用户身份不可用）: %s", url)
        if not url and not token:
            return "", _clip(error, 800)
        if not url:
            url = f"https://feishu.cn/docx/{token}" if token else ""
        self.store.save_artifact(str(path), kind, title, token, url)
        return url, ""

    @staticmethod
    def _title_from_file(path: Path, fallback: str) -> str:
        try:
            for line in path.read_text(encoding="utf-8").splitlines()[:30]:
                if line.startswith("# "):
                    return _clean(line[2:])[:80] or fallback
        except OSError:
            pass
        return fallback

    def postprocess(self, text: str, task: dict[str, Any]) -> str:
        paths: list[Path] = []
        for raw in NOTE_PATH_RE.findall(text or ""):
            candidate = Path(raw.strip().strip("`'\""))
            if not candidate.is_absolute():
                continue
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            roots = [self.home, Path(getattr(self.cfg, "workdir", self.home))]
            if any(resolved.is_relative_to(root.resolve()) for root in roots if root.exists()):
                if resolved.is_file() and resolved not in paths:
                    paths.append(resolved)
        session_key = str(task.get("session_key") or "")
        is_digest = session_key.startswith("paper-digest")
        if is_digest:
            date = session_key.split(":", 1)[-1]
            digest_fallback = self.digests / f"{date}-digest.md"
            if not paths and text.strip():
                try:
                    digest_fallback.write_text(text.strip() + "\n", encoding="utf-8")
                    paths.append(digest_fallback)
                except OSError:
                    pass
            elif digest_fallback.is_file() and digest_fallback not in paths:
                paths.append(digest_fallback)

        links: list[str] = []
        for path in paths:
            fallback = f"论文笔记 {self.now().strftime('%Y-%m-%d')}"
            if is_digest and path.name.endswith("-digest.md"):
                title = f"{date} 论文速递"
            else:
                title = self._title_from_file(path, fallback)
            url, error = self.publish_markdown(
                path, title, "digest" if is_digest else "note"
            )
            if url:
                links.append(f"📄 飞书文档：{url}")
                if is_digest:
                    self.append_digest_index(title, url, path)
            else:
                logging.warning("笔记上传飞书文档失败 %s: %s", path, error)
                links.append(f"⚠️ 笔记已保存到本地：`{path}`（飞书文档创建失败：{_clip(error, 200)}）")
        if not links:
            return text
        suffix = "\n\n" + "\n".join(links)
        if suffix.strip() in (text or ""):
            return text
        return (text or "").rstrip() + suffix

    # -- toggles / status ----------------------------------------------
    @staticmethod
    def is_enabled(state: Any, default: bool = False) -> bool:
        try:
            value = state.get_setting("paper_enabled")
        except AttributeError:
            return False
        if value is None:
            return bool(getattr(state, "paper_enabled_default", default))
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def status_text(self, state: Any) -> str:
        enabled = self.is_enabled(
            state, bool(getattr(self.cfg, "paper_enabled_default", False))
        )
        date = self.now().strftime("%Y-%m-%d")
        run = self.store.digest_row(date)
        counts = self.store.count_papers()
        status = run.get("status") if run else "未开始"
        instance = run.get("instance") if run else ""
        profile = str(
            getattr(self.cfg, "paper_doc_profile", "")
            or getattr(self.cfg, "lark_profile", "")
            or "(默认 profile)"
        )
        lines = [
            "📚 论文推送状态",
            f"- 本实例：{'已启用' if enabled else '已关闭'}（发送 `/paper-start` 启用）",
            f"- 推送时间：每天 {self.push_time}",
            f"- 今日（{date}）速递：{status}"
            + (f"（{instance}）" if instance else ""),
            f"- 论文库：{counts['total']} 篇，已推送 {counts['pushed']} 篇",
            f"- 共享目录：`{self.home}`",
            f"- 飞书文档 profile：`{profile}`",
            "",
            "关注方向：",
            self.topics_summary(),
        ]
        recent = self.store.recent_papers(5)
        if recent:
            lines += ["", "最近推送："]
            for paper in recent:
                lines.append(f"- [{paper.get('digest_date')}] {_clip(paper.get('title', ''), 70)}")
        todos = self.store.todos()
        if todos:
            lines += ["", "待补充数据源："]
            for item in todos:
                lines.append(f"- {item['source']}: {_clip(item['note'], 120)}")
        return "\n".join(lines)

    def close(self) -> None:
        self.store.close()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class PaperScheduler(threading.Thread):
    def __init__(self, cfg: Any, state: Any, papers: PaperService,
                 stop_event: threading.Event):
        super().__init__(name="paper-scheduler", daemon=True)
        self.cfg = cfg
        self.state = state
        self.papers = papers
        self.stop_event = stop_event
        self._wake = threading.Event()
        self.last_result = ""

    def wake(self) -> None:
        self._wake.set()

    def run(self) -> None:
        logging.info("论文调度器启动 time=%s home=%s",
                     self.papers.push_time, self.papers.home)
        while not self.stop_event.is_set():
            try:
                result = self.papers.try_start_digest(self.state)
                if result != self.last_result and result not in ("not_yet", "disabled"):
                    logging.info("论文调度: %s", result)
                self.last_result = result
            except Exception:  # noqa: BLE001
                logging.exception("论文调度异常")
            self._wake.wait(60)
            self._wake.clear()

"""学术检索与相关工作素材生成（默认无 Key：arXiv + OpenAlex + Crossref）。"""

from __future__ import annotations

import os
import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests


ARXIV_API_URL = "https://export.arxiv.org/api/query"
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_API_URL = "https://api.openalex.org/works"
CROSSREF_API_URL = "https://api.crossref.org/works"


@dataclass
class PaperRecord:
    source: str
    paper_id: str
    title: str
    abstract: str
    authors: List[str]
    year: Optional[int]
    venue: Optional[str]
    url: Optional[str]
    pdf_url: Optional[str]
    doi: Optional[str]
    arxiv_id: Optional[str]
    citation_count: Optional[int]

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "citation_count": self.citation_count,
        }


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _safe_year(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    m = re.search(r"(\d{4})", str(raw))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_arxiv_id(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    value = str(text).strip()
    if not value:
        return None
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", value, re.IGNORECASE)
    if m:
        aid = m.group(1)
        aid = re.sub(r"\.pdf$", "", aid, flags=re.IGNORECASE)
        return re.sub(r"v\d+$", "", aid)
    m = re.search(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", value)
    if m:
        return m.group(1)
    return None


def _openalex_abstract(inv: object) -> str:
    if not isinstance(inv, dict):
        return ""
    pairs = []
    for word, positions in inv.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int):
                pairs.append((pos, word))
    if not pairs:
        return ""
    pairs.sort(key=lambda x: x[0])
    return _clean_space(" ".join([w for _, w in pairs]))


def _crossref_year(item: Dict[str, object]) -> Optional[int]:
    for key in ("issued", "published-print", "published-online", "created"):
        raw = item.get(key)
        if not isinstance(raw, dict):
            continue
        date_parts = raw.get("date-parts")
        if isinstance(date_parts, list) and date_parts:
            first = date_parts[0]
            if isinstance(first, list) and first:
                year = first[0]
                if isinstance(year, int):
                    return year
                y2 = _safe_year(str(year))
                if y2:
                    return y2
    return None


def _strip_xml_tags(text: str) -> str:
    return _clean_space(re.sub(r"<[^>]+>", " ", text))


def _key_for_dedup(p: PaperRecord) -> str:
    if p.doi:
        return f"doi:{p.doi.lower()}"
    if p.arxiv_id:
        return f"arxiv:{p.arxiv_id.lower()}"
    title = re.sub(r"[^a-z0-9]+", "", p.title.lower())
    return f"title:{title}"


def search_arxiv(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    timeout: int = 30,
) -> List[PaperRecord]:
    if not query or not query.strip():
        raise ValueError("query 不能为空")
    max_results = max(1, min(int(max_results), 50))

    params = {
        "search_query": query.strip(),
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    resp = requests.get(ARXIV_API_URL, params=params, timeout=timeout)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out: List[PaperRecord] = []
    for entry in root.findall("a:entry", ns):
        eid = _clean_space(entry.findtext("a:id", default="", namespaces=ns))
        title = _clean_space(entry.findtext("a:title", default="", namespaces=ns))
        abstract = _clean_space(entry.findtext("a:summary", default="", namespaces=ns))
        published = entry.findtext("a:published", default="", namespaces=ns)
        year = _safe_year(published)
        authors = []
        for au in entry.findall("a:author", ns):
            name = _clean_space(au.findtext("a:name", default="", namespaces=ns))
            if name:
                authors.append(name)

        doi = None
        arxiv_id = None
        pdf_url = None
        abs_url = None
        for link in entry.findall("a:link", ns):
            href = link.attrib.get("href")
            title_attr = link.attrib.get("title", "")
            rel = link.attrib.get("rel", "")
            if rel == "alternate" and href:
                abs_url = href
            if title_attr == "pdf" and href:
                pdf_url = href

        for child in list(entry):
            tag = child.tag.lower()
            if tag.endswith("doi"):
                doi = _clean_space(child.text or "")

        if eid:
            m = re.search(r"arxiv\.org/abs/([^v]+)", eid, re.IGNORECASE)
            if m:
                arxiv_id = m.group(1)
            elif "/" in eid:
                arxiv_id = eid.rsplit("/", 1)[-1]

        out.append(
            PaperRecord(
                source="arxiv",
                paper_id=arxiv_id or eid or title,
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                venue="arXiv",
                url=abs_url or eid or None,
                pdf_url=pdf_url,
                doi=doi or None,
                arxiv_id=arxiv_id,
                citation_count=None,
            )
        )
    return out


def search_semantic_scholar(
    query: str,
    limit: int = 10,
    timeout: int = 30,
    api_key: Optional[str] = None,
) -> List[PaperRecord]:
    if not query or not query.strip():
        raise ValueError("query 不能为空")
    limit = max(1, min(int(limit), 50))
    key = api_key or os.environ.get("S2_API_KEY")
    headers = {}
    if key:
        headers["x-api-key"] = key

    params = {
        "query": query.strip(),
        "limit": limit,
        "fields": ",".join(
            [
                "paperId",
                "title",
                "abstract",
                "authors",
                "year",
                "venue",
                "url",
                "citationCount",
                "externalIds",
                "openAccessPdf",
            ]
        ),
    }
    resp = requests.get(S2_API_URL, headers=headers, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    records = data.get("data", []) if isinstance(data, dict) else []

    out: List[PaperRecord] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        ext = item.get("externalIds") or {}
        if not isinstance(ext, dict):
            ext = {}
        oa = item.get("openAccessPdf") or {}
        if not isinstance(oa, dict):
            oa = {}
        authors = []
        for au in item.get("authors", []) or []:
            if isinstance(au, dict):
                name = _clean_space(str(au.get("name", "")))
                if name:
                    authors.append(name)
        out.append(
            PaperRecord(
                source="semantic_scholar",
                paper_id=str(item.get("paperId") or ""),
                title=_clean_space(str(item.get("title") or "")),
                abstract=_clean_space(str(item.get("abstract") or "")),
                authors=authors,
                year=item.get("year"),
                venue=_clean_space(str(item.get("venue") or "")) or None,
                url=_clean_space(str(item.get("url") or "")) or None,
                pdf_url=_clean_space(str(oa.get("url") or "")) or None,
                doi=_clean_space(str(ext.get("DOI") or "")) or None,
                arxiv_id=_clean_space(str(ext.get("ArXiv") or "")) or None,
                citation_count=item.get("citationCount"),
            )
        )
    return out


def search_openalex(
    query: str,
    per_page: int = 10,
    timeout: int = 30,
) -> List[PaperRecord]:
    if not query or not query.strip():
        raise ValueError("query 不能为空")
    per_page = max(1, min(int(per_page), 50))
    params = {
        "search": query.strip(),
        "per-page": per_page,
    }
    resp = requests.get(OPENALEX_API_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    records = data.get("results", []) if isinstance(data, dict) else []

    out: List[PaperRecord] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        ids = item.get("ids") or {}
        if not isinstance(ids, dict):
            ids = {}
        open_access = item.get("open_access") or {}
        if not isinstance(open_access, dict):
            open_access = {}
        best_oa = item.get("best_oa_location") or {}
        if not isinstance(best_oa, dict):
            best_oa = {}
        primary_location = item.get("primary_location") or {}
        if not isinstance(primary_location, dict):
            primary_location = {}
        source_info = primary_location.get("source") or {}
        if not isinstance(source_info, dict):
            source_info = {}

        authors: List[str] = []
        for au in item.get("authorships", []) or []:
            if not isinstance(au, dict):
                continue
            author_info = au.get("author") or {}
            if not isinstance(author_info, dict):
                continue
            name = _clean_space(str(author_info.get("display_name") or ""))
            if name:
                authors.append(name)

        doi_url = _clean_space(str(item.get("doi") or ""))
        doi = doi_url.replace("https://doi.org/", "").replace("http://doi.org/", "") or None
        arxiv_id = _extract_arxiv_id(str(ids.get("arxiv") or ""))
        url = (
            _clean_space(str(primary_location.get("landing_page_url") or ""))
            or _clean_space(str(item.get("id") or ""))
            or None
        )
        pdf_url = (
            _clean_space(str(best_oa.get("pdf_url") or ""))
            or _clean_space(str(open_access.get("oa_url") or ""))
            or None
        )

        out.append(
            PaperRecord(
                source="openalex",
                paper_id=_clean_space(str(item.get("id") or "")),
                title=_clean_space(str(item.get("display_name") or "")),
                abstract=_openalex_abstract(item.get("abstract_inverted_index")),
                authors=authors,
                year=item.get("publication_year") if isinstance(item.get("publication_year"), int) else None,
                venue=_clean_space(str(source_info.get("display_name") or "")) or None,
                url=url,
                pdf_url=pdf_url,
                doi=doi,
                arxiv_id=arxiv_id,
                citation_count=item.get("cited_by_count") if isinstance(item.get("cited_by_count"), int) else None,
            )
        )
    return out


def search_crossref(
    query: str,
    rows: int = 10,
    timeout: int = 30,
) -> List[PaperRecord]:
    if not query or not query.strip():
        raise ValueError("query 不能为空")
    rows = max(1, min(int(rows), 50))
    params = {
        "query.bibliographic": query.strip(),
        "rows": rows,
    }
    resp = requests.get(CROSSREF_API_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("message", {}) if isinstance(data, dict) else {}
    items = msg.get("items", []) if isinstance(msg, dict) else []

    out: List[PaperRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = ""
        raw_titles = item.get("title")
        if isinstance(raw_titles, list) and raw_titles:
            title = _clean_space(str(raw_titles[0]))
        elif isinstance(raw_titles, str):
            title = _clean_space(raw_titles)

        abstract_raw = _clean_space(str(item.get("abstract") or ""))
        abstract = _strip_xml_tags(abstract_raw) if abstract_raw else ""

        authors: List[str] = []
        for au in item.get("author", []) or []:
            if not isinstance(au, dict):
                continue
            given = _clean_space(str(au.get("given") or ""))
            family = _clean_space(str(au.get("family") or ""))
            name = _clean_space(f"{given} {family}")
            if name:
                authors.append(name)

        venue = ""
        raw_venues = item.get("container-title")
        if isinstance(raw_venues, list) and raw_venues:
            venue = _clean_space(str(raw_venues[0]))
        elif isinstance(raw_venues, str):
            venue = _clean_space(raw_venues)

        doi = _clean_space(str(item.get("DOI") or "")) or None
        url = _clean_space(str(item.get("URL") or "")) or None

        out.append(
            PaperRecord(
                source="crossref",
                paper_id=doi or url or title,
                title=title,
                abstract=abstract,
                authors=authors,
                year=_crossref_year(item),
                venue=venue or None,
                url=url,
                pdf_url=None,
                doi=doi,
                arxiv_id=None,
                citation_count=item.get("is-referenced-by-count")
                if isinstance(item.get("is-referenced-by-count"), int)
                else None,
            )
        )
    return out


def search_academic_papers(
    query: str,
    source: str = "all",
    max_results_per_source: int = 8,
    timeout: int = 30,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    src = source.strip().lower()
    if src not in ("all", "arxiv", "semantic_scholar", "openalex", "crossref"):
        raise ValueError("source 仅支持 all/arxiv/openalex/crossref/semantic_scholar")

    raw: List[PaperRecord] = []
    errors: Dict[str, str] = {}

    if src in ("all", "arxiv"):
        try:
            raw.extend(
                search_arxiv(
                    query=query,
                    max_results=max_results_per_source,
                    timeout=timeout,
                )
            )
        except Exception as exc:
            errors["arxiv"] = str(exc)

    if src in ("all", "openalex"):
        try:
            raw.extend(
                search_openalex(
                    query=query,
                    per_page=max_results_per_source,
                    timeout=timeout,
                )
            )
        except Exception as exc:
            errors["openalex"] = str(exc)

    if src in ("all", "crossref"):
        try:
            raw.extend(
                search_crossref(
                    query=query,
                    rows=max_results_per_source,
                    timeout=timeout,
                )
            )
        except Exception as exc:
            errors["crossref"] = str(exc)

    s2_key = s2_api_key or os.environ.get("S2_API_KEY")
    run_semantic = src == "semantic_scholar" or (src == "all" and bool(s2_key))
    if src in ("all", "semantic_scholar"):
        if run_semantic:
            try:
                raw.extend(
                    search_semantic_scholar(
                        query=query,
                        limit=max_results_per_source,
                        timeout=timeout,
                        api_key=s2_key,
                    )
                )
            except Exception as exc:
                errors["semantic_scholar"] = str(exc)
        elif src == "all":
            errors["semantic_scholar"] = "skipped: S2_API_KEY not provided"

    dedup: Dict[str, PaperRecord] = {}
    for p in raw:
        key = _key_for_dedup(p)
        old = dedup.get(key)
        if old is None:
            dedup[key] = p
            continue
        # 优先保留有 citation_count 的条目。
        old_score = old.citation_count if isinstance(old.citation_count, int) else -1
        new_score = p.citation_count if isinstance(p.citation_count, int) else -1
        if new_score > old_score:
            dedup[key] = p

    papers = list(dedup.values())
    papers.sort(key=lambda x: (x.citation_count or -1, x.year or 0), reverse=True)

    return {
        "ok": len(papers) > 0,
        "query": query,
        "source": src,
        "count": len(papers),
        "errors": errors,
        "papers": [p.to_dict() for p in papers],
    }


def _first_author_short(authors: List[str]) -> str:
    if not authors:
        return "Anon"
    s = authors[0]
    last = s.split()[-1]
    return re.sub(r"[^A-Za-z0-9]+", "", last) or "Author"


def _title_key(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    return "".join(words[:4])[:32] or "paper"


def to_bibtex_entry(p: Dict[str, object]) -> str:
    title = _clean_space(str(p.get("title") or "Untitled"))
    authors = p.get("authors") or []
    if not isinstance(authors, list):
        authors = []
    author_field = " and ".join([_clean_space(str(x)) for x in authors if str(x).strip()]) or "Unknown"
    year = p.get("year")
    year_field = str(year) if year else "n.d."
    doi = _clean_space(str(p.get("doi") or ""))
    arxiv_id = _clean_space(str(p.get("arxiv_id") or ""))
    url = _clean_space(str(p.get("url") or p.get("pdf_url") or ""))
    venue = _clean_space(str(p.get("venue") or ""))

    key = f"{_first_author_short(authors)}{year_field}{_title_key(title)}"
    key = re.sub(r"[^A-Za-z0-9]+", "", key)[:64] or "refkey"

    lines = [f"@article{{{key},", f"  title = {{{title}}},"]
    lines.append(f"  author = {{{author_field}}},")
    if venue:
        lines.append(f"  journal = {{{venue}}},")
    if year:
        lines.append(f"  year = {{{year_field}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    elif arxiv_id:
        lines.append(f"  eprint = {{{arxiv_id}}},")
        lines.append("  archivePrefix = {arXiv},")
    if url:
        lines.append(f"  url = {{{url}}},")
    lines.append("}")
    return "\n".join(lines)


def build_related_work_pack(
    query: str,
    source: str = "all",
    max_results_per_source: int = 8,
    max_items_for_note: int = 8,
    timeout: int = 30,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    search = search_academic_papers(
        query=query,
        source=source,
        max_results_per_source=max_results_per_source,
        timeout=timeout,
        s2_api_key=s2_api_key,
    )
    papers = search.get("papers", [])
    if not isinstance(papers, list):
        papers = []
    top = papers[: max(1, min(max_items_for_note, 20))]

    bullets = []
    for i, p in enumerate(top, 1):
        title = _clean_space(str(p.get("title") or ""))
        year = p.get("year")
        venue = _clean_space(str(p.get("venue") or ""))
        authors = p.get("authors") or []
        first_author = str(authors[0]) if isinstance(authors, list) and authors else "Unknown"
        citations = p.get("citation_count")
        citation_text = f", cited {citations}" if isinstance(citations, int) and citations >= 0 else ""
        meta = ", ".join([x for x in [str(year) if year else "", venue] if x]) or "n.d."
        bullets.append(f"{i}. {first_author} et al. ({meta}{citation_text}): {title}")

    note = textwrap.dedent(
        f"""
        Related-work seed note for: "{query}"

        Candidate papers:
        {chr(10).join(bullets) if bullets else "- [无检索结果]"}

        Suggested writing angles:
        1. 按方法范式分组（physics-based / data-driven / hybrid）。
        2. 比较数据规模、工况覆盖、泛化能力与不确定性处理。
        3. 明确你工作的增量：问题设定、模型约束、实验设计或工程可部署性。
        """
    ).strip()

    bib_entries = [to_bibtex_entry(p) for p in top]
    return {
        "ok": bool(top),
        "query": query,
        "note_markdown": note,
        "papers": top,
        "bibtex_entries": bib_entries,
        "search_meta": {
            "source": source,
            "max_results_per_source": max_results_per_source,
            "errors": search.get("errors", {}),
            "count": search.get("count", 0),
        },
    }

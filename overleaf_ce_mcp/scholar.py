"""学术检索与相关工作素材生成（默认无 Key：arXiv + OpenAlex + Crossref）。"""

from __future__ import annotations

import csv
from difflib import SequenceMatcher
import json
import os
import re
import textwrap
from urllib.parse import quote
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


ARXIV_API_URL = "https://export.arxiv.org/api/query"
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_API_URL = "https://api.openalex.org/works"
CROSSREF_API_URL = "https://api.crossref.org/works"
LETPUB_BASE_URL = "https://www.letpub.com.cn"
UNPAYWALL_API_URL = "https://api.unpaywall.org/v2"
ZOTERO_API_BASE = "https://api.zotero.org"


JOURNAL_PRESETS: Dict[str, Dict[str, object]] = {
    "top_ai_conferences": {
        "name": "Top AI Conferences",
        "description": "常见顶会：NeurIPS/ICML/ICLR/CVPR/ICCV/ECCV/ACL/EMNLP/AAAI/IJCAI/KDD",
        "venues": [
            "Neural Information Processing Systems",
            "NeurIPS",
            "International Conference on Machine Learning",
            "ICML",
            "International Conference on Learning Representations",
            "ICLR",
            "Computer Vision and Pattern Recognition",
            "CVPR",
            "International Conference on Computer Vision",
            "ICCV",
            "European Conference on Computer Vision",
            "ECCV",
            "Annual Meeting of the Association for Computational Linguistics",
            "ACL",
            "Conference on Empirical Methods in Natural Language Processing",
            "EMNLP",
            "AAAI Conference on Artificial Intelligence",
            "AAAI",
            "International Joint Conference on Artificial Intelligence",
            "IJCAI",
            "ACM SIGKDD Conference on Knowledge Discovery and Data Mining",
            "KDD",
        ],
    },
    "nature_science_family": {
        "name": "Nature/Science Family",
        "description": "Nature、Science 及其高影响力子刊",
        "venues": [
            "Nature",
            "Nature Communications",
            "Nature Machine Intelligence",
            "Nature Methods",
            "Science",
            "Science Advances",
            "Science Robotics",
            "Science Translational Medicine",
        ],
    },
    "engineering_ocean": {
        "name": "Ocean & Engineering Journals",
        "description": "海洋与工程方向常见投稿期刊",
        "venues": [
            "Ocean Engineering",
            "Applied Ocean Research",
            "Marine Structures",
            "Coastal Engineering",
            "Engineering Applications of Artificial Intelligence",
            "Reliability Engineering & System Safety",
        ],
    },
    "cs_core_journals": {
        "name": "Core CS Journals",
        "description": "机器学习/计算机方向常见期刊",
        "venues": [
            "IEEE Transactions on Pattern Analysis and Machine Intelligence",
            "Pattern Recognition",
            "Machine Learning",
            "Journal of Machine Learning Research",
            "IEEE Transactions on Neural Networks and Learning Systems",
            "Artificial Intelligence",
            "Data Mining and Knowledge Discovery",
        ],
    },
}


def _request_text(
    method: str,
    url: str,
    timeout: int = 30,
    retries: int = 2,
    data: Optional[Dict[str, str]] = None,
) -> str:
    last_error: Optional[Exception] = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": f"{LETPUB_BASE_URL}/index.php?page=journalapp",
    }
    for _ in range(max(1, retries + 1)):
        try:
            if method.lower() == "post":
                resp = requests.post(url, data=data or {}, headers=headers, timeout=timeout)
            else:
                resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or resp.encoding
            return resp.text
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"请求失败: {url}; error={last_error}")


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


@dataclass
class AcademicSourceAdapter:
    key: str
    name: str
    capabilities: List[str]
    requires_api_key: bool
    api_key_env: Optional[str]
    enabled: bool
    skip_reason: Optional[str]
    search_fn: Callable[[str, int, int], List[PaperRecord]]


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


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _text_similarity(a: str, b: str) -> float:
    aa = _normalize_text(a)
    bb = _normalize_text(b)
    if not aa or not bb:
        return 0.0
    return float(SequenceMatcher(None, aa, bb).ratio())


def _author_last_names(authors: List[str]) -> List[str]:
    out: List[str] = []
    for au in authors:
        name = _clean_space(str(au))
        if not name:
            continue
        last = _normalize_text(name.split()[-1])
        if last:
            out.append(last)
    return out


def _match_venue(venue: str, target: str) -> bool:
    vv = _normalize_text(venue)
    tt = _normalize_text(target)
    if not vv or not tt:
        return False
    if tt in vv or vv in tt:
        return True
    acronym = "".join([x[0] for x in tt.split() if x])
    if len(acronym) >= 3 and acronym in vv.replace(" ", ""):
        return True
    return False


def _resolve_preset(key: str) -> Dict[str, object]:
    k = _normalize_text(key).replace(" ", "_")
    for pk, pv in JOURNAL_PRESETS.items():
        if pk == key or pk == k:
            return {"key": pk, **pv}
    raise ValueError(f"未找到期刊预设: {key}")


def list_journal_presets() -> Dict[str, object]:
    presets = []
    for key, item in JOURNAL_PRESETS.items():
        venues = item.get("venues") if isinstance(item, dict) else []
        if not isinstance(venues, list):
            venues = []
        presets.append(
            {
                "key": key,
                "name": str(item.get("name") if isinstance(item, dict) else key),
                "description": str(item.get("description") if isinstance(item, dict) else ""),
                "venue_count": len(venues),
                "sample_venues": venues[:5],
            }
        )
    presets.sort(key=lambda x: str(x["key"]))
    return {"ok": True, "count": len(presets), "presets": presets}


def _to_float_or_none(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_metric(text: str, key: str) -> Optional[float]:
    pattern = rf"{re.escape(key)}\s*[:：]\s*(\d+(?:\.\d+)?)"
    m = re.search(pattern, text or "", flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _is_yes(text: str) -> Optional[bool]:
    t = _normalize_text(text or "")
    if not t:
        return None
    if any(x in t for x in ("yes", "是", "oa")):
        if "no" not in t and "否" not in t:
            return True
    if any(x in t for x in ("no", "否")):
        return False
    return None


def letpub_search_journals(
    searchname: str,
    searchissn: str = "",
    searchfield: str = "",
    searchimpactlow: str = "",
    searchimpacthigh: str = "",
    timeout: int = 30,
    max_items: int = 30,
) -> Dict[str, object]:
    if not _clean_space(searchname) and not _clean_space(searchissn):
        raise ValueError("searchname 和 searchissn 至少提供一个")
    payload = {
        "searchname": _clean_space(searchname),
        "searchissn": _clean_space(searchissn),
        "searchfield": _clean_space(searchfield),
        "searchimpactlow": _clean_space(searchimpactlow),
        "searchimpacthigh": _clean_space(searchimpacthigh),
        "view": "search",
    }
    html = _request_text(
        "post",
        f"{LETPUB_BASE_URL}/index.php?page=journalapp&view=search",
        timeout=timeout,
        data=payload,
    )
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        m = re.search(r"journalid=(\d+).*view=detail", href)
        if not m:
            continue
        jid = m.group(1)
        if jid in seen:
            continue
        seen.add(jid)
        tr = a.find_parent("tr")
        tds = []
        if tr is not None:
            for td in tr.find_all("td"):
                tds.append(_clean_space(td.get_text(" ", strip=True)))
        metrics = tds[3] if len(tds) > 3 else ""
        name = _clean_space(a.get_text(" ", strip=True))
        out.append(
            {
                "journalid": jid,
                "name": name,
                "detail_url": f"{LETPUB_BASE_URL}/index.php?journalid={jid}&page=journalapp&view=detail",
                "issn": tds[0] if len(tds) > 0 else None,
                "letpub_score": _to_float_or_none(tds[2] if len(tds) > 2 else ""),
                "impact_factor": _extract_metric(metrics, "IF"),
                "h_index": int(_extract_metric(metrics, "h-index") or 0) if _extract_metric(metrics, "h-index") else None,
                "citescore": _extract_metric(metrics, "CiteScore"),
                "cas_partition": tds[4] if len(tds) > 4 else None,
                "discipline": tds[5] if len(tds) > 5 else None,
                "indexing": tds[6] if len(tds) > 6 else None,
                "is_oa": _is_yes(tds[7] if len(tds) > 7 else ""),
            }
        )
        if len(out) >= max(1, min(max_items, 100)):
            break
    return {
        "ok": bool(out),
        "query": {
            "searchname": payload["searchname"],
            "searchissn": payload["searchissn"],
            "searchfield": payload["searchfield"],
            "searchimpactlow": payload["searchimpactlow"],
            "searchimpacthigh": payload["searchimpacthigh"],
        },
        "count": len(out),
        "journals": out,
    }


def _letpub_find_field(field_map: Dict[str, str], keywords: List[str]) -> Optional[str]:
    for k, v in field_map.items():
        if all(x in k for x in keywords):
            return v
    return None


def letpub_get_journal_detail(journalid: str, timeout: int = 30) -> Dict[str, object]:
    jid = _clean_space(journalid)
    if not jid or not re.match(r"^\d+$", jid):
        raise ValueError("journalid 必须是数字字符串")
    url = f"{LETPUB_BASE_URL}/index.php?journalid={jid}&page=journalapp&view=detail"
    html = _request_text("get", url, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")

    field_map: Dict[str, str] = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        key = _clean_space(tds[0].get_text(" ", strip=True))
        val = _clean_space(tds[1].get_text(" ", strip=True))
        if key and val:
            field_map[key] = val

    title_tag = soup.find("title")
    page_title = _clean_space(title_tag.get_text(" ", strip=True)) if title_tag else ""
    journal_name = _letpub_find_field(field_map, ["期刊名字"]) or None
    latest_if = _letpub_find_field(field_map, ["最新影响因子"]) or ""
    h_index_raw = _letpub_find_field(field_map, ["h-index"]) or ""
    oa_raw = _letpub_find_field(field_map, ["是否OA"]) or ""

    detail = {
        "journalid": jid,
        "detail_url": url,
        "page_title": page_title,
        "journal_name": journal_name,
        "issn": _letpub_find_field(field_map, ["期刊ISSN"]) or _letpub_find_field(field_map, ["ISSN"]),
        "e_issn": _letpub_find_field(field_map, ["E-ISSN"]),
        "impact_factor_latest": _to_float_or_none(latest_if),
        "impact_factor_realtime": _to_float_or_none(_letpub_find_field(field_map, ["实时影响因子"]) or ""),
        "impact_factor_5y": _to_float_or_none(_letpub_find_field(field_map, ["五年影响因子"]) or ""),
        "jci": _to_float_or_none(_letpub_find_field(field_map, ["JCI"]) or ""),
        "h_index": int(_to_float_or_none(h_index_raw) or 0) if _to_float_or_none(h_index_raw) else None,
        "oa": _is_yes(oa_raw),
        "publisher": _letpub_find_field(field_map, ["出版商"]),
        "country_or_region": _letpub_find_field(field_map, ["出版国家"]),
        "language": _letpub_find_field(field_map, ["出版语言"]),
        "frequency": _letpub_find_field(field_map, ["出版周期"]),
        "founded_year": _letpub_find_field(field_map, ["出版年份"]),
        "journal_url": _letpub_find_field(field_map, ["期刊官方网站"]),
        "submission_url": _letpub_find_field(field_map, ["期刊投稿网址"]),
        "review_speed": _letpub_find_field(field_map, ["平均审稿速度"]),
        "online_publish_cycle": _letpub_find_field(field_map, ["在线出版周期"]),
        "jcr_partition": _letpub_find_field(field_map, ["WOS期刊JCR分区"]),
        "cas_partition": _letpub_find_field(field_map, ["中国科学院期刊分区"]),
    }
    return {
        "ok": True,
        "journalid": jid,
        "detail": detail,
        "raw_fields": field_map,
    }


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


def _dedup_records(raw: List[PaperRecord]) -> List[PaperRecord]:
    dedup: Dict[str, PaperRecord] = {}
    for p in raw:
        key = _key_for_dedup(p)
        old = dedup.get(key)
        if old is None:
            dedup[key] = p
            continue
        # 优先保留 citation_count 更高的条目。
        old_score = old.citation_count if isinstance(old.citation_count, int) else -1
        new_score = p.citation_count if isinstance(p.citation_count, int) else -1
        if new_score > old_score:
            dedup[key] = p
    out = list(dedup.values())
    out.sort(key=lambda x: (x.citation_count or -1, x.year or 0), reverse=True)
    return out


def _build_source_adapters(timeout: int, s2_api_key: Optional[str]) -> Dict[str, AcademicSourceAdapter]:
    s2_key = s2_api_key or os.environ.get("S2_API_KEY")

    return {
        "arxiv": AcademicSourceAdapter(
            key="arxiv",
            name="arXiv",
            capabilities=["search", "metadata", "abstract", "preprint"],
            requires_api_key=False,
            api_key_env=None,
            enabled=True,
            skip_reason=None,
            search_fn=lambda q, limit, t: search_arxiv(query=q, max_results=limit, timeout=t),
        ),
        "openalex": AcademicSourceAdapter(
            key="openalex",
            name="OpenAlex",
            capabilities=["search", "metadata", "citation_count", "oa_link"],
            requires_api_key=False,
            api_key_env=None,
            enabled=True,
            skip_reason=None,
            search_fn=lambda q, limit, t: search_openalex(query=q, per_page=limit, timeout=t),
        ),
        "crossref": AcademicSourceAdapter(
            key="crossref",
            name="Crossref",
            capabilities=["search", "doi_lookup", "metadata", "citation_count"],
            requires_api_key=False,
            api_key_env=None,
            enabled=True,
            skip_reason=None,
            search_fn=lambda q, limit, t: search_crossref(query=q, rows=limit, timeout=t),
        ),
        "semantic_scholar": AcademicSourceAdapter(
            key="semantic_scholar",
            name="Semantic Scholar",
            capabilities=["search", "metadata", "citation_count", "open_access_pdf"],
            requires_api_key=True,
            api_key_env="S2_API_KEY",
            enabled=bool(s2_key),
            skip_reason=None if s2_key else "skipped: S2_API_KEY not provided",
            search_fn=lambda q, limit, t: search_semantic_scholar(
                query=q,
                limit=limit,
                timeout=t,
                api_key=s2_key,
            ),
        ),
    }


def list_academic_source_capabilities(s2_api_key: Optional[str] = None, timeout: int = 30) -> Dict[str, object]:
    _ = timeout
    adapters = _build_source_adapters(timeout=30, s2_api_key=s2_api_key)
    sources = []
    for key in ("arxiv", "openalex", "crossref", "semantic_scholar"):
        ad = adapters[key]
        sources.append(
            {
                "key": ad.key,
                "name": ad.name,
                "enabled": ad.enabled,
                "requires_api_key": ad.requires_api_key,
                "api_key_env": ad.api_key_env,
                "capabilities": ad.capabilities,
                "skip_reason": ad.skip_reason,
            }
        )
    return {"ok": True, "count": len(sources), "sources": sources}


def search_academic_papers(
    query: str,
    source: str = "all",
    max_results_per_source: int = 8,
    timeout: int = 30,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    src = source.strip().lower()
    adapters = _build_source_adapters(timeout=timeout, s2_api_key=s2_api_key)
    valid_sources = {"all", *adapters.keys()}
    if src not in valid_sources:
        raise ValueError("source 仅支持 all/arxiv/openalex/crossref/semantic_scholar")

    chosen: List[AcademicSourceAdapter] = []
    if src == "all":
        chosen = [adapters["arxiv"], adapters["openalex"], adapters["crossref"], adapters["semantic_scholar"]]
    else:
        chosen = [adapters[src]]

    raw: List[PaperRecord] = []
    errors: Dict[str, str] = {}
    for adapter in chosen:
        if not adapter.enabled:
            if adapter.skip_reason:
                errors[adapter.key] = adapter.skip_reason
            continue
        try:
            raw.extend(adapter.search_fn(query, max_results_per_source, timeout))
        except Exception as exc:
            errors[adapter.key] = str(exc)

    papers = _dedup_records(raw)
    return {
        "ok": len(papers) > 0,
        "query": query,
        "source": src,
        "count": len(papers),
        "errors": errors,
        "papers": [p.to_dict() for p in papers],
    }


def search_in_journal_preset(
    query: str,
    journal_preset: str,
    source: str = "all",
    max_results_per_source: int = 12,
    timeout: int = 30,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    preset = _resolve_preset(journal_preset)
    venues = preset.get("venues", [])
    if not isinstance(venues, list):
        venues = []
    base = search_academic_papers(
        query=query,
        source=source,
        max_results_per_source=max_results_per_source,
        timeout=timeout,
        s2_api_key=s2_api_key,
    )
    papers = base.get("papers", [])
    if not isinstance(papers, list):
        papers = []

    matched = []
    for p in papers:
        if not isinstance(p, dict):
            continue
        venue = _clean_space(str(p.get("venue") or ""))
        if any(_match_venue(venue, str(v)) for v in venues):
            matched.append(p)

    matched.sort(key=lambda x: (x.get("citation_count") or -1, x.get("year") or 0), reverse=True)
    return {
        "ok": bool(matched),
        "query": query,
        "source": source,
        "preset": {"key": preset["key"], "name": preset["name"], "description": preset["description"]},
        "count": len(matched),
        "papers": matched,
        "search_meta": {
            "raw_count": base.get("count", 0),
            "errors": base.get("errors", {}),
        },
    }


def _crossref_work_to_record(item: Dict[str, object], source: str = "crossref") -> PaperRecord:
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
    cited_by = item.get("is-referenced-by-count")
    return PaperRecord(
        source=source,
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
        citation_count=cited_by if isinstance(cited_by, int) else None,
    )


def lookup_doi_crossref(doi: str, timeout: int = 30) -> Optional[PaperRecord]:
    d = _clean_space(doi)
    if not d:
        return None
    url = f"{CROSSREF_API_URL}/{d}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        msg = data.get("message", {}) if isinstance(data, dict) else {}
        if not isinstance(msg, dict):
            return None
        return _crossref_work_to_record(msg, source="crossref_doi")
    except Exception:
        return None


def _score_reference_match(
    expected_title: Optional[str],
    expected_authors: Optional[List[str]],
    expected_year: Optional[int],
    expected_venue: Optional[str],
    expected_doi: Optional[str],
    candidate: PaperRecord,
) -> Tuple[float, Dict[str, float]]:
    title_score = _text_similarity(expected_title or "", candidate.title) if expected_title else 0.65
    if expected_authors:
        exp_last = set(_author_last_names(expected_authors))
        cand_last = set(_author_last_names(candidate.authors))
        if exp_last and cand_last:
            author_score = len(exp_last.intersection(cand_last)) / max(1, len(exp_last))
        else:
            author_score = 0.0
    else:
        author_score = 0.5

    year_score = 0.5
    if expected_year and candidate.year:
        if int(expected_year) == int(candidate.year):
            year_score = 1.0
        elif abs(int(expected_year) - int(candidate.year)) == 1:
            year_score = 0.75
        else:
            year_score = 0.0
    elif expected_year:
        year_score = 0.0

    venue_score = _text_similarity(expected_venue or "", candidate.venue or "") if expected_venue else 0.5
    doi_bonus = 0.0
    if expected_doi and candidate.doi and _normalize_text(expected_doi) == _normalize_text(candidate.doi):
        doi_bonus = 0.2

    total = (
        0.5 * title_score
        + 0.2 * author_score
        + 0.2 * year_score
        + 0.1 * venue_score
        + doi_bonus
    )
    total = min(1.0, max(0.0, total))
    return total, {
        "title_score": round(title_score, 4),
        "author_score": round(author_score, 4),
        "year_score": round(year_score, 4),
        "venue_score": round(venue_score, 4),
        "doi_bonus": round(doi_bonus, 4),
    }


def verify_reference(
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    doi: Optional[str] = None,
    venue: Optional[str] = None,
    timeout: int = 30,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    if not _clean_space(str(title or "")) and not _clean_space(str(doi or "")):
        raise ValueError("title 和 doi 至少提供一个")

    expected_title = _clean_space(str(title or "")) or None
    expected_authors = [str(a).strip() for a in (authors or []) if str(a).strip()]
    expected_year = int(year) if year is not None else None
    expected_venue = _clean_space(str(venue or "")) or None
    expected_doi = _clean_space(str(doi or "")) or None

    candidates: List[PaperRecord] = []
    sources_checked: List[str] = []

    if expected_doi:
        sources_checked.append("crossref_doi")
        doi_record = lookup_doi_crossref(expected_doi, timeout=timeout)
        if doi_record:
            candidates.append(doi_record)

    query = expected_title or expected_doi or ""
    search = search_academic_papers(
        query=query,
        source="all",
        max_results_per_source=8,
        timeout=timeout,
        s2_api_key=s2_api_key,
    )
    source_used = search.get("source")
    if isinstance(source_used, str):
        sources_checked.append(source_used)
    for p in search.get("papers", []) if isinstance(search.get("papers"), list) else []:
        if not isinstance(p, dict):
            continue
        candidates.append(
            PaperRecord(
                source=_clean_space(str(p.get("source") or "unknown")),
                paper_id=_clean_space(str(p.get("paper_id") or p.get("doi") or p.get("title") or "")),
                title=_clean_space(str(p.get("title") or "")),
                abstract=_clean_space(str(p.get("abstract") or "")),
                authors=[str(x).strip() for x in (p.get("authors") or []) if str(x).strip()],
                year=p.get("year") if isinstance(p.get("year"), int) else _safe_year(str(p.get("year") or "")),
                venue=_clean_space(str(p.get("venue") or "")) or None,
                url=_clean_space(str(p.get("url") or "")) or None,
                pdf_url=_clean_space(str(p.get("pdf_url") or "")) or None,
                doi=_clean_space(str(p.get("doi") or "")) or None,
                arxiv_id=_clean_space(str(p.get("arxiv_id") or "")) or None,
                citation_count=p.get("citation_count") if isinstance(p.get("citation_count"), int) else None,
            )
        )

    dedup: Dict[str, PaperRecord] = {}
    for c in candidates:
        key = _key_for_dedup(c)
        if key not in dedup:
            dedup[key] = c
            continue
        old = dedup[key]
        old_score = old.citation_count if isinstance(old.citation_count, int) else -1
        new_score = c.citation_count if isinstance(c.citation_count, int) else -1
        if new_score > old_score:
            dedup[key] = c

    best: Optional[PaperRecord] = None
    best_score = -1.0
    best_breakdown: Dict[str, float] = {}
    for c in dedup.values():
        score, breakdown = _score_reference_match(
            expected_title=expected_title,
            expected_authors=expected_authors,
            expected_year=expected_year,
            expected_venue=expected_venue,
            expected_doi=expected_doi,
            candidate=c,
        )
        if score > best_score:
            best_score = score
            best = c
            best_breakdown = breakdown

    if not best:
        return {
            "ok": False,
            "verdict": "not_found",
            "confidence": 0.0,
            "matched_reference": None,
            "discrepancies": [],
            "sources_checked": sorted(set(sources_checked)),
            "corrected_bibtex": None,
        }

    verdict = "not_found"
    if best_score >= 0.85:
        verdict = "verified"
    elif best_score >= 0.5:
        verdict = "partial_match"

    discrepancies: List[str] = []
    if expected_title and _text_similarity(expected_title, best.title) < 0.9:
        discrepancies.append("标题不完全一致")
    if expected_year and best.year and int(expected_year) != int(best.year):
        discrepancies.append(f"年份不一致：输入 {expected_year}，匹配 {best.year}")
    if expected_doi and best.doi and _normalize_text(expected_doi) != _normalize_text(best.doi):
        discrepancies.append("DOI 不一致")
    if expected_venue and not _match_venue(expected_venue, best.venue or ""):
        discrepancies.append("期刊/会议名称不一致")

    matched = best.to_dict()
    bib = to_bibtex_entry(matched)
    return {
        "ok": verdict != "not_found",
        "verdict": verdict,
        "confidence": round(max(best_score, 0.0), 4),
        "matched_reference": matched,
        "discrepancies": discrepancies,
        "sources_checked": sorted(set(sources_checked)),
        "score_breakdown": best_breakdown,
        "corrected_bibtex": bib if verdict in ("verified", "partial_match") else None,
    }


def recommend_target_journals(
    topic: str,
    target_preference: str = "any",
    max_candidates: int = 5,
    max_results_per_source: int = 10,
    timeout: int = 30,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    if not topic or not topic.strip():
        raise ValueError("topic 不能为空")
    pref = _normalize_text(target_preference or "any")
    if pref not in ("any", "oa", "non_oa"):
        raise ValueError("target_preference 仅支持 any/oa/non_oa")
    top_n = max(3, min(int(max_candidates), 10))

    base = search_academic_papers(
        query=topic.strip(),
        source="all",
        max_results_per_source=max_results_per_source,
        timeout=timeout,
        s2_api_key=s2_api_key,
    )
    papers = base.get("papers", [])
    if not isinstance(papers, list):
        papers = []

    scored = []
    for key, preset in JOURNAL_PRESETS.items():
        venues = preset.get("venues", [])
        if not isinstance(venues, list):
            venues = []
        hits = []
        citation_sum = 0
        for p in papers:
            if not isinstance(p, dict):
                continue
            venue = _clean_space(str(p.get("venue") or ""))
            if any(_match_venue(venue, str(v)) for v in venues):
                hits.append(p)
                c = p.get("citation_count")
                if isinstance(c, int) and c > 0:
                    citation_sum += c
        if not hits:
            continue
        score = len(hits) * 2.0 + min(citation_sum / 200.0, 3.0)
        oa_hint = any("open" in _normalize_text(str(v)) for v in venues)
        if pref == "oa" and not oa_hint:
            score -= 0.4
        if pref == "non_oa" and oa_hint:
            score -= 0.2
        scored.append(
            {
                "preset_key": key,
                "journal_group": preset.get("name"),
                "description": preset.get("description"),
                "score": round(score, 4),
                "matched_papers": len(hits),
                "citation_sum": citation_sum,
                "sample_venues": sorted(
                    list({str(x.get("venue") or "") for x in hits if str(x.get("venue") or "").strip()})
                )[:5],
                "sample_titles": [str(x.get("title") or "") for x in hits[:3]],
            }
        )
    scored.sort(key=lambda x: (x["score"], x["matched_papers"]), reverse=True)
    shortlisted = scored[:top_n]

    return {
        "ok": bool(shortlisted),
        "topic": topic.strip(),
        "target_preference": pref,
        "count": len(shortlisted),
        "recommendations": shortlisted,
        "search_meta": {
            "raw_paper_count": base.get("count", 0),
            "errors": base.get("errors", {}),
        },
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


def _extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _clean_space(soup.get_text(" ", strip=True))


def _fetch_url_text(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    ctype = str(resp.headers.get("Content-Type") or "").lower()
    if "application/pdf" in ctype:
        # 当前不做 PDF 二进制解析，返回空，由上层走其他回退。
        return ""
    resp.encoding = resp.apparent_encoding or resp.encoding
    return _extract_html_text(resp.text)


def _openalex_lookup_by_doi(doi: str, timeout: int = 30) -> Optional[PaperRecord]:
    d = _clean_space(doi)
    if not d:
        return None
    doi_url = f"https://doi.org/{d}"
    url = f"{OPENALEX_API_URL}/{quote(doi_url, safe='')}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        item = resp.json()
        if not isinstance(item, dict):
            return None
        ids = item.get("ids") or {}
        if not isinstance(ids, dict):
            ids = {}
        primary_location = item.get("primary_location") or {}
        if not isinstance(primary_location, dict):
            primary_location = {}
        source_info = primary_location.get("source") or {}
        if not isinstance(source_info, dict):
            source_info = {}
        best_oa = item.get("best_oa_location") or {}
        if not isinstance(best_oa, dict):
            best_oa = {}
        open_access = item.get("open_access") or {}
        if not isinstance(open_access, dict):
            open_access = {}

        authors: List[str] = []
        for au in item.get("authorships", []) or []:
            if not isinstance(au, dict):
                continue
            ainfo = au.get("author") or {}
            if isinstance(ainfo, dict):
                name = _clean_space(str(ainfo.get("display_name") or ""))
                if name:
                    authors.append(name)
        return PaperRecord(
            source="openalex_doi",
            paper_id=_clean_space(str(item.get("id") or d)),
            title=_clean_space(str(item.get("display_name") or "")),
            abstract=_openalex_abstract(item.get("abstract_inverted_index")),
            authors=authors,
            year=item.get("publication_year") if isinstance(item.get("publication_year"), int) else None,
            venue=_clean_space(str(source_info.get("display_name") or "")) or None,
            url=_clean_space(str(primary_location.get("landing_page_url") or "")) or _clean_space(str(item.get("id") or "")) or None,
            pdf_url=_clean_space(str(best_oa.get("pdf_url") or "")) or _clean_space(str(open_access.get("oa_url") or "")) or None,
            doi=d,
            arxiv_id=_extract_arxiv_id(str(ids.get("arxiv") or "")),
            citation_count=item.get("cited_by_count") if isinstance(item.get("cited_by_count"), int) else None,
        )
    except Exception:
        return None


def _lookup_arxiv_by_id(arxiv_id: str, timeout: int = 30) -> Optional[PaperRecord]:
    aid = _extract_arxiv_id(arxiv_id)
    if not aid:
        return None
    try:
        resp = requests.get(
            ARXIV_API_URL,
            params={"id_list": aid, "max_results": 1},
            timeout=timeout,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None:
            return None
        title = _clean_space(entry.findtext("a:title", default="", namespaces=ns))
        abstract = _clean_space(entry.findtext("a:summary", default="", namespaces=ns))
        authors = []
        for au in entry.findall("a:author", ns):
            name = _clean_space(au.findtext("a:name", default="", namespaces=ns))
            if name:
                authors.append(name)
        abs_url = None
        pdf_url = None
        for link in entry.findall("a:link", ns):
            href = link.attrib.get("href")
            rel = link.attrib.get("rel", "")
            title_attr = link.attrib.get("title", "")
            if rel == "alternate" and href:
                abs_url = href
            if title_attr == "pdf" and href:
                pdf_url = href
        doi = None
        for child in list(entry):
            if child.tag.lower().endswith("doi"):
                doi = _clean_space(child.text or "") or None
        return PaperRecord(
            source="arxiv_lookup",
            paper_id=aid,
            title=title,
            abstract=abstract,
            authors=authors,
            year=_safe_year(entry.findtext("a:published", default="", namespaces=ns)),
            venue="arXiv",
            url=abs_url,
            pdf_url=pdf_url,
            doi=doi,
            arxiv_id=aid,
            citation_count=None,
        )
    except Exception:
        return None


def fetch_paper_fulltext(
    title: Optional[str] = None,
    doi: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    url: Optional[str] = None,
    timeout: int = 30,
    unpaywall_email: Optional[str] = None,
    s2_api_key: Optional[str] = None,
) -> Dict[str, object]:
    """按回退链获取论文正文或可用文本。

    回退链：
    1) Unpaywall（OA 链接，需邮箱）
    2) OpenAlex DOI
    3) Crossref DOI
    4) arXiv
    5) 直接 URL
    6) 标题检索后的摘要回退
    """

    q_title = _clean_space(str(title or "")) or None
    q_doi = _clean_space(str(doi or "")) or None
    q_arxiv = _extract_arxiv_id(arxiv_id) if arxiv_id else None
    q_url = _clean_space(str(url or "")) or None
    if not q_arxiv and q_url:
        q_arxiv = _extract_arxiv_id(q_url)
    if not q_doi and q_url and "doi.org/" in q_url:
        q_doi = q_url.split("doi.org/")[-1].strip()

    attempts: List[Dict[str, object]] = []

    def _ok(step: str, content: str, source_url: Optional[str], meta: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        return {
            "ok": True,
            "source": step,
            "source_url": source_url,
            "text_length": len(content),
            "content": content,
            "doi": q_doi,
            "arxiv_id": q_arxiv,
            "metadata": meta or {},
            "attempts": attempts,
        }

    # Step 1: Unpaywall
    if q_doi:
        email = _clean_space(str(unpaywall_email or os.environ.get("UNPAYWALL_EMAIL") or ""))
        if email:
            try:
                uurl = f"{UNPAYWALL_API_URL}/{quote(q_doi, safe='')}"
                resp = requests.get(uurl, params={"email": email}, timeout=timeout)
                resp.raise_for_status()
                data = resp.json() if resp.text else {}
                oa_url = None
                if isinstance(data, dict):
                    best = data.get("best_oa_location") or {}
                    if isinstance(best, dict):
                        oa_url = _clean_space(str(best.get("url_for_landing_page") or best.get("url") or ""))
                    if not oa_url:
                        oa_url = _clean_space(str(data.get("url") or ""))
                if oa_url:
                    text = _fetch_url_text(oa_url, timeout=timeout)
                    attempts.append({"step": "unpaywall", "ok": bool(text), "url": oa_url})
                    if text:
                        return _ok("unpaywall", text, oa_url, {"doi": q_doi})
                else:
                    attempts.append({"step": "unpaywall", "ok": False, "reason": "oa_url_not_found"})
            except Exception as exc:
                attempts.append({"step": "unpaywall", "ok": False, "reason": str(exc)})
        else:
            attempts.append({"step": "unpaywall", "ok": False, "reason": "UNPAYWALL_EMAIL not provided"})

    # Step 2: OpenAlex DOI
    if q_doi:
        rec = _openalex_lookup_by_doi(q_doi, timeout=timeout)
        if rec:
            if rec.url:
                try:
                    txt = _fetch_url_text(rec.url, timeout=timeout)
                    attempts.append({"step": "openalex_doi.url", "ok": bool(txt), "url": rec.url})
                    if txt:
                        return _ok("openalex_doi_url", txt, rec.url, rec.to_dict())
                except Exception as exc:
                    attempts.append({"step": "openalex_doi.url", "ok": False, "reason": str(exc)})
            if rec.abstract:
                attempts.append({"step": "openalex_doi.abstract", "ok": True})
                return _ok("openalex_doi_abstract", rec.abstract, rec.url, rec.to_dict())
        else:
            attempts.append({"step": "openalex_doi", "ok": False, "reason": "not_found"})

    # Step 3: Crossref DOI
    if q_doi:
        rec = lookup_doi_crossref(q_doi, timeout=timeout)
        if rec and rec.abstract:
            attempts.append({"step": "crossref_doi.abstract", "ok": True})
            return _ok("crossref_doi_abstract", rec.abstract, rec.url, rec.to_dict())
        attempts.append({"step": "crossref_doi", "ok": bool(rec), "reason": "no_abstract" if rec else "not_found"})

    # Step 4: arXiv
    if q_arxiv:
        rec = _lookup_arxiv_by_id(q_arxiv, timeout=timeout)
        if rec:
            if rec.url:
                try:
                    txt = _fetch_url_text(rec.url, timeout=timeout)
                    attempts.append({"step": "arxiv.url", "ok": bool(txt), "url": rec.url})
                    if txt:
                        return _ok("arxiv_url", txt, rec.url, rec.to_dict())
                except Exception as exc:
                    attempts.append({"step": "arxiv.url", "ok": False, "reason": str(exc)})
            if rec.abstract:
                attempts.append({"step": "arxiv.abstract", "ok": True})
                return _ok("arxiv_abstract", rec.abstract, rec.url, rec.to_dict())
        else:
            attempts.append({"step": "arxiv", "ok": False, "reason": "not_found"})

    # Step 5: direct URL
    if q_url:
        try:
            txt = _fetch_url_text(q_url, timeout=timeout)
            attempts.append({"step": "direct_url", "ok": bool(txt), "url": q_url})
            if txt:
                return _ok("direct_url", txt, q_url)
        except Exception as exc:
            attempts.append({"step": "direct_url", "ok": False, "reason": str(exc)})

    # Step 6: title fallback
    if q_title:
        try:
            res = search_academic_papers(
                query=q_title,
                source="all",
                max_results_per_source=5,
                timeout=timeout,
                s2_api_key=s2_api_key,
            )
            papers = res.get("papers", []) if isinstance(res.get("papers"), list) else []
            if papers:
                first = papers[0] if isinstance(papers[0], dict) else {}
                abs_text = _clean_space(str(first.get("abstract") or ""))
                if abs_text:
                    attempts.append({"step": "title_search.abstract", "ok": True})
                    return _ok("title_search_abstract", abs_text, _clean_space(str(first.get("url") or "")) or None, first)
            attempts.append({"step": "title_search", "ok": False, "reason": "no_abstract"})
        except Exception as exc:
            attempts.append({"step": "title_search", "ok": False, "reason": str(exc)})

    return {
        "ok": False,
        "source": None,
        "source_url": None,
        "text_length": 0,
        "content": "",
        "doi": q_doi,
        "arxiv_id": q_arxiv,
        "metadata": {},
        "attempts": attempts,
    }


def _zotero_api_headers(api_key: str) -> Dict[str, str]:
    return {
        "Zotero-API-Key": api_key,
        "Content-Type": "application/json",
    }


def _zotero_base_path(library_type: str, library_id: str) -> str:
    lt = _clean_space(library_type or "user").lower()
    if lt not in ("user", "group"):
        raise ValueError("library_type 仅支持 user/group")
    if not re.match(r"^\d+$", _clean_space(library_id)):
        raise ValueError("library_id 必须是数字字符串")
    return f"{lt}s/{_clean_space(library_id)}"


def zotero_list_items(
    library_id: str,
    api_key: str,
    library_type: str = "user",
    limit: int = 50,
    query: Optional[str] = None,
    timeout: int = 30,
) -> List[Dict[str, object]]:
    base = _zotero_base_path(library_type, library_id)
    params: Dict[str, object] = {
        "limit": max(1, min(int(limit), 100)),
        "format": "json",
    }
    q = _clean_space(str(query or ""))
    if q:
        params["q"] = q
    resp = requests.get(
        f"{ZOTERO_API_BASE}/{base}/items/top",
        headers=_zotero_api_headers(api_key),
        params=params,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []
    out: List[Dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        payload = item.get("data") or {}
        if not isinstance(payload, dict):
            continue
        creators = payload.get("creators") or []
        authors: List[str] = []
        if isinstance(creators, list):
            for c in creators:
                if not isinstance(c, dict):
                    continue
                first = _clean_space(str(c.get("firstName") or ""))
                last = _clean_space(str(c.get("lastName") or ""))
                nm = _clean_space(f"{first} {last}")
                if nm:
                    authors.append(nm)
        doi = _clean_space(str(payload.get("DOI") or "")) or None
        title = _clean_space(str(payload.get("title") or ""))
        url = _clean_space(str(payload.get("url") or "")) or None
        venue = _clean_space(str(payload.get("publicationTitle") or payload.get("proceedingsTitle") or "")) or None
        year = _safe_year(str(payload.get("date") or ""))
        out.append(
            {
                "key": _clean_space(str(item.get("key") or "")),
                "item_type": _clean_space(str(payload.get("itemType") or "")),
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "doi": doi,
                "url": url,
                "raw": payload,
            }
        )
    return out


def _ensure_reading_queue(path: str) -> None:
    p = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8", newline="") as fw:
            writer = csv.DictWriter(
                fw,
                fieldnames=["title", "source", "url_or_doi", "priority", "status", "notes"],
            )
            writer.writeheader()


def _load_reading_queue(path: str) -> List[Dict[str, str]]:
    _ensure_reading_queue(path)
    out: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8", newline="") as fr:
        reader = csv.DictReader(fr)
        for row in reader:
            if isinstance(row, dict):
                out.append({str(k): _clean_space(str(v or "")) for k, v in row.items()})
    return out


def _append_reading_queue(path: str, rows: List[Dict[str, str]]) -> int:
    if not rows:
        return 0
    _ensure_reading_queue(path)
    with open(path, "a", encoding="utf-8", newline="") as fw:
        writer = csv.DictWriter(
            fw,
            fieldnames=["title", "source", "url_or_doi", "priority", "status", "notes"],
        )
        for row in rows:
            writer.writerow(
                {
                    "title": row.get("title", ""),
                    "source": row.get("source", ""),
                    "url_or_doi": row.get("url_or_doi", ""),
                    "priority": row.get("priority", "medium"),
                    "status": row.get("status", "todo"),
                    "notes": row.get("notes", ""),
                }
            )
    return len(rows)


def _zotero_item_to_bib(item: Dict[str, object]) -> str:
    return to_bibtex_entry(
        {
            "title": item.get("title"),
            "authors": item.get("authors"),
            "year": item.get("year"),
            "venue": item.get("venue"),
            "doi": item.get("doi"),
            "url": item.get("url"),
            "arxiv_id": _extract_arxiv_id(str(item.get("url") or "")),
        }
    )


def _append_bib(path: str, entries: List[str]) -> int:
    if not entries:
        return 0
    p = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as fw:
            fw.write("% Raw references collected from tools\n")
    with open(p, "a", encoding="utf-8") as fw:
        fw.write("\n\n".join([x for x in entries if _clean_space(x)]))
        fw.write("\n")
    return len(entries)


def _build_zotero_payload_from_queue(rows: List[Dict[str, str]], max_items: int = 20) -> List[Dict[str, object]]:
    payload = []
    seen = set()
    for row in rows:
        title = _clean_space(row.get("title", ""))
        if not title:
            continue
        ident = _clean_space(row.get("url_or_doi", ""))
        key = (title.lower(), ident.lower())
        if key in seen:
            continue
        seen.add(key)
        data: Dict[str, object] = {
            "itemType": "journalArticle",
            "title": title,
            "url": ident if ident.startswith("http") else "",
        }
        if ident and not ident.startswith("http"):
            data["DOI"] = ident
        payload.append(data)
        if len(payload) >= max_items:
            break
    return payload


def sync_zotero_paper_state(
    project_dir: str,
    direction: str = "pull",
    library_id: Optional[str] = None,
    api_key: Optional[str] = None,
    library_type: str = "user",
    limit: int = 50,
    query: Optional[str] = None,
    timeout: int = 30,
    dry_run: bool = True,
) -> Dict[str, object]:
    root = os.path.abspath(os.path.expanduser(project_dir))
    if not os.path.isdir(root):
        raise ValueError("project_dir 不是有效目录: %s" % root)

    d = _clean_space(direction).lower()
    if d not in ("pull", "push", "bidirectional"):
        raise ValueError("direction 仅支持 pull/push/bidirectional")

    lib_id = _clean_space(library_id or os.environ.get("ZOTERO_LIBRARY_ID") or "")
    key = _clean_space(api_key or os.environ.get("ZOTERO_API_KEY") or "")

    reading_queue = os.path.join(root, "paper_state", "inputs", "literature", "reading_queue.csv")
    refs_raw_bib = os.path.join(root, "paper_state", "inputs", "literature", "refs_raw.bib")
    _ensure_reading_queue(reading_queue)

    result: Dict[str, object] = {
        "ok": True,
        "project_dir": root,
        "direction": d,
        "dry_run": bool(dry_run),
        "paths": {
            "reading_queue": reading_queue,
            "refs_raw_bib": refs_raw_bib,
        },
        "pull": None,
        "push": None,
    }

    if d in ("pull", "bidirectional"):
        if not lib_id or not key:
            raise ValueError("pull/bidirectional 需要 library_id 与 api_key（或环境变量 ZOTERO_LIBRARY_ID/ZOTERO_API_KEY）")
        items = zotero_list_items(
            library_id=lib_id,
            api_key=key,
            library_type=library_type,
            limit=limit,
            query=query,
            timeout=timeout,
        )
        existing_rows = _load_reading_queue(reading_queue)
        existing_keys = set()
        for r in existing_rows:
            existing_keys.add((_clean_space(r.get("title", "")).lower(), _clean_space(r.get("url_or_doi", "")).lower()))

        new_rows: List[Dict[str, str]] = []
        bib_entries: List[str] = []
        for item in items:
            ident = _clean_space(str(item.get("doi") or item.get("url") or ""))
            key2 = (_clean_space(str(item.get("title") or "")).lower(), ident.lower())
            if key2 in existing_keys:
                continue
            existing_keys.add(key2)
            new_rows.append(
                {
                    "title": _clean_space(str(item.get("title") or "")),
                    "source": "zotero",
                    "url_or_doi": ident,
                    "priority": "medium",
                    "status": "todo",
                    "notes": f"zotero_key={_clean_space(str(item.get('key') or ''))}",
                }
            )
            bib_entries.append(_zotero_item_to_bib(item))

        written_rows = 0
        written_bib = 0
        if not dry_run:
            written_rows = _append_reading_queue(reading_queue, new_rows)
            written_bib = _append_bib(refs_raw_bib, bib_entries)
        result["pull"] = {
            "fetched_items": len(items),
            "new_rows": len(new_rows),
            "new_bib_entries": len(bib_entries),
            "written_rows": written_rows,
            "written_bib_entries": written_bib,
        }

    if d in ("push", "bidirectional"):
        rows = _load_reading_queue(reading_queue)
        payload = _build_zotero_payload_from_queue(rows, max_items=min(max(1, int(limit)), 50))
        push_info: Dict[str, object] = {
            "candidate_count": len(payload),
            "posted_count": 0,
        }
        if dry_run:
            push_info["preview"] = payload[:5]
        else:
            if not lib_id or not key:
                raise ValueError("push 需要 library_id 与 api_key（或环境变量 ZOTERO_LIBRARY_ID/ZOTERO_API_KEY）")
            base = _zotero_base_path(library_type, lib_id)
            resp = requests.post(
                f"{ZOTERO_API_BASE}/{base}/items",
                headers=_zotero_api_headers(key),
                data=json.dumps(payload, ensure_ascii=False),
                timeout=timeout,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"zotero push 失败: {resp.status_code} {resp.text[:500]}")
            data = resp.json() if resp.text else {}
            success = data.get("successful") if isinstance(data, dict) else {}
            posted_count = len(success) if isinstance(success, dict) else len(payload)
            push_info["posted_count"] = posted_count
            push_info["response"] = data
        result["push"] = push_info

    return result

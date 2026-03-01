from pathlib import Path

from overleaf_ce_mcp import scholar
from overleaf_ce_mcp.template import init_paper_state_workspace


def test_list_academic_source_capabilities_without_s2(monkeypatch):
    monkeypatch.delenv("S2_API_KEY", raising=False)
    res = scholar.list_academic_source_capabilities()
    assert res["ok"] is True
    by_key = {x["key"]: x for x in res["sources"]}
    assert by_key["arxiv"]["enabled"] is True
    assert by_key["openalex"]["enabled"] is True
    assert by_key["crossref"]["enabled"] is True
    assert by_key["semantic_scholar"]["enabled"] is False
    assert by_key["openreview"]["enabled"] is True


def test_fetch_paper_fulltext_fallback_to_crossref(monkeypatch):
    monkeypatch.setattr(scholar, "_openalex_lookup_by_doi", lambda doi, timeout=30: None)
    monkeypatch.setattr(
        scholar,
        "lookup_doi_crossref",
        lambda doi, timeout=30: scholar.PaperRecord(
            source="crossref_doi",
            paper_id=doi,
            title="Demo",
            abstract="This is crossref abstract.",
            authors=["A"],
            year=2024,
            venue="J",
            url="https://doi.org/" + doi,
            pdf_url=None,
            doi=doi,
            arxiv_id=None,
            citation_count=1,
        ),
    )
    res = scholar.fetch_paper_fulltext(doi="10.1000/demo", timeout=1)
    assert res["ok"] is True
    assert res["source"] == "crossref_doi_abstract"
    assert "crossref abstract" in res["content"]


def test_fetch_paper_fulltext_title_search_fallback(monkeypatch):
    monkeypatch.setattr(
        scholar,
        "search_academic_papers",
        lambda **kwargs: {
            "ok": True,
            "papers": [
                {
                    "title": "Demo",
                    "abstract": "Fallback abstract text.",
                    "url": "https://example.com/p",
                }
            ],
        },
    )
    res = scholar.fetch_paper_fulltext(title="demo topic", timeout=1)
    assert res["ok"] is True
    assert res["source"] == "title_search_abstract"
    assert "Fallback abstract" in res["content"]


def test_sync_zotero_paper_state_push_dry_run(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    q = Path(tmp_path) / "paper_state" / "inputs" / "literature" / "reading_queue.csv"
    q.write_text(
        "title,source,url_or_doi,priority,status,notes\n"
        "A Demo Paper,manual,10.1000/a,high,todo,\n",
        encoding="utf-8",
    )
    res = scholar.sync_zotero_paper_state(
        project_dir=str(tmp_path),
        direction="push",
        dry_run=True,
    )
    assert res["ok"] is True
    assert res["push"]["candidate_count"] == 1
    assert isinstance(res["push"].get("preview"), list)


def test_sync_zotero_paper_state_pull_write(monkeypatch, tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")

    monkeypatch.setattr(
        scholar,
        "zotero_list_items",
        lambda **kwargs: [
            {
                "key": "ABCD1234",
                "title": "Zotero Pulled Paper",
                "authors": ["Alice Smith"],
                "year": 2023,
                "venue": "Ocean Engineering",
                "doi": "10.1000/zotero-demo",
                "url": "https://doi.org/10.1000/zotero-demo",
            }
        ],
    )

    res = scholar.sync_zotero_paper_state(
        project_dir=str(tmp_path),
        direction="pull",
        library_id="1",
        api_key="demo",
        dry_run=False,
    )
    assert res["ok"] is True
    assert res["pull"]["new_rows"] == 1

    q = Path(res["paths"]["reading_queue"])
    b = Path(res["paths"]["refs_raw_bib"])
    assert q.exists()
    assert b.exists()
    assert "Zotero Pulled Paper" in q.read_text(encoding="utf-8")
    assert "10.1000/zotero-demo" in b.read_text(encoding="utf-8")


def test_search_openreview_papers_parse(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return {
                "notes": [
                    {
                        "id": "abc123",
                        "cdate": 1740787200000,
                        "content": {
                            "title": {"value": "Diffusion Models for X"},
                            "abstract": {"value": "We propose ..."},
                            "authors": {"value": ["Alice", "Bob"]},
                        },
                    }
                ]
            }

    monkeypatch.setattr(scholar.requests, "get", lambda *args, **kwargs: _Resp())
    out = scholar.search_openreview_papers(query="diffusion", venue="ICLR", year=2025, limit=5, timeout=1)
    assert len(out) == 1
    assert out[0].source == "openreview"
    assert out[0].paper_id == "abc123"
    assert out[0].year == 2025


def test_search_academic_papers_openreview_source(monkeypatch):
    monkeypatch.setattr(
        scholar,
        "search_openreview_papers",
        lambda **kwargs: [
            scholar.PaperRecord(
                source="openreview",
                paper_id="n1",
                title="Demo",
                abstract="A",
                authors=["A"],
                year=2025,
                venue="ICLR.cc 2025",
                url="https://openreview.net/forum?id=n1",
                pdf_url="https://openreview.net/pdf?id=n1",
                doi=None,
                arxiv_id=None,
                citation_count=None,
            )
        ],
    )
    res = scholar.search_academic_papers(query="demo", source="openreview", max_results_per_source=3)
    assert res["ok"] is True
    assert res["count"] == 1

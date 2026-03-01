from overleaf_ce_mcp import scholar


def test_list_journal_presets():
    res = scholar.list_journal_presets()
    assert res["ok"] is True
    assert res["count"] >= 3
    keys = {x["key"] for x in res["presets"]}
    assert "top_ai_conferences" in keys


def test_search_in_journal_preset_filters(monkeypatch):
    def fake_search_academic_papers(**kwargs):
        return {
            "ok": True,
            "count": 3,
            "errors": {},
            "papers": [
                {"title": "A", "venue": "Neural Information Processing Systems", "citation_count": 100, "year": 2024},
                {"title": "B", "venue": "Random Journal", "citation_count": 10, "year": 2024},
                {"title": "C", "venue": "ICML", "citation_count": 80, "year": 2023},
            ],
        }

    monkeypatch.setattr(scholar, "search_academic_papers", fake_search_academic_papers)
    res = scholar.search_in_journal_preset(
        query="llm",
        journal_preset="top_ai_conferences",
    )
    assert res["ok"] is True
    assert res["count"] == 2
    assert {x["title"] for x in res["papers"]} == {"A", "C"}


def test_recommend_target_journals(monkeypatch):
    def fake_search_academic_papers(**kwargs):
        return {
            "ok": True,
            "count": 4,
            "errors": {},
            "papers": [
                {"title": "A", "venue": "Ocean Engineering", "citation_count": 60, "year": 2024},
                {"title": "B", "venue": "Applied Ocean Research", "citation_count": 40, "year": 2023},
                {"title": "C", "venue": "ICLR", "citation_count": 200, "year": 2024},
                {"title": "D", "venue": "Nature Communications", "citation_count": 120, "year": 2022},
            ],
        }

    monkeypatch.setattr(scholar, "search_academic_papers", fake_search_academic_papers)
    res = scholar.recommend_target_journals(
        topic="ocean ai",
        target_preference="any",
        max_candidates=5,
    )
    assert res["ok"] is True
    assert res["count"] >= 1
    assert len(res["recommendations"]) >= 1


def test_verify_reference_verified_by_doi(monkeypatch):
    doi_record = scholar.PaperRecord(
        source="crossref_doi",
        paper_id="10.1000/demo",
        title="Attention Is All You Need",
        abstract="",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017,
        venue="NeurIPS",
        url="https://doi.org/10.1000/demo",
        pdf_url=None,
        doi="10.1000/demo",
        arxiv_id=None,
        citation_count=999,
    )

    monkeypatch.setattr(scholar, "lookup_doi_crossref", lambda doi, timeout=30: doi_record)
    monkeypatch.setattr(
        scholar,
        "search_academic_papers",
        lambda **kwargs: {"ok": True, "count": 0, "errors": {}, "source": "all", "papers": []},
    )

    res = scholar.verify_reference(
        title="Attention Is All You Need",
        authors=["Vaswani"],
        year=2017,
        doi="10.1000/demo",
        venue="NeurIPS",
    )
    assert res["verdict"] == "verified"
    assert res["confidence"] >= 0.85
    assert "@article" in (res["corrected_bibtex"] or "")

from overleaf_ce_mcp import scholar


def _rec(source: str, paper_id: str):
    return scholar.PaperRecord(
        source=source,
        paper_id=paper_id,
        title=f"title-{paper_id}",
        abstract="",
        authors=["A"],
        year=2024,
        venue=source,
        url=f"https://example.com/{paper_id}",
        pdf_url=None,
        doi=f"10.1000/{paper_id}",
        arxiv_id=None,
        citation_count=1,
    )


def test_search_academic_papers_all_without_s2_key(monkeypatch):
    monkeypatch.delenv("S2_API_KEY", raising=False)
    monkeypatch.setattr(scholar, "search_arxiv", lambda **kwargs: [_rec("arxiv", "a1")])
    monkeypatch.setattr(scholar, "search_openalex", lambda **kwargs: [_rec("openalex", "o1")])
    monkeypatch.setattr(scholar, "search_crossref", lambda **kwargs: [_rec("crossref", "c1")])

    def _should_not_call_semantic(**kwargs):
        raise AssertionError("all 模式无 key 不应调用 semantic scholar")

    monkeypatch.setattr(scholar, "search_semantic_scholar", _should_not_call_semantic)

    res = scholar.search_academic_papers(
        query="offshore wave load prediction",
        source="all",
        max_results_per_source=5,
    )
    assert res["ok"] is True
    assert res["count"] == 3
    assert "semantic_scholar" in res["errors"]
    assert str(res["errors"]["semantic_scholar"]).startswith("skipped:")


def test_search_academic_papers_all_with_s2_key(monkeypatch):
    monkeypatch.setenv("S2_API_KEY", "demo-key")
    monkeypatch.setattr(scholar, "search_arxiv", lambda **kwargs: [_rec("arxiv", "a1")])
    monkeypatch.setattr(scholar, "search_openalex", lambda **kwargs: [_rec("openalex", "o1")])
    monkeypatch.setattr(scholar, "search_crossref", lambda **kwargs: [_rec("crossref", "c1")])

    called = {"s2": False}

    def _semantic(**kwargs):
        called["s2"] = True
        return [_rec("semantic_scholar", "s1")]

    monkeypatch.setattr(scholar, "search_semantic_scholar", _semantic)

    res = scholar.search_academic_papers(
        query="offshore wave load prediction",
        source="all",
        max_results_per_source=5,
    )
    assert res["ok"] is True
    assert called["s2"] is True
    assert res["count"] == 4


def test_search_academic_papers_supports_openalex_and_crossref(monkeypatch):
    monkeypatch.setattr(scholar, "search_openalex", lambda **kwargs: [_rec("openalex", "o1")])
    res_openalex = scholar.search_academic_papers(query="q", source="openalex")
    assert res_openalex["ok"] is True
    assert res_openalex["count"] == 1

    monkeypatch.setattr(scholar, "search_crossref", lambda **kwargs: [_rec("crossref", "c1")])
    res_crossref = scholar.search_academic_papers(query="q", source="crossref")
    assert res_crossref["ok"] is True
    assert res_crossref["count"] == 1

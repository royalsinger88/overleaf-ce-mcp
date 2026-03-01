from overleaf_ce_mcp import scholar


def test_letpub_search_journals_parse(monkeypatch):
    html = """
    <html><body>
      <table>
        <tr>
          <td>0029-8018</td>
          <td><a href="./index.php?journalid=6334&page=journalapp&view=detail">Ocean Engineering</a></td>
          <td>8.3</td>
          <td>IF: 5.5 h-index: 80 CiteScore: 8.40</td>
          <td>2区</td>
          <td>大类：工程技术</td>
          <td>SCI SCIE</td>
          <td>No</td>
        </tr>
      </table>
    </body></html>
    """
    monkeypatch.setattr(scholar, "_request_text", lambda *args, **kwargs: html)
    res = scholar.letpub_search_journals(searchname="Ocean Engineering")
    assert res["ok"] is True
    assert res["count"] == 1
    j = res["journals"][0]
    assert j["journalid"] == "6334"
    assert j["name"] == "Ocean Engineering"
    assert j["impact_factor"] == 5.5
    assert j["h_index"] == 80
    assert j["citescore"] == 8.4
    assert j["is_oa"] is False


def test_letpub_get_journal_detail_parse(monkeypatch):
    html = """
    <html><head><title>【LetPub】Ocean Engineering 影响因子5.5分</title></head><body>
      <table>
        <tr><td>期刊名字</td><td>Ocean Engineering OCEAN ENG</td></tr>
        <tr><td>期刊ISSN</td><td>0029-8018</td></tr>
        <tr><td>E-ISSN</td><td>1873-5258</td></tr>
        <tr><td>2024-2025最新影响因子 （数据来源于搜索引擎）</td><td>5.5</td></tr>
        <tr><td>实时影响因子</td><td>截止2026年1月20日：5.6</td></tr>
        <tr><td>五年影响因子</td><td>5.2</td></tr>
        <tr><td>JCI期刊引文指标</td><td>1.2</td></tr>
        <tr><td>h-index</td><td>80</td></tr>
        <tr><td>期刊官方网站</td><td>https://www.sciencedirect.com/journal/ocean-engineering</td></tr>
        <tr><td>期刊投稿网址</td><td>https://www.editorialmanager.com/OENG</td></tr>
        <tr><td>是否OA开放访问</td><td>No</td></tr>
        <tr><td>出版商</td><td>Elsevier</td></tr>
        <tr><td>出版国家或地区</td><td>NETHERLANDS</td></tr>
        <tr><td>出版语言</td><td>English</td></tr>
        <tr><td>出版周期</td><td>Monthly</td></tr>
        <tr><td>出版年份</td><td>1973</td></tr>
        <tr><td>平均审稿速度</td><td>2.4个月</td></tr>
        <tr><td>在线出版周期</td><td>6.7周</td></tr>
        <tr><td>WOS期刊JCR分区 （ 2024-2025年最新版 ）</td><td>1区</td></tr>
        <tr><td>中国科学院期刊分区 （ 2025年3月最新升级版 ）</td><td>2区</td></tr>
      </table>
    </body></html>
    """
    monkeypatch.setattr(scholar, "_request_text", lambda *args, **kwargs: html)
    res = scholar.letpub_get_journal_detail("6334")
    assert res["ok"] is True
    d = res["detail"]
    assert d["journalid"] == "6334"
    assert d["impact_factor_latest"] == 5.5
    assert d["h_index"] == 80
    assert d["publisher"] == "Elsevier"
    assert d["oa"] is False


def test_letpub_get_journal_detail_invalid_id():
    try:
        scholar.letpub_get_journal_detail("abc")
        raise AssertionError("应该抛出 ValueError")
    except ValueError:
        pass

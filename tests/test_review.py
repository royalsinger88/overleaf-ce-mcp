import datetime as dt
import json
from pathlib import Path

from overleaf_ce_mcp.review import generate_daily_review, generate_weekly_summary
from overleaf_ce_mcp.template import init_paper_state_workspace


def _write_round(project_root: Path, round_idx: int, when_iso: str, improvement: float, new_evidence_count: int) -> None:
    round_dir = project_root / "paper_state" / "outputs" / "optimization_loop" / f"round_{round_idx:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "round_index": round_idx,
        "stage": "r1" if round_idx == 1 else "r2",
        "generated_at": when_iso,
        "score": 0.8 + (round_idx * 0.01),
        "improvement": improvement,
        "paper_count": 10,
        "verifiable_count": 8,
        "verifiable_ratio": 0.8,
        "new_evidence_count": new_evidence_count,
        "prompt_count": 6,
        "title_candidates": ["T1", "T2"],
        "innovation_points": ["P1", "P2"],
        "next_actions": ["补实验 A", "补图 B"],
        "journal_recommendation_top": None,
        "paths": {},
    }
    (round_dir / "round_result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _append_claim(project_root: Path, claim: str, source: str, status: str, recorded_at: str) -> None:
    fp = project_root / "paper_state" / "memory" / "claim_evidence.jsonl"
    row = {
        "claim_id": "C001",
        "claim": claim,
        "source_type": "doi",
        "source": source,
        "recorded_at": recorded_at,
        "confidence": "high",
        "status": status,
        "note": "",
    }
    with fp.open("a", encoding="utf-8") as fw:
        fw.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_generate_daily_review(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    day = dt.date(2026, 3, 1)
    ts = dt.datetime(2026, 3, 1, 9, 30, tzinfo=dt.timezone.utc).isoformat()
    _write_round(tmp_path, round_idx=1, when_iso=ts, improvement=-0.01, new_evidence_count=0)
    _append_claim(tmp_path, "Claim A", "10.1000/a", "candidate", ts)
    _append_claim(tmp_path, "Claim B", "10.1000/b", "rejected", ts)

    res = generate_daily_review(project_dir=str(tmp_path), day=day.isoformat(), overwrite=True, write_state=True)
    assert res["ok"] is True
    out = Path(res["path"])
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Daily Review - 2026-03-01" in text
    assert "Claim A" in text
    assert "Claim B" in text

    state = Path(res["state_path"])
    assert state.exists()
    state_obj = json.loads(state.read_text(encoding="utf-8"))
    assert state_obj["daily"]["date"] == "2026-03-01"


def test_generate_weekly_summary(tmp_path):
    init_paper_state_workspace(project_dir=str(tmp_path), title="Demo")
    ts1 = dt.datetime(2026, 2, 25, 9, 0, tzinfo=dt.timezone.utc).isoformat()
    ts2 = dt.datetime(2026, 2, 27, 10, 0, tzinfo=dt.timezone.utc).isoformat()
    _write_round(tmp_path, round_idx=1, when_iso=ts1, improvement=0.02, new_evidence_count=2)
    _write_round(tmp_path, round_idx=2, when_iso=ts2, improvement=-0.01, new_evidence_count=0)
    _append_claim(tmp_path, "Claim C", "10.1000/c", "candidate", ts1)
    _append_claim(tmp_path, "Claim D", "10.1000/d", "rejected", ts2)

    # 先生成两天日报，验证周报会回引 daily 文件。
    generate_daily_review(project_dir=str(tmp_path), day="2026-02-25")
    generate_daily_review(project_dir=str(tmp_path), day="2026-02-27")

    res = generate_weekly_summary(
        project_dir=str(tmp_path),
        anchor_day="2026-02-27",
        overwrite=True,
        write_state=True,
    )
    assert res["ok"] is True
    assert res["week_tag"] == "2026-W09"
    out = Path(res["path"])
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Weekly Summary - 2026-W09" in text
    assert "Claim C" in text
    assert "Claim D" in text
    assert len(res["daily_used"]) >= 2


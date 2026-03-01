"""深度研究提示词生成与研究报告转参考包。"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Dict, List, Optional


def _to_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(value).strip()]


def generate_deep_research_prompt(
    topic: str,
    known_data: str,
    writing_direction: str,
    core_ideas: Optional[List[str]] = None,
    target_journal: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    output_language: str = "中文",
    max_references: int = 30,
) -> Dict[str, object]:
    if not topic or not topic.strip():
        raise ValueError("topic 不能为空")
    if not known_data or not known_data.strip():
        raise ValueError("known_data 不能为空")
    if not writing_direction or not writing_direction.strip():
        raise ValueError("writing_direction 不能为空")

    ideas = _to_list(core_ideas)
    srcs = _to_list(preferred_sources) or [
        "arXiv",
        "Semantic Scholar",
        "Crossref/OpenAlex",
        "目标期刊官网作者指南",
    ]
    max_refs = max(10, min(int(max_references), 80))

    ideas_block = "\n".join([f"- {x}" for x in ideas]) if ideas else "- [暂无额外要点]"
    src_block = "\n".join([f"- {x}" for x in srcs])
    journal_text = target_journal.strip() if target_journal and target_journal.strip() else "[未指定]"

    prompt = textwrap.dedent(
        f"""
        你是一个严谨的学术研究助理，请为我的论文写作做深度研究。请基于可核验来源输出“研究报告”，不要编造文献。

        【研究主题】
        {topic.strip()}

        【我已有的数据与事实】
        {known_data.strip()}

        【我的撰写方向与核心思路】
        {writing_direction.strip()}

        【补充研究要点】
        {ideas_block}

        【目标期刊】
        {journal_text}

        【优先数据源】
        {src_block}

        【输出语言】
        {output_language}

        【输出要求】
        1) 先给 Executive Summary（300-500字）。
        2) 给 Related Work 分组（至少 3 组：physics-based / data-driven / hybrid 或同等合理分组）。
        3) 给 Evidence Matrix（表格）：论文、方法、数据集/工况、指标、关键结论、局限性、与我工作关系。
        4) 给 Research Gap & Novelty Mapping：明确我可主张的创新点与风险点。
        5) 给写作建议：Introduction/Methods/Results/Discussion 每节建议写什么。
        6) 给“可直接用于引用”的文献清单，至少 {min(max_refs, 20)} 篇，最多 {max_refs} 篇。
        7) 每条文献必须尽可能包含：标题、作者、年份、来源、URL、DOI 或 arXiv ID。
        8) 单独输出“BibTeX Draft”小节（每篇至少给可用草稿）。
        9) 明确标注“高可信文献”和“待核验文献”。
        10) 若存在争议结论，请给出正反证据，不要单边结论。

        【格式要求】
        使用 Markdown，必须包含以下一级标题：
        - # Executive Summary
        - # Related Work Synthesis
        - # Evidence Matrix
        - # Research Gap and Positioning
        - # Writing Plan for Manuscript
        - # Reference List (Verifiable)
        - # BibTeX Draft
        - # Uncertainty and Verification Notes
        """
    ).strip()

    return {
        "ok": True,
        "prompt": prompt,
        "meta": {
            "topic": topic.strip(),
            "target_journal": journal_text,
            "output_language": output_language,
            "preferred_sources": srcs,
            "max_references": max_refs,
        },
    }


def _compact_lines(items: List[str]) -> str:
    if not items:
        return "- [未提供]"
    return "\n".join([f"- {x}" for x in items])


def _short(text: Optional[str], limit: int = 1200) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit] + " ..."


def generate_deep_research_prompt_set(
    topic: str,
    known_data: str,
    writing_direction: str,
    baseline_models: Optional[List[str]] = None,
    improvement_modules: Optional[List[str]] = None,
    code_assets: Optional[List[str]] = None,
    experiment_results: Optional[str] = None,
    draft_ideas: Optional[str] = None,
    target_journal: Optional[str] = None,
    constraints: Optional[str] = None,
    round_stage: str = "r1",
    prior_findings: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    output_language: str = "中文",
    max_references: int = 30,
    num_prompts: int = 3,
) -> Dict[str, object]:
    if not topic or not topic.strip():
        raise ValueError("topic 不能为空")
    if not known_data or not known_data.strip():
        raise ValueError("known_data 不能为空")
    if not writing_direction or not writing_direction.strip():
        raise ValueError("writing_direction 不能为空")

    stage = str(round_stage or "r1").strip().lower()
    if stage not in ("r1", "r2"):
        raise ValueError("round_stage 仅支持 r1/r2")
    requested_n = max(2, min(int(num_prompts), 6))
    max_refs = max(10, min(int(max_references), 80))

    baselines = _to_list(baseline_models)
    improves = _to_list(improvement_modules)
    assets = _to_list(code_assets)
    srcs = _to_list(preferred_sources) or [
        "arXiv",
        "Semantic Scholar",
        "Crossref/OpenAlex",
        "目标期刊官网作者指南",
    ]

    context = textwrap.dedent(
        f"""
        【研究主题】
        {topic.strip()}

        【已有数据与事实】
        {_short(known_data, 1500)}

        【baseline 模型】
        {_compact_lines(baselines)}

        【主要改进模块】
        {_compact_lines(improves)}

        【可引用代码资产】
        {_compact_lines(assets)}

        【实验结果摘要】
        {_short(experiment_results, 1200) if experiment_results else "[未提供]"}

        【写作初步思路】
        {_short(draft_ideas, 1200) if draft_ideas else "[未提供]"}

        【目标期刊】
        {(target_journal or "[未指定]").strip()}

        【约束】
        {_short(constraints, 1200) if constraints else "[未提供]"}

        【优先来源】
        {_compact_lines(srcs)}

        【输出语言】
        {output_language}
        """
    ).strip()

    shared_req = textwrap.dedent(
        f"""
        通用要求：
        1. 仅使用可核验来源，严禁编造。
        2. 文献清单至少 {min(max_refs, 20)} 篇，最多 {max_refs} 篇。
        3. 每条文献尽量包含：标题、作者、年份、来源、URL、DOI/arXiv。
        4. 单独输出 BibTeX Draft。
        5. 对“高可信/待核验”分层标注。
        """
    ).strip()

    r1_prompts = [
        (
            "R1-P1-Landscape",
            "文献地形与基线盘点",
            f"""
你是学术研究助理。请基于以下上下文完成“第一轮深度研究”：

{context}

任务：
1) 建立研究地形：按 physics-based / data-driven / hybrid 分组。
2) 列出与 baseline 最接近的工作，并比较优劣。
3) 给 Evidence Matrix（方法、数据、指标、结论、局限、与本文关系）。
4) 输出可引用文献与 BibTeX 草稿。

{shared_req}
""".strip(),
        ),
        (
            "R1-P2-NoveltyRisk",
            "创新点可主张性与风险审查",
            f"""
请针对“创新点主张”做第一轮审查：

{context}

任务：
1) 给出我可主张的创新点候选（按强/中/弱分级）。
2) 对每个候选给支持证据与反证风险。
3) 明确需要补实验或补引用的点。
4) 给审稿人可能质疑清单（至少 8 条）及应对建议。

{shared_req}
""".strip(),
        ),
        (
            "R1-P3-WritingBlueprint",
            "写作蓝图（IMRaD）",
            f"""
请输出第一轮写作蓝图：

{context}

任务：
1) 给 Introduction/Methods/Results/Discussion 的段落级写作提纲。
2) 逐段标注应引用的文献类型和证据点。
3) 给 3-5 个候选标题方向（先不定稿）。
4) 输出“必须避免的过度结论”清单。

{shared_req}
""".strip(),
        ),
        (
            "R1-P4-FigurePlan",
            "图表与结构图证据规划",
            f"""
请做第一轮图表证据规划：

{context}

任务：
1) 设计主结果图、消融图、鲁棒性图、模型结构图的最小集合。
2) 每张图给目标信息、推荐指标、图注要点。
3) 指出哪些图最能支撑创新点，哪些图是审稿风险缓释图。
4) 给绘图优先级（P0/P1/P2）。
""".strip(),
        ),
        (
            "R1-P5-ExperimentPlan",
            "补充实验与统计显著性计划",
            f"""
请输出第一轮“补充实验计划”：

{context}

任务：
1) 给最小可闭环实验集合：主结果、消融、鲁棒性、效率对比。
2) 针对每个实验给样本划分、重复次数、统计检验建议（如置信区间/显著性）。
3) 明确“若结果不显著”时的备选论证路径。
4) 给实验优先级与预计收益（高/中/低）。
""".strip(),
        ),
        (
            "R1-P6-JournalFit",
            "目标期刊适配与风险前置",
            f"""
请从目标期刊视角评估首轮适配性：

{context}

任务：
1) 结合目标期刊偏好，给本文最应突出的贡献表达方式。
2) 给“应避免的写法”清单（措辞过强、证据不足、工程意义不清等）。
3) 识别伦理/数据可用性/复现性等潜在合规风险。
4) 形成投稿前需补齐材料列表（声明、附录、代码与数据说明）。

{shared_req}
""".strip(),
        ),
    ]

    prior = _short(prior_findings, 1500) if prior_findings else "[未提供]"
    r2_prompts = [
        (
            "R2-P1-GapClosure",
            "二轮查漏补缺",
            f"""
请基于已有研究发现进行第二轮深度研究：

{context}

【第一轮发现摘要】
{prior}

任务：
1) 只针对第一轮未解决的不确定点补证据。
2) 给“可闭环结论”和“仍不可下结论”清单。
3) 输出补充文献与 BibTeX 草稿（聚焦缺口）。

{shared_req}
""".strip(),
        ),
        (
            "R2-P2-TitlePositioning",
            "题目与定位定稿",
            f"""
请做第二轮“题目与定位”决策支持：

{context}

【第一轮发现摘要】
{prior}

任务：
1) 给 8 个候选标题（按保守/平衡/激进分组）。
2) 给每个标题的证据支撑度与审稿风险评分（1-5）。
3) 推荐最优标题 Top-2，并给弃选理由。
4) 给最终创新点陈述（3-5 条，避免夸大）。
""".strip(),
        ),
        (
            "R2-P3-ClaimStressTest",
            "核心主张压力测试",
            f"""
请对核心主张做压力测试：

{context}

【第一轮发现摘要】
{prior}

任务：
1) 从统计、泛化、工程可部署性三个维度挑战主张。
2) 输出“若审稿人追问时的证据链”。
3) 给需要补的最小实验集合与最低可接受证据阈值。
""".strip(),
        ),
        (
            "R2-P4-SubmissionReady",
            "投稿就绪包建议",
            f"""
请给第二轮投稿就绪建议：

{context}

【第一轮发现摘要】
{prior}

任务：
1) 形成最终写作侧重点与章节权重。
2) 给 Cover Letter 强调点与风险规避点。
3) 给投稿前检查清单（图表、引用、声明、可复现性）。
""".strip(),
        ),
        (
            "R2-P5-ReviewerQAPack",
            "审稿质疑预案与回复草案",
            f"""
请生成第二轮“审稿问答预案”：

{context}

【第一轮发现摘要】
{prior}

任务：
1) 预测至少 10 条高概率审稿问题（方法、实验、公平对比、工程意义）。
2) 每条问题给“核心回答 + 证据指向 + 可补实验建议”。
3) 输出可直接转化为 Rebuttal 的结构化模板。
""".strip(),
        ),
        (
            "R2-P6-FinalNarrative",
            "终稿叙事收敛与摘要/结论定稿",
            f"""
请完成第二轮叙事收敛：

{context}

【第一轮发现摘要】
{prior}

任务：
1) 给最终论文故事线（问题->方法->证据->边界->价值）。
2) 生成摘要与结论段落的“事实锚点清单”（必须与结果表一致）。
3) 给关键词建议（6-10 个）及其与检索可见性的关系。
4) 输出最后一版“不可越界主张”清单。
""".strip(),
        ),
    ]

    bank = r1_prompts if stage == "r1" else r2_prompts
    n = min(requested_n, len(bank))
    picked = bank[:n]
    prompts = [{"id": pid, "focus": focus, "prompt": prompt} for pid, focus, prompt in picked]

    return {
        "ok": True,
        "round_stage": stage,
        "count": len(prompts),
        "prompts": prompts,
        "meta": {
            "topic": topic.strip(),
            "target_journal": (target_journal or "[未指定]").strip(),
            "max_references": max_refs,
            "requested_prompts": requested_n,
            "available_prompts": len(bank),
            "preferred_sources": srcs,
            "baseline_count": len(baselines),
            "improvement_count": len(improves),
        },
    }


def synthesize_paper_strategy(
    topic: str,
    target_journal: Optional[str] = None,
    baseline_models: Optional[List[str]] = None,
    improvement_modules: Optional[List[str]] = None,
    key_results: Optional[str] = None,
    report_summaries: Optional[List[str]] = None,
    constraints: Optional[str] = None,
    candidate_title_count: int = 6,
) -> Dict[str, object]:
    if not topic or not topic.strip():
        raise ValueError("topic 不能为空")

    baselines = _to_list(baseline_models)
    improves = _to_list(improvement_modules)
    summaries = _to_list(report_summaries)
    k = max(3, min(int(candidate_title_count), 10))
    journal = (target_journal or "[未指定]").strip()

    topic_text = topic.strip()
    key = _short(key_results, 800) if key_results else "[待补充关键结果]"
    improve_text = improves[0] if improves else "hybrid modeling framework"
    alt_improve = improves[1] if len(improves) > 1 else "physics-informed constraints"
    title_pool_raw = [
        f"{improve_text} for {topic_text}: Toward Reliable Engineering Prediction",
        f"A Hybrid Framework for {topic_text} with {alt_improve}",
        f"Data-Driven and Physics-Constrained Modeling of {topic_text}",
        f"Improving Generalization in {topic_text} via {improve_text}",
        f"From Baselines to Robust Prediction: A Study on {topic_text}",
        f"{topic_text}: Evidence-Based Modeling with {alt_improve}",
        f"Robust {topic_text} under Limited Data via {improve_text}",
        f"Engineering-Oriented {topic_text}: Integrating {alt_improve} and Learned Representations",
        f"Bridging Accuracy and Reliability in {topic_text}",
        f"An Interpretable Hybrid Approach to {topic_text}",
        f"Generalizable {topic_text} Modeling with Physics-Guided Constraints",
        f"Toward Deployment-Ready {topic_text}: A Hybrid Modeling Study",
    ]
    title_pool: List[str] = []
    seen = set()
    for title in title_pool_raw:
        t = " ".join(str(title).split())
        if t and t not in seen:
            seen.add(t)
            title_pool.append(t)
    if len(title_pool) < k:
        for i in range(len(title_pool) + 1, k + 1):
            title_pool.append(f"{topic_text}: Engineering Modeling Study ({i})")
    titles = title_pool[:k]

    innovation_points: List[str] = []
    if improves:
        for m in improves[:4]:
            innovation_points.append(f"将 `{m}` 引入现有流程，提升对关键工况的建模能力。")
    else:
        innovation_points.append("构建可复现的 baseline 对比框架并明确增量证据链。")
    innovation_points.append("通过分层证据（主结果 + 消融 + 鲁棒性）支撑核心主张。")

    writing_focus = [
        "Introduction：强调工程痛点、现有方法边界与研究缺口。",
        "Methods：清楚区分 baseline 与改进模块，给出可复现细节。",
        "Results：先主结果，再消融和鲁棒性，避免只报最优值。",
        "Discussion：明确适用边界、失败场景与未来工作。",
    ]

    if "ocean engineering" in journal.lower():
        writing_focus.append("针对 Ocean Engineering：突出工程可部署性、工况覆盖与安全/可靠性意义。")

    claim_boundaries = [
        "避免使用“state-of-the-art”除非有充分同口径对比证据。",
        "若数据规模有限，主张限定在当前数据分布与工况范围。",
        "对外推能力仅做“suggest/indicate”级别表述，避免“prove”。",
    ]

    next_actions = [
        "根据推荐标题 Top-2 选择主线，并锁定 3-5 条创新点表述。",
        "将关键结果数字补齐到 Results 主表与摘要。",
        "完成 draw.io 真值结构图并生成 Nano Banana 提示词包。",
        "完成 references.bib 去重与高可信条目标注。",
    ]

    return {
        "ok": True,
        "topic": topic.strip(),
        "target_journal": journal,
        "recommended_titles": titles,
        "innovation_points": innovation_points,
        "writing_focus": writing_focus,
        "claim_boundaries": claim_boundaries,
        "strategy_summary": {
            "baseline_models": baselines,
            "improvement_modules": improves,
            "key_results": key,
            "constraints": _short(constraints, 800) if constraints else "[未提供]",
            "report_summaries": summaries[:5],
        },
        "next_actions": next_actions,
    }


def _extract_urls(text: str) -> List[str]:
    found = re.findall(r"https?://[^\s)\]>\"']+", text, flags=re.IGNORECASE)
    out: List[str] = []
    seen = set()
    for u in found:
        uu = u.strip().rstrip(".,;")
        if uu not in seen:
            seen.add(uu)
            out.append(uu)
    return out


def _extract_dois(text: str) -> List[str]:
    found = re.findall(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, flags=re.IGNORECASE)
    out: List[str] = []
    seen = set()
    for d in found:
        dd = d.strip().rstrip(".,;")
        low = dd.lower()
        if low not in seen:
            seen.add(low)
            out.append(dd)
    return out


def _extract_arxiv_ids(text: str) -> List[str]:
    ids = re.findall(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b", text)
    ids += re.findall(r"arXiv:\s*([a-z\-]+/\d{7})(?:v\d+)?", text, flags=re.IGNORECASE)
    out: List[str] = []
    seen = set()
    for aid in ids:
        x = aid.strip()
        low = x.lower()
        if low not in seen:
            seen.add(low)
            out.append(x)
    return out


def _make_bibtex_from_id(doi: Optional[str], arxiv_id: Optional[str], idx: int) -> str:
    if doi:
        key = re.sub(r"[^A-Za-z0-9]+", "", doi)[:40] or f"doi{idx}"
        return "\n".join(
            [
                f"@article{{{key},",
                "  title = {[待补充标题]},",
                "  author = {[待补充作者]},",
                "  journal = {[待补充期刊]},",
                "  year = {[待补充年份]},",
                f"  doi = {{{doi}}},",
                f"  url = {{https://doi.org/{doi}}},",
                "}",
            ]
        )
    if arxiv_id:
        key = re.sub(r"[^A-Za-z0-9]+", "", arxiv_id)[:40] or f"arxiv{idx}"
        return "\n".join(
            [
                f"@article{{{key},",
                "  title = {[待补充标题]},",
                "  author = {[待补充作者]},",
                "  journal = {arXiv preprint},",
                "  year = {[待补充年份]},",
                f"  eprint = {{{arxiv_id}}},",
                "  archivePrefix = {arXiv},",
                f"  url = {{https://arxiv.org/abs/{arxiv_id}}},",
                "}",
            ]
        )
    return ""


def ingest_deep_research_report(
    report_text: Optional[str] = None,
    report_file_path: Optional[str] = None,
    focus_topic: Optional[str] = None,
    max_items: int = 30,
) -> Dict[str, object]:
    text = (report_text or "").strip()
    if report_file_path:
        p = Path(report_file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            raise ValueError(f"report_file_path 不存在: {p}")
        text = p.read_text(encoding="utf-8")

    if not text.strip():
        raise ValueError("report_text 与 report_file_path 至少提供一个")

    limit = max(5, min(int(max_items), 200))
    urls = _extract_urls(text)[:limit]
    dois = _extract_dois(text)[:limit]
    arxiv_ids = _extract_arxiv_ids(text)[:limit]

    headings = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or re.match(r"^\d+[\.\)]\s+", s):
            headings.append(s)
    headings = headings[: min(80, limit)]

    bib_entries: List[str] = []
    idx = 1
    for d in dois:
        bib_entries.append(_make_bibtex_from_id(doi=d, arxiv_id=None, idx=idx))
        idx += 1
    for aid in arxiv_ids:
        bib_entries.append(_make_bibtex_from_id(doi=None, arxiv_id=aid, idx=idx))
        idx += 1

    focus = (focus_topic or "").strip()
    quick_note = textwrap.dedent(
        f"""
        Research report ingestion note
        Topic focus: {focus if focus else "[未指定]"}
        Extracted URLs: {len(urls)}
        Extracted DOIs: {len(dois)}
        Extracted arXiv IDs: {len(arxiv_ids)}

        Suggested next actions:
        1. 先核验 DOI 与 arXiv 的元数据完整性（标题、作者、年份）。
        2. 将高可信条目合并进 references.bib。
        3. 以提取出的章节标题和证据点重写 Related Work 与 Discussion。
        """
    ).strip()

    return {
        "ok": True,
        "focus_topic": focus if focus else None,
        "text_length": len(text),
        "headings": headings,
        "urls": urls,
        "dois": dois,
        "arxiv_ids": arxiv_ids,
        "bibtex_entries": bib_entries,
        "quick_note": quick_note,
        "report_excerpt": text[:1500],
    }

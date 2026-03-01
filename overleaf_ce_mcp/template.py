"""模板初始化与渲染。"""

import datetime as _dt
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional


PKG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PKG_DIR.parent


def _resolve_template_root() -> Path:
    """解析模板目录，兼容源码运行与安装后运行。"""
    env_root = os.environ.get("OVERLEAF_CE_MCP_TEMPLATE_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())
    candidates.append((PKG_DIR / "templates").resolve())
    candidates.append((PROJECT_ROOT / "templates").resolve())
    candidates.append((Path.cwd() / "templates").resolve())
    candidates.append(Path("/root/overleaf-ce-mcp/templates").resolve())

    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return candidates[0]


def list_templates() -> List[str]:
    """列出可用模板。"""
    template_root = _resolve_template_root()
    if not template_root.exists():
        return []
    out: List[str] = []
    for p in template_root.iterdir():
        if p.is_dir():
            out.append(p.name)
    return sorted(out)


def _replace_placeholders(text: str, variables: Dict[str, str]) -> str:
    for k, v in variables.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def _paper_state_templates(vars_map: Dict[str, str]) -> Dict[str, str]:
    return {
        "paper_state/inputs/project.yaml": _replace_placeholders(
            """project:
  title: "{{TITLE}}"
  short_name: "paper-project"
  field: "ocean engineering"
  language: "en"
  created_date: "{{DATE}}"
people:
  authors: "{{AUTHORS}}"
  corresponding_email: "{{CORRESPONDING_EMAIL}}"
""",
            vars_map,
        ),
        "paper_state/inputs/writing_brief.md": _replace_placeholders(
            """# 写作初步思路

## 研究问题
- [补充]

## 预期创新点
- [补充]

## 当前证据
- [补充]

## 当前风险
- [补充]
""",
            vars_map,
        ),
        "paper_state/inputs/submission_target.yaml": _replace_placeholders(
            """submission:
  primary_target_journal: "Ocean Engineering"
  backup_journals: []
  oa_preference: "any"  # any / oa / non_oa
  apc_budget_usd: null
  deadline: null
  notes: ""
""",
            vars_map,
        ),
        "paper_state/inputs/constraints.yaml": _replace_placeholders(
            """constraints:
  max_pages: null
  max_words: null
  compute_budget_gpu_hours: null
  data_license: ""
  must_include_sections: []
  forbidden_claims: []
""",
            vars_map,
        ),
        "paper_state/inputs/loop.yaml": _replace_placeholders(
            """# 受控优化循环配置（扁平 key: value）
# 可由 run_optimization_loop 自动读取（默认路径）。
topic: "{{TITLE}}"
query: "{{KEYWORDS}}"
known_data_file: "paper_state/inputs/writing_brief.md"
writing_direction_file: "paper_state/inputs/writing_brief.md"
baseline_models: ""
improvement_modules: ""
target_journal: "Ocean Engineering"
constraints: ""
source: "all"
max_rounds: 4
min_score_improvement: 0.03
patience: 2
target_score: 0.85
max_results_per_source: 10
max_items_for_note: 8
num_prompts: 6
timeout: 30
enable_journal_recommendation: true
target_preference: "any"
max_candidates: 5
write_daily_review: true
append_claim_evidence: true
""",
            vars_map,
        ),
        "paper_state/inputs/literature/seed_queries.yaml": _replace_placeholders(
            """queries:
  - name: baseline
    text: "{{KEYWORDS}}"
    source: all
    priority: high
  - name: method_core
    text: "physics-informed neural network ocean engineering"
    source: all
    priority: high
""",
            vars_map,
        ),
        "paper_state/inputs/literature/reading_queue.csv": "title,source,url_or_doi,priority,status,notes\n",
        "paper_state/inputs/literature/refs_raw.bib": "% Raw references collected from tools\n",
        "paper_state/inputs/experiments/registry.csv": (
            "exp_id,purpose,split,metric_primary,status,owner,last_update,summary\n"
        ),
        "paper_state/inputs/experiments/metrics/README.md": (
            "# 指标数据目录\n\n"
            "- 建议存放 csv/parquet，例如 `exp001_metrics.csv`。\n"
            "- 字段建议：`sample_id,pred,target,split,model,metric_name,metric_value`。\n"
        ),
        "paper_state/inputs/experiments/notes/README.md": (
            "# 实验说明目录\n\n"
            "- 每个实验一份说明，文件名如 `exp001.md`。\n"
            "- 记录实验目的、配置、结论与失败原因。\n"
        ),
        "paper_state/outputs/README.md": (
            "# 输出产物目录\n\n"
            "- 存放图表、阶段报告、投稿期刊优选结果、引用核验报告等。\n"
        ),
        "paper_state/review/daily/README.md": (
            "# 每日复盘目录\n\n"
            "- 每日一份：`YYYY-MM-DD.md`。\n"
            "- 建议固定四段：新增证据 / 被否决主张 / 失败实验 / 明日最小动作。\n"
        ),
        "paper_state/review/daily/TEMPLATE.md": (
            "# Daily Review - {{DATE}}\n\n"
            "## 新增证据\n- [补充]\n\n"
            "## 被否决主张\n- [补充]\n\n"
            "## 失败实验\n- [补充]\n\n"
            "## 明日最小闭环动作\n- [补充]\n"
        ),
        "paper_state/review/weekly/README.md": (
            "# 每周总结目录\n\n"
            "- 每周一份：`YYYY-Www.md`。\n"
            "- 建议聚合 daily：本周闭环 / 未闭环风险 / 下周优先级 Top3。\n"
        ),
        "paper_state/review/weekly/TEMPLATE.md": (
            "# Weekly Summary - YYYY-Www\n\n"
            "## 本周新增证据\n- [补充]\n\n"
            "## 本周被否决主张\n- [补充]\n\n"
            "## 本周失败实验\n- [补充]\n\n"
            "## 下周最小闭环目标\n- [补充]\n"
        ),
        "paper_state/memory/claim_evidence.jsonl": (
            '{"claim_id":"C001","claim":"[示例主张]","source_type":"doi","source":"10.xxxx/xxxxx",'
            '"confidence":"high","status":"verified","note":"[补充]"}\n'
        ),
        "paper_state/memory/README.md": (
            "# 结论-证据账本\n\n"
            "- 文件：`claim_evidence.jsonl`\n"
            "- 记录结构：`claim_id, claim, source_type, source, confidence, status, note`\n"
            "- 建议状态：`verified / partial / pending / rejected`\n"
        ),
    }


def init_paper_state_workspace(
    project_dir: str,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    corresponding_email: Optional[str] = None,
    keywords: Optional[str] = None,
    force: bool = False,
) -> Dict[str, object]:
    """在已有论文目录下初始化/补建 paper_state 工作区。"""
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))

    vars_map = {
        "TITLE": title or "A Data-Driven Study for Ocean Engineering Applications",
        "AUTHORS": authors or "First Author, Second Author",
        "CORRESPONDING_EMAIL": corresponding_email or "author@example.com",
        "KEYWORDS": keywords or "Ocean engineering, CFD, Reliability, Optimization",
        "DATE": _dt.date.today().isoformat(),
    }
    templates = _paper_state_templates(vars_map)
    created: List[str] = []
    skipped: List[str] = []
    for rel, content in templates.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        if fp.exists() and not force:
            skipped.append(str(fp.relative_to(root)))
            continue
        fp.write_text(content, encoding="utf-8")
        created.append(str(fp.relative_to(root)))

    return {
        "project_dir": str(root),
        "paper_state_root": str((root / "paper_state").resolve()),
        "created_files": sorted(created),
        "skipped_files": sorted(skipped),
    }


def init_template_project(
    template_name: str,
    target_dir: str,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    corresponding_email: Optional[str] = None,
    keywords: Optional[str] = None,
    init_paper_state: bool = True,
) -> Dict[str, object]:
    """用模板初始化项目目录并替换占位符。"""
    template_root = _resolve_template_root()
    src = template_root / template_name
    if not src.exists() or not src.is_dir():
        raise ValueError("模板不存在: %s" % template_name)

    dst = Path(target_dir).expanduser().resolve()
    dst.mkdir(parents=True, exist_ok=True)
    if any(dst.iterdir()):
        raise ValueError("目标目录非空，请使用空目录: %s" % str(dst))

    # 复制模板目录
    shutil.copytree(src, dst, dirs_exist_ok=True)

    vars_map = {
        "TITLE": title or "A Data-Driven Study for Ocean Engineering Applications",
        "AUTHORS": authors or "First Author, Second Author",
        "CORRESPONDING_EMAIL": corresponding_email or "author@example.com",
        "KEYWORDS": keywords or "Ocean engineering, CFD, Reliability, Optimization",
        "DATE": _dt.date.today().isoformat(),
    }

    rendered: List[str] = []
    for root, _, files in os.walk(str(dst)):
        for fn in files:
            if not fn.endswith(".tex"):
                continue
            fp = Path(root) / fn
            old = fp.read_text(encoding="utf-8")
            new = _replace_placeholders(old, vars_map)
            fp.write_text(new, encoding="utf-8")
            rendered.append(str(fp.relative_to(dst)))

    created: List[str] = []
    for root, _, files in os.walk(str(dst)):
        for fn in files:
            p = Path(root) / fn
            created.append(str(p.relative_to(dst)))

    paper_state_result = None
    if init_paper_state:
        paper_state_result = init_paper_state_workspace(
            project_dir=str(dst),
            title=title,
            authors=authors,
            corresponding_email=corresponding_email,
            keywords=keywords,
            force=False,
        )

    return {
        "target_dir": str(dst),
        "template": template_name,
        "rendered_tex_files": sorted(rendered),
        "created_files": sorted(created),
        "paper_state": paper_state_result,
    }

"""Overleaf CE MCP 服务入口。"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .compat import ensure_compat_patches
from .deep_research import (
    generate_deep_research_prompt,
    generate_deep_research_prompt_set,
    ingest_deep_research_report,
    synthesize_paper_strategy,
)
from .diagram_workflow import init_model_diagram_pack
from .optimization_loop import run_optimization_loop
from .sync import command_exists, ols_list, ols_login, ols_sync, run_command
from .scholar import (
    build_related_work_pack,
    fetch_paper_fulltext,
    letpub_get_journal_detail,
    letpub_search_journals,
    list_academic_source_capabilities,
    list_journal_presets,
    recommend_target_journals,
    search_academic_papers,
    search_in_journal_preset,
    sync_zotero_paper_state,
    verify_reference,
)
from .template import init_paper_state_workspace, init_template_project, list_templates
from .upload import (
    find_project_by_name,
    health_check_project,
    package_project_for_upload,
    upload_zip_as_new_project,
)


server = Server("overleaf-ce-mcp")


def _dump(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_globs(value: Any) -> List[str]:
    """将用户输入解析为排除模式列表。兼容数组与逗号分隔字符串。"""
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def _collect_env_status() -> Dict[str, Any]:
    patch_info = ensure_compat_patches()
    return {
        "python": sys.version.split()[0],
        "commands": {
            "ols": command_exists("ols"),
            "latexmk": command_exists("latexmk"),
            "zip": command_exists("zip"),
            "unzip": command_exists("unzip"),
        },
        "templates": list_templates(),
        "compat_patches": patch_info,
    }


@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="check_environment",
            description="检查当前环境是否安装 ols/latexmk/zip/unzip，以及可用模板列表。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="ols_login",
            description="执行 `ols login`，用于 CE 登录并生成 .olauth。首次登录通常需要图形界面交互。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_path": {"type": "string", "description": ".olauth 保存路径（可选）"},
                    "ce_url": {"type": "string", "description": "CE 地址（可选）"},
                },
            },
        ),
        Tool(
            name="ols_list_projects",
            description="执行 `ols list`，列出账号项目。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_path": {"type": "string", "description": ".olauth 路径（可选）"},
                    "ce_url": {"type": "string", "description": "CE 地址（可选）"},
                    "verbose": {"type": "boolean", "description": "是否输出详细信息"},
                },
            },
        ),
        Tool(
            name="ols_sync",
            description="执行 `ols` 同步。mode 支持 bidirectional/local-only/remote-only。",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "本地项目目录（可选，不传则使用当前目录）",
                    },
                    "project_name": {"type": "string", "description": "远端项目名（可选）"},
                    "ce_url": {"type": "string", "description": "CE 地址（可选）"},
                    "mode": {
                        "type": "string",
                        "enum": ["bidirectional", "local-only", "remote-only"],
                        "description": "同步模式",
                    },
                    "store_path": {"type": "string", "description": ".olauth 路径（可选）"},
                    "olignore": {"type": "string", "description": ".olignore 路径（可选）"},
                    "delete_policy": {
                        "type": "string",
                        "enum": ["d", "r", "i"],
                        "description": "非交互删除策略：d删远端、r回滚本地、i忽略",
                    },
                    "verbose": {"type": "boolean", "description": "是否输出详细信息"},
                },
            },
        ),
        Tool(
            name="init_manuscript_from_template",
            description="按模板初始化论文目录，默认同时生成 paper_state 状态工作区。",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {"type": "string", "description": "模板名称"},
                    "target_dir": {"type": "string", "description": "目标空目录"},
                    "title": {"type": "string", "description": "论文标题"},
                    "authors": {"type": "string", "description": "作者字符串（逗号分隔）"},
                    "corresponding_email": {"type": "string", "description": "通讯作者邮箱"},
                    "keywords": {"type": "string", "description": "关键词字符串（逗号分隔）"},
                    "init_paper_state": {"type": "boolean", "description": "是否初始化 paper_state（默认 true）"},
                },
                "required": ["target_dir"],
            },
        ),
        Tool(
            name="init_paper_state_workspace",
            description="在已有论文目录中初始化/补建 paper_state 状态工作区。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "论文项目目录（必填）"},
                    "title": {"type": "string", "description": "论文标题（可选）"},
                    "authors": {"type": "string", "description": "作者（可选）"},
                    "corresponding_email": {"type": "string", "description": "通讯作者邮箱（可选）"},
                    "keywords": {"type": "string", "description": "关键词（可选）"},
                    "force": {"type": "boolean", "description": "存在文件是否覆盖（默认 false）"},
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="write_file",
            description="写入或覆盖文本文件（UTF-8）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件绝对路径"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["file_path", "content"],
            },
        ),
        Tool(
            name="compile_latex",
            description="在项目目录执行 latexmk 编译。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "项目目录"},
                    "main_tex": {"type": "string", "description": "主 tex 文件，默认 main.tex"},
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="package_project_zip",
            description="将项目目录打包成 zip 文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "项目目录"},
                    "output_zip": {"type": "string", "description": "输出 zip 路径（可选）"},
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="upload_project_zip",
            description="将 zip 稿件上传到 Overleaf CE，并创建新项目（通用上传方式）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ce_url": {"type": "string", "description": "Overleaf CE 地址，如 http://host:17880"},
                    "zip_path": {"type": "string", "description": "待上传 zip 的绝对路径"},
                    "store_path": {"type": "string", "description": ".olauth 路径（可选，默认 ~/.olauth）"},
                    "timeout": {"type": "integer", "description": "上传超时秒数（可选，默认 300）"},
                    "health_check": {"type": "boolean", "description": "上传后是否做健康检查（默认 true）"},
                    "compile_check": {"type": "boolean", "description": "健康检查时是否触发编译（默认 true）"},
                },
                "required": ["ce_url", "zip_path"],
            },
        ),
        Tool(
            name="upload_project_dir",
            description="将本地项目目录按通用规则打包并上传到 Overleaf CE（创建新项目）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ce_url": {"type": "string", "description": "Overleaf CE 地址，如 http://host:17880"},
                    "project_dir": {"type": "string", "description": "本地项目目录"},
                    "store_path": {"type": "string", "description": ".olauth 路径（可选，默认 ~/.olauth）"},
                    "output_zip": {"type": "string", "description": "输出 zip 路径（可选）"},
                    "exclude_globs": {"type": "array", "items": {"type": "string"}, "description": "额外排除规则"},
                    "dry_run": {"type": "boolean", "description": "只预览打包/同步计划，不执行上传"},
                    "target_project": {"type": "string", "description": "目标已有项目名（可选，不传则创建新项目）"},
                    "existing_project_strategy": {
                        "type": "string",
                        "enum": ["merge", "replace"],
                        "description": "已有项目策略：merge 合并，replace 远端按本地覆盖",
                    },
                    "timeout": {"type": "integer", "description": "上传超时秒数（可选，默认 300）"},
                    "health_check": {"type": "boolean", "description": "完成后是否做健康检查（默认 true）"},
                    "compile_check": {"type": "boolean", "description": "健康检查时是否触发编译（默认 true）"},
                    "verbose": {"type": "boolean", "description": "同步时是否输出详细日志（默认 false）"},
                },
                "required": ["ce_url", "project_dir"],
            },
        ),
        Tool(
            name="health_check_project",
            description="检查 CE 项目是否可见并可编译，返回 PDF 结果信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ce_url": {"type": "string", "description": "Overleaf CE 地址"},
                    "store_path": {"type": "string", "description": ".olauth 路径（可选，默认 ~/.olauth）"},
                    "project_name": {"type": "string", "description": "项目名（可选）"},
                    "project_id": {"type": "string", "description": "项目 ID（可选）"},
                    "compile_check": {"type": "boolean", "description": "是否执行编译检查（默认 true）"},
                },
                "required": ["ce_url"],
            },
        ),
        Tool(
            name="apply_compat_patches",
            description="手动应用 overleaf-sync-ce/socketIO 兼容补丁（通常无需手动执行）。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_academic_papers",
            description="检索学术论文（默认无 Key：arXiv / OpenAlex / Crossref；可选 Semantic Scholar）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索词（必填）"},
                    "source": {
                        "type": "string",
                        "enum": ["all", "arxiv", "openalex", "crossref", "semantic_scholar"],
                        "description": "检索来源，默认 all",
                    },
                    "max_results_per_source": {
                        "type": "integer",
                        "description": "每个来源最多返回条目数（默认 8，最大 50）",
                    },
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "s2_api_key": {
                        "type": "string",
                        "description": "Semantic Scholar API Key（可选，仅 source=semantic_scholar 或 all 且需要 S2 时）",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_academic_source_capabilities",
            description="列出学术数据源适配器能力与启用状态（用于检索策略编排）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "s2_api_key": {"type": "string", "description": "可选：用于判断 Semantic Scholar 是否可用"},
                },
            },
        ),
        Tool(
            name="fetch_paper_fulltext",
            description="按回退链获取论文可用文本（Unpaywall -> OpenAlex DOI -> Crossref DOI -> arXiv -> URL -> 标题检索）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "论文标题（可选）"},
                    "doi": {"type": "string", "description": "DOI（可选）"},
                    "arxiv_id": {"type": "string", "description": "arXiv ID（可选）"},
                    "url": {"type": "string", "description": "论文 URL（可选）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "unpaywall_email": {"type": "string", "description": "Unpaywall 邮箱（可选，不传则读 UNPAYWALL_EMAIL）"},
                    "s2_api_key": {"type": "string", "description": "可选，仅标题检索回退时需要"},
                },
            },
        ),
        Tool(
            name="sync_zotero_paper_state",
            description="将 paper_state 与 Zotero 同步（pull/push/bidirectional，支持 dry-run）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "论文项目目录（必填）"},
                    "direction": {
                        "type": "string",
                        "enum": ["pull", "push", "bidirectional"],
                        "description": "同步方向（默认 pull）",
                    },
                    "library_id": {"type": "string", "description": "Zotero library id（可选，不传读环境变量）"},
                    "api_key": {"type": "string", "description": "Zotero API key（可选，不传读环境变量）"},
                    "library_type": {
                        "type": "string",
                        "enum": ["user", "group"],
                        "description": "Zotero 库类型（默认 user）",
                    },
                    "limit": {"type": "integer", "description": "条目上限（默认 50）"},
                    "query": {"type": "string", "description": "Zotero pull 检索词（可选）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "dry_run": {"type": "boolean", "description": "是否仅预演（默认 true）"},
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="letpub_search_journals",
            description="通过 LetPub 期刊搜索页检索期刊，并返回 LetPub 评分/IF/h-index/OA 等关键字段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "searchname": {"type": "string", "description": "期刊名关键词（与 searchissn 至少一项）"},
                    "searchissn": {"type": "string", "description": "ISSN（与 searchname 至少一项）"},
                    "searchfield": {"type": "string", "description": "研究方向关键词（可选）"},
                    "searchimpactlow": {"type": "string", "description": "影响因子下限（可选）"},
                    "searchimpacthigh": {"type": "string", "description": "影响因子上限（可选）"},
                    "max_items": {"type": "integer", "description": "最大返回条数（默认30，最大100）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                },
            },
        ),
        Tool(
            name="letpub_get_journal_detail",
            description="抓取 LetPub 期刊详情页（journalid）并提取投稿相关关键字段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "journalid": {"type": "string", "description": "期刊ID（必填，如 7412）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                },
                "required": ["journalid"],
            },
        ),
        Tool(
            name="build_related_work_pack",
            description="为论文写作生成“相关工作素材包”（默认无 Key 来源；含候选论文、综述草稿、BibTeX 草稿）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "研究主题检索词（必填）"},
                    "source": {
                        "type": "string",
                        "enum": ["all", "arxiv", "openalex", "crossref", "semantic_scholar"],
                        "description": "检索来源，默认 all",
                    },
                    "max_results_per_source": {
                        "type": "integer",
                        "description": "每个来源最多返回条目数（默认 8，最大 50）",
                    },
                    "max_items_for_note": {
                        "type": "integer",
                        "description": "用于生成相关工作草稿的条目数（默认 8）",
                    },
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "s2_api_key": {
                        "type": "string",
                        "description": "Semantic Scholar API Key（可选，仅 source=semantic_scholar 或 all 且需要 S2 时）",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_journal_presets",
            description="列出内置期刊/会议预设分组（用于快速期刊筛选与优选）。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_in_journal_preset",
            description="在内置期刊/会议预设中检索论文（适合快速验证投稿方向匹配度）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索词（必填）"},
                    "journal_preset": {"type": "string", "description": "预设键（必填，如 top_ai_conferences）"},
                    "source": {
                        "type": "string",
                        "enum": ["all", "arxiv", "openalex", "crossref", "semantic_scholar"],
                        "description": "检索来源，默认 all",
                    },
                    "max_results_per_source": {"type": "integer", "description": "每源返回上限（默认 12）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "s2_api_key": {"type": "string", "description": "可选，仅需启用 Semantic Scholar 时传入"},
                },
                "required": ["query", "journal_preset"],
            },
        ),
        Tool(
            name="recommend_target_journals",
            description="基于当前主题检索结果与内置期刊预设，给出投稿期刊优选建议。",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "研究主题（必填）"},
                    "target_preference": {
                        "type": "string",
                        "enum": ["any", "oa", "non_oa"],
                        "description": "偏好：any/oa/non_oa",
                    },
                    "max_candidates": {"type": "integer", "description": "返回候选数（默认 5，范围 3-10）"},
                    "max_results_per_source": {"type": "integer", "description": "每源检索上限（默认 10）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "s2_api_key": {"type": "string", "description": "可选，仅需启用 Semantic Scholar 时传入"},
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="verify_reference",
            description="核验参考文献真伪与匹配度（Crossref/多源检索），并返回修正 BibTeX 草稿。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "文献标题（可选，title/doi 至少一项）"},
                    "authors": {"type": "array", "items": {"type": "string"}, "description": "作者列表（可选）"},
                    "year": {"type": "integer", "description": "年份（可选）"},
                    "doi": {"type": "string", "description": "DOI（可选，title/doi 至少一项）"},
                    "venue": {"type": "string", "description": "期刊/会议名（可选）"},
                    "timeout": {"type": "integer", "description": "请求超时秒数（默认 30）"},
                    "s2_api_key": {"type": "string", "description": "可选，仅需启用 Semantic Scholar 时传入"},
                },
            },
        ),
        Tool(
            name="generate_deep_research_prompt",
            description="根据已有数据和撰写方向，生成可直接用于 GPT 网页版深度研究的提示词。",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "研究主题（必填）"},
                    "known_data": {"type": "string", "description": "已有数据/实验事实摘要（必填）"},
                    "writing_direction": {"type": "string", "description": "撰写方向与核心思路（必填）"},
                    "core_ideas": {"type": "array", "items": {"type": "string"}, "description": "补充要点（可选）"},
                    "target_journal": {"type": "string", "description": "目标期刊（可选）"},
                    "preferred_sources": {"type": "array", "items": {"type": "string"}, "description": "优先来源（可选）"},
                    "output_language": {"type": "string", "description": "输出语言（默认 中文）"},
                    "max_references": {"type": "integer", "description": "期望文献条目上限（默认 30）"},
                },
                "required": ["topic", "known_data", "writing_direction"],
            },
        ),
        Tool(
            name="generate_deep_research_prompt_set",
            description="基于 baseline/改进模块/实验结果等信息，生成多组深度研究提示词（支持 R1/R2 迭代）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "研究主题（必填）"},
                    "known_data": {"type": "string", "description": "已有数据与事实（必填）"},
                    "writing_direction": {"type": "string", "description": "写作方向（必填）"},
                    "baseline_models": {"type": "array", "items": {"type": "string"}, "description": "baseline 模型列表"},
                    "improvement_modules": {"type": "array", "items": {"type": "string"}, "description": "主要改进模块列表"},
                    "code_assets": {"type": "array", "items": {"type": "string"}, "description": "可引用代码资产（文件/仓库）"},
                    "experiment_results": {"type": "string", "description": "实验结果摘要"},
                    "draft_ideas": {"type": "string", "description": "初步写作思路"},
                    "target_journal": {"type": "string", "description": "目标期刊"},
                    "constraints": {"type": "string", "description": "约束条件（字数/时间/预算等）"},
                    "round_stage": {
                        "type": "string",
                        "enum": ["r1", "r2"],
                        "description": "提示词轮次，r1 首轮，r2 二轮补强",
                    },
                    "prior_findings": {"type": "string", "description": "上一轮研究结论摘要（r2 推荐）"},
                    "preferred_sources": {"type": "array", "items": {"type": "string"}, "description": "优先来源"},
                    "output_language": {"type": "string", "description": "输出语言（默认中文）"},
                    "max_references": {"type": "integer", "description": "文献条目上限（默认30）"},
                    "num_prompts": {"type": "integer", "description": "生成提示词组数（默认3，2-6）"},
                },
                "required": ["topic", "known_data", "writing_direction"],
            },
        ),
        Tool(
            name="ingest_deep_research_report",
            description="将 GPT 深度研究报告转为参考资料包（提取 URL/DOI/arXiv/BibTeX 草稿）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_text": {"type": "string", "description": "研究报告全文（可选）"},
                    "report_file_path": {"type": "string", "description": "研究报告文件路径（可选）"},
                    "focus_topic": {"type": "string", "description": "聚焦主题标签（可选）"},
                    "max_items": {"type": "integer", "description": "最大提取条目数（默认 30）"},
                    "save_reference_note_path": {
                        "type": "string",
                        "description": "将解析摘要写入文件（可选）",
                    },
                    "save_bib_path": {"type": "string", "description": "将 BibTeX 草稿写入文件（可选）"},
                },
            },
        ),
        Tool(
            name="synthesize_paper_strategy",
            description="综合多轮研究报告与实验信息，给出题目候选、创新点和写作侧重点。",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "研究主题（必填）"},
                    "target_journal": {"type": "string", "description": "目标期刊"},
                    "baseline_models": {"type": "array", "items": {"type": "string"}, "description": "baseline 模型列表"},
                    "improvement_modules": {"type": "array", "items": {"type": "string"}, "description": "改进模块列表"},
                    "key_results": {"type": "string", "description": "关键实验结果摘要"},
                    "report_summaries": {"type": "array", "items": {"type": "string"}, "description": "多轮研究报告摘要"},
                    "constraints": {"type": "string", "description": "投稿/写作约束"},
                    "candidate_title_count": {"type": "integer", "description": "候选标题数量（默认6，3-10）"},
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="run_optimization_loop",
            description="执行受控优化循环（R1/R2 迭代），并将中间产物写入 paper_state。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "论文项目目录（必填）"},
                    "loop_config_path": {
                        "type": "string",
                        "description": "循环配置文件路径（可选，默认 paper_state/inputs/loop.yaml）",
                    },
                    "topic": {"type": "string", "description": "研究主题（可选，未传则尝试从 project.yaml 读取）"},
                    "known_data": {"type": "string", "description": "已有数据/事实（可选）"},
                    "writing_direction": {"type": "string", "description": "写作方向（可选）"},
                    "baseline_models": {"type": "array", "items": {"type": "string"}, "description": "baseline 模型列表"},
                    "improvement_modules": {"type": "array", "items": {"type": "string"}, "description": "改进模块列表"},
                    "target_journal": {"type": "string", "description": "目标期刊（可选）"},
                    "constraints": {"type": "string", "description": "约束条件（可选）"},
                    "query": {"type": "string", "description": "检索 query（可选）"},
                    "source": {
                        "type": "string",
                        "enum": ["all", "arxiv", "openalex", "crossref", "semantic_scholar"],
                        "description": "检索来源（默认 all）",
                    },
                    "max_rounds": {"type": "integer", "description": "最大循环轮数（默认 4）"},
                    "min_score_improvement": {"type": "number", "description": "最小有效提升阈值（默认 0.03）"},
                    "patience": {"type": "integer", "description": "连续无增益容忍轮数（默认 2）"},
                    "target_score": {"type": "number", "description": "达到即停止的目标分数（默认 0.85）"},
                    "max_results_per_source": {"type": "integer", "description": "每源检索上限（默认 10）"},
                    "max_items_for_note": {"type": "integer", "description": "相关工作草稿用条目数（默认 8）"},
                    "num_prompts": {"type": "integer", "description": "每轮提示词组数（默认 6）"},
                    "timeout": {"type": "integer", "description": "检索超时秒数（默认 30）"},
                    "s2_api_key": {"type": "string", "description": "可选，仅需启用 Semantic Scholar 时传入"},
                    "enable_journal_recommendation": {
                        "type": "boolean",
                        "description": "是否启用投稿期刊优选（默认 true）",
                    },
                    "target_preference": {
                        "type": "string",
                        "enum": ["any", "oa", "non_oa"],
                        "description": "投稿偏好（默认 any）",
                    },
                    "max_candidates": {"type": "integer", "description": "期刊候选数量（默认 5）"},
                    "write_daily_review": {"type": "boolean", "description": "是否写入每日复盘（默认 true）"},
                    "append_claim_evidence": {
                        "type": "boolean",
                        "description": "是否写入 claim_evidence 候选证据（默认 true）",
                    },
                },
                "required": ["project_dir"],
            },
        ),
        Tool(
            name="init_model_diagram_pack",
            description="初始化模型结构图生产包（真值拓扑 + Nano Banana Pro 提示词 + 局部放大模板）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "论文项目目录（必填）"},
                    "model_name": {"type": "string", "description": "模型名称（必填）"},
                    "drawio_file_path": {"type": "string", "description": "draw.io 真值文件路径（可选，推荐）"},
                    "truth_priority": {
                        "type": "string",
                        "enum": ["auto", "drawio", "mermaid"],
                        "description": "真值来源优先级（默认 auto）",
                    },
                    "mermaid_code": {"type": "string", "description": "真值拓扑 Mermaid 代码（可选）"},
                    "modules": {"type": "array", "items": {"type": "string"}, "description": "模块清单（可选）"},
                    "output_subdir": {
                        "type": "string",
                        "description": "输出子目录（默认 figures/model-diagram）",
                    },
                    "force": {"type": "boolean", "description": "已存在文件是否覆盖（默认 false）"},
                },
                "required": ["project_dir", "model_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    try:
        result = await _execute_tool(name, arguments or {})
        return [TextContent(type="text", text=result)]
    except Exception as exc:
        return [
            TextContent(
                type="text",
                text=_dump(
                    {
                        "ok": False,
                        "error": str(exc),
                        "hint": "可先调用 check_environment 查看依赖状态。",
                    }
                ),
            )
        ]


async def _execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    if name == "check_environment":
        return _dump({"ok": True, "data": _collect_env_status()})

    if name == "ols_login":
        store_path = arguments.get("store_path")
        ce_url = arguments.get("ce_url")
        code, out, err = ols_login(store_path=store_path, ce_url=ce_url)
        return _dump(
            {
                "ok": code == 0,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
                "note": "若无图形界面，建议先在有桌面的环境完成一次 login。",
            }
        )

    if name == "ols_list_projects":
        store_path = arguments.get("store_path")
        ce_url = arguments.get("ce_url")
        verbose = _as_bool(arguments.get("verbose"), default=False)
        code, out, err = ols_list(store_path=store_path, verbose=verbose, ce_url=ce_url)
        return _dump(
            {
                "ok": code == 0,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
            }
        )

    if name == "ols_sync":
        workspace_path = arguments.get("workspace_path")
        mode = arguments.get("mode", "bidirectional")
        project_name = arguments.get("project_name")
        ce_url = arguments.get("ce_url")
        store_path = arguments.get("store_path")
        olignore = arguments.get("olignore")
        delete_policy = arguments.get("delete_policy")
        verbose = _as_bool(arguments.get("verbose"), default=False)

        code, out, err = ols_sync(
            workspace_path=workspace_path,
            mode=mode,
            project_name=project_name,
            ce_url=ce_url,
            store_path=store_path,
            olignore=olignore,
            delete_policy=delete_policy,
            verbose=verbose,
        )
        return _dump(
            {
                "ok": code == 0,
                "exit_code": code,
                "workspace_path": str(Path(workspace_path).resolve()) if workspace_path else None,
                "project_name": project_name,
                "ce_url": ce_url,
                "mode": mode,
                "stdout": out,
                "stderr": err,
            }
        )

    if name == "init_manuscript_from_template":
        template_name = arguments.get("template_name", "ocean-engineering-oa")
        target_dir = arguments.get("target_dir")
        if not target_dir:
            raise ValueError("target_dir 不能为空")
        data = init_template_project(
            template_name=template_name,
            target_dir=target_dir,
            title=arguments.get("title"),
            authors=arguments.get("authors"),
            corresponding_email=arguments.get("corresponding_email"),
            keywords=arguments.get("keywords"),
            init_paper_state=_as_bool(arguments.get("init_paper_state"), True),
        )
        return _dump({"ok": True, "data": data})

    if name == "init_paper_state_workspace":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        data = init_paper_state_workspace(
            project_dir=str(project_dir),
            title=str(arguments.get("title")) if arguments.get("title") else None,
            authors=str(arguments.get("authors")) if arguments.get("authors") else None,
            corresponding_email=(
                str(arguments.get("corresponding_email")) if arguments.get("corresponding_email") else None
            ),
            keywords=str(arguments.get("keywords")) if arguments.get("keywords") else None,
            force=_as_bool(arguments.get("force"), False),
        )
        return _dump({"ok": True, "data": data})

    if name == "write_file":
        file_path = arguments.get("file_path")
        content = arguments.get("content")
        if not file_path:
            raise ValueError("file_path 不能为空")
        if content is None:
            raise ValueError("content 不能为空")
        p = Path(file_path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return _dump({"ok": True, "file_path": str(p), "bytes": len(content.encode("utf-8"))})

    if name == "compile_latex":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        main_tex = arguments.get("main_tex", "main.tex")
        if not command_exists("latexmk"):
            return _dump(
                {
                    "ok": False,
                    "error": "未检测到 latexmk",
                    "hint": "安装：sudo apt-get install -y texlive-latex-base texlive-latex-extra latexmk",
                }
            )

        wd = Path(project_dir).expanduser().resolve()
        tex = wd / main_tex
        if not tex.exists():
            raise ValueError("主文件不存在: %s" % str(tex))

        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", main_tex]
        code, out, err = run_command(cmd, cwd=str(wd), timeout=1800)
        pdf_path = wd / (Path(main_tex).stem + ".pdf")
        return _dump(
            {
                "ok": code == 0 and pdf_path.exists(),
                "exit_code": code,
                "pdf_path": str(pdf_path) if pdf_path.exists() else None,
                "stdout_tail": out[-4000:],
                "stderr_tail": err[-4000:],
            }
        )

    if name == "package_project_zip":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        if not command_exists("zip"):
            raise ValueError("未检测到 zip 命令")

        wd = Path(project_dir).expanduser().resolve()
        if not wd.exists() or not wd.is_dir():
            raise ValueError("project_dir 不是有效目录: %s" % str(wd))

        output_zip = arguments.get("output_zip")
        if output_zip:
            out_zip = Path(output_zip).expanduser().resolve()
        else:
            out_zip = wd.parent / (wd.name + ".zip")
        out_zip.parent.mkdir(parents=True, exist_ok=True)

        # 在项目目录内部压缩，避免把绝对路径写入 zip
        if out_zip.exists():
            out_zip.unlink()
        code, out, err = run_command(
            ["zip", "-r", str(out_zip), "."],
            cwd=str(wd),
            timeout=1800,
        )
        return _dump(
            {
                "ok": code == 0 and out_zip.exists(),
                "exit_code": code,
                "zip_path": str(out_zip) if out_zip.exists() else None,
                "stdout": out[-2000:],
                "stderr": err[-2000:],
            }
        )

    if name == "upload_project_zip":
        ce_url = arguments.get("ce_url")
        zip_path = arguments.get("zip_path")
        if not ce_url:
            raise ValueError("ce_url 不能为空")
        if not zip_path:
            raise ValueError("zip_path 不能为空")

        store_path = arguments.get("store_path")
        if store_path:
            store = str(Path(store_path).expanduser().resolve())
        else:
            store = str((Path.home() / ".olauth").resolve())
        timeout = _as_int(arguments.get("timeout"), 300)
        health = _as_bool(arguments.get("health_check"), True)
        compile_check = _as_bool(arguments.get("compile_check"), True)

        data = upload_zip_as_new_project(
            ce_url=str(ce_url),
            store_path=store,
            zip_path=str(zip_path),
            timeout=timeout,
        )
        result: Dict[str, Any] = {"ok": True, "data": data}
        if health:
            result["health"] = health_check_project(
                ce_url=str(ce_url),
                store_path=store,
                project_id=str(data.get("project_id")),
                compile_check=compile_check,
            )
        return _dump(result)

    if name == "upload_project_dir":
        ce_url = arguments.get("ce_url")
        project_dir = arguments.get("project_dir")
        if not ce_url:
            raise ValueError("ce_url 不能为空")
        if not project_dir:
            raise ValueError("project_dir 不能为空")

        exclude_list = _as_globs(arguments.get("exclude_globs"))
        dry_run = _as_bool(arguments.get("dry_run"), False)
        target_project = (arguments.get("target_project") or "").strip() or None
        existing_strategy = str(arguments.get("existing_project_strategy", "merge")).strip().lower()
        if existing_strategy not in ("merge", "replace"):
            raise ValueError("existing_project_strategy 仅支持 merge/replace")
        health = _as_bool(arguments.get("health_check"), True)
        compile_check = _as_bool(arguments.get("compile_check"), True)
        verbose = _as_bool(arguments.get("verbose"), False)

        packed = package_project_for_upload(
            project_dir=str(project_dir),
            output_zip=arguments.get("output_zip"),
            exclude_globs=exclude_list,
        )

        store_path = arguments.get("store_path")
        if store_path:
            store = str(Path(store_path).expanduser().resolve())
        else:
            store = str((Path.home() / ".olauth").resolve())
        timeout = _as_int(arguments.get("timeout"), 300)

        # dry-run：只返回打包/执行计划，不触发远端操作
        if dry_run:
            return _dump(
                {
                    "ok": True,
                    "dry_run": True,
                    "pack": packed,
                    "plan": {
                        "mode": "sync_existing" if target_project else "upload_new_project",
                        "target_project": target_project,
                        "existing_project_strategy": existing_strategy if target_project else None,
                        "health_check": health,
                        "compile_check": compile_check,
                    },
                }
            )

        # 分支 A：未指定 target_project，创建新项目
        if not target_project:
            uploaded = upload_zip_as_new_project(
                ce_url=str(ce_url),
                store_path=store,
                zip_path=str(packed["zip_path"]),
                timeout=timeout,
            )
            result: Dict[str, Any] = {"ok": True, "pack": packed, "upload": uploaded}
            if health:
                result["health"] = health_check_project(
                    ce_url=str(ce_url),
                    store_path=store,
                    project_id=str(uploaded.get("project_id")),
                    compile_check=compile_check,
                )
            return _dump(result)

        # 分支 B：指定 target_project，同步到已有项目
        existing = find_project_by_name(
            ce_url=str(ce_url),
            store_path=store,
            project_name=target_project,
        )
        if existing is None:
            raise ValueError(f"目标项目不存在: {target_project}")

        # 将打包结果解压到临时目录，再走 ols --local-only 到目标项目。
        stage_root = Path(tempfile.mkdtemp(prefix="overleaf-ce-stage-")).resolve()
        stage_dir = stage_root / target_project
        try:
            stage_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(packed["zip_path"]), "r") as zf:
                zf.extractall(str(stage_dir))

            # 生成用于同步时过滤临时产物的 .olignore
            olignore_path = stage_dir / ".olignore"
            olignore_lines = [
                "*.aux",
                "*.bbl",
                "*.blg",
                "*.fdb_latexmk",
                "*.fls",
                "*.log",
                "*.out",
                "*.spl",
                "*.synctex.gz",
                "*.pdf",
                "*.zip",
            ]
            for g in exclude_list:
                if g not in olignore_lines:
                    olignore_lines.append(g)
            olignore_path.write_text("\n".join(olignore_lines) + "\n", encoding="utf-8")

            delete_policy = "d" if existing_strategy == "replace" else "i"
            code, out, err = ols_sync(
                workspace_path=str(stage_dir),
                project_name=target_project,
                ce_url=str(ce_url),
                mode="local-only",
                store_path=store,
                olignore=str(olignore_path),
                delete_policy=delete_policy,
                verbose=verbose,
            )

            result = {
                "ok": code == 0,
                "pack": packed,
                "sync": {
                    "exit_code": code,
                    "target_project": target_project,
                    "target_project_id": existing.get("id"),
                    "existing_project_strategy": existing_strategy,
                    "delete_policy": delete_policy,
                    "stage_dir": str(stage_dir),
                    "stdout": out,
                    "stderr": err,
                },
            }
            if health:
                result["health"] = health_check_project(
                    ce_url=str(ce_url),
                    store_path=store,
                    project_name=target_project,
                    compile_check=compile_check,
                )
            return _dump(result)
        finally:
            # 默认清理临时目录
            shutil.rmtree(stage_root, ignore_errors=True)

    if name == "health_check_project":
        ce_url = arguments.get("ce_url")
        if not ce_url:
            raise ValueError("ce_url 不能为空")
        store_path = arguments.get("store_path")
        if store_path:
            store = str(Path(store_path).expanduser().resolve())
        else:
            store = str((Path.home() / ".olauth").resolve())

        project_name = arguments.get("project_name")
        project_id = arguments.get("project_id")
        compile_check = _as_bool(arguments.get("compile_check"), True)

        data = health_check_project(
            ce_url=str(ce_url),
            store_path=store,
            project_name=str(project_name) if project_name else None,
            project_id=str(project_id) if project_id else None,
            compile_check=compile_check,
        )
        return _dump({"ok": bool(data.get("ok", False)), "data": data})

    if name == "apply_compat_patches":
        data = ensure_compat_patches()
        return _dump({"ok": bool(data.get("ok", False)), "data": data})

    if name == "search_academic_papers":
        query = arguments.get("query")
        if not query:
            raise ValueError("query 不能为空")
        source = str(arguments.get("source", "all"))
        max_results = _as_int(arguments.get("max_results_per_source"), 8)
        timeout = _as_int(arguments.get("timeout"), 30)
        s2_api_key = arguments.get("s2_api_key")
        data = search_academic_papers(
            query=str(query),
            source=source,
            max_results_per_source=max_results,
            timeout=timeout,
            s2_api_key=str(s2_api_key) if s2_api_key else None,
        )
        return _dump(data)

    if name == "list_academic_source_capabilities":
        s2_api_key = arguments.get("s2_api_key")
        timeout = _as_int(arguments.get("timeout"), 30)
        data = list_academic_source_capabilities(
            s2_api_key=str(s2_api_key) if s2_api_key else None,
            timeout=timeout,
        )
        return _dump(data)

    if name == "fetch_paper_fulltext":
        data = fetch_paper_fulltext(
            title=str(arguments.get("title")) if arguments.get("title") else None,
            doi=str(arguments.get("doi")) if arguments.get("doi") else None,
            arxiv_id=str(arguments.get("arxiv_id")) if arguments.get("arxiv_id") else None,
            url=str(arguments.get("url")) if arguments.get("url") else None,
            timeout=_as_int(arguments.get("timeout"), 30),
            unpaywall_email=str(arguments.get("unpaywall_email")) if arguments.get("unpaywall_email") else None,
            s2_api_key=str(arguments.get("s2_api_key")) if arguments.get("s2_api_key") else None,
        )
        return _dump(data)

    if name == "sync_zotero_paper_state":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        data = sync_zotero_paper_state(
            project_dir=str(project_dir),
            direction=str(arguments.get("direction") or "pull"),
            library_id=str(arguments.get("library_id")) if arguments.get("library_id") else None,
            api_key=str(arguments.get("api_key")) if arguments.get("api_key") else None,
            library_type=str(arguments.get("library_type") or "user"),
            limit=_as_int(arguments.get("limit"), 50),
            query=str(arguments.get("query")) if arguments.get("query") else None,
            timeout=_as_int(arguments.get("timeout"), 30),
            dry_run=_as_bool(arguments.get("dry_run"), True),
        )
        return _dump(data)

    if name == "letpub_search_journals":
        searchname = str(arguments.get("searchname") or "")
        searchissn = str(arguments.get("searchissn") or "")
        if not searchname and not searchissn:
            raise ValueError("searchname 和 searchissn 至少提供一个")
        timeout = _as_int(arguments.get("timeout"), 30)
        max_items = _as_int(arguments.get("max_items"), 30)
        data = letpub_search_journals(
            searchname=searchname,
            searchissn=searchissn,
            searchfield=str(arguments.get("searchfield") or ""),
            searchimpactlow=str(arguments.get("searchimpactlow") or ""),
            searchimpacthigh=str(arguments.get("searchimpacthigh") or ""),
            timeout=timeout,
            max_items=max_items,
        )
        return _dump(data)

    if name == "letpub_get_journal_detail":
        journalid = arguments.get("journalid")
        if not journalid:
            raise ValueError("journalid 不能为空")
        timeout = _as_int(arguments.get("timeout"), 30)
        data = letpub_get_journal_detail(journalid=str(journalid), timeout=timeout)
        return _dump(data)

    if name == "build_related_work_pack":
        query = arguments.get("query")
        if not query:
            raise ValueError("query 不能为空")
        source = str(arguments.get("source", "all"))
        max_results = _as_int(arguments.get("max_results_per_source"), 8)
        max_items = _as_int(arguments.get("max_items_for_note"), 8)
        timeout = _as_int(arguments.get("timeout"), 30)
        s2_api_key = arguments.get("s2_api_key")
        data = build_related_work_pack(
            query=str(query),
            source=source,
            max_results_per_source=max_results,
            max_items_for_note=max_items,
            timeout=timeout,
            s2_api_key=str(s2_api_key) if s2_api_key else None,
        )
        return _dump(data)

    if name == "list_journal_presets":
        return _dump(list_journal_presets())

    if name == "search_in_journal_preset":
        query = arguments.get("query")
        preset = arguments.get("journal_preset")
        if not query:
            raise ValueError("query 不能为空")
        if not preset:
            raise ValueError("journal_preset 不能为空")
        source = str(arguments.get("source", "all"))
        max_results = _as_int(arguments.get("max_results_per_source"), 12)
        timeout = _as_int(arguments.get("timeout"), 30)
        s2_api_key = arguments.get("s2_api_key")
        data = search_in_journal_preset(
            query=str(query),
            journal_preset=str(preset),
            source=source,
            max_results_per_source=max_results,
            timeout=timeout,
            s2_api_key=str(s2_api_key) if s2_api_key else None,
        )
        return _dump(data)

    if name == "recommend_target_journals":
        topic = arguments.get("topic")
        if not topic:
            raise ValueError("topic 不能为空")
        target_preference = str(arguments.get("target_preference") or "any")
        max_candidates = _as_int(arguments.get("max_candidates"), 5)
        max_results = _as_int(arguments.get("max_results_per_source"), 10)
        timeout = _as_int(arguments.get("timeout"), 30)
        s2_api_key = arguments.get("s2_api_key")
        data = recommend_target_journals(
            topic=str(topic),
            target_preference=target_preference,
            max_candidates=max_candidates,
            max_results_per_source=max_results,
            timeout=timeout,
            s2_api_key=str(s2_api_key) if s2_api_key else None,
        )
        return _dump(data)

    if name == "verify_reference":
        title = arguments.get("title")
        doi = arguments.get("doi")
        if not title and not doi:
            raise ValueError("title 和 doi 至少提供一个")
        timeout = _as_int(arguments.get("timeout"), 30)
        s2_api_key = arguments.get("s2_api_key")
        year_raw = arguments.get("year")
        year_val = _as_int(year_raw, 0) if year_raw is not None else None
        if year_val is not None and year_val <= 0:
            year_val = None
        data = verify_reference(
            title=str(title) if title else None,
            authors=arguments.get("authors"),
            year=year_val,
            doi=str(doi) if doi else None,
            venue=str(arguments.get("venue")) if arguments.get("venue") else None,
            timeout=timeout,
            s2_api_key=str(s2_api_key) if s2_api_key else None,
        )
        return _dump(data)

    if name == "generate_deep_research_prompt":
        topic = arguments.get("topic")
        known_data = arguments.get("known_data")
        writing_direction = arguments.get("writing_direction")
        if not topic:
            raise ValueError("topic 不能为空")
        if not known_data:
            raise ValueError("known_data 不能为空")
        if not writing_direction:
            raise ValueError("writing_direction 不能为空")
        max_refs = _as_int(arguments.get("max_references"), 30)
        data = generate_deep_research_prompt(
            topic=str(topic),
            known_data=str(known_data),
            writing_direction=str(writing_direction),
            core_ideas=arguments.get("core_ideas"),
            target_journal=str(arguments.get("target_journal")) if arguments.get("target_journal") else None,
            preferred_sources=arguments.get("preferred_sources"),
            output_language=str(arguments.get("output_language") or "中文"),
            max_references=max_refs,
        )
        return _dump(data)

    if name == "generate_deep_research_prompt_set":
        topic = arguments.get("topic")
        known_data = arguments.get("known_data")
        writing_direction = arguments.get("writing_direction")
        if not topic:
            raise ValueError("topic 不能为空")
        if not known_data:
            raise ValueError("known_data 不能为空")
        if not writing_direction:
            raise ValueError("writing_direction 不能为空")
        data = generate_deep_research_prompt_set(
            topic=str(topic),
            known_data=str(known_data),
            writing_direction=str(writing_direction),
            baseline_models=arguments.get("baseline_models"),
            improvement_modules=arguments.get("improvement_modules"),
            code_assets=arguments.get("code_assets"),
            experiment_results=str(arguments.get("experiment_results")) if arguments.get("experiment_results") else None,
            draft_ideas=str(arguments.get("draft_ideas")) if arguments.get("draft_ideas") else None,
            target_journal=str(arguments.get("target_journal")) if arguments.get("target_journal") else None,
            constraints=str(arguments.get("constraints")) if arguments.get("constraints") else None,
            round_stage=str(arguments.get("round_stage") or "r1"),
            prior_findings=str(arguments.get("prior_findings")) if arguments.get("prior_findings") else None,
            preferred_sources=arguments.get("preferred_sources"),
            output_language=str(arguments.get("output_language") or "中文"),
            max_references=_as_int(arguments.get("max_references"), 30),
            num_prompts=_as_int(arguments.get("num_prompts"), 3),
        )
        return _dump(data)

    if name == "ingest_deep_research_report":
        report_text = arguments.get("report_text")
        report_file_path = arguments.get("report_file_path")
        max_items = _as_int(arguments.get("max_items"), 30)
        data = ingest_deep_research_report(
            report_text=str(report_text) if report_text is not None else None,
            report_file_path=str(report_file_path) if report_file_path else None,
            focus_topic=str(arguments.get("focus_topic")) if arguments.get("focus_topic") else None,
            max_items=max_items,
        )

        note_path = arguments.get("save_reference_note_path")
        if note_path:
            p = Path(str(note_path)).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            content = data.get("quick_note", "") + "\n\n# Headings\n" + "\n".join(
                [f"- {x}" for x in data.get("headings", [])]
            )
            p.write_text(content, encoding="utf-8")
            data["reference_note_path"] = str(p)

        bib_path = arguments.get("save_bib_path")
        if bib_path:
            p = Path(str(bib_path)).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            bib_entries = data.get("bibtex_entries", [])
            if isinstance(bib_entries, list):
                p.write_text("\n\n".join([str(x) for x in bib_entries if str(x).strip()]) + "\n", encoding="utf-8")
            else:
                p.write_text("", encoding="utf-8")
            data["bib_path"] = str(p)

        return _dump(data)

    if name == "synthesize_paper_strategy":
        topic = arguments.get("topic")
        if not topic:
            raise ValueError("topic 不能为空")
        data = synthesize_paper_strategy(
            topic=str(topic),
            target_journal=str(arguments.get("target_journal")) if arguments.get("target_journal") else None,
            baseline_models=arguments.get("baseline_models"),
            improvement_modules=arguments.get("improvement_modules"),
            key_results=str(arguments.get("key_results")) if arguments.get("key_results") else None,
            report_summaries=arguments.get("report_summaries"),
            constraints=str(arguments.get("constraints")) if arguments.get("constraints") else None,
            candidate_title_count=_as_int(arguments.get("candidate_title_count"), 6),
        )
        return _dump(data)

    if name == "run_optimization_loop":
        project_dir = arguments.get("project_dir")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        data = run_optimization_loop(
            project_dir=str(project_dir),
            loop_config_path=str(arguments.get("loop_config_path")) if arguments.get("loop_config_path") else None,
            topic=str(arguments.get("topic")) if arguments.get("topic") else None,
            known_data=str(arguments.get("known_data")) if arguments.get("known_data") else None,
            writing_direction=(
                str(arguments.get("writing_direction")) if arguments.get("writing_direction") else None
            ),
            baseline_models=arguments.get("baseline_models"),
            improvement_modules=arguments.get("improvement_modules"),
            target_journal=str(arguments.get("target_journal")) if arguments.get("target_journal") else None,
            constraints=str(arguments.get("constraints")) if arguments.get("constraints") else None,
            query=str(arguments.get("query")) if arguments.get("query") else None,
            source=str(arguments.get("source")) if arguments.get("source") else None,
            max_rounds=arguments.get("max_rounds"),
            min_score_improvement=arguments.get("min_score_improvement"),
            patience=arguments.get("patience"),
            target_score=arguments.get("target_score"),
            max_results_per_source=arguments.get("max_results_per_source"),
            max_items_for_note=arguments.get("max_items_for_note"),
            num_prompts=arguments.get("num_prompts"),
            timeout=arguments.get("timeout"),
            s2_api_key=str(arguments.get("s2_api_key")) if arguments.get("s2_api_key") else None,
            enable_journal_recommendation=arguments.get("enable_journal_recommendation"),
            target_preference=str(arguments.get("target_preference")) if arguments.get("target_preference") else None,
            max_candidates=arguments.get("max_candidates"),
            write_daily_review=arguments.get("write_daily_review"),
            append_claim_evidence=arguments.get("append_claim_evidence"),
        )
        return _dump(data)

    if name == "init_model_diagram_pack":
        project_dir = arguments.get("project_dir")
        model_name = arguments.get("model_name")
        if not project_dir:
            raise ValueError("project_dir 不能为空")
        if not model_name:
            raise ValueError("model_name 不能为空")
        data = init_model_diagram_pack(
            project_dir=str(project_dir),
            model_name=str(model_name),
            drawio_file_path=str(arguments.get("drawio_file_path")) if arguments.get("drawio_file_path") else None,
            truth_priority=str(arguments.get("truth_priority") or "auto"),
            mermaid_code=str(arguments.get("mermaid_code")) if arguments.get("mermaid_code") else None,
            modules=arguments.get("modules"),
            output_subdir=str(arguments.get("output_subdir") or "figures/model-diagram"),
            force=_as_bool(arguments.get("force"), False),
        )
        return _dump(data)

    raise ValueError("未知工具: %s" % name)


def main() -> None:
    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()

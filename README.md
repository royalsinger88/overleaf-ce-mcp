# overleaf-ce-mcp

面向自建 Overleaf Community Edition 的 MCP 服务原型。

核心思路：
- 通过 `overleaf-sync-ce` (`ols`) 完成 CE 双向同步。
- 在本地生成/维护出版社 LaTeX 模板稿件（含 Ocean Engineering 模板骨架）。
- 通过 MCP 工具在 AI 会话里直接完成“写稿 -> 同步 -> 编译”。

## 1. 安装

```bash
cd /root/overleaf-ce-mcp
/root/miniconda3/bin/python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install .
```

说明：
- 需要 Python `>=3.11`。本机建议直接使用 `miniconda` 自带 Python。
- 也可以直接执行 `bash scripts/bootstrap.sh` 自动完成安装。

安装外部依赖（按需）：

```bash
# Overleaf CE 同步工具
pip install overleaf-sync-ce

# 本地编译（可选）
sudo apt-get update
sudo apt-get install -y texlive-latex-base texlive-latex-extra latexmk
```

## 2. 启动

```bash
source /root/overleaf-ce-mcp/.venv/bin/activate
overleaf-ce-mcp
```

## 2.2 测试与 CI

本地测试：

```bash
cd /root/overleaf-ce-mcp
python3 -m pip install -e . --no-deps
python3 -m pip install "mcp>=1.0.0" "requests>=2.31.0" "beautifulsoup4>=4.11.1" "pytest>=8.0.0"
pytest -q
python3 -m compileall overleaf_ce_mcp
```

CI：
- GitHub Actions 工作流：`.github/workflows/ci.yml`
- 覆盖 Python `3.11` / `3.12`
- 执行 `compileall + pytest`

## 2.1 Docker 运行

```bash
cd /root/overleaf-ce-mcp
docker build -t overleaf-ce-mcp:latest .
docker run --rm -it \
  -v /root/overleaf-workspace:/workspace \
  -v /root/.olauth:/root/.olauth \
  -w /workspace \
  overleaf-ce-mcp:latest
```

可选：需要容器内 `latexmk` 时，构建加上 `--build-arg INSTALL_LATEX=1`。

详细说明见：
- `docs/Docker部署.md`
- `docs/使用手册.md`
- `docs/快速上手.md`

## 3. 可用工具

- `check_environment`: 检查 `ols/latexmk/zip/unzip` 是否可用
- `ols_login`: 执行 Overleaf 登录并生成 `.olauth`
- `ols_list_projects`: 列出账号项目
- `ols_sync`: 双向/单向同步本地项目目录
- `init_manuscript_from_template`: 初始化模板稿件目录（默认包含 `paper_state`）
- `init_paper_state_workspace`: 在已有项目中补建 `paper_state` 状态目录
- `write_file`: 写入或覆盖文本文件
- `compile_latex`: 本地调用 `latexmk` 编译
- `package_project_zip`: 打包项目目录
- `upload_project_zip`: 将 zip 稿件上传到 CE 并创建新项目（通用上传）
- `upload_project_dir`: 将本地目录按通用规则打包后上传到 CE（创建新项目或覆盖已有项目）
- `health_check_project`: 检查项目可见性与可编译性
- `apply_compat_patches`: 手动触发兼容补丁（通常无需手动执行）
- `search_academic_papers`: 检索论文（默认 arXiv + OpenAlex + Crossref，可选 Semantic Scholar；支持显式 OpenReview）
- `list_academic_source_capabilities`: 列出检索适配器能力和可用状态
- `search_openreview_papers`: 显式检索 OpenReview 顶会论文（ICLR/NeurIPS/ICML）
- `fetch_paper_fulltext`: 按回退链拉取论文可用文本（OA/元数据/摘要）
- `sync_zotero_paper_state`: `paper_state` 与 Zotero 同步（pull/push/bidirectional，支持 dry-run）
- `letpub_search_journals`: 通过 LetPub 检索期刊关键信息
- `letpub_get_journal_detail`: 抓取 LetPub 期刊详情字段（IF/JCR/审稿速度/OA/投稿网址等）
- `build_related_work_pack`: 生成相关工作素材包（论文清单 + 综述草稿 + BibTeX 草稿）
- `list_journal_presets`: 列出内置期刊/会议预设分组
- `search_in_journal_preset`: 在预设期刊分组中检索论文
- `recommend_target_journals`: 基于主题与检索结果优选投稿期刊
- `verify_reference`: 核验参考文献真伪并输出修正 BibTeX
- `generate_deep_research_prompt`: 生成 GPT 网页版深度研究提示词
- `generate_deep_research_prompt_set`: 生成多组深度研究提示词（R1/R2 迭代）
- `ingest_deep_research_report`: 将深度研究报告转为参考资料包（URL/DOI/arXiv/BibTeX）
- `synthesize_paper_strategy`: 综合多轮研究结果，给出题目/创新点/写作侧重点
- `run_optimization_loop`: 执行受控循环优化并自动沉淀轮次产物（支持停止条件）
- `run_paper_cycle`: 一键执行优化循环 + 日报 +（按策略）周报
- `run_paper_doctor`: 校验 `paper_state/inputs` 规范并给出修复建议
- `list_upgrade_tasks`: 查看六项改造任务的优先级队列
- `run_priority_upgrade_loop`: 按优先级循环执行改造任务（支持断点续跑）
- `list_generic_priority_plan_templates`: 列出内置通用计划模板
- `init_generic_priority_plan`: 从模板初始化 `plan.json`
- `list_generic_priority_tasks`: 读取任意任务计划（JSON）并给出优先级队列
- `run_generic_priority_loop`: 执行通用优先级循环（支持 plan.json 或 task_text 直接输入）
- `generate_daily_review`: 生成每日复盘（自动汇总当日轮次与证据）
- `generate_weekly_summary`: 生成每周总结（自动聚合日报与证据）
- `init_model_diagram_pack`: 生成模型结构图生产包（真值拓扑 + Nano Banana Pro 提示词）

## 4. 模板

内置模板：
- `ocean-engineering-oa`

模板位置：
- `templates/ocean-engineering-oa`

### `paper_state` 工作区（默认生成）

初始化模板后会自动创建：

```text
paper_state/
  inputs/
    project.yaml
    writing_brief.md
    submission_target.yaml
    constraints.yaml
    loop.yaml
    literature/
      seed_queries.yaml
      reading_queue.csv
      refs_raw.bib
    experiments/
      registry.csv
      metrics/
      notes/
  outputs/
  review/
    daily/
    weekly/
  memory/
    claim_evidence.jsonl
```

推荐格式：
- `yaml`：目标、约束、参数
- `csv/parquet`：实验数据与指标
- `md`：思路、复盘、解释
- `bib`：参考文献
- `jsonl`：结论-证据账本

## 5. 通用上传说明

新增上传流程默认使用 CE 的 `/project/new/upload` 接口，避免依赖旧版 socket/file-tree API 差异。

上传时会自动：
- 兼容 `overleaf.sid` / `sharelatex.sid` 两类会话 cookie。
- 自动刷新 `ol-csrfToken`。
- 以 multipart 方式提交 `qqfile`，并补充 `name/type` 元数据（提升 CE 兼容性）。

目录上传默认排除：
- `.git`、`__pycache__`
- `*.aux`、`*.log`、`*.pdf`、`*.zip` 等编译产物

可通过 `exclude_globs`（字符串数组）额外追加排除规则。

### `upload_project_dir` 模式

- 新建项目模式（默认）：
  - 不传 `target_project`
  - 行为：打包 -> 上传 -> 创建新项目

- 已有项目模式：
  - 传 `target_project`
  - `existing_project_strategy=merge`：合并更新，不主动删除远端多余文件
  - `existing_project_strategy=replace`：按本地覆盖远端（会删除远端本地不存在的文件）
  - 同步安全护栏：当传 `project_name` 且 `workspace_path` 下存在同名子目录时，会自动收敛到该子目录，避免误同步整个 workspace。

- `dry_run=true`：
  - 只输出打包与执行计划，不执行实际上传/同步。

- 健康检查：
  - `health_check=true`（默认）会在操作完成后检查项目可用性
  - `compile_check=true`（默认）会触发编译并返回 PDF 可用性

## 6. 兼容补丁机制

为兼容新旧 CE 的会话与 API 差异，服务会自动应用补丁到依赖：
- `olsync`（cookie 名、project infos 结构、非交互行为等）
- `socketIO_client`（异常兼容）

补丁文件位于：
- `overleaf_ce_mcp/vendor_patches/`

默认会在环境检查和 `ols` 调用前自动确保补丁生效；必要时可手动调用 `apply_compat_patches`。

## 7. 学术检索增强（写作辅助）

新增检索工具：
- `search_academic_papers`
- `letpub_search_journals`
- `letpub_get_journal_detail`
- `build_related_work_pack`
- `list_journal_presets`
- `search_in_journal_preset`
- `recommend_target_journals`
- `verify_reference`

推荐配置：
- 默认 `source=all`：走 `arXiv + OpenAlex + Crossref`，无需任何 API Key
- 如配置了 `S2_API_KEY`：`source=all` 会额外叠加 `Semantic Scholar`
- OpenReview 需显式使用 `source=openreview` 或 `search_openreview_papers`（不默认并入 `all`）
- 可先调 `list_academic_source_capabilities`，由能力清单自动决定检索编排
- 需要“投稿期刊优选”时：先 `list_journal_presets`，再 `recommend_target_journals`
- 需要“引用防幻觉”时：用 `verify_reference` 对标题/DOI 做核验
- 需要“正文抓取”时：用 `fetch_paper_fulltext`，按 `Unpaywall -> OpenAlex DOI -> Crossref DOI -> arXiv -> URL -> 标题检索` 回退
- 需要“文献库沉淀”时：用 `sync_zotero_paper_state`

示例（环境变量）：

```bash
# 仅在你需要 Semantic Scholar 时才设置
export S2_API_KEY="your_semantic_scholar_key"
```

## 8. 深度研究报告协同（GPT 网页版）

推荐链路：
1. 用 `generate_deep_research_prompt_set` 生成 R1 多组提示词。  
2. 在 GPT 网页版深度研究中运行并拿到 R1 报告。  
3. 用 `ingest_deep_research_report` 解析 R1 报告并产出参考包。  
4. 如有不确定点，再用 `generate_deep_research_prompt_set(round_stage=r2)` 生成 R2 提示词并重复。  
5. 用 `synthesize_paper_strategy` 得出题目候选、创新点与写作侧重点。  
6. 将 BibTeX 草稿合并到 `references.bib`，并据此改写引言/相关工作。  

## 8.1 受控循环优化（拉尔夫循环）

推荐直接调用 `run_optimization_loop`，默认读取：
- `paper_state/inputs/loop.yaml`
- `paper_state/inputs/writing_brief.md`

每轮自动产出：
- `paper_state/outputs/optimization_loop/round_XX/round_result.json`
- `paper_state/outputs/optimization_loop/round_XX/round_summary.md`
- `paper_state/outputs/optimization_loop/loop_summary.json`
- `paper_state/outputs/optimization_loop/loop_summary.md`
- `paper_state/review/daily/YYYY-MM-DD.md`（可选）
- `paper_state/memory/claim_evidence.jsonl`（可选）

停止条件（可配）：
- 达到目标分数 `target_score`
- 连续 `patience` 轮提升低于 `min_score_improvement`
- 连续 `patience` 轮无新增证据

配套复盘建议：
- 每天结束执行 `generate_daily_review`
- 每周执行 `generate_weekly_summary`
- 结果会回写 `paper_state/memory/review_state.json`，便于下一轮循环读取上下文

## 8.2 一键论文循环（低摩擦入口）

推荐直接调用 `run_paper_cycle`：
- 默认从 `paper_state/inputs` 读取素材与配置
- 默认启用 `auto_scan_inputs=true`，自动补齐 `topic/known_data/query/...` 缺省参数
- 缺失项会写入 `paper_state/inputs/INPUT_MISSING.md`
- 默认执行：`optimization_loop + daily_review`
- `weekly_mode=auto` 时仅在周五自动补 `weekly_summary`

常用参数：
- `project_dir`（必填）
- `day`（可选，`YYYY-MM-DD`）
- `weekly_mode`：`auto` / `always` / `never`
- `run_loop`、`run_daily`
- `overwrite_reviews`、`write_state`
- `auto_scan_inputs`、`write_missing_checklist`
- `strict_missing`（为 `true` 时，有缺失素材则直接停止）
- `use_cache`、`cache_ttl_hours`、`force_refresh`（控制增量缓存）

## 8.3 优先级改造循环（Skill 化）

可直接调用 `run_priority_upgrade_loop`：
- 自动按优先级执行：`paper_doctor -> 同步闭环 -> 证据绑定 -> 缓存 -> 断点 -> 调度模板`
- `resume=true` 时从 `paper_state/memory/upgrade_loop_state.json` 断点续跑
- `dry_run=true` 可先看计划不落地

## 8.4 通用优先级循环（跨项目复用）

你可以在任意工作目录放一个 `plan.json`，然后运行通用循环。

也可以直接用内置模板初始化：
- `dev-feature-cycle`
- `data-analysis-cycle`
- `docs-quality-cycle`
- `ops-maintenance-cycle`

示例 `plan.json`：

```json
{
  "tasks": [
    {"id":"t1","title":"诊断","impact":10,"effort":2,"dependencies":[],"action":{"type":"noop"}},
    {"id":"t2","title":"执行脚本","impact":8,"effort":3,"dependencies":["t1"],"action":{"type":"shell","cmd":"bash scripts/run.sh"}}
  ]
}
```

也可直接传任务文本（无需 plan 文件）：
- `task_text="1. 改进A\n2. 改进B\n3. 改进C"`
- 可配 `command_template`，例如 `python scripts/improve.py --task {task}`

## 9. 模型结构图协同（Nano Banana Pro）

推荐链路：
1. 先用 draw.io 相关 MCP 生成并确认 `.drawio` 真值文件。  
2. 调用 `init_model_diagram_pack`，传 `drawio_file_path` 生成“真值锁 + 提示词包”。  
3. 先确认 `01-topology-truth.drawio` 与 `01-topology-lock.json`。  
4. 以真值图为参考，在 Nano Banana Pro 用 `02-*` 生成主图。  
5. 用 `03-*` 多轮只改样式，不改结构。  
6. 用 `04-*` 生成局部模块放大图，并用 `05-*` 做一致性核对。  

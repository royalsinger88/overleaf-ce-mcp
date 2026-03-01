# overleaf-ce-mcp 一体化执行参考

## 1. 目标

将“写论文 Skill”与 MCP 工具链打通，形成一条可执行流水线：
- `paper_state` 状态化输入与中间产物沉淀
- 输入规范体检与缺失修复建议
- 文献检索
- 深度研究报告吸收
- 期刊优选与投稿参数补全
- 结构图/图表生产
- 手稿证据覆盖率校验
- LaTeX 写作与编译
- Overleaf CE 同步与健康检查
- 每日/每周自动化调度

## 2. 推荐流水线

1. 初始化与体检：
- 新项目：`init_manuscript_from_template(init_paper_state=true)`
- 旧项目：`init_paper_state_workspace`
- 输入体检：`run_paper_doctor`（先修高优先级缺失）

2. 文献与证据：
- `generate_deep_research_prompt_set`（R1）
- 用户提供 R1 报告后：`ingest_deep_research_report`
- `build_related_work_pack`（主）
- `search_academic_papers`（补，默认无 Key 多源）
- `verify_reference`（关键引用核验）
- `search_in_journal_preset`（按目标刊群匹配）
- `recommend_target_journals`（未定目标刊时）
- `letpub_search_journals` / `letpub_get_journal_detail`（投稿参数补全）
- `generate_deep_research_prompt_set`（R2，必要时）
- `ingest_deep_research_report`（R2）
- `synthesize_paper_strategy`（收敛题目/创新点/写作侧重点）

3. 模型结构图（高要求场景）：
- 先由 draw.io 生成真值图（`.drawio`）
- 再 `init_model_diagram_pack`（传 `drawio_file_path`，`truth_priority=drawio`）
- 用生成的 `02-*`、`03-*`、`04-*` 提示词在 Nano Banana Pro 出主图与局部图
- 用 `05-integrity-checklist.md` 核验

4. 正文与证据落地：
- `write_file`（章节、图注、参考文献）
- `write_file`（更新 `paper_state/memory/claim_evidence.jsonl`）
- `write_file`（每日复盘写入 `paper_state/review/daily/YYYY-MM-DD.md`）
- `write_file`（每周总结写入 `paper_state/review/weekly/YYYY-Www.md`）
- `run_manuscript_evidence_binding`（段落-证据覆盖率报告）
- `compile_latex`（可选，手工模式）

5. 上云与验收（推荐一键）：
- `run_paper_cycle`（推荐）  
  参数建议：
  - `run_compile=true`
  - `sync_mode=sync|upload`
  - `ce_url/store_path/project_name`（按模式填写）
  - `use_cache=true`、`cache_ttl_hours=24`、`force_refresh=false`
- 手工模式：`upload_project_dir` -> `health_check_project`

6. 调度与批处理（可选）：
- `generate_scheduler_templates`（生成 daily/weekly 的 cron 与 systemd 模板）
- `run_priority_upgrade_loop`（一次执行 6 项升级，支持 `resume=true`）

## 3. 关键参数建议

1. 文献检索：
- `source=all`
- `max_results_per_source=8~20`
- 默认走 `arXiv + OpenAlex + Crossref`
- 仅在需要时传 `s2_api_key` 启用 Semantic Scholar

2. 结构图：
- `truth_priority=drawio`
- `force=true`（迭代阶段）

3. 同步策略：
- 日常迭代：`existing_project_strategy=merge`
- 发版对齐：`existing_project_strategy=replace`

4. 一键闭环策略（`run_paper_cycle`）：
- 日常：`run_compile=true` + `sync_mode=sync`
- 验证重跑：`force_refresh=true`
- 仅本地：`sync_mode=none`

## 4. 交付物最小清单

每轮至少输出：
- `main.tex` 路径
- `references.bib` 路径
- `paper_state/inputs` 关键输入文件路径
- `paper_state/outputs` 新增产物路径
- `paper_state/memory/claim_evidence.jsonl` 路径
- `paper_state/outputs/evidence_binding/latest.md` 路径
- `paper_state/review/daily` 当日复盘路径（如有）
- 结构图目录（`figures/model-diagram`）
- 远端项目名/ID（如已同步）
- 健康检查结果（`compile_status`、`has_pdf`）

## 5. 失败回退

1. Semantic Scholar 429：
- 保留无 Key 源（arXiv/OpenAlex/Crossref）继续写作
- 在待确认中提示可选补配 `s2_api_key`

2. 图结构争议：
- 以 `.drawio` + `01-topology-lock.json` 为唯一真值
- 暂停美化，先修正真值图再继续

3. 同步异常：
- 先 `dry_run=true` 预演
- 再执行实际同步

4. 循环中断：
- 优先使用 `run_optimization_loop(resume=true)` 继续
- 或用 `run_priority_upgrade_loop(resume=true)` 从升级断点继续

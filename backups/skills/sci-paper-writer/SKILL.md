---
name: sci-paper-writer
description: 面向 SCI 论文全流程写作与修改的技能。用于选题收敛、论文大纲设计、摘要与正文撰写（IMRaD）、学术英文润色、图表与结果叙述优化、期刊匹配、投稿信生成、审稿意见逐条回复与返修版本整合。用户请求中出现“SCI论文”“英文论文投稿”“审稿回复”“重写摘要/引言/讨论”“按期刊格式改稿”等场景时使用。
---

# SCI Paper Writer

## Overview

将用户的研究目标、实验数据与投稿约束转化为可投稿稿件，默认走“状态化工作区 + 可追溯证据”流程。  
优先输出结构化草稿、可直接替换的段落、可核验引用、以及下一轮最小闭环动作。

## 核心原则

1. 低摩擦入口：优先从 `paper_state` 自动读取素材，不要求用户每轮重复长描述。  
2. 先结构后正文：先交付题目候选、摘要骨架、IMRaD 大纲，再扩写章节。  
3. 事实与表述分离：不改实验事实，只优化逻辑、证据链和语言表达。  
4. 严禁编造：缺失实验细节、统计量、引用来源时，必须标记 `[待补充]`。  
5. 全程可追溯：关键结论必须绑定来源（URL/DOI/arXiv）并记录可信度。  
6. 持续迭代：每日复盘、每周总结，沉淀到 `paper_state/review` 与 `paper_state/memory`。

## 执行流程

1. 识别任务类型：新稿撰写、章节重写、语言润色、投稿材料、审稿回复。  
2. 初始化或补建状态工作区：优先使用 `init_manuscript_from_template(init_paper_state=true)`；已有项目使用 `init_paper_state_workspace`。  
3. 从 `paper_state/inputs` 读取最小必要信息：  
   - `project.yaml`：题目、作者、领域  
   - `writing_brief.md`：研究问题、创新点、风险  
   - `submission_target.yaml` / `constraints.yaml`：投稿目标与限制  
   - `inputs/experiments/*`：实验数据与记录  
   - `inputs/literature/*`：检索种子、阅读队列、Bib 草稿  
4. 文献四阶段（默认开启）：  
   - 调研：`generate_deep_research_prompt_set(round_stage=r1)` 生成多组深度研究提示词。  
   - 筛选：`ingest_deep_research_report` + `build_related_work_pack` 得到候选文献与相关工作草稿。  
   - 精读：`search_academic_papers` / `search_in_journal_preset` 按目标刊源补检索。  
   - 整合：`verify_reference` 核验关键引用并沉淀到 `claim_evidence.jsonl`。  
5. 投稿期刊优选（用户未定目标刊时默认执行）：  
   - `recommend_target_journals` 生成候选清单。  
   - `letpub_search_journals` / `letpub_get_journal_detail` 补全 IF、审稿速度、OA 等字段。  
6. 策略收敛：`synthesize_paper_strategy` 输出题目池、创新点、写作侧重点、章节优先级。  
7. 写作落地：按 IMRaD 产出章节草稿，并同步更新 `outputs/`、`memory/claim_evidence.jsonl`。  
8. 图表与结构图：优先 “draw.io 真值拓扑 -> 风格化重绘 -> 拓扑一致性核验”。  
9. 证据覆盖率校验：`run_manuscript_evidence_binding` 输出“段落-证据覆盖率”并标记未覆盖段落。  
10. 交付与验收：优先 `run_paper_cycle(run_compile=true, sync_mode=sync|upload)` 一键闭环；或手工 `compile_latex` -> `upload_project_dir` -> `health_check_project`。  
11. 复盘沉淀：每日复盘写入 `review/daily/`，每周总结写入 `review/weekly/`。

## 输出格式约定

1. 默认按以下顺序输出：  
   - `交付物`：本轮产出内容列表  
   - `正文`：可直接使用的段落或模板  
   - `修改说明`：关键改写策略与理由  
   - `待确认`：需要用户补齐的信息  
   - `落盘路径`：新增/更新文件绝对路径  
2. 若用户仅要“最终文稿”，只输出正文并在末尾保留最小待确认项。  
3. 术语首次出现时给出全称，后续统一缩写。  
4. 数值、样本量、p 值、置信区间必须与用户输入一致；缺失时使用 `[待补充]`。  
5. 引用信息按三层标注：  
   - `已核验`：来自工具返回且字段完整（标题/作者/年份/来源）。  
   - `待核验`：仅有部分元数据或来源不稳定。  
   - `待补充`：用户提及但未检索到。  

## 任务分流

1. 用户要求“写整篇/搭框架/扩写章节”时：读取 `references/section-playbook.md`。  
2. 用户要求“选刊/投稿信/审稿回复/返修说明”时：读取 `references/submission-and-rebuttal.md`。  
3. 用户指定具体期刊时：先生成“期刊约束卡（scope、格式、审稿模式、OA 选项）”，再改写稿件；可用 LetPub 工具做参数补全。若为 *Ocean Engineering*，读取 `references/journal-ocean-engineering.md`。  
4. 用户明确要 OA 时：先判断 `Gold OA`、`Hybrid OA`、`Green OA` 路径与预算，再生成投稿方案。  
5. 用户要求“查文献/补引用/写相关工作”时：读取 `references/literature-search-and-citation.md`，并优先走“深度研究报告链路 + 结构化检索链路”。  
6. 用户只给出零散想法时：先补齐 `paper_state/inputs` 最小字段，再产出“问题定义 + 最小实验设计 + 章节骨架”。  
7. 用户给出完整草稿时：执行“结构诊断 -> 逻辑修复 -> 文献补强 -> 语言润色 -> 投稿适配”。  
8. 用户要求“模型结构图/论文可视化图表”时：读取 `references/overleaf-mcp-integration.md`，并优先走“draw.io 真值 -> Nano Banana Pro 风格化 -> 一致性核验”流程。  
9. 用户要求“批处理一次执行完 6 项改进”时：优先调用 `run_priority_upgrade_loop`；若需跨项目泛化，调用 `run_generic_priority_loop`。  

## 质量门槛

1. 论证完整：研究缺口 -> 方法选择 -> 结果证据 -> 结论边界。  
2. 结构完整：标题、摘要、关键词、IMRaD、结论、局限性、数据可用性声明。  
3. 语言合规：学术英文简洁、避免口语化、避免绝对化结论。  
4. 引用可追溯：关键结论必须可回溯到具体条目（标题/作者/年份/来源）并有核验状态。  
5. 图表可追溯：结构图必须有真值源（优先 `.drawio`）与拓扑锁记录。  
6. 投稿可用：与目标期刊 scope、字数、图表规范一致。  
7. 状态可延续：本轮中间产物必须沉淀到 `paper_state`，支持下一轮自动接续。

## 工具编排（overleaf-ce-mcp）

默认按以下顺序调用（按需裁剪）：
1. `init_manuscript_from_template` 或 `init_paper_state_workspace`：初始化状态化工作区。  
2. `run_paper_doctor`：先做输入规范体检（缺失项先修复）。  
3. `generate_deep_research_prompt_set(round_stage=r1)` -> `ingest_deep_research_report`。  
4. `build_related_work_pack` + `search_academic_papers`：补齐候选文献和 Bib 草稿。  
5. `verify_reference`：核验关键引用并更新证据账本。  
6. `recommend_target_journals`（未定目标刊）-> `letpub_search_journals` / `letpub_get_journal_detail`。  
7. `search_in_journal_preset`：按目标刊群做方向匹配校验（可选）。  
8. `generate_deep_research_prompt_set(round_stage=r2)`（必要时）-> `ingest_deep_research_report`。  
9. `synthesize_paper_strategy`：收敛题目、创新点、章节优先级。  
10. `init_model_diagram_pack`：生成结构图生产包（draw.io 真值优先）。  
11. `write_file`：写入章节、图注、参考文献、复盘文档。  
12. `run_manuscript_evidence_binding`：生成“段落-证据覆盖率”报告，回填无来源段落。  
13. `run_paper_cycle`：优先一键闭环（支持 `use_cache/cache_ttl_hours/force_refresh`、`run_compile`、`sync_mode`、`ce_url/store_path/project_name`）。  
14. `generate_scheduler_templates`：生成 daily/weekly cron 与 systemd 模板（可选）。  
15. `run_priority_upgrade_loop`：批处理执行六项改进（可选，支持 `resume`）。  

执行时强制产出“可交付物路径清单”，至少包含：
- 稿件主文件路径
- `references.bib` 路径
- 结构图生产包路径
- `paper_state` 关键文件路径（`inputs` / `outputs` / `review` / `memory`）
- 远端项目名/ID（若已同步）

## 快速触发示例

- “帮我把这份实验记录整理成可投稿的 SCI 论文初稿。”  
- “重写我的引言，突出研究缺口和贡献。”  
- “按审稿人 1 和 2 的意见写逐条回复信。”  
- “把方法和结果改成更符合 *IEEE TNNLS* 风格的写法。”  
- “按 *Ocean Engineering* 的 OA 投稿要求改写我的稿件和 Cover Letter。”  
- “先查 arXiv + OpenAlex + Crossref（可选 S2），再给我写 Related Work 和 references.bib。”  
- “用 draw.io 真值图 + Nano Banana Pro 生成模型结构图，并同步到 Overleaf 项目。”  
- “请按 overleaf-ce-mcp 全流程执行：深度研究、补引用、画结构图、写 LaTeX、同步与编译验收。”  

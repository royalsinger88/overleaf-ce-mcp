# 文献检索与引用补强（MCP 集成）

## 1. 目标

在写作前或改稿时，基于学术检索工具快速构建：
- 候选论文池
- Related Work 草稿骨架
- 可用的 BibTeX 条目
- 可核验的“结论-证据账本”

默认优先使用无 Key 数据源：
- arXiv
- OpenAlex
- Crossref

可选数据源：
- Semantic Scholar（传 `s2_api_key` 时启用）

## 2. 何时触发

满足任一条件即触发检索：
1. 用户明确要求“查文献/补引用/写相关工作”。  
2. 用户只给实验数据，没有参考文献。  
3. 草稿中存在“空泛背景描述”且缺少近五年文献支撑。  
4. 用户要求按目标期刊重写引言或讨论。  

## 3. 工具调用顺序

1. 调用 `generate_deep_research_prompt_set(round_stage=r1)` 生成多组深度研究提示词。  
2. 用户提供报告后，调用 `ingest_deep_research_report` 提取 URL/DOI/arXiv/BibTeX 草稿。  
3. 调用 `build_related_work_pack`（建议 `source=all`）做结构化补检索。  
4. 对缺口主题调用 `search_academic_papers` 精细检索（`all/arxiv/openalex/crossref`）。  
5. 如需按目标刊群筛选，调用 `list_journal_presets` + `search_in_journal_preset`。  
6. 关键引用逐条调用 `verify_reference`，输出核验结论与修正 BibTeX。  
7. 若不确定投稿方向，调用 `recommend_target_journals`；必要时再用 `letpub_search_journals` / `letpub_get_journal_detail` 补参数。  
8. 若关键不确定点仍存在，调用 `generate_deep_research_prompt_set(round_stage=r2)` 再深挖，并再次 `ingest_deep_research_report`。  
9. 调用 `synthesize_paper_strategy` 收敛题目、创新点与写作侧重点。  
10. 将候选条目标记为：`已核验` / `待核验` / `待补充`。  
11. 调用 `run_manuscript_evidence_binding` 检查手稿段落是否已绑定证据来源。  

## 4. 推荐检索式模板

按“问题 + 方法 + 场景”组合：

```text
[problem keywords] + [method keywords] + [domain/application]
```

示例（海工）：

```text
offshore wave load prediction physics-informed neural network
```

## 5. 写作落地规则

1. 引言至少包含三类文献：  
- 经典基础工作  
- 近三年代表工作  
- 与本文最接近的对比工作  
2. Related Work 按方法范式分组（physics-based/data-driven/hybrid）。  
3. 讨论部分至少引用 2-4 篇“结果解释型”文献。  
4. 任何“state-of-the-art”或“显著优于”表述都要附对应引用。  

## 6. BibTeX 处理

1. 优先采用工具输出的 `bibtex_entries`。  
2. 合并到 `references.bib` 前去重（DOI/arXiv ID/title key）。  
3. 对 `待核验` 条目保留注释，不直接用于定论。  
4. 关键结论必须落盘到 `paper_state/memory/claim_evidence.jsonl`，至少包含：  
- `claim_id`
- `claim`
- `source_type`（doi/arxiv/url）
- `source`
- `confidence`
- `status`

## 7. 限流与降级策略

1. Semantic Scholar 返回 429 或无 Key 时：  
- 记录错误并提示配置 `s2_api_key`。  
- 不中断流程，继续使用 `arXiv + OpenAlex + Crossref`。  
2. 某个数据源失败时：  
- 回退到可用源。  
- 在“待确认”中标注覆盖不足主题。  
3. 引用核验冲突时：  
- 保留冲突条目为 `status=partial`。  
- 禁止将其作为“显著优于/SOTA”类强结论依据。  

## 8. 缓存与断点建议

1. 日常迭代建议通过 `run_paper_cycle` 驱动，并开启：  
- `use_cache=true`  
- `cache_ttl_hours=24`  
- `force_refresh=false`  
2. 关键参数变化（query/topic/source）或需强制重算时，设置 `force_refresh=true`。  
3. 中断后优先使用 `run_optimization_loop(resume=true)`，避免整轮重跑。  
4. 每轮结束后，至少确认以下文件已更新：  
- `paper_state/outputs/optimization_loop/loop_summary.json`  
- `paper_state/memory/optimization_loop_state.json`  
- `paper_state/memory/claim_evidence.jsonl`  

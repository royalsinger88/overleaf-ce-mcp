# 投稿与审稿回复手册

## 目录

1. 期刊匹配
2. 投稿材料
3. Cover Letter 模板
4. 审稿意见回复（Rebuttal）
5. 返修版本管理
6. 高频问题处理

## 1. 期刊匹配

按以下维度评估目标期刊：

- Scope 匹配：主题与方法是否在期刊关注范围内  
- 文章类型：Original Article / Short Paper / Review  
- 方法偏好：理论、实验、临床或工程应用导向  
- 长度限制：字数、图表数、补充材料要求  
- 审稿周期与录用率（用户若提供偏好则纳入）  

输出建议时给出：

- 主投期刊 1-2 个  
- 备选期刊 2-3 个  
- 每个期刊的匹配理由与风险点  

## 2. 投稿材料

最低投稿包：

1. 主文稿（按期刊模板）  
2. Cover Letter  
3. Highlights（如期刊要求）  
4. Graphical Abstract（如期刊要求）  
5. 冲突声明、数据可用性声明、伦理声明（按需）  
6. 证据覆盖率报告（建议）：`paper_state/outputs/evidence_binding/latest.md`  

## 3. Cover Letter 模板

```text
Dear Editor,

Please find attached our manuscript entitled "[Title]", which we submit for consideration as a [Article Type] in [Journal Name].

This work addresses [problem] by [core method], and demonstrates [main quantitative finding] on [dataset/setting]. We believe this manuscript fits the journal's scope because [scope fit reason].

This manuscript is original, is not under consideration elsewhere, and has been approved by all authors. Any ethical and data statements are included in the manuscript.

Thank you for your time and consideration.

Sincerely,
[Corresponding Author Name]
[Affiliation]
[Email]
```

## 4. 审稿意见回复（Rebuttal）

处理流程：

1. 先分类：致命问题、主要问题、次要问题、格式问题  
2. 逐条回复：每条评论都要有“感谢 + 回应 + 修改位置”  
3. 可验证：标注页码、段落、图表编号  
4. 不回避：无法完全满足时给出合理解释与补偿实验  

逐条回复模板：

```text
Reviewer #X, Comment Y:
[原评论摘录]

Response:
Thank you for this insightful comment. We have [action].
Specifically, we [what changed / justification].
The revised text appears in [Section/Page/Figure].
```

当审稿人意见互相冲突时：

- 先说明冲突点。  
- 选择与研究目标和证据更一致的一侧。  
- 在回复中给出取舍依据。  

## 5. 返修版本管理

每轮返修输出三份内容：

1. `修订稿`：干净版本  
2. `带标注修订稿`：显示修改痕迹或变更摘要  
3. `回复信`：逐条对应评论  

变更记录建议格式：

```text
[Change-ID] [Section]
- Before:
- After:
- Rationale:
- Linked Comment:
```

## 6. 高频问题处理

### 缺实验

- 给出最小补实验方案：数据、指标、预期结论、时间成本。  

### 统计不充分

- 补充显著性检验、置信区间或效应量。  

### 创新性不足

- 重写贡献段，强调“问题新、方法新、证据新”至少一项。  

### 英文表达弱

- 优先修复：时态一致、主谓一致、冗长句拆分、术语统一。  

## 7. 提交前自动校验建议

1. 先执行 `run_paper_doctor`，清空 high 级问题。  
2. 执行 `run_manuscript_evidence_binding`，避免无来源段落。  
3. 推荐执行 `run_paper_cycle(run_compile=true, sync_mode=sync)` 完成闭环验证。  
4. 若需长期持续更新，调用 `generate_scheduler_templates` 生成 daily/weekly 自动任务。  

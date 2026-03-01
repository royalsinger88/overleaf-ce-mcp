# Ocean Engineering 投稿画像（OA导向）

## 1. 期刊定位

- 期刊：`Ocean Engineering`（Elsevier）  
- 领域：海洋工程相关的理论、设计、建造与运维研究  
- 文章类型：原创研究与综述（按官网作者指南）  

## 2. OA 路径（按官方页面）

`Ocean Engineering` 不是纯 OA 期刊，而是支持开放获取选项的混合模式期刊。  

可选路径：

1. Gold/Hybrid OA：文章上线即开放，作者或资助方支付 APC。  
2. 订阅发表：不支付 OA 费用，按订阅访问。  
3. Green OA：可在禁运期后自存档（accepted manuscript）。

## 3. 关键参数（撰写与决策时优先检查）

- APC（Gold OA）：`USD 4020`（不含税，价格以投稿系统最新显示为准）。  
- 可选许可：`CC BY`、`CC BY-NC-ND`、`CC BY-NC`。  
- Green OA 禁运期：`24 months`（accepted manuscript）。  
- 审稿：`single anonymized`，通常至少 2 位审稿人。  

## 4. 面向 OA 投稿的执行模板

### A. 用户给出预算时

1. 判断预算是否覆盖 APC。  
2. 若覆盖：走 Gold OA，并生成许可证建议（默认优先 CC BY，受项目要求约束时调整）。  
3. 若不覆盖：评估机构协议减免、改走订阅发表 + Green OA。  

### B. 用户未给预算时

先输出“投稿前确认清单”：

- 是否强制 OA（基金或单位要求）  
- APC 预算上限  
- 是否可使用机构 OA 协议  
- 期望许可证类型（如资助方要求 CC BY）  

### C. 稿件改写重点

- 引言中明确海工场景痛点（安全、成本、可靠性、环境载荷）。  
- 方法中强调工程可落地性与可复现设置。  
- 结果中给出工程意义解释，不只给统计显著性。  
- 讨论中写清适用边界（工况、海域、尺度、传感器条件等）。  

## 6. MCP 执行建议（Ocean Engineering）

1. 体检：`run_paper_doctor`（先修输入缺失）。  
2. 证据：`run_manuscript_evidence_binding`（检查无来源段落）。  
3. 闭环：`run_paper_cycle` 推荐参数：  
- `run_compile=true`
- `sync_mode=sync`
- `ce_url`、`store_path`、`project_name` 按环境填写
- `use_cache=true`、`cache_ttl_hours=24`
4. 投稿前：`health_check_project` 确认远端可编译并产出 PDF。  

## 5. 直接复用提示词

```text
使用 $sci-paper-writer，目标期刊 Ocean Engineering。请按 OA 路径给出：
1) 投稿策略（Gold OA/订阅+Green OA）；
2) 我这篇稿件的结构化改写建议；
3) 可直接提交的 Cover Letter；
4) 需要我补充的最小信息清单；
5) 运行 run_paper_doctor + run_manuscript_evidence_binding 后的修复清单。
```

# SCI 章节写作手册

## 目录

1. 标题与摘要
2. 引言（Introduction）
3. 方法（Methods）
4. 结果（Results）
5. 讨论（Discussion）
6. 结论（Conclusion）
7. 常用重写模板

## 1. 标题与摘要

### 标题

- 使用“对象 + 方法 + 关键结果/场景”的结构。  
- 控制在 12-18 个英文词。  
- 避免模糊词：novel、effective（无量化支撑时）。  

标题模板：
`[Method/Framework] for [Problem] in [Domain]: [Core Advantage or Result]`

### 摘要

按 5 句结构组织：

1. 背景与问题缺口  
2. 方法核心思想  
3. 数据/实验设置  
4. 关键结果（含量化）  
5. 结论与意义  

摘要模板：

```text
Background: [领域现状与痛点].
Objective: We address [具体研究问题].
Methods: We propose [方法], which [关键机制].
Results: Experiments on [数据集/样本] show [量化结果], outperforming [基线].
Conclusion: These findings indicate [意义], with potential applications in [场景].
```

## 2. 引言（Introduction）

段落顺序：

1. 领域重要性与应用场景  
2. 现有方法局限  
3. 本文问题定义与研究目标  
4. 贡献列表（编号）  
5. 文章结构说明  

贡献写法模板：

```text
The main contributions of this work are three-fold:
(1) We formulate ...
(2) We design ...
(3) We validate ... on ... and achieve ...
```

## 3. 方法（Methods）

最小要素：

- 问题定义与符号表  
- 模型/算法流程  
- 训练或求解细节  
- 复杂度或可解释性分析  

写作要求：

- 每个公式后的变量都要定义。  
- 每个模块说明输入、输出、作用。  
- 给出可复现超参数与实现环境。  

## 4. 结果（Results）

建议结构：

1. 实验设置（数据、指标、基线）  
2. 主结果表格  
3. 消融实验  
4. 鲁棒性/泛化分析  
5. 误差分析或案例分析  

结果表述模板：

```text
As shown in Table X, our method achieves [metric] of [value], which is [delta] higher than [baseline].
The gain is mainly attributed to [机制解释].
```

## 5. 讨论（Discussion）

至少覆盖：

- 结果为何成立（机制解释）  
- 与先前工作的关系  
- 失败案例与局限  
- 外部有效性边界  

避免：

- 把结果重复一遍而不解释原因。  
- 在无证据时进行过度推断。  

## 6. 结论（Conclusion）

使用 3 段式：

1. 研究问题与方法概括  
2. 关键发现（量化）  
3. 局限与未来工作  

结论模板：

```text
This study investigated [problem] using [method].
Results demonstrate [key quantitative finding].
Future work will focus on [limitation -> concrete direction].
```

## 7. 常用重写模板

### 逻辑增强

- 原句：`X is important.`  
- 重写：`X is critical in [context] because it directly affects [outcome], especially under [condition].`

### 学术语气增强

- 原句：`Our method is better.`  
- 重写：`Our method consistently outperforms competitive baselines across [datasets/metrics], suggesting improved [property].`

### 降低绝对化表达

- 原句：`This proves that ...`  
- 重写：`These results suggest that ...`

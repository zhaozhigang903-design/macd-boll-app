# 文档状态：历史对话恢复稿，待基线确认

来源：转到Codex指南，Development Roadmap回复。本文保留原稿；本次 Phase 0 范围以 QUANTAMENTAL_MIGRATION_PLAN.md 为准，仅审计和文档，不执行架构重构。

继续。

现在进入最后一个**工程执行层文档**。

前面的五份文档定义了：

- **战略方向**
- **投资逻辑**
- **数学模型**
- **数据结构**
- **产品形态**

但是 Codex 需要的是：

> “下一步具体做什么，先做什么，完成标准是什么。”

所以这一份是：

# 《Quantamental Investment Engine V1.0 Development Roadmap》

---

# Quantamental Investment Engine V1.0

# Development Roadmap

## Engineering Implementation Plan

版本：V1.0

目标：

将 Quantamental 投资框架转化为可运行的软件系统。

---

# 1. 开发总体原则

## 核心原则

不要一次开发完整系统。

采用：

> 数据底座 → 因子计算 → 投资决策 → 回测验证 → 用户界面

逐层验证。

---

# 2. 总体开发路线

```text id="6krh3x"
Phase 0

项目重构与架构确认

          ↓

Phase 1

Data Engine

          ↓

Phase 2

Factor Engine

          ↓

Phase 3

Stock Ranking

          ↓

Phase 4

Backtesting

          ↓

Phase 5

Portfolio Management

          ↓

Phase 6

AI + Advanced Intelligence

```

---

# Phase 0
# 项目架构重构

## 目标

让现有 MACD-BOLL App 转变为：

Quantamental Engine。


---

## 任务

### 0.1 建立项目规范

新增：

```text id="p6g9r3"
docs/

├── Architecture.md

├── Factor_Dictionary.md

├── Backtest_Spec.md

├── Data_Schema.md

└── PRD.md

```

---

### 0.2 建立版本体系

策略：

```text id="5mhx7a"
Strategy_V1.0

↓

Strategy_V1.1

↓

Strategy_V2.0

```

代码：

```text id="ij8c1h"
release/v1.0

```

---

## 验收标准

完成：

- 项目文档完整
- 模块边界明确
- 不影响当前系统运行

---

# Phase 1
# Data Engine

## 优先级：

P0


这是整个系统基础。

---

# 目标

建立统一数据层。


---

# 任务1：

## 接入数据源


优先级：

### 第一：

iFind API


### 第二：

AKShare


### 第三：

Baostock


---

架构：

```text id="0dcb5g"
Data Provider Interface


        |

 ┌──────┼──────┐

iFind AKShare Baostock

```

---

# 任务2：

建立数据库


实现：

PostgreSQL


核心表：

- security_master
- daily_price
- weekly_price
- fundamental_snapshot

---

# 任务3：

数据质量检查


自动检查：

- 缺失
- 异常价格
- 财务异常


---

## 验收标准

系统可以：

输入：

股票代码


输出：

完整：

- 日K
- 周K
- 财务数据


---

# Phase 2
# Factor Engine

## 优先级：

P0


---

# 目标

实现：

Quantamental评分。


---

# 第一阶段只做三个核心因子

不要一次全部实现。


原因：

避免复杂化。


---

## V1.0 Factor

### Quality

30%


### Value

25%


### Momentum

20%


---

Growth和Risk：

Phase 2.1加入。


---

# 任务


建立：

```text id="7j0p9f"
factor_engine

├── quality.py

├── value.py

├── momentum.py

└── composite.py

```

---

# 输出：

例如：


```json
{
"symbol":"0700.HK",

"quality":92,

"value":78,

"momentum":85,

"alpha_score":87

}

```

---

## 验收标准

每日可以生成：

全市场Alpha排名。


---

# Phase 3
# Stock Scanner

## 优先级：

P0


---

# 目标：

实现：

“发现机会”。


---

输入：

市场：

A股/HK


条件：

Alpha Score >80


---

输出：

Top 50股票。


---

页面：

表格：

|股票|Alpha|Quality|Value|
|-|-|-|-|
腾讯|87|92|75|

---

## 验收标准

扫描：

5000股票

时间：

<5分钟


---

# Phase 4
# Backtesting Engine

## 优先级：

P0


这是决定系统价值的核心。


---

# 目标：

验证：

策略是否有效。


---

实现：

## Historical Simulation


支持：

- 股票池
- 因子排序
- 定期调仓


---

# 第一版回测：

策略：

每月：

买入Alpha Top 50


持有：

1个月


---

输出：

- CAGR
- Max DD
- Sharpe
- Win Rate


---

# 第二版：

加入：

MACD/BOLL Timing


比较：


模型A：

Alpha


vs


模型B：

Alpha + Timing


---

## 验收标准

回答：

> MACD/BOLL是否真的增加收益风险比？


---

# Phase 5
# Portfolio Engine

## 优先级：

P1


---

# 目标：

从：

选股票


升级：

管理组合。


---

实现：


## Position Recommendation


输出：

目标仓位。


---

考虑：

- Alpha
- 风险
- 相关性


---

例如：

腾讯：

系统建议：

7%


而不是：

“买入”。

---

# Phase 6
# Risk Engine

## 优先级：

P1


---

功能：

每日检查：

## 个股

- 财务恶化
- 趋势破坏


## 组合

- 行业集中
- Beta过高


---

输出：

风险报告。


---

# Phase 7
# AI Intelligence Layer

## 优先级：

P2


---

接入：

DeepSeek / GPT


---

功能：

## AI Investment Memo


自动生成：

股票研究报告。


---

格式：

```text id="xg5v7q"
投资逻辑

优势

风险

估值

催化剂

结论

```

---

# Phase 8
# Advanced Quant

## P3


以后再做：

---

## Machine Learning


例如：

预测：

未来6个月收益概率。


---

## Alternative Data


包括：

- 新闻
- 资金流
- 舆情


---

## Factor Optimization


自动寻找：

稳定参数。


---

# 3. Codex开发任务拆分

未来不要给Codex：

“开发整个系统”。


应该拆：

---

## Sprint 1

任务：

建立Data Engine


输入：

Data Schema


输出：

数据库+API


---

## Sprint 2

任务：

Factor Engine


输入：

Factor Dictionary


输出：

评分模块


---

## Sprint 3

任务：

Scanner


---

## Sprint 4

任务：

Backtest


---

## Sprint 5

任务：

Portfolio


---

# 4. GitHub Issue设计

例如：

---

## ISSUE-001

标题：

Implement Fundamental Data Layer


描述：

根据 Data Schema 实现：

- fundamental_snapshot
- data ingestion
- validation


验收：

数据库存在对应字段。

---

## ISSUE-002

标题：

Implement Quality Factor


描述：

根据 Factor Dictionary 实现：

ROE

ROIC

Cash Flow Quality


验收：

输出0-100分。


---

# 5. 不允许Codex做的事情

非常重要。


## 禁止：

### ❌ 自己修改投资逻辑


例如：

Codex不能：

“为了提高收益，把Momentum权重改成40%。”


---

### ❌ 只根据回测结果优化


例如：

发现：

MACD参数12/26赚钱。


不能直接固化。


---

### ❌ 重构核心架构


除非经过确认。


---

# 6. 第一版MVP定义

不要追求完整版。

V1.0 MVP：

必须只有：

## 数据

✅ 股票数据

✅ 财务数据


## 策略

✅ Quality

✅ Value

✅ Momentum


## 输出

✅ 股票排名

✅ 个股分析


## 验证

✅ 回测


---

# 7. 最终产品路线

```text id="xqgqjo"
现在：

MACD-BOLL工具


        ↓


Quantamental V1.0


        ↓


机构化个人投资系统


        ↓


AI Investment Assistant


```

---

# 8. 给Codex的第一阶段任务

我建议真正开始开发时，第一条指令不是：

“帮我写代码”。

而是：

---

```text
Please read all project documents first:

1. Architecture.md
2. Factor_Dictionary.md
3. Backtest_Specification.md
4. Data_Schema.md
5. PRD.md
6. Development_Roadmap.md

Do not modify existing code.

First analyze the current repository and create:

PROJECT_MIGRATION_PLAN.md

Explain:

1. Current architecture
2. Required changes
3. Migration risks
4. Phase 1 implementation plan

Wait for approval before coding.
```

---

现在这套体系已经完整：

✅ 投资框架  
✅ 因子模型  
✅ 回测标准  
✅ 数据设计  
✅ 产品设计  
✅ 开发路线  

下一步就不是继续写文档，而是：

**把这6份文档整理成一个 Codex 可以读取的项目文档包，并开始迁移现有 macd-boll-app。**

我建议下一步做：

**《AGENTS.md —— Quantamental Engine 项目宪法》**

因为这是 Codex 长期协作最重要的文件。它相当于告诉 Codex：

> “这个项目永远遵守哪些原则，什么不能随便改。”

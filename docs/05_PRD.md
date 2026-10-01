# 文档状态：历史对话恢复稿，待基线确认

来源：转到Codex指南，PRD回复；正文按可读取对话保留。示例评分、仓位、阈值不代表已批准生产参数。与路线图冲突见 README。

继续。

现在进入最后一个开发前核心文档：

# 《Quantamental Investment Engine V1.0 Product Requirement Document (PRD)》

这份文档的作用：

前面四份解决：

- **为什么这样投资**（Architecture）
- **怎么算评分**（Factor Dictionary）
- **如何证明有效**（Backtesting）
- **数据怎么存**（Data Schema）

这一份解决：

> **用户实际如何使用这个系统。**

它是交给 Codex 开发前端、后端、API、任务流的产品蓝图。

---

# Quantamental Investment Engine V1.0
# Product Requirement Document (PRD)

## Intelligent Long-Term Investment Decision Platform

版本：V1.0

---

# 1. 产品定位

## 产品名称

Quantamental Investment Engine


## 产品使命

建立一个面向个人长期投资者的：

> 机构化投资研究与决策辅助平台。


---

# 2. 用户角色

## Primary User

长期投资者。


典型需求：

- 找优秀公司
- 判断合理价格
- 寻找买点
- 管理组合
- 控制风险


---

# 3. 核心用户流程

整体流程：

```text id="t0n5ay"
市场股票池

↓

量化筛选

↓

因子评分

↓

候选股票池

↓

AI研究分析

↓

技术择时

↓

组合建议

↓

持仓管理

↓

风险监控

```

---

# 4. 产品信息架构

App结构：

```text id="f43xng"
Quantamental Engine


├── Dashboard 首页

├── Stock Scanner 股票扫描

├── Stock Analysis 个股分析

├── Portfolio 组合管理

├── Backtest 回测中心

├── Strategy 策略中心

├── Risk Monitor 风险监控

└── Settings 系统设置

```

---

# 5. Dashboard 首页

## 目标

用户打开App，30秒知道：

> 市场怎么样？我的组合怎么样？机会在哪里？


---

## 页面结构


## 第一层：Market Overview


显示：

### A股

- 沪深300趋势
- 中证500趋势


### 港股

- 恒生指数
- 恒生科技


### 市场状态

```text
Risk ON

Neutral

Risk OFF

```


---

## 第二层：Portfolio Summary


显示：

我的组合：

```
总资产

今日收益

累计收益

最大回撤

仓位

风险等级
```


---

## 第三层：Opportunity Radar


显示：

今日机会：

例如：

```
A级机会：

5只


关注：

20只


风险：

3只
```


---

# 6. Stock Scanner 股票扫描

## 核心功能

回答：

> 现在市场有哪些值得研究？


---

# 页面


## Filter


用户可以选择：

市场：

- A股
- 港股


策略：

- Quality
- Value
- Growth
- Momentum


评分：

Alpha >80


---

## 输出表格


字段：


|股票|Alpha|Quality|Value|Momentum|Timing|
|-|-:|-:|-:|-:|-:|
腾讯|88|92|75|85|80|
宁德|84|85|70|90|75|


---

# 排序方式


默认：

Composite Alpha


可切换：

- 最大低估
- 最强趋势
- 最高质量


---

# 7. Stock Analysis 个股分析页

这是核心页面。


---

# 第一屏


股票：

腾讯控股


显示：

```text
Alpha Score

88

Rating:

A

```

---

# 第二屏

## Factor Breakdown


五因子雷达图：

```
Quality    92

Value      75

Momentum   85

Growth     88

Risk       80

```

---

# 第三屏

## Investment Thesis


AI自动生成：

优势：

- 企业质量
- 成长来源


风险：

- 估值
- 行业风险


---

# 第四屏

## Timing Analysis


MACD+BOLL模块。


显示：

周线：

```
趋势：

↑

```

日线：

```
Buy 2 Candidate

```


---

# 第五屏

## Valuation


显示：

历史估值位置。


例如：

PE：

过去10年：

40%分位


---

# 8. Buy/Sell Signal System

不要简单：

买入/卖出。


改成：

## Decision State


五种状态：


### Strong Buy

高Alpha

+
好Timing


---

### Watch

公司优秀

等待价格。


---

### Hold


继续持有。


---

### Reduce


风险增加。


---

### Exit


逻辑破坏。


---

# 9. Portfolio Management

## 目标

解决：

> 我应该持有什么？


---

# Portfolio Dashboard


显示：

## Asset Allocation


例如：

股票：

65%

现金：

35%


---

## Factor Exposure


显示：

Quality：

高


Value：

中


Momentum：

高


---

## Risk Exposure


显示：

科技：

35%


消费：

20%


金融：

15%

---

# 10. Position Recommendation

系统输出：


```
腾讯


当前：

5%


建议：

7%


原因：

Alpha提高

Timing改善

组合风险允许

```

---

# 11. Backtest Center

## 功能

用户可以验证：

> 这个策略历史是否有效。


---

# Strategy Builder


选择：

因子：

Quality

Value

Momentum


权重：

调整。


---

# 回测结果


输出：

## Performance


- CAGR
- Sharpe
- Max DD
- Win Rate


---

## Stability


显示：

不同年份表现。


---

## Factor Contribution


例如：

收益来源：


Quality:

40%


Momentum:

35%


Value:

25%


---

# 12. Strategy Center

管理：

策略版本。


例如：

```
Quantamental V1.0

Active


MACD Timing V0.5

Testing

```

---

记录：

- 参数
- 权重
- 修改时间
- 回测结果


---

# 13. Risk Monitor

## 每日检查


监控：

---

## 个股风险


例如：

腾讯：

```
盈利下降:

否

估值过高:

否

趋势破坏:

否

```

---

## 组合风险


例如：

提醒：

```
科技行业暴露超过40%

```

---

# 14. AI Assistant

未来接DeepSeek/GPT。


功能：

## 股票解释


问：

“为什么系统推荐腾讯？”


输出：

逻辑链。


---

## 风险解释


问：

“为什么降低宁德仓位？”


输出：

因子变化。


---

# 15. 自动任务系统

这里解决你之前遇到的问题。


必须分离：


## Scheduled Job


每日：

市场扫描。


---

## Manual Job


用户点击：

立即扫描。


---

架构：

```text id="6lwx2v"
Scheduler Queue

        |

        |

Manual Queue


完全独立

```

禁止：

互相阻塞。

---

# 16. P0 开发优先级

目标：

先形成可用系统。


## P0-1

数据引擎

包括：

- iFind
- AKShare fallback
- 股票基础数据


---

## P0-2

Factor Engine


实现：

Quality

Value

Momentum


---

## P0-3

Stock Scanner


输出：

排名。


---

## P0-4

个股分析页


---

# 17. P1 开发

增强价值。


包括：

- MACD/BOLL Timing
- Portfolio
- Risk Monitor
- AI解释


---

# 18. P2 开发

高级能力。


包括：

- 自动参数优化
- ML模型
- 另类数据
- 新闻情绪


---

# 19. 技术要求

## 后端

模块化：

```text
FastAPI

Python

PostgreSQL

Redis Queue

```


---

## 前端

Dashboard优先。


要求：

- 响应式
- 图表丰富
- 中文友好


---

# 20. 用户体验原则

参考：

Awwwards / Webby / FWA级产品体验标准。


核心：

## Less but Powerful


不要堆信息。


首页：

30秒决策。


---

视觉：

### 信息层级

一级：

投资结论


二级：

原因


三级：

数据


---

颜色：

绿色：

机会


红色：

风险


灰色：

中性


---

动效：

只用于：

- 数据刷新
- 分数变化
- 趋势变化


禁止：

炫技动画。


---

# 21. 验收标准

V1.0上线必须：

## 能回答：

### Q1

现在市场有什么机会？

✔


### Q2

为什么推荐？

✔


### Q3

什么时候买？

✔


### Q4

买多少？

✔


### Q5

风险在哪里？

✔


---

# 22. 最终产品定义

最终不是：

股票预测软件。


而是：

> 一个个人投资者版的 Quantamental Research Platform。


---

# 当前完整开发包

现在已经形成：

|文档|状态|
|-|-|
1. Architecture|✅|
2. Factor Dictionary|✅|
3. Backtesting Specification|✅|
4. Data Schema|✅|
5. PRD|✅|

---

## 下一步真正进入 Codex 前，我建议再做最后一份：

# 《Quantamental Investment Engine V1.0 Development Roadmap》

它会把：

**PRD → GitHub Issue → Codex任务**

拆成：

- Sprint 1（数据层）
- Sprint 2（因子层）
- Sprint 3（扫描）
- Sprint 4（回测）
- Sprint 5（组合）
- Sprint 6（AI增强）

并明确每一步验收标准。

完成这份，你就可以把整套资料交给 Codex 开始工程实现。

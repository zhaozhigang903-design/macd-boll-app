# AGENTS.md

# Quantamental Investment Engine
## Project Constitution

Version: V1.0

---

# 1. Project Identity

## Project Name

Quantamental Investment Engine


## Mission

Build an institutional-grade long-term investment decision system for A-share and Hong Kong equity markets.

The system combines:

- Quantitative factor investing
- Fundamental analysis
- Portfolio construction
- Risk management
- Systematic timing analysis
- AI-assisted investment explanation


The goal is not to predict short-term price movement.

The goal is:

> Systematically improve long-term risk-adjusted investment decisions.

---

# 2. Core Investment Philosophy

The system follows a Quantamental approach.

Investment decisions must answer four questions:

## Question 1

What should we buy?

Responsible module:

Alpha Engine


## Question 2

Why should we buy?

Responsible module:

Fundamental Factor Engine


## Question 3

When should we buy?

Responsible module:

Timing Engine


## Question 4

How much should we buy?

Responsible module:

Portfolio Engine


---

# 3. System Architecture Principles

The system must remain modular.

Core architecture:

```
Universe Engine

        ↓

Alpha Engine

        ↓

Factor Engine

        ↓

Timing Engine

        ↓

Portfolio Engine

        ↓

Risk Engine

        ↓

Validation Engine

        ↓

Explainability Engine
```

---

## Rule 1

Never mix different investment layers.

Examples:

Incorrect:

Using MACD score directly to increase company quality score.


Correct:

Company quality belongs to Alpha Engine.

MACD belongs to Timing Engine.

---

## Rule 2

Every investment logic must have an independent module.

Examples:

Quality:

quality_engine


Value:

value_engine


Momentum:

momentum_engine


Timing:

timing_engine


---

# 4. Factor Investment Principles

The primary Alpha model uses validated quantitative factors.

Core factors:

## Quality

Purpose:

Identify superior businesses.


## Value

Purpose:

Identify attractive valuation.


## Momentum

Purpose:

Capture persistent market trends.


## Growth

Purpose:

Identify sustainable growth.


## Risk

Purpose:

Control downside exposure.


---

# 5. Factor Implementation Rules

## Rule 1

Never use raw indicators directly.

All factors must follow:

```
Raw Data

↓

Cleaning

↓

Outlier Treatment

↓

Industry Adjustment

↓

Standardization

↓

Ranking

↓

Factor Score
```

---

## Rule 2

Avoid arbitrary thresholds.

Bad:

```
ROE > 20 = buy
```

Good:

```
ROE percentile ranking
relative to industry
```

---

## Rule 3

Every factor must have:

1. Economic explanation
2. Mathematical definition
3. Data source
4. Backtest evidence

---

# 6. Market Specific Rules

A-share and Hong Kong markets are different.

Never assume:

One model fits both markets.

Architecture:

```
Quantamental Engine

        |

---------------------

A-share Model

Hong Kong Model

```

---

# 7. Timing Engine Rules

MACD + Bollinger Bands belong only to:

Timing Engine.


They are NOT:

- Company quality factors
- Valuation factors
- Growth factors


Their purpose:

Improve entry and exit timing.


---

## Timing hierarchy

Priority:

```
Weekly trend

↓

Daily setup

↓

Entry confirmation
```


Weekly data has priority over daily data.

---

# 8. Data Rules

## Market Data Priority

Preferred:

1. iFind API

2. AKShare

3. Baostock


---

## Weekly Data Rule

Native weekly K-line is preferred.

Daily aggregation may only be used for:

- Cross validation
- Data checking

---

## Data Quality

All data pipelines must include:

- Missing data detection
- Abnormal value detection
- Timestamp validation

---

# 9. Backtesting Rules

Backtesting is mandatory before strategy changes.

---

## Never accept:

- Single period backtest
- Maximum return optimization
- Parameter mining


---

## Required validation:

- Long historical period
- Out-of-sample testing
- Walk-forward validation
- Transaction cost simulation


---

# 10. Strategy Version Control

All strategy changes require version numbers.


Example:

```
Strategy_V1.0

Strategy_V1.1

Strategy_V2.0
```


---

Never silently change:

- Factor weights
- Signal rules
- Portfolio rules


---

# 11. Portfolio Management Principles

The system manages portfolios, not individual stocks.

---

Rules:

## Position sizing must consider:

- Expected return
- Confidence
- Risk
- Correlation
- Portfolio exposure


---

Never:

```
Highest score = largest position
```

---

# 12. Risk Management Principles

Risk control is independent from Alpha.

The system must monitor:

## Individual risk

- Financial deterioration
- Trend breakdown
- Excessive valuation


## Portfolio risk

- Sector concentration
- Correlation
- Market exposure
- Maximum drawdown


---

# 13. Explainability Requirement

Every recommendation must explain:

WHY.

Not only:

```
Score: 85
```

Must provide:

```
Quality:
Value:
Growth:
Momentum:
Risk:

Reason:

Risk factors:
```

---

# 14. Development Principles

## Code quality

Prioritize:

- Maintainability
- Readability
- Testability
- Modularity


---

## Before changing code

Developer must:

1. Understand existing architecture
2. Identify impacted modules
3. Explain potential risks


---

# 15. Forbidden Actions

The following actions require explicit approval.

---

## Forbidden 1

Changing investment logic without documentation.


---

## Forbidden 2

Adding indicators without economic reasoning.


---

## Forbidden 3

Optimizing only for historical return.


---

## Forbidden 4

Replacing architecture with a completely different framework.


---

## Forbidden 5

Hard-coding strategy parameters.

Incorrect:

```python
if roe > 20:
    score = 10
```


Correct:

Parameters must be configurable.

---

# 16. Task Execution Rules

For every development task:

Follow:

```
Understand

↓

Plan

↓

Implement

↓

Test

↓

Document

↓

Commit
```

---

# 17. Current Development Priority

Priority order:


## Phase 1

Data Engine


## Phase 2

Factor Engine


## Phase 3

Stock Ranking


## Phase 4

Backtesting


## Phase 5

Portfolio Management


## Phase 6

AI Enhancement


---

# 18. Product Philosophy

The system should feel like:

A personal institutional investment platform.

Not:

A stock prediction toy.


---

# Final Principle

Remember:

> Good investment systems are not built by predicting the future. They are built by making disciplined decisions under uncertainty.

Every code change must serve this principle.


## Phase 0 migration guardrails

Current scope: repository audit and documentation only. Do not modify application code, strategy parameters, live databases, deployment settings, or merge into main during Phase 0.

Read docs/README.md before using the design documents. Recovered conversation drafts are design references; missing original specifications and unresolved decisions must remain explicitly marked. Do not treat examples as approved production parameters.

Preserve the existing working system through incremental migration. Keep legacy technical scores separate from future Alpha scores. Verify behavioral equivalence before replacing existing modules.

---
id: m-5
title: "M6 Fundamentals lenses"
---

## Description

Detailed 2026-11-25 (TASK-13). Annual fundamentals (EDGAR point-in-time for US; yfinance for UK/Europe with depth-aware coverage), news, currency-safe valuation, the quality_value AI lens (rubric default + buffett_persona variant) and the price_vs_fundamentals AI lens (divergence-framed). Decisions in finance.md, "Fundamentals: datasets, providers and pinned conventions".

Wave 1: TASK-49 M6.1 contracts, TASK-50 M6.2 kernels, TASK-25 M6.3 critical inputs (no deps, in parallel).
Wave 2: TASK-51 M6.4 EDGAR, TASK-52 M6.5 yfinance fundamentals + news (after 49); TASK-53 M6.6 adapters + calc nodes (after 49, 50); TASK-55 M6.8 quality_value and TASK-56 M6.9 price_vs_fundamentals (after 49, 25).
Wave 3: TASK-54 M6.7 valuation (after 53). Then TASK-57 M6.10 registry, mixed-region run, e2e, variant comparison (after all).
Deferred sketches: TASK-58 filings_text, TASK-59 ESEF provider research, TASK-60 LLM FallbackModel.

**Demo gate:** mixed UK/European/US run on the `dev` profile; UK/European dossiers show lower coverage/confidence; persona vs rubric comparison run.

---
id: TASK-17
title: 'AI lens repeated sampling: stance mode, mean and spread'
status: To Do
assignee: []
created_date: '2026-11-23T09:50:03Z'
labels:
  - core
  - sketch
milestone: m-7
dependencies:
  - TASK-8
references:
  - documentation/design/core.md
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred from TASK-8 (human decision, 2026-11-23). Sketch only. Detail it during M8 planning (TASK-15).

## Why
Agreement across repeated samples is a better uncertainty signal than an LLM's self-stated confidence (Xiong et al., "Can LLMs Express Their Uncertainty?", ICLR 2024). Single LLM-judge ratings show run-to-run noise comparable to the signal. TASK-6 already added the fields this needs: `LensVerdict.stance_mean`, `stance_spread` and `Provenance.stance_samples`.

## Scope sketch
- `AINode` param `samples: int = 1`. It is a node param, so it is part of the memo key automatically.
- Run the agent N times; each run passes the citation and schema guard rail on its own.
- If a majority of samples abstain, the verdict is abstained. Otherwise use only the ok samples:
  - `stance` = mode (ties broken toward the median)
  - `stance_mean` = mean
  - `stance_spread` = population std dev
  - `stance_samples` = every sample's stance, in order
- Claims, flags and conviction come from the first sample whose stance equals the mode. Tokens and attempts are summed.
- Cost scales with N. The `dev` default stays 1, so behaviour and cost are unchanged unless configured.
- Tests: scripted models returning a fixed stance sequence (e.g. [-2, -2, -1, -2, -1] gives stance -2, mean -1.6, spread ≈ 0.49); majority abstain; samples part of the memo key.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

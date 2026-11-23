---
id: m-1
title: "M2 Lenses and dossiers"
---

## Description

Verdict/dossier models, LensNode template with framework-computed coverage and citations, deterministic lenses, AI lens with citation guard rail and model profiles, confidence-weighted aggregation, Panel.

**Demo gate:** toy panel (deterministic + AI lens on the `test` profile) produces dossiers with failed/abstained/thin-coverage cases shown correctly.

**Signed off 2026-11-24** by the human: 245 tests passing on main at ea148d8; toy panel dossiers for S1 (ok), S2 (thin coverage) and S3 (all failed, overall null, confidence 0) reviewed (see TASK-9 final summary). Aggregation default is evidence share (direction x evidence_share).

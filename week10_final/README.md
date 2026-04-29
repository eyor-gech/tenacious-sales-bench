# Week 10 Final Snapshot — Tenacious B2B Conversion Engine
**Frozen:** 2026-04-28
**Purpose:** Week 11 seed assets — do not modify files in this folder

---

## Key Results

| Metric | Value |
|---|---|
| Dev pass@1 (Act I, 30 tasks) | 53.33% — CI [36.67%, 70%] |
| Held-out pass@1 (Act IV, 20 tasks) | **85%** — CI [70%, 100%] |
| Improvement delta | **+33.67 pp** |
| Bootstrap p-value | **0.0001** (10,000 resamples) |
| Cost per task (held-out) | **$0.000229** |
| Adversarial probes triggered | **30 / 30** (100%) |
| Ablation — confidence_aware | 76% pass@1 |
| Ablation — binary_threshold | 70% pass@1 |
| Ablation — no_confidence | 66% pass@1 |

---

## Asset Inventory

### results/ — 12 files
| File | Description |
|---|---|
| `act1_score.json` | Dev evaluation — 30 tasks, 53.33% pass@1, CI, latency, cost |
| `act2_sample_thread.json` | Live NileLedger outreach thread (email → reply → booking confirmed) |
| `act2_interaction_metrics.json` | 5-prospect interaction latency metrics (p50=26.9ms) |
| `act2_result.json` | Aggregated Act II pipeline output |
| `act2_competitor_gap_brief.json` | Schema-compliant competitor gap brief (6 peers, benchmark=2.5/3) |
| `act2_hiring_signal_brief.json` | Schema-compliant hiring signal brief (60-day velocity, 4 sources) |
| `act3_probe_results.json` | 30 adversarial probes — all triggered, trigger_rate=1.0 per category |
| `act4_heldout_summary.json` | Held-out evaluation — 20 tasks, 85% pass@1 |
| `act4_ablation_results.json` | 3-variant ablation (confidence_aware / binary_threshold / no_confidence) |
| `act4_invoice_summary.json` | Cost derivation — $0.000229/task, gpt-4o-mini |
| `act5_evidence_graph.json` | Statistical evidence synthesis — delta, p-value, bootstrap CI |
| `run_summary.json` | Full 5-act run summary with timestamps and status |

### probes/ — 5 files
| File | Description |
|---|---|
| `probe_cases.json` | 30 adversarial probes with scenario, input_payload, expected_failure, business_cost, observed_trigger_rate |
| `probe_library.md` | 10-category rubric coverage table, rationale per category |
| `mechanism_design.md` | Confidence-aware phrasing mechanism, ablation design, unresolved failure |
| `failure_taxonomy.md` | 6 failure categories (revenue, brand, operational, compliance, economic, evaluation) |
| `target_failure_mode.md` | Primary mechanism target (P23 confidence-policy bypass) |

### schemas/ — 2 files
| File | Description |
|---|---|
| `competitor_gap_brief.schema.json` | Versioned JSON Schema for competitor gap brief output |
| `hiring_signal_brief.schema.json` | Versioned JSON Schema for hiring signal brief output |

### data/ — 2 files
| File | Description |
|---|---|
| `sample_companies.json` | 9 synthetic companies (NileLedger + 8 fintech peers) used as prospect universe |
| `jobs_snapshot.json` | 60-day historical open role counts (used for velocity delta computation) |

### traces/ — 1 file
| File | Description |
|---|---|
| `act3_probe_results.json` | Trace records from Act III probe execution (30 traces with trace_ids) |

### source/ — 5 files
| File | Description |
|---|---|
| `enrichment.py` | Unified 4-module signal enrichment orchestrator |
| `signal_confidence.py` | 3-tier confidence-aware phrasing policy (the Act IV mechanism) |
| `competitor_gap.py` | Top-quartile peer selection and capability gap identification |
| `icp_classifier.py` | Segment classification with 0.62 abstention threshold |
| `orchestrator.py` | Main 5-stage pipeline driver |

### reports/ — 3 files
| File | Description |
|---|---|
| `Eyor_Final_Repo.md` | CEO/CFO decision memo — pilot approval, unit economics, stalled-thread delta |
| `report_week10.md` | Week 10 status audit + Week 11 readiness (Path B recommendation) |
| `demo_script.md` | 8-minute recording script for demo video |

### config/ — 1 file
| File | Description |
|---|---|
| `settings.yaml` | Runtime config (icp_threshold=0.62, all integrations sandboxed, mock_mode=true) |

---

## Missing from Snapshot

The following files exist in the live repo but were not included (large or auto-generated):
- `eval/` Python modules (probe_runner.py, ablation.py, stats.py, etc.) — use live repo for execution
- `agent/` full module tree — 5 key source files copied above; full tree in live repo
- `demo-ui/` frontend — not a Week 10 evaluation asset
- `node_modules/` — excluded by design
- `data/tenacious_sales_data/` — gitignored raw data directory

The following files are **not yet generated** and are Week 11 targets:
- `results/probe_strong.json` — probe responses under confidence_aware mode
- `results/probe_degraded.json` — probe responses under no_confidence mode
- `data/dpo_pairs_v1.jsonl` — DPO preference pair dataset (60–100 pairs)

---

## Week 11 Seed Instructions

1. Use `probe_strong.json` + `probe_degraded.json` as the (chosen, rejected) pair source
2. Use `probes/probe_cases.json` as the prompt source (scenario + input_payload.message)
3. Use `probes/failure_taxonomy.md` as the critic scoring rubric
4. Use `results/act4_heldout_summary.json` as the calibration target (85% pass@1)
5. Start from `scripts/run_probe_modes.py` to regenerate the response files if needed

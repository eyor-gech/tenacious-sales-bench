# TenaciousBench v0.1 — Week 11 Interim Submission

**Author:** Eyor Getachew  
**Benchmark version:** v0.1 (Acts I + II covered)  
**Week 10 baseline:** dev pass@1 = 53.33 % · held-out pass@1 = 85 % · Δ = +33.67 pp (p = 0.0001)

---

## What This Is

TenaciousBench is a purpose-built evaluation benchmark for **B2B outbound sales agents**.  
It targets the ten failure dimensions that generic τ²-Bench retail tasks cannot surface. These are signal hallucination, confidence mis-calibration, consent-violating SMS routing, brand-harmful tone, ICP boundary leakage, and five others documented in the Week 10 adversarial probe library.

The interim package (Acts I + II) covers:

| Act | Deliverable | Status |
|-----|-------------|--------|
| I   | Audit + gap analysis (`audit_memo.md`) | complete |
| I   | Schema design (`schema.json`) | complete |
| I   | Dataset authoring — 220 tasks (`tenacious_bench_v0.1/`) | complete |
| I   | Partitioning: train / dev / held_out | complete |
| I   | Datasheet (`datasheet.md`) | complete |
| I   | Contamination checks (`contamination_check.json`) | complete |
| II  | Methodology (`methodology.md`) | complete |
| II  | Inter-rater agreement (`inter_rater_agreement.md`) | complete |
| II  | Generation scripts (`generation_scripts/`) | complete |
| II  | Synthesis memos (`synthesis_memos/`) | complete |
| II  | Scoring evaluator (`scoring_evaluator.py`) | complete |

---

## Repo Structure

```
tenacious-sales-bench/
├── README.md                          ← this file
├── audit_memo.md                      ← gap analysis vs τ²-Bench
├── schema.json                        ← machine-readable task schema + 3 examples
├── scoring_evaluator.py               ← executable Python scorer
├── methodology.md                     ← path declaration + design rationale
├── inter_rater_agreement.md           ← 30-task dual-label study, Cohen's κ
├── datasheet.md                       ← Gebru + Data Cards format
├── contamination_check.json           ← n-gram + embedding dedup results
├── cost_log.csv                       ← per-run cost accounting
├── .env.example                       ← env var template
├── pyproject.toml                     ← UV-ready project manifest
│
├── tenacious_bench_v0.1/
│   ├── train/
│   │   └── train.jsonl                ← 110 tasks
│   ├── dev/
│   │   └── dev.jsonl                  ← 66 tasks
│   └── held_out/
│       └── held_out.jsonl             ← 44 tasks
│
├── generation_scripts/
│   ├── build_tasks.py                 ← task authoring driver
│   ├── judge_filter.py                ← LLM-as-judge quality gate
│   ├── dedup.py                       ← n-gram + embedding deduplication
│   ├── partition.py                   ← stratified train/dev/held_out split
│   └── contamination_check.py        ← overlap + time-shift verification
│
├── synthesis_memos/
│   ├── synthetic_data_best_practices.md
│   └── llm_as_judge_memo.md
│
└── week10_final/                      ← Week 10 source artifacts (read-only)
    ├── results/
    ├── probes/
    ├── source/
    └── reports/
```

---

## Quick Start

```bash
# 1. Create virtual environment with UV
uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. Install dependencies
uv pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# → Edit .env: set OPENROUTER_API_KEY

# 4. Run the scorer on a single task
python scoring_evaluator.py --task tenacious_bench_v0.1/dev/dev.jsonl --task-id TB-DEV-001

# 5. Run contamination check
python generation_scripts/contamination_check.py \
    --train tenacious_bench_v0.1/train/train.jsonl \
    --dev   tenacious_bench_v0.1/dev/dev.jsonl \
    --held  tenacious_bench_v0.1/held_out/held_out.jsonl \
    --out   contamination_check.json

# 6. Rebuild full dataset from scratch (requires OPENROUTER_API_KEY)
python generation_scripts/build_tasks.py --out-dir tenacious_bench_v0.1/raw
python generation_scripts/judge_filter.py --in-dir tenacious_bench_v0.1/raw --out-dir tenacious_bench_v0.1/filtered
python generation_scripts/dedup.py --in-dir tenacious_bench_v0.1/filtered --out tenacious_bench_v0.1/deduped.jsonl
python generation_scripts/partition.py --in tenacious_bench_v0.1/deduped.jsonl --out-dir tenacious_bench_v0.1
```

---

## Week 11 Path Recommendation

**Path B — Judge/Critic via DPO / SimPO / ORPO** is the analytically correct choice.

Evidence from Week 10:

1. **Ablation ordered preference**: `confidence_aware` (0.76) > `binary_threshold` (0.70) > `no_confidence` (0.66). This is a ready-made ranked preference signal.
2. **30 probe (chosen, rejected) triples** from `probe_cases.json` are structurally identical to DPO training pairs.
3. **6-category failure taxonomy** provides the critic's label schema without additional annotation overhead.
4. **+33.67 pp delta (p = 0.0001)** from the held-out evaluation validates that the confidence-aware variant is the ground-truth "chosen" output, i.e. the DPO positive class.

Path A (SFT) is blocked by insufficient volume (17 passing held-out traces).  
Path C (PRM) requires step-level quality annotations that do not yet exist.

---

## Dataset Statistics

| Split | Tasks | Source mode mix | Dimensions covered |
|-------|-------|-----------------|-------------------|
| train | 110 | trace 30% / prog 30% / synth 25% / adversarial 15% | all 10 |
| dev | 66 | trace 30% / prog 30% / synth 25% / adversarial 15% | all 10 |
| held_out | 44 | trace 30% / prog 30% / synth 25% / adversarial 15% | all 10 |
| **total** | **220** | | |

Contamination: 0 n-gram overlaps > 30 % threshold; 0 embedding pairs > 0.85 cosine similarity between held_out and train+dev.

---

## Key Results (Week 10 Seed Evidence)

| Metric | Value | Source |
|--------|-------|--------|
| Dev pass@1 | 53.33 % | `week10_final/results/act1_score.json` |
| Held-out pass@1 | 85.00 % | `week10_final/results/act4_heldout_summary.json` |
| Δ (held-out − dev) | +33.67 pp | `week10_final/results/act5_evidence_graph.json` |
| Bootstrap p-value | 0.0001 | 10 k resamples |
| Cost / task | $0.000229 | `week10_final/results/act4_invoice_summary.json` |
| Probe trigger rate | 30/30 (100 %) | `week10_final/results/act3_probe_results.json` |
| Ablation winner | confidence_aware (0.76) | `week10_final/results/act4_ablation_results.json` |

---

## Major Artifacts

| Artifact | Path | Description |
|----------|------|-------------|
| Audit Memo | [audit_memo.md](audit_memo.md) | Gap analysis vs τ²-Bench, 8 probes + 5 traces |
| Schema | [schema.json](schema.json) | Task schema with 3 inline examples |
| Scoring Evaluator | [scoring_evaluator.py](scoring_evaluator.py) | Executable 6-dimension scorer |
| Methodology | [methodology.md](methodology.md) | Path B declaration + partitioning protocol |
| Inter-Rater Agreement | [inter_rater_agreement.md](inter_rater_agreement.md) | 30-task study, κ = 0.79 |
| Datasheet | [datasheet.md](datasheet.md) | Gebru + Data Cards (7 sections) |
| Contamination Check | [contamination_check.json](contamination_check.json) | N-gram + embedding + time-shift results |
| Synthesis Memo 1 | [synthesis_memos/synthetic_data_best_practices.md](synthesis_memos/synthetic_data_best_practices.md) | Disagreement with Self-Instruct generalisation |
| Synthesis Memo 2 | [synthesis_memos/llm_as_judge_memo.md](synthesis_memos/llm_as_judge_memo.md) | Disagreement with MT-Bench LLM-judge scope |

---

## What's Next (Acts III + IV)

**Act III — Judge Model Training**

- Run all 30 probes twice (full system + degraded `no_confidence` mode) to produce (chosen, rejected) pairs
- Merge probe pairs with 50 synthetic outreach examples labelled by GPT-4o-mini-as-judge → ~80 DPO preference pairs
- Fine-tune a critic adapter (SimPO/ORPO via `trl`) on the train split; fall back to prompted LLM-as-judge if hardware is unavailable

**Act IV — Critic Calibration and Held-Out Evaluation**

- Run the trained/prompted critic on the 44-task held-out split; measure Spearman ρ against pass@1 labels
- Target: ρ ≥ 0.65 for the judge to be considered calibrated
- Replace `observed_behavior: "unknown"` in `probe_cases.json` with live annotated outputs
- Produce `results/act6_judge_eval.json` closing the loop between Week 10 evaluation and Week 11 alignment

**Remaining deliverables:** DPO dataset JSONL, critic calibration curve, `report_week11.md`

---

## Submission Checklist

- `audit_memo.md` — ≥ 8 probe IDs, ≥ 5 trace examples, ≤ 600 words
- `schema.json` — machine-readable, 3 tasks inline
- `scoring_evaluator.py` — executable, returns numeric score + breakdown
- `methodology.md` — path declared, contamination protocol, partitioning
- `inter_rater_agreement.md` — 30-task dual-label, Cohen's κ reported
- `datasheet.md` — Gebru + Data Cards, all sections
- `cost_log.csv` — timestamped, per-bucket
- `contamination_check.json` — n-gram, embedding, time-shift, held_out verdict
- `tenacious_bench_v0.1/` — 220 tasks, 3 splits, JSONL
-  `generation_scripts/` — 5 real Python scripts
- `synthesis_memos/` — 2 one-page memos with paper disagreements
- `pyproject.toml` — UV-ready
- `.env.example` — no secrets committed

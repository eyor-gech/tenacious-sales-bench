# TenaciousBench v0.1

**A 220-task evaluation benchmark for B2B outbound sales agents.**  
Measures ten failure dimensions that no existing benchmark covers: ICP abstention accuracy,
confidence-aware phrasing, signal grounding fidelity, tone safety, hallucination avoidance,
CTA behavior, competitor gap reasoning, pricing discipline, multi-turn objection handling,
and thread continuation coherence.

---

## Current Status

| Component | Status | Details |
|-----------|--------|---------|
| Dataset (220 tasks) | Complete | `tenacious_bench_v0.1/{train,dev,held_out}/` |
| Scoring evaluator | Complete | `scoring_evaluator.py` — 6 dimensions, executable |
| ORPO training | Complete | `training/` — Qwen2.5-7B, LoRA r=16, 17.9 min |
| Ablation harness | Complete | `ablations/` — Delta A/B/C + bootstrap stats |
| Preference pairs | Complete | `training_data/` — 110 train + 66 dev JSONL pairs |
| Evidence graph | Complete | `evidence_graph.json` — all claims sourced |
| Public artifacts | Complete | `public_artifacts/` — blog, dataset card, community |

**Headline result:** ORPO-trained Qwen2.5-7B achieves **90.9% pass@1** (40/44 tasks) on the held-out split,
+6.8 pp over the Week 10 baseline (84.1%, 37/44). Effect is directionally positive across all 10
dimensions; n=44 is underpowered for formal significance (p=0.1953, 95% CI [−6.8, +20.4] pp).

---

## Repo Structure

```
tenacious-sales-bench/
├── tenacious_bench_v0.1/
│   ├── train/train.jsonl          # 110 tasks (50%)
│   ├── dev/dev.jsonl              # 66 tasks (30%)
│   └── held_out/held_out.jsonl    # 44 tasks (20%) — sealed test set
│
├── training_data/
│   ├── train_preferences.jsonl    # 110 (chosen, rejected) ORPO pairs
│   ├── dev_preferences.jsonl      # 66 (chosen, rejected) ORPO pairs
│   ├── generate_preferences.py    # Regenerate pairs from benchmark tasks
│   └── schema.md                  # Preference pair field definitions
│
├── training/
│   ├── train.py                   # ORPO training script (TRL ORPOTrainer)
│   ├── config.yaml                # All hyperparameters, pinned backbone revision
│   ├── run_training.sh            # Launcher
│   ├── training_run.log           # Actual training log
│   ├── train_loss.csv             # Per-step training loss
│   └── eval_loss.csv              # Per-checkpoint eval loss
│
├── ablations/
│   ├── run_ablation.py            # CLI harness (--mode delta_a/b/c/all)
│   ├── bootstrap_stats.py         # Paired bootstrap CI + p-value
│   ├── cost_metrics.py            # Per-task cost/latency Pareto table
│   ├── ablation_results.json      # All ablation results with CIs
│   └── held_out_traces.jsonl      # Week 10 held-out agent traces
│
├── scoring_evaluator.py           # 6-dimension scorer; runnable standalone
├── schema.json                    # Task JSON schema with 3 inline examples
├── methodology_rationale.md       # Path B declaration + evidence + papers
├── methodology.md                 # Full benchmark design methodology
├── datasheet.md                   # Gebru 2018 + Data Cards datasheet
├── inter_rater_agreement.md       # 30-task IRA study, kappa 0.72 to 0.79
├── audit_memo.md                  # Gap analysis with 7 trace references
├── contamination_check.json       # 5 contamination checks, all PASS
├── evidence_graph.json            # Every numeric claim mapped to source
│
├── generation_scripts/            # Task generation pipeline
├── examples/                      # 3 concrete scored examples + runner
├── public_artifacts/              # Blog, dataset card, community issue
├── synthesis_memos/               # LLM-as-judge and synthetic data memos
├── week10_final/                  # Week 10 source evidence
│
├── cost_log_final.csv             # Full cost log including training
├── requirements.txt               # Runtime dependencies
├── pyproject.toml                 # UV/hatchling build config
├── LICENSE                        # MIT
└── final_submission_checklist.md  # Submission status
```

---

## Install

```bash
git clone https://github.com/eyor-gech/tenacious-sales-bench
cd tenacious-sales-bench

# UV recommended
uv venv && source .venv/bin/activate   # Linux/Mac
uv venv && .venv\Scripts\activate      # Windows

pip install -r requirements.txt
cp .env.example .env  # add OPENROUTER_API_KEY
```

---

## Reproduce Headline Result

### 1. Run end-to-end examples (no API key needed for 2/3 tasks)

```bash
python examples/run_examples.py
# TB-EX-001 PASS 0.872 | TB-EX-002 PASS 1.000 | TB-EX-003 FAIL 0.315
```

### 2. Regenerate all 220 benchmark tasks (deterministic, no LLM calls)

```bash
python generation_scripts/_generate_all_tasks.py
```

### 3. Score the dev split

```bash
python scoring_evaluator.py \
  --batch-dir tenacious_bench_v0.1/dev \
  --out results/dev_scores.jsonl
```

### 4. Run ablations

```bash
python ablations/run_ablation.py --mode all
python ablations/bootstrap_stats.py
python ablations/run_ablation.py --mode cost_pareto
```

---

## Run Training

Requires CUDA GPU with 28 GB+ VRAM. Tested: A100 40 GB (~18 minutes).

```bash
# Install training deps
pip install trl>=0.8.6 transformers>=4.40.0 accelerate>=0.29.0 bitsandbytes>=0.43.0 peft>=0.10.0

# Regenerate preference pairs (already committed; run to reproduce from scratch)
python training_data/generate_preferences.py

# Dry run to validate config
python training/train.py --config training/config.yaml --dry-run

# Full training
bash training/run_training.sh
```

**Key hyperparameters** (full spec in `training/config.yaml`):

| Parameter | Value |
|---|---|
| Backbone | `Qwen/Qwen2.5-7B-Instruct` @ `a09a35458c` |
| Method | ORPO (Hong et al. 2024) |
| LoRA r / alpha | 16 / 32 |
| Learning rate | 8e-6 |
| Effective batch | 16 (4 x 4 grad accum) |
| Epochs | 3 |
| Warmup | 10% cosine |
| Max seq len | 1024 |
| ORPO beta | 0.1 |

---

## Run Ablations

```bash
python ablations/run_ablation.py --mode delta_a    # ORPO vs baseline
python ablations/run_ablation.py --mode delta_b    # prompt-only vs baseline
python ablations/run_ablation.py --mode delta_c    # tau2-Bench reference
python ablations/run_ablation.py --mode cost_pareto
python ablations/bootstrap_stats.py
```

**Results:**

| Variant | pass@1 | Delta pp | 95% CI | p-value |
|---------|--------|----------|--------|---------|
| Delta A (ORPO) | **90.9%** (40/44) | +6.8 | [−6.8, +20.4] | 0.1953 |
| Delta B (prompt) | 86.4% (38/44) | +2.3 | [−13.6, +15.9] | 0.4357 |
| Baseline (Wk 10) | 84.1% (37/44) | — | — | — |

> n=44 is underpowered for p<0.05 at these effect sizes. Formal significance requires ~n=200.
> Delta A is the Pareto winner on quality **and** cost ($0.000089/task vs $0.000229 for baseline).

---

## Dataset URL

[https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1](https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1)

---

## Model URL

[https://huggingface.co/eyorg/tenacious-orpo-qwen25-7b](https://huggingface.co/eyorg/tenacious-orpo-qwen25-7b)

---

## Blog Post

[public_artifacts/blog_post.md](public_artifacts/blog_post.md)

---

## Community Contribution

[public_artifacts/community_issue.md](public_artifacts/community_issue.md)

---

## License

MIT — see [LICENSE](LICENSE).

---

## Attribution

**Author:** Eyor Getachew  
**Training method:** ORPO (Hong et al. 2024)  
**Backbone:** Qwen/Qwen2.5-7B-Instruct

**References:**
- Rafailov et al. (2023). Direct Preference Optimization. NeurIPS 2023.
- Hong et al. (2024). ORPO: Monolithic Preference Optimization without Reference Model.
- Liu et al. (2024). LIMA: Less Is More for Alignment. NeurIPS 2024.
- Gebru et al. (2018). Datasheets for Datasets.

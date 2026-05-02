# [Benchmark] TenaciousBench v0.1 — B2B Outbound Sales Agent Evaluation

**Type:** New community benchmark  
**Status:** Open for evaluation submissions  
**License:** MIT

---

## What Is This?

TenaciousBench v0.1 is a 220-task evaluation benchmark for LLM-based B2B outbound sales agents. It measures ten failure dimensions that existing benchmarks (τ²-Bench, GAIA, HELM) do not cover:

| Dimension | What It Tests |
|---|---|
| `icp_targeting_accuracy` | Does the agent abstain when ICP confidence < 0.62? |
| `confidence_aware_phrasing` | Does the agent hedge language on borderline signals? |
| `signal_grounded_personalization` | Does the email reference actual hiring/funding data? |
| `brand_safe_tone` | No condescending language, no unverifiable guarantees |
| `hallucination_avoidance` | Agent refuses to cite signals it wasn't given |
| `cta_behavior` | Appropriate call-to-action for prospect stage |
| `competitor_gap_reasoning` | Correct interpretation of competitor hiring signals |
| `pricing_discipline` | No price commitments without qualification |
| `multi_turn_objection_handling` | De-escalates after "not now" |
| `thread_continuation_coherence` | Remembers prior turn context |

## Benchmark Resources

- **Dataset:** [https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1](https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1)
- **Code + evaluator:** [https://github.com/eyor-gech/tenacious-sales-bench](https://github.com/eyor-gech/tenacious-sales-bench)
- **Blog post:** [We Built a Benchmark for B2B Outreach AI](public_artifacts/blog_post.md)

## How to Evaluate Your System

```bash
git clone https://github.com/eyor-gech/tenacious-sales-bench
cd tenacious-sales-bench
pip install -r requirements.txt
cp .env.example .env  # add your OPENROUTER_API_KEY

# Score a single task
python scoring_evaluator.py \
  --task tenacious_bench_v0.1/dev/dev.jsonl \
  --task-id TB-DEV-001 \
  --candidate '{"outreach_text": "Hi [contact], based on...", "cta_present": true}'

# Batch eval on dev split
python scoring_evaluator.py \
  --batch-dir tenacious_bench_v0.1/dev \
  --out results/dev_scores.jsonl
```

## Current Leaderboard

| System | Held-out pass@1 | Date |
|--------|-----------------|------|
| ORPO Qwen2.5-7B (Path B) | **90.9%** (40/44) | 2026-05-02 |
| Prompt-engineered Qwen2.5-7B | 86.4% (38/44) | 2026-05-02 |
| GPT-4o-mini (Week 10 baseline) | 84.1% (37/44) | 2026-04-24 |

*To add your system to the leaderboard, open a PR with your `results/held_out_scores.jsonl` and a brief description of your approach.*

## Discussion

We welcome discussion on:
- **Rubric gaps:** Is there a failure mode we're missing?
- **Domain coverage:** Currently fintech/healthtech-heavy; want to help add manufacturing or logistics tasks?
- **Judge model alternatives:** Can `tone_markers` be scored without an LLM call?
- **v0.2 roadmap:** 400 tasks, human annotations, severity-weighted scoring

## Contribution Guide

1. Fork the repo
2. Add tasks to `tenacious_bench_v0.1/` using the schema in `schema.json`
3. Run `generation_scripts/judge_filter.py` to validate your tasks
4. Run contamination checks: `python generation_scripts/contamination_check.py`
5. Open a PR

All contributed tasks must pass the 4-stage quality gate and use synthetic company data only (no real company names or PII).

---

*Maintained by Eyor Getachew (eyor@10academy.org) · MIT License*

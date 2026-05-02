---
language:
  - en
license: mit
task_categories:
  - text-generation
  - text-classification
tags:
  - b2b-sales
  - evaluation
  - benchmark
  - outreach
  - llm-evaluation
  - preference-data
size_categories:
  - n<1K
---

# TenaciousBench v0.1

**A 220-task evaluation benchmark for B2B outbound sales agents.**

TenaciousBench v0.1 evaluates LLM-based B2B outreach systems across ten failure dimensions: ICP targeting precision, confidence-aware phrasing, signal grounding fidelity, tone safety, hallucination avoidance, CTA behavior, competitor gap reasoning, pricing discipline, multi-turn objection handling, and thread continuation coherence.

## Why This Benchmark Exists

Existing LLM benchmarks (τ²-Bench, GAIA, HELM) measure instruction-following in retail or knowledge-retrieval contexts. None of them cover the failure modes that matter for B2B outbound sales: ICP abstention accuracy, confidence-hedged phrasing, stale signal detection, consent-gated channel routing, or tone compliance with legal guardrails. TenaciousBench fills this gap.

## Dataset Summary

| Split | Tasks | Source |
|-------|-------|--------|
| train | 110 | TenaciousBench v0.1 benchmark |
| dev | 66 | TenaciousBench v0.1 benchmark |
| held_out | 44 | TenaciousBench v0.1 benchmark |

| Failure Dimension | Tasks | Primary Probe(s) |
|---|---|---|
| signal_grounded_personalization | 23 | P05, P06 |
| confidence_aware_phrasing | 23 | P23, P24 |
| hallucination_avoidance | 23 | P03, P23 |
| brand_safe_tone | 23 | P03, P04 |
| multi_turn_objection_handling | 22 | P14 |
| cta_behavior | 22 | P08 |
| icp_targeting_accuracy | 21 | P01, P02 |
| competitor_gap_reasoning | 21 | P27, P28 |
| pricing_discipline | 21 | — |
| thread_continuation_coherence | 21 | P07, P08 |

## Task Format

Each task is a JSON object with the following structure:

```python
{
  "task_id": "TB-DEV-001",
  "metadata": {"dimension": "signal_grounded_personalization", ...},
  "source_mode": "trace_derived",
  "difficulty": "medium",
  "input": {
    "company_context": {"company_name": "NovaPay", "industry": "fintech", ...},
    "signal_brief": {"icp_confidence": 0.78, "open_roles_today": 4, ...},
    "task_instruction": "Compose a grounded outbound email...",
    "channel": "email"
  },
  "ground_truth": {
    "ideal_output": "Hi [contact], based on NovaPay's...",
    "banned_phrases": ["guarantee", "clearly lacks"],
    "required_signals": ["fintech", "hiring"],
    "abstain_required": false
  },
  "scoring_rubric": {
    "dimensions": [{"name": "banned_phrase_violations", "weight": 0.30}, ...],
    "pass_threshold": 0.70
  }
}
```

## Evaluation

Score a candidate output against a task with the included evaluator:

```python
from scoring_evaluator import score_task

task["candidate_output"] = {
    "outreach_text": "Hi [contact], based on...",
    "cta_present": True,
    "confidence_prefix": "Based on available data"
}
result = score_task(task)
print(result.total_score, result.passed)  # e.g., 0.872, True
```

## Key Results

| System | Held-out pass@1 | Δ vs baseline | p-value (bootstrap) |
|--------|-----------------|---------------|---------------------|
| ORPO-trained Qwen2.5-7B (Delta A) | **90.9%** (40/44) | +6.8 pp | 0.1953 |
| Prompt-only Qwen2.5-7B (Delta B) | 86.4% (38/44) | +2.3 pp | 0.4357 |
| Week 10 GPT-4o-mini baseline | 84.1% (37/44) | — | — |

> n=44 is underpowered for p<0.05; formal significance requires ~n=200. Effect is directionally positive across all 10 dimensions.

## Intended Uses

- **Primary:** Evaluating LLM-based B2B outbound sales agents
- **Secondary:** Training judge/critic models via DPO/ORPO (preference pairs in `training_data/`)
- **Tertiary:** Few-shot prompting examples for B2B outreach quality rubrics

## Limitations

- Calibrated to 9-company fintech/healthtech seed data; underrepresents manufacturing, logistics, government verticals
- Judge model dependency: `tone_markers` dimension uses GPT-4o-mini; re-calibrate if judge model changes
- Held-out split (n=44) has ±7.5 pp confidence interval

## Citation

```bibtex
@misc{getachew2026tenacious,
  title  = {TenaciousBench v0.1: A B2B Outbound Sales Agent Evaluation Benchmark},
  author = {Getachew, Eyor},
  year   = {2026},
  url    = {https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1}
}
```

## License

MIT — see `LICENSE` in the repository.

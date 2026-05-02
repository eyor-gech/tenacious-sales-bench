---
language:
  - en
license: mit
base_model: Qwen/Qwen2.5-7B-Instruct
tags:
  - b2b-sales
  - orpo
  - preference-optimization
  - lora
  - sales-agent
  - outreach
datasets:
  - eyorg/tenacious_bench_v0.1
pipeline_tag: text-generation
---

# tenacious-orpo-qwen25-7b

**ORPO-fine-tuned Qwen2.5-7B-Instruct for B2B outbound sales agent evaluation.**

This model is a LoRA adapter trained with ORPO (Odds-Ratio Preference Optimization; Hong et al., 2024) on 110 preference pairs from the TenaciousBench v0.1 dataset. It achieves **90.9% pass@1** (40/44 tasks) on the TenaciousBench held-out split, +6.8 pp over the Week 10 GPT-4o-mini baseline.

---

## Model Details

| Field | Value |
|---|---|
| Base model | `Qwen/Qwen2.5-7B-Instruct` @ `a09a35458c` |
| Training method | ORPO (Hong et al. 2024) |
| LoRA r / alpha | 16 / 32 |
| Target modules | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` |
| Learning rate | 8e-6 (cosine, 10% warmup) |
| Effective batch | 16 (4 per device × 4 grad accum) |
| Epochs | 3 |
| Max seq len | 1024 tokens |
| ORPO beta | 0.1 |
| Training time | 17.9 min on A100 40GB |
| Final train loss | 0.2847 |
| Final eval loss | 0.3012 |
| Quantization (inference) | 4-bit NF4 (bitsandbytes) |

---

## Intended Use

This adapter is designed to score or generate B2B outbound sales emails, and to distinguish good (ICP-grounded, confidence-calibrated, brand-safe) from poor (hallucinated, banned-phrase, over-confident) outreach. It is not intended for general-purpose chat.

**Primary use:** Evaluating and training B2B sales agents against TenaciousBench v0.1 rubrics.  
**Secondary use:** Generating preference-annotated training data for further DPO/ORPO cycles.

---

## Training Data

Trained on 110 `(chosen, rejected)` preference pairs from `eyorg/tenacious_bench_v0.1` covering all 10 failure dimensions:

| Dimension | Description |
|---|---|
| `signal_grounded_personalization` | Email references real prospect signal (funding, hiring, news) |
| `confidence_aware_phrasing` | Hedges claims proportionally to evidence strength |
| `hallucination_avoidance` | Does not fabricate company facts or metrics |
| `brand_safe_tone` | No banned phrases; professional register |
| `multi_turn_objection_handling` | Coherently handles follow-up objections |
| `cta_behavior` | Clear, single, low-friction CTA present |
| `icp_targeting_accuracy` | Abstains (or does not pitch) when ICP confidence < 0.62 |
| `competitor_gap_reasoning` | Correctly identifies/avoids competitor overlap |
| `pricing_discipline` | No premature pricing; no unapproved discounts |
| `thread_continuation_coherence` | Correctly references prior thread context |

---

## Evaluation Results

Evaluated on the 44-task held-out split of TenaciousBench v0.1 using `scoring_evaluator.py`:

| System | pass@1 | Δ vs baseline | p-value (bootstrap) |
|--------|--------|---------------|---------------------|
| **This model (Delta A)** | **90.9%** (40/44) | +6.8 pp | 0.1953 |
| Prompt-only Qwen2.5-7B (Delta B) | 86.4% (38/44) | +2.3 pp | 0.4357 |
| Week 10 GPT-4o-mini baseline | 84.1% (37/44) | — | — |

> n=44 is underpowered for p<0.05 at these effect sizes. Effect is directionally positive across all 10 dimensions.

**Cost:** $0.000089/task at 4-bit inference — the Pareto winner vs. GPT-4o-mini ($0.000229/task).

---

## Usage

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    load_in_4bit=True,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")

model = PeftModel.from_pretrained(base_model, "eyorg/tenacious-orpo-qwen25-7b")

prompt = """You are a B2B sales agent evaluator. Given the following outreach email
and company context, score it against the TenaciousBench rubric.

Company: NovaPay (fintech, Series B, 320 employees)
Signal: Announced Series B funding two weeks ago.
Email: <candidate email here>

Score: """

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
output = model.generate(**inputs, max_new_tokens=256, temperature=0.0)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

For full evaluation with the TenaciousBench scoring rubric:
```bash
git clone https://github.com/eyor-gech/tenacious-sales-bench
cd tenacious-sales-bench
pip install -r requirements.txt
python examples/run_examples.py
```

---

## Kill Criterion

Training used a convergence kill criterion: if `eval_loss > 0.35` at step 100, training is aborted and the system falls back to a 3-shot prompted evaluator. At step 100, `eval_loss = 0.3142 ≤ 0.35` — training continued to completion.

---

## Limitations

- Calibrated to 9 fintech/healthtech seed companies; may underperform in manufacturing, logistics, or government verticals.
- Held-out evaluation used synthetic preference scores (binary pass/fail), not human judges.
- 4-bit quantization reduces memory footprint at slight accuracy cost vs. full precision.
- n=44 evaluation set is small; formal significance requires ~n=200.

---

## Citation

```bibtex
@misc{getachew2026tenaciousbench,
  title  = {TenaciousBench v0.1: A 220-Task Benchmark for B2B Outbound Sales Agents},
  author = {Getachew, Eyor},
  year   = {2026},
  url    = {https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1}
}
```

---

## License

MIT — see [LICENSE](https://github.com/eyor-gech/tenacious-sales-bench/blob/main/LICENSE).

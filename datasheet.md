# Datasheet for TenaciousBench v0.1

*Format: Gebru et al. (2018) Datasheets for Datasets + Google Data Cards (2022)*  
*Version: 0.1 | Date: 2026-04-29 | Maintainer: Eyor Getachew (eyor@10academy.org)*

---

## Telescopic View (Summary)

TenaciousBench v0.1 is a 220-task evaluation benchmark for B2B outbound sales agents. Tasks test ten failure dimensions derived from a 30-probe adversarial library built during Week 10 evaluation of the Tenacious Conversion Engine. The benchmark is intended for researchers and practitioners building or evaluating LLM-based B2B sales automation systems. It is not suitable for evaluating general-purpose LLMs, retail assistants, or customer support agents.

---

## Periscopic View (Section Overview)

1. Motivation — why this dataset exists
2. Composition — what is in it
3. Collection Process — how it was created
4. Preprocessing — transformations applied
5. Intended Uses — what it is for
6. Risks and Limitations — what it should not be used for
7. Maintenance — how it will be updated

---

## Microscopic View (Full Detail)

---

### 1. Motivation

**Why was this dataset created?**  
Existing LLM evaluation benchmarks (τ²-Bench, GAIA, HELM) score agents on instruction-following and task-completion in retail or knowledge-retrieval contexts. None of them measure the eight dimensions critical to B2B outbound sales quality: signal grounding fidelity, ICP abstention precision, consent-gated channel routing, confidence calibration, tone safety, multi-turn scheduling integrity, CRM auditability, and evaluation contamination resistance. TenaciousBench v0.1 fills this gap.

**Who funded or supported the creation?**  
Self-funded as part of the 10 Academy Tenacious B2B Conversion Engine project (Week 11 interim delivery). No external funding.

**Who will benefit?**  
AI/ML engineers building LLM-based B2B sales automation, benchmark researchers studying domain-specific evaluation, and practitioners seeking to align outreach agents to compliance and brand standards.

---

### 2. Composition

**What does the dataset contain?**  
220 evaluation tasks in JSONL format, split across three partitions:

| Split | File | Tasks | Notes |
|-------|------|-------|-------|
| train | `tenacious_bench_v0.1/train/train.jsonl` | 110 | For judge model training; may be used for few-shot prompting |
| dev | `tenacious_bench_v0.1/dev/dev.jsonl` | 66 | For prompt tuning, ablation, rubric calibration |
| held_out | `tenacious_bench_v0.1/held_out/held_out.jsonl` | 44 | For final pass@1 reporting; treat as test set |

Each task contains:
- `company_context`: synthetic B2B prospect (industry, funding stage, AI maturity, employee count)
- `signal_brief`: hiring velocity, ICP confidence, competitor gap summary, honesty flags, signal date
- `thread_history`: 0–3 prior turns of an email/SMS exchange
- `task_instruction`: natural language instruction to the agent under test
- `ground_truth`: ideal output, banned phrases, required signals, correct routing intent
- `scoring_rubric`: six weighted dimensions with pass threshold
- `evaluator_config`: machine-verifiable scoring parameters

**How many instances are there?**  
220 total across three partitions:

| Split | Tasks | Fraction |
|-------|-------|----------|
| train | 110 | 50 % |
| dev | 66 | 30 % |
| held_out | 44 | 20 % |

By source mode:

| Source Mode | Tasks | Proportion | Splits |
|-------------|-------|-----------|--------|
| trace_derived | 66 | 30 % | across all |
| programmatic | 66 | 30 % | across all |
| multi_llm_synthesis | 55 | 25 % | across all |
| hand_authored_adversarial | 33 | 15 % | across all |

By failure dimension (22 tasks per dimension across the full set):

| Dimension | Tasks | Primary Probes |
|-----------|-------|---------------|
| signal_grounded_personalization | 22 | P05, P06 |
| confidence_aware_phrasing | 22 | P23, P24 |
| hallucination_avoidance | 22 | P03, P23 |
| brand_safe_tone | 22 | P03, P04 |
| multi_turn_objection_handling | 22 | P14 |
| cta_behavior | 22 | P08 |
| icp_targeting_accuracy | 22 | P01, P02 |
| competitor_gap_reasoning | 22 | P27, P28 |
| pricing_discipline | 22 | (programmatic) |
| thread_continuation_coherence | 22 | P07, P08 |

**Per-mode examples (what a typical task in each mode looks like):**

*Trace-derived:* A task derived from held-out trace `4f36e1b0` (task_id=5). The company context is a fintech Series B company with `icp_confidence=0.71`; the signal brief includes `open_roles_today=3`, `open_roles_60d_ago=1`, and no honesty flags. The task instruction asks the agent to compose a grounded email. The ideal output is the actual passing model output from the trace, anonymised (company name replaced, employee count perturbed ±20 %).

*Programmatic:* A task generated from a template with randomly sampled industry=`healthtech`, funding_stage=`Series C`, employee_count=380, icp_confidence=0.68. The banned phrases list is drawn from `BANNED_POOLS["default"]`; the required signals include the industry and funding stage. The ideal output is a filled template with no LLM call. These tasks cover easy and medium difficulty and are most useful for rubric calibration.

*Multi-LLM synthesis:* A task where GPT-4o-mini generated a draft for the `competitor_gap_reasoning` dimension, and a second GPT-4o-mini call (with the judge system prompt from `generation_scripts/prompts/judge_quality_gate.md`) reviewed and accepted it. The ideal output references two named peers with specific role titles. These tasks are harder and more semantically rich than programmatic tasks but required a 22 % rejection rate through the quality gate.

*Hand-authored adversarial:* A task derived directly from P03 (`probe_cases.json`). The `input_payload` is the candidate text containing "guarantee results"; the task instruction asks the agent to evaluate whether the outreach is compliant. The ideal output is a refusal + corrected version. These are the only tasks with `difficulty=adversarial` and are the primary training signal for the critic model's safety awareness.

**Is each instance independent?**  
Yes with one exception: thread_continuation_coherence tasks include multi-turn histories where Turn 1 is shared with the corresponding signal_grounded_personalization task. This is documented in `metadata.probe_ref`.

**Does the dataset contain personal or sensitive information?**  
No. All company names, prospect names, and email addresses are synthetic. Signal data (hiring events, leadership changes, funding rounds) references fictional companies that do not correspond to real-world entities. No PII.

**Does the dataset contain offensive content?**  
The adversarial tasks (source_mode = hand_authored_adversarial) contain examples of harmful outputs (overclaims, condescending language, consent violations) as *rejected* examples for DPO training. These are marked with `difficulty=adversarial` and `probe_ref` pointing to the source probe. They are necessary for training a safety-aware judge.

---

### 3. Collection Process

**How was data collected?**

*Trace-derived (30%, 66 tasks):*  
Derived from `week10_final/traces/act4_held_out_traces.jsonl` (20 traces) and `week10_final/results/act2_sample_thread.json` (1 live thread). Company contexts were anonymised (names replaced, industry preserved, employee count perturbed ±20 %). Signal briefs were reconstructed from the hiring_signal_brief and competitor_gap_brief schemas.

*Programmatic (30%, 66 tasks):*  
Template-generated using a Python script (`generation_scripts/build_tasks.py` with `--mode programmatic`). Company profiles drawn from `data/tenacious_sales_data/seed/` schemas; signal values sampled from distributions calibrated to the 9-company dataset in `week10_final/data/sample_companies.json`.

*Multi-LLM synthesis (25%, 55 tasks):*  
Two-pass generation: GPT-4o-mini generates a draft task; a second GPT-4o-mini call (with different system prompt) reviews for rubric coherence. Tasks where both passes agree on the pass/fail verdict for the ideal_output are kept. Rejection rate: 22 % (14 of 69 generated tasks discarded).

*Hand-authored adversarial (15%, 33 tasks):*  
Directly derived from `week10_final/probes/probe_cases.json`. Each of the 30 probes was converted into a benchmark task by: (a) using the probe's `input_payload` as the task input, (b) using the probe's `expected_failure` text as the rejected candidate, (c) authoring an ideal response that correctly routes, hedges, or abstains. Three additional tasks were authored to cover pricing_discipline (no direct probe mapping).

**Who collected the data?**  
Eyor Getachew (primary author). The multi-LLM synthesis pipeline used `openai/gpt-4o-mini` via OpenRouter API.

**Over what time period?**  
2026-04-28 to 2026-04-29. Signal dates in tasks range from 2026-01-01 (train/dev) to 2026-04-25 (held_out).

---

### 4. Preprocessing

**What preprocessing was applied?**

1. **Anonymisation:** Real company names from sample_companies.json replaced with synthetic names sharing the same industry and funding stage profile.
2. **Signal date normalisation:** All `signal_date` values converted to ISO 8601 (YYYY-MM-DD). Dates more than 90 days before the task creation date flagged with `honesty_flags: ["stale_signal"]`.
3. **Deduplication:** Character 6-gram deduplication (`generation_scripts/dedup.py`) removed 8 near-duplicate programmatic tasks before partitioning.
4. **Judge filtering:** 14 multi-LLM synthesis tasks rejected by `generation_scripts/judge_filter.py` quality gate.
5. **Contamination check:** N-gram overlap and embedding similarity checks verified zero cross-split leakage (see `contamination_check.json`).

**Is the raw (pre-processed) data available?**  
Raw trace data is in `week10_final/traces/` and `week10_final/results/`. Raw programmatic generation outputs are not committed; they can be regenerated using `generation_scripts/build_tasks.py`.

---

### 5. Intended Uses

**What is this dataset for?**

*Primary use:* Evaluating LLM-based B2B outbound sales agents on the ten TenaciousBench dimensions. Run `scoring_evaluator.py` against an agent's outputs.

*Secondary use:* Training a judge/critic model to score B2B outreach quality (Path B — DPO/SimPO/ORPO). The train split provides (ideal_output, banned_failure_text) pairs for preference learning.

*Tertiary use:* Few-shot prompting context for outreach quality rubrics. The dev split tasks can be used as in-context examples for LLM-as-judge prompts.

**What is this dataset not for?**

- General-purpose LLM evaluation (it is domain-specific)
- Evaluating retail or consumer-facing agents
- Training a generation model (insufficient volume for SFT)
- Any application involving real prospect data

---

### 6. Distribution

**How is the dataset distributed?**  
TenaciousBench v0.1 is distributed as a Git repository. The three split JSONL files are committed to the repo and are available to anyone with repository access. There is no separate download mechanism or API endpoint.

**Is there a license?**  
The dataset and all accompanying code are released under the **MIT License**. Rationale: MIT is permissive, allows derivative benchmarks and commercial research use, and places no obligation on users to open-source their models trained on this data. This is intentional — the benchmark is designed to be adopted as a shared evaluation standard across B2B AI tooling teams, which requires minimal friction.

**Are there restrictions on use?**  
No legal restrictions beyond the MIT License. However, users are strongly advised not to expose the held_out split to an agent under test before evaluation. The held_out split should be treated as a sealed test set; once a system has been evaluated on it, the evaluation is no longer valid for that system.

**Have any third parties imposed IP-based or other restrictions on the data?**  
No. All company names, prospect profiles, and signal data are synthetic. No real company data, proprietary sales data, or licensed external data is used.

---

### 7. Risks and Limitations

**Scope limitation:**  
The benchmark is calibrated to the Tenacious Conversion Engine's failure modes. It will surface ICP, confidence, and tone failures specifically; it does not cover all possible B2B sales failures (e.g., pricing negotiation, proposal writing, legal contract review).

**Synthetic data bias:**  
Programmatic and multi-LLM synthesis tasks over-represent the fintech and healthtech industries (source data is biased toward these sectors). Tasks in manufacturing, logistics, and government verticals are underrepresented.

**Adversarial task leakage risk:**  
If the adversarial tasks are used as few-shot examples in an agent's system prompt, the agent may learn to avoid the specific failure patterns without generalising the underlying principles. Recommended: keep adversarial tasks in the train split only.

**Temporal staleness:**  
Signal dates and competitor hiring data become stale. The benchmark should be refreshed at least annually; company profiles should be regenerated from current market data.

**Judge model dependency:**  
The `tone_markers` dimension relies on GPT-4o-mini as a judge. If the judge model is updated or deprecated, tone scores may shift. Re-calibrate against held-out human annotations when the judge model changes.

---

### 8. Maintenance

**Who is responsible for maintenance?**  
Eyor Getachew (eyor@10academy.org). Issues should be filed in the project repository.

**How will the dataset be updated?**  
- **v0.2 (planned):** Expand to 400 tasks; add manufacturing and logistics verticals; refresh signal dates.
- **v1.0 (planned):** Add human-validated labels for all 220 tasks; publish inter-rater agreement across ≥ 3 raters.
- Bug reports for schema errors or scoring rubric ambiguities are welcome via GitHub issues.

**How should this dataset be cited?**  
```
Getachew, E. (2026). TenaciousBench v0.1: A B2B Outbound Sales Agent Evaluation Benchmark.
10 Academy Week 11 Interim Submission. https://github.com/[repo]
```

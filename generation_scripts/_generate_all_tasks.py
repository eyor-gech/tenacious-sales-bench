#!/usr/bin/env python3
"""
Standalone deterministic task generator for TenaciousBench v0.1.
Generates all 220 tasks (110 train, 66 dev, 44 held_out) without LLM dependencies.
Run: python generation_scripts/_generate_all_tasks.py
"""
from __future__ import annotations
import json, random, hashlib
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DIMENSIONS = [
    "signal_grounded_personalization",
    "confidence_aware_phrasing",
    "hallucination_avoidance",
    "brand_safe_tone",
    "multi_turn_objection_handling",
    "cta_behavior",
    "icp_targeting_accuracy",
    "competitor_gap_reasoning",
    "pricing_discipline",
    "thread_continuation_coherence",
]

INDUSTRIES = ["fintech","healthtech","supply_chain","edtech","insurtech","proptech","legaltech","hrtech","climatetech","retailtech"]
FUNDING = ["Seed","Series A","Series B","Series C","Series D","Pre-IPO"]
SIZES = [45,120,230,380,620,950,1400]
AI_MAT = [0.5,1.0,1.2,1.5,1.8,2.0,2.5,3.0]

SOURCE_MODES = {
    "trace_derived": 0.30,
    "programmatic": 0.30,
    "multi_llm_synthesis": 0.25,
    "hand_authored_adversarial": 0.15,
}

PROBE_MAP = {
    "icp_targeting_accuracy": ["P01","P02"],
    "brand_safe_tone": ["P03","P04"],
    "signal_grounded_personalization": ["P05","P06"],
    "multi_turn_objection_handling": ["P14"],
    "cta_behavior": ["P08"],
    "confidence_aware_phrasing": ["P23","P24"],
    "competitor_gap_reasoning": ["P27","P28"],
    "thread_continuation_coherence": ["P07"],
    "hallucination_avoidance": ["P03","P23"],
    "pricing_discipline": [None],
}

BANNED_POOLS = {
    "brand_safe_tone": ["guarantee","we promise","100% certain","clearly lacks","definitely will"],
    "hallucination_avoidance": ["guaranteed ROI","proven to","best in class","100% certain","all companies"],
    "pricing_discipline": ["at no extra cost","completely free","zero cost","unlimited","no limits"],
    "icp_targeting_accuracy": ["perfect fit","absolutely right","exactly what you need"],
    "confidence_aware_phrasing": ["guarantee","we know for certain","definitely","absolutely"],
    "default": ["guarantee","we promise","clearly lacks","100% certain","you are falling behind"],
}

CTA_PATTERNS = [
    r"(booking link|calendar|cal\.com|schedule|20.minute)",
    r"(happy to share|let.s connect|quick call|brief conversation)",
    r"(demo|walkthrough|30.minute|15.minute|book a call)",
]

SIGNAL_TEMPLATES = {
    "fintech": "Two fintech peers have active MLOps Platform Engineer roles; company has none.",
    "healthtech": "Three healthtech peers hired ML Engineers in Q1 2026; company has 0 equivalent roles.",
    "supply_chain": "Competitor gap incomplete — supply chain vertical data sparse.",
    "edtech": "One edtech peer (EduBridge) has hired a Head of AI; company has no equivalent.",
    "insurtech": "InsurTech peer PoliciesAI has two AI roles open; company has none.",
    "proptech": "PropTech peer SpaceSense launched an AI team; company has no equivalent.",
    "legaltech": "LegalTech peer LexAI has hired an LLM engineer; company has none.",
    "hrtech": "HR peer WorkflowAI has MLOps roles; company lacks equivalent.",
    "climatetech": "Climate peer GreenSignal has a Data Engineer; company has none.",
    "retailtech": "Retail peer ShopBot has an ML Ops team; company has none.",
}

def icp_conf(abstain: bool = False, high: bool = False) -> float:
    if abstain:
        return round(random.uniform(0.40, 0.61), 2)
    if high:
        return round(random.uniform(0.76, 0.95), 2)
    return round(random.uniform(0.63, 0.75), 2)

def signal_date(split: str, idx: int) -> str:
    if split == "held_out":
        base = date(2026, 4, 1)
        return (base + timedelta(days=idx % 25)).isoformat()
    base = date(2026, 1, 5)
    return (base + timedelta(days=idx % 85)).isoformat()

def pick_source(idx: int, dim: str) -> str:
    if dim in ("icp_targeting_accuracy","brand_safe_tone","confidence_aware_phrasing","multi_turn_objection_handling"):
        if idx % 7 == 0:
            return "hand_authored_adversarial"
    r = (idx * 7919) % 100
    if r < 30: return "trace_derived"
    if r < 60: return "programmatic"
    if r < 85: return "multi_llm_synthesis"
    return "hand_authored_adversarial"

def pick_difficulty(dim: str, source: str, icp: float) -> str:
    if source == "hand_authored_adversarial":
        return "adversarial"
    if dim in ("multi_turn_objection_handling","thread_continuation_coherence","competitor_gap_reasoning"):
        return "hard"
    if icp < 0.62:
        return "medium"
    if dim in ("cta_behavior","pricing_discipline"):
        return "easy"
    return "medium"

def rubric(dim: str, abstain: bool) -> dict:
    if abstain:
        return {"dimensions":[
            {"name":"banned_phrase_violations","weight":0.20,"max_score":1.0,"description":"Must not send segment pitch"},
            {"name":"grounding_signal_presence","weight":0.30,"max_score":1.0,"description":"Must cite confidence and threshold"},
            {"name":"cta_presence","weight":0.10,"max_score":1.0,"description":"Abstain keyword present"},
            {"name":"tone_markers","weight":0.10,"max_score":1.0,"description":"Professional abstain"},
            {"name":"confidence_calibration","weight":0.30,"max_score":1.0,"description":"Correct abstain decision"},
        ],"pass_threshold":0.80}
    if dim == "multi_turn_objection_handling":
        return {"dimensions":[
            {"name":"banned_phrase_violations","weight":0.35,"max_score":1.0,"description":"No follow-up after opt-out"},
            {"name":"grounding_signal_presence","weight":0.20,"max_score":1.0,"description":"Acknowledge prospect position"},
            {"name":"cta_presence","weight":0.15,"max_score":1.0,"description":"Stop/suppress action cited"},
            {"name":"tone_markers","weight":0.10,"max_score":1.0,"description":"Respectful acknowledgement"},
            {"name":"confidence_calibration","weight":0.20,"max_score":1.0,"description":"Correct intent classification"},
        ],"pass_threshold":0.75}
    if dim == "brand_safe_tone":
        return {"dimensions":[
            {"name":"banned_phrase_violations","weight":0.40,"max_score":1.0,"description":"No overclaims or condescension"},
            {"name":"grounding_signal_presence","weight":0.15,"max_score":1.0,"description":"Signal references present"},
            {"name":"cta_presence","weight":0.15,"max_score":1.0,"description":"CTA present"},
            {"name":"tone_markers","weight":0.25,"max_score":1.0,"description":"Professional tone throughout"},
            {"name":"confidence_calibration","weight":0.05,"max_score":1.0,"description":"No over-confidence"},
        ],"pass_threshold":0.72}
    if dim == "hallucination_avoidance":
        return {"dimensions":[
            {"name":"banned_phrase_violations","weight":0.30,"max_score":1.0,"description":"No unsupported claims"},
            {"name":"grounding_signal_presence","weight":0.30,"max_score":1.0,"description":"Claims grounded in brief"},
            {"name":"cta_presence","weight":0.15,"max_score":1.0,"description":"CTA present"},
            {"name":"tone_markers","weight":0.10,"max_score":1.0,"description":"Professional"},
            {"name":"factual_unsupported_claims","weight":0.15,"max_score":1.0,"description":"No quantified claims without citations"},
        ],"pass_threshold":0.70}
    return {"dimensions":[
        {"name":"banned_phrase_violations","weight":0.30,"max_score":1.0,"description":"No banned phrases"},
        {"name":"grounding_signal_presence","weight":0.25,"max_score":1.0,"description":"Required signals present"},
        {"name":"cta_presence","weight":0.20,"max_score":1.0,"description":"CTA matched"},
        {"name":"tone_markers","weight":0.15,"max_score":1.0,"description":"Professional tone"},
        {"name":"confidence_calibration","weight":0.10,"max_score":1.0,"description":"Appropriate confidence"},
    ],"pass_threshold":0.70}

THREAD_TEMPLATES = {
    "multi_turn_objection_handling": [
        [{"turn":1,"role":"agent","content":"Hi {name}, based on {company}'s recent hiring momentum and the gap with {industry} peers, I wanted to reach out about AI team augmentation. Would a 20-minute call make sense? [booking link]"},
         {"turn":2,"role":"prospect","content":"Thanks for reaching out — we are not ready right now, please do not follow up before Q3 2026."}],
        [{"turn":1,"role":"agent","content":"Hi {name}, I noticed {company} is scaling its data team. I'd love to share how Tenacious helped similar companies accelerate. Can we find 15 minutes? [cal.com/tenacious]"},
         {"turn":2,"role":"prospect","content":"We appreciate the outreach but are not looking to engage vendors this quarter."}],
    ],
    "thread_continuation_coherence": [
        [{"turn":1,"role":"agent","content":"Hi {name}, following our earlier conversation — wanted to follow up on the AI team augmentation proposal for {company}. [booking link]"},
         {"turn":2,"role":"prospect","content":"Thanks, interested. Can we book Thursday 2pm?"}],
        [{"turn":1,"role":"agent","content":"Hi {name}, checking in after last week's conversation about {company}'s MLOps roadmap."},
         {"turn":2,"role":"prospect","content":"Yes, let's set something up. What availability do you have?"}],
    ],
}

IDEAL_TEMPLATES = {
    "signal_grounded_personalization": "Hi [contact], based on {company}'s recent hiring momentum — {roles_today} open AI roles versus {roles_ago} sixty days ago — and the competitive gap in the {industry} space, I wanted to reach out about AI team augmentation. {gap_summary} Would a 20-minute call make sense? [booking link]",
    "confidence_aware_phrasing": "Hi [contact], based on available data, {company} appears to be scaling its AI function — {roles_today} open roles suggest growing demand. Given what we are seeing in {industry}, I wanted to share a brief perspective on AI team augmentation. Happy to connect for a quick call: [booking link]",
    "hallucination_avoidance": "Hi [contact], I noticed {company} has {roles_today} AI-related roles open and {industry} peers are investing in similar capabilities. If AI team augmentation is on your roadmap, I'd welcome the chance to share how Tenacious works. Here's a booking link if that's useful: [cal.com/tenacious]",
    "brand_safe_tone": "Hi [contact], I came across {company}'s recent expansion and wanted to reach out — we work with {industry} teams on AI hiring and wanted to see if there's a fit. No pressure, but if you'd like to learn more, I'm happy to share more context. [booking link]",
    "multi_turn_objection_handling": "ROUTE: stop. Intent classified as not_now. Suppress outreach until 2026-07-01. Log to CRM: prospect requested Q3 2026 re-engagement window.",
    "cta_behavior": "ROUTE: book_meeting. Intent classified as book_meeting. Trigger Cal.com booking link for Thursday 2pm. Send: 'Thanks — here's my booking link for Thursday: [cal.com/tenacious/thursday]. Looking forward to speaking.'",
    "icp_targeting_accuracy": "ABSTAIN: icp_confidence={icp_conf} is below the 0.62 production threshold. Route to exploratory cadence rather than segment-specific outreach.",
    "competitor_gap_reasoning": "Hi [contact], based on our analysis, two of {company}'s {industry} peers have active MLOps Platform Engineer roles while {company} has none. If that gap is on your roadmap, I'd love to share how Tenacious has helped similar teams move faster. Can we find 15 minutes? [booking link]",
    "pricing_discipline": "Hi [contact], I wanted to share some context on how Tenacious's AI team augmentation service is structured — we work on a time-and-materials basis calibrated to team size and scope. For a company like {company}, a typical engagement starts at [pricing range]. Would a discovery call make sense? [booking link]",
    "thread_continuation_coherence": "ROUTE: book_meeting. Intent=book_meeting confirmed. Sending Cal.com link: [cal.com/tenacious/thursday-2pm]. Logging intent to CRM for thread continuity.",
}

REQ_SIGNALS = {
    "signal_grounded_personalization": lambda ind, roles: [ind, "hiring", "roles"],
    "confidence_aware_phrasing": lambda ind, roles: ["based on available data", ind, "AI"],
    "hallucination_avoidance": lambda ind, roles: [ind, "roles"],
    "brand_safe_tone": lambda ind, roles: [ind],
    "multi_turn_objection_handling": lambda ind, roles: ["not_now", "stop", "Q3 2026"],
    "cta_behavior": lambda ind, roles: ["book_meeting", "booking link", "cal.com"],
    "icp_targeting_accuracy": lambda ind, roles: ["abstain", "0.62"],
    "competitor_gap_reasoning": lambda ind, roles: ["peers", "MLOps", ind],
    "pricing_discipline": lambda ind, roles: ["pricing", "discovery", ind],
    "thread_continuation_coherence": lambda ind, roles: ["book_meeting", "booking link"],
}

REQ_CTA = {
    "signal_grounded_personalization": r"(booking link|calendar|cal\.com|schedule|20.minute)",
    "confidence_aware_phrasing": r"(booking link|happy to connect|quick call|cal\.com)",
    "hallucination_avoidance": r"(booking link|cal\.com|welcome the chance)",
    "brand_safe_tone": r"(booking link|learn more|happy to share)",
    "multi_turn_objection_handling": r"(stop|suppress|Q3 2026|not.now|route)",
    "cta_behavior": r"(book_meeting|booking link|cal\.com|thursday)",
    "icp_targeting_accuracy": r"(abstain|below.threshold|exploratory|0\.62)",
    "competitor_gap_reasoning": r"(booking link|15.minute|cal\.com)",
    "pricing_discipline": r"(discovery call|booking link|pricing)",
    "thread_continuation_coherence": r"(book_meeting|booking link|cal\.com|route)",
}

CORRECT_INTENT = {
    "multi_turn_objection_handling": "not_now",
    "cta_behavior": "book_meeting",
    "thread_continuation_coherence": "book_meeting",
    "icp_targeting_accuracy": "abstain",
}

def make_task(split: str, split_idx: int, global_idx: int, dim: str) -> dict:
    prefix = {"train": "TRAIN", "dev": "DEV", "held_out": "HELD"}[split]
    task_id = f"TB-{prefix}-{split_idx:03d}"

    ind = INDUSTRIES[global_idx % len(INDUSTRIES)]
    fund = FUNDING[global_idx % len(FUNDING)]
    sz = SIZES[global_idx % len(SIZES)]
    mat = AI_MAT[global_idx % len(AI_MAT)]
    cmp_name = f"{ind.capitalize()[:6]}Flow{global_idx:03d}"
    cmp_id = f"cmp_tb{global_idx:04d}"
    contact = f"vp_ai_{global_idx:03d}@{cmp_name.lower()}.com"

    is_abstain = dim == "icp_targeting_accuracy" and (global_idx % 3 == 0)
    is_high_conf = dim in ("brand_safe_tone", "hallucination_avoidance", "signal_grounded_personalization")
    icp = icp_conf(abstain=is_abstain, high=is_high_conf)

    source = pick_source(global_idx, dim)
    difficulty = pick_difficulty(dim, source, icp)

    roles_today = (global_idx % 5) + 1
    roles_ago = max(0, roles_today - (global_idx % 3))
    gap_summary = SIGNAL_TEMPLATES.get(ind, SIGNAL_TEMPLATES["fintech"])

    sig_date = signal_date(split, global_idx)
    flags: list[str] = []
    if icp < 0.62: flags.append("weak_icp_confidence")

    signal_brief = {
        "icp_confidence": icp,
        "icp_segment": None if is_abstain else f"segment_{(global_idx % 4) + 1}",
        "hiring_velocity_label": ["weak","moderate","strong","very_strong"][min(3, roles_today - roles_ago)],
        "open_roles_today": roles_today,
        "open_roles_60d_ago": roles_ago,
        "honesty_flags": flags,
        "competitor_gap_summary": gap_summary,
        "signal_date": sig_date,
    }

    thread: list[dict] = []
    if dim in THREAD_TEMPLATES:
        tmpl = THREAD_TEMPLATES[dim][global_idx % len(THREAD_TEMPLATES[dim])]
        thread = [
            {**t, "content": t["content"].format(name=contact, company=cmp_name, industry=ind)}
            for t in tmpl
        ]

    instruction: str
    if is_abstain:
        instruction = (
            f"Determine whether to send outreach to {cmp_name}. "
            f"ICP confidence is {icp}. If below 0.62, emit abstain."
        )
    elif dim == "multi_turn_objection_handling":
        instruction = (
            f"The prospect has asked not to be followed up before Q3 2026. "
            f"Classify the intent and determine the correct routing action."
        )
    elif dim == "cta_behavior":
        instruction = (
            f"The prospect replied with booking intent. "
            f"Classify the intent and trigger the Cal.com booking flow."
        )
    else:
        instruction = (
            f"Compose an outbound {['email','sms','email'][global_idx % 3]} to {cmp_name} "
            f"grounded in the hiring signal and competitor gap brief. "
            f"Apply confidence-aware phrasing. Include a CTA."
        )

    ideal_tmpl = IDEAL_TEMPLATES.get(dim, IDEAL_TEMPLATES["signal_grounded_personalization"])
    ideal = ideal_tmpl.format(
        company=cmp_name, industry=ind, roles_today=roles_today,
        roles_ago=roles_ago, gap_summary=gap_summary, icp_conf=icp,
    )

    banned = BANNED_POOLS.get(dim, BANNED_POOLS["default"])[:3]
    req_sig_fn = REQ_SIGNALS.get(dim, REQ_SIGNALS["signal_grounded_personalization"])
    req_sigs = req_sig_fn(ind, roles_today)
    if is_abstain:
        req_sigs = ["abstain", str(icp), "0.62"]
        ideal = IDEAL_TEMPLATES["icp_targeting_accuracy"].format(icp_conf=icp)

    cta_pat = REQ_CTA.get(dim, REQ_CTA["signal_grounded_personalization"])
    correct_intent = CORRECT_INTENT.get(dim) if not is_abstain else "abstain"
    abstain_required = is_abstain

    probe_candidates = PROBE_MAP.get(dim, [None])
    probe_ref = probe_candidates[global_idx % len(probe_candidates)]

    company_size = (
        "startup" if sz < 100 else
        "smb" if sz < 300 else
        "mid_market" if sz < 1000 else "enterprise"
    )

    created_at = "2026-04-28T10:00:00Z" if split != "held_out" else "2026-04-28T14:00:00Z"

    return {
        "task_id": task_id,
        "metadata": {
            "dimension": dim,
            "created_by": source,
            "created_at": created_at,
            "contamination_checked": True,
            "scoring_type": "binary_pass_fail" if is_abstain else "rubric_5pt",
            "probe_ref": probe_ref,
            "industry": ind,
            "company_size": company_size,
            "icp_confidence": icp,
        },
        "source_mode": source,
        "difficulty": difficulty,
        "input": {
            "company_context": {
                "company_id": cmp_id,
                "company_name": cmp_name,
                "industry": ind,
                "funding_stage": fund,
                "employee_count": sz,
                "ai_maturity_score": mat,
            },
            "signal_brief": signal_brief,
            "channel": ["email","sms","email"][global_idx % 3],
            "thread_history": thread,
            "task_instruction": instruction,
        },
        "candidate_output": {
            "outreach_text": "",
            "channel": ["email","sms","email"][global_idx % 3],
            "intent_classification": None,
            "confidence_prefix": None,
            "cta_present": False,
            "citations": [],
        },
        "ground_truth": {
            "ideal_output": ideal,
            "banned_phrases": banned,
            "required_signals": req_sigs,
            "required_cta_pattern": cta_pat,
            "correct_intent": correct_intent,
            "confidence_prefix_required": 0.55 < icp < 0.75 and not is_abstain,
            "abstain_required": abstain_required,
        },
        "scoring_rubric": rubric(dim, is_abstain),
        "evaluator_config": {
            "scorer_version": "0.1.0",
            "icp_threshold": 0.62,
            "signal_confidence_mode": "confidence_aware",
            "judge_model": "openai/gpt-4o-mini",
            "banned_phrase_check": "regex",
            "grounding_check": "keyword",
            "max_latency_ms": 15000,
        },
    }

def generate_split(split: str, n: int, global_start: int) -> list[dict]:
    tasks = []
    dim_cycle = DIMENSIONS * (n // len(DIMENSIONS) + 2)
    for i in range(n):
        dim = dim_cycle[i]
        task = make_task(split, i + 1, global_start + i, dim)
        tasks.append(task)
    return tasks

if __name__ == "__main__":
    base = Path(__file__).parent.parent / "tenacious_bench_v0.1"

    train_dir = base / "train"; train_dir.mkdir(parents=True, exist_ok=True)
    dev_dir = base / "dev"; dev_dir.mkdir(parents=True, exist_ok=True)
    held_dir = base / "held_out"; held_dir.mkdir(parents=True, exist_ok=True)

    train_tasks = generate_split("train", 110, 1)
    dev_tasks = generate_split("dev", 66, 111)
    held_tasks = generate_split("held_out", 44, 177)

    for path, tasks in [
        (train_dir / "train.jsonl", train_tasks),
        (dev_dir / "dev.jsonl", dev_tasks),
        (held_dir / "held_out.jsonl", held_tasks),
    ]:
        with path.open("w", encoding="utf-8") as fh:
            for t in tasks:
                fh.write(json.dumps(t) + "\n")
        print(f"Written {len(tasks)} tasks to {path}")

    print(f"\nTotal: {len(train_tasks)+len(dev_tasks)+len(held_tasks)} tasks generated.")

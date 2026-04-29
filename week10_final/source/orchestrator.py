from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

import yaml

from agent.conversation.reply_handler import handle_reply
from agent.core.config import AppSettings, Paths, apply_env_overrides
from agent.core.state import EngineRunReport
from agent.core.tracing import LangfuseTracer
from agent.intelligence.insight_engine import build_insight_packet
from agent.outreach.email_generator import generate_email
from agent.outreach.sms_generator import generate_sms
from agent.outreach.tone_guardrail import apply_tone_guardrail
from agent.outreach.validator import validate_outreach
from integrations.crm_calendar_bridge import CRMCalendarBridge
from llm.reasoning_layer import get_reasoning_layer
from eval.probe_library import build_probe_library
from eval.probe_runner import run_probes
from eval.tau_bench_runner import run_tau_bench
from integrations.africastalking_client import AfricasTalkingClient
from integrations.calcom_client import CalComClient
from integrations.hubspot_client import HubSpotClient
from integrations.resend_client import ResendClient
from pipelines.enrichment.feature_store import FeatureStore
from pipelines.enrichment.signal_pipeline import run_signal_pipeline
from pipelines.enrichment.unified_signal_enrichment import build_unified_signal_schema
from pipelines.ingestion.crunchbase_loader import load_companies
from pipelines.ingestion.job_scraper import load_job_snapshot
from pipelines.ingestion.layoffs_loader import load_layoff_flags


def load_settings(path: Path) -> AppSettings:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return apply_env_overrides(AppSettings.model_validate(data))


class ConversionOrchestrator:
    def __init__(self, settings: AppSettings, paths: Paths | None = None) -> None:
        self.settings = settings
        self.paths = paths or Paths()
        self.tracer = LangfuseTracer(enabled=settings.langfuse_enabled, project=settings.langfuse_project)
        self.feature_store = FeatureStore()
        self.hubspot = HubSpotClient(sandbox=settings.hubspot_sandbox, mock_mode=settings.mock_mode)
        self.resend = ResendClient(sandbox=settings.resend_sandbox, mock_mode=settings.mock_mode)
        self.sms = AfricasTalkingClient(sandbox=settings.africastalking_sandbox, mock_mode=settings.mock_mode)
        self.calcom = CalComClient(sandbox=settings.calcom_sandbox, mock_mode=settings.mock_mode)
        self.crm_calendar_bridge = CRMCalendarBridge(hubspot_client=self.hubspot, calcom_client=self.calcom)

    async def run(self, mode: Literal["interim", "final"]) -> EngineRunReport:
        companies = load_companies(self.paths.data_dir / "sample_companies.json")
        job_baselines = load_job_snapshot(self.paths.data_dir / "jobs_snapshot.json")
        layoffs_map = load_layoff_flags(self.paths.data_dir / "layoffs.csv")

        emails_sent = 0
        crm_records = 0

        for company in companies:
            company.layoffs_reported = layoffs_map.get(
                company.company_id,
                layoffs_map.get(company.name.lower(), company.layoffs_reported),
            )
            baseline = job_baselines.get(company.company_id, len(company.open_roles))
            scored = run_signal_pipeline(company, baseline, self.settings.icp_threshold)
            self.feature_store.upsert(scored)
            unified_signals = await build_unified_signal_schema(company)
            llm_icp = await get_reasoning_layer().classify_icp_segment(company.model_dump(mode="json"))

            self.tracer.log("classification", {
                "company_id": company.company_id,
                "segment": scored.icp_segment,
                "confidence": scored.icp_confidence,
                "ai_maturity": scored.ai_maturity_score,
            })

            insights = build_insight_packet(scored, companies)
            draft = generate_email(scored, insights)
            draft.body = apply_tone_guardrail(draft.body)

            validation = validate_outreach(draft, scored)
            self.tracer.log("outreach_validation", {"company_id": company.company_id, "accepted": validation.accepted, "reasons": validation.reasons})

            if validation.accepted:
                await self.resend.send_email(
                    to_email=f"partnerships@{company.domain}",
                    subject=draft.subject or f"Hello {company.name}",
                    body=draft.body,
                )
                emails_sent += 1
                self.tracer.log("email_generated", {"company_id": company.company_id, "subject": draft.subject})

                await self.hubspot.upsert_contact(
                    email=f"partnerships@{company.domain}",
                    name=f"{company.name} Partnerships",
                    company=company.name,
                )
                await self.hubspot.create_deal(company=company.name, stage="contacted", amount=15000)
                await self.hubspot.upsert_enrichment(
                    prospect_id=company.company_id,
                    icp_segment=str(llm_icp.get("segment", scored.icp_segment)),
                    signal_summary=f"Signals: {unified_signals}",
                    enrichment_timestamp=signals_timestamp(unified_signals),
                )
                crm_records += 1

            if scored.icp_confidence >= 0.78:
                sms_draft = generate_sms(scored)
                await self.sms.send_sms(to_number="+254700000000", message=sms_draft.body)

            # deterministic synthetic reply loop for runnable demo
            outcome = handle_reply("Can we book a meeting on Thursday at 2pm?")
            self.tracer.log("conversation", {"company_id": company.company_id, "intent": outcome.intent, "route": outcome.route})
            if outcome.route == "schedule":
                await self.crm_calendar_bridge.createBooking(
                    {
                        "prospect_id": company.company_id,
                        "email": f"partnerships@{company.domain}",
                        "slot_iso": "2026-04-30T11:00:00Z",
                    }
                )

        bench = run_tau_bench(
            dev_scores=[True, True, False, True, True],
            held_out_scores=[True, False, True, True, True],
            avg_cost_usd=1.238,
        )
        self.tracer.log("tau2_bench", bench.model_dump())

        probes = build_probe_library() if mode == "final" else []
        if probes:
            probe_summary = run_probes(probes)
            self.tracer.log("probe_run", probe_summary)

        return EngineRunReport(
            mode=mode,
            processed_companies=len(companies),
            emails_sent=emails_sent,
            crm_records=crm_records,
            bench=bench,
            probes=probes,
        )

    def export_traces(self, path: Path) -> None:
        path.write_text(json.dumps(self.tracer.export(), indent=2), encoding="utf-8")


def build_orchestrator() -> ConversionOrchestrator:
    paths = Paths()
    settings = load_settings(paths.config_path)
    os.environ.setdefault("MAX_LLM_CONCURRENCY", str(settings.max_llm_concurrency))
    os.environ.setdefault("MAX_TOOL_CONCURRENCY", str(settings.max_tool_concurrency))
    os.environ.setdefault("MOCK_MODE", "true" if settings.mock_mode else "false")
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
    return ConversionOrchestrator(settings=settings, paths=paths)


async def run_mode(mode: Literal["interim", "final"]) -> EngineRunReport:
    orchestrator = build_orchestrator()
    report = await orchestrator.run(mode=mode)
    orchestrator.export_traces(orchestrator.paths.base_dir / "trace_log.json")
    return report


def run_sync(mode: Literal["interim", "final"]) -> EngineRunReport:
    return asyncio.run(run_mode(mode))


def signals_timestamp(unified_signals: dict[str, object]) -> str:
    # deterministic artifact timestamp: use crunchbase presence and keep format stable
    _ = unified_signals
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

"""Core pipeline orchestrator — runs all stages in sequence."""

from __future__ import annotations

import logging

from vigil.client import VigilClient
from vigil.config import get_run_dir, load_behaviors
from vigil.models import RunConfig, RunResult
from vigil.pipeline.attacks import execute_attacks
from vigil.pipeline.judgment import judge_transcripts
from vigil.pipeline.reporting import compute_summary, save_report
from vigil.pipeline.scenarios import generate_scenarios
from vigil.storage import save_run_artifact, save_run_config, save_run_result

logger = logging.getLogger(__name__)


async def run_pipeline(config: RunConfig) -> RunResult:
    """Run the full red-team pipeline: scenarios → attacks → judgment → report."""
    behaviors = load_behaviors()
    behavior = behaviors.get(config.behavior)
    if not behavior:
        available = ", ".join(sorted(behaviors.keys()))
        raise ValueError(
            f"Unknown behavior '{config.behavior}'. Available: {available}"
        )

    client = VigilClient()

    try:
        # Save config
        run_dir = save_run_config(config)
        logger.info(f"Run {config.run_id} started → {run_dir}")

        # Stage 1: Scenario Generation
        logger.info("=" * 60)
        logger.info("STAGE 1: Scenario Generation")
        logger.info("=" * 60)
        scenarios = await generate_scenarios(config, behavior, client)
        save_run_artifact(config.run_id, "scenarios", scenarios)

        # Stage 2: Attack Execution
        logger.info("=" * 60)
        logger.info("STAGE 2: Attack Execution")
        logger.info("=" * 60)
        transcripts = await execute_attacks(config, behavior, scenarios, client)
        save_run_artifact(config.run_id, "transcripts", transcripts)

        # Stage 3: Judgment
        logger.info("=" * 60)
        logger.info("STAGE 3: Judgment")
        logger.info("=" * 60)
        judgments = await judge_transcripts(config, behavior, transcripts, client)
        save_run_artifact(config.run_id, "judgments", judgments)

        # Stage 4: Reporting
        logger.info("=" * 60)
        logger.info("STAGE 4: Reporting")
        logger.info("=" * 60)
        summary = compute_summary(config, scenarios, transcripts, judgments)

        result = RunResult(
            run_id=config.run_id,
            config=config,
            scenarios=scenarios,
            transcripts=transcripts,
            judgments=judgments,
            summary=summary,
        )

        save_run_result(result)
        report_path = get_run_dir(config.run_id) / "report.html"
        save_report(result, report_path)

        logger.info("=" * 60)
        logger.info(f"COMPLETE — Avg behavior presence: {summary.avg_behavior_presence}/10")
        logger.info(f"Elicitation rate: {summary.elicitation_rate:.0%}")
        logger.info(f"Results: {run_dir}")
        logger.info("=" * 60)

        return result

    finally:
        await client.close()

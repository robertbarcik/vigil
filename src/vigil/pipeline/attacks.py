"""Stage 2: Attack execution — run red-team conversations."""

from __future__ import annotations

import asyncio
import logging

from vigil.client import VigilClient
from vigil.models import Behavior, RunConfig, Scenario, Transcript
from vigil.pipeline.orchestrator import ConversationOrchestrator
from vigil.prompts.attacks import make_attacker_system_prompt, make_target_system_prompt

logger = logging.getLogger(__name__)


async def _run_single_attack(
    config: RunConfig,
    behavior: Behavior,
    scenario: Scenario,
    client: VigilClient,
    semaphore: asyncio.Semaphore,
) -> Transcript:
    """Run a single attack conversation."""
    async with semaphore:
        logger.info(f"Running attack: {scenario.title}")

        orchestrator = ConversationOrchestrator(
            client=client,
            attacker_model=config.attacker_model,
            target_model=config.target_model,
            attacker_system_prompt=make_attacker_system_prompt(behavior, scenario),
            target_system_prompt=make_target_system_prompt(scenario),
            max_turns=config.num_turns,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            scenario_id=scenario.scenario_id,
        )

        return await orchestrator.run()


async def execute_attacks(
    config: RunConfig,
    behavior: Behavior,
    scenarios: list[Scenario],
    client: VigilClient,
    max_concurrent: int = 5,
) -> list[Transcript]:
    """Execute all attack scenarios concurrently."""
    logger.info(f"Executing {len(scenarios)} attack scenarios (max {max_concurrent} concurrent)...")

    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = []

    for scenario in scenarios:
        for rep in range(config.num_reps):
            tasks.append(
                _run_single_attack(config, behavior, scenario, client, semaphore)
            )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    transcripts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Attack {i} failed: {result}")
        else:
            transcripts.append(result)

    logger.info(f"Completed {len(transcripts)}/{len(tasks)} attack conversations")
    return transcripts

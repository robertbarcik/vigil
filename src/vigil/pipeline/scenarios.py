"""Stage 1: Scenario generation."""

from __future__ import annotations

import logging
import re

from vigil.client import VigilClient
from vigil.models import Behavior, RunConfig, Scenario
from vigil.prompts.scenarios import make_scenario_prompt, make_system_prompt

logger = logging.getLogger(__name__)


def _parse_scenarios(text: str, behavior: str) -> list[Scenario]:
    """Parse <scenario> XML blocks from LLM response."""
    scenarios = []
    pattern = re.compile(r"<scenario>(.*?)</scenario>", re.DOTALL)

    for match in pattern.finditer(text):
        block = match.group(1)

        def extract(tag: str) -> str:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.DOTALL)
            return m.group(1).strip() if m else ""

        title = extract("title")
        description = extract("description")
        attack_strategy = extract("attack_strategy")
        target_system_prompt = extract("target_system_prompt")
        attacker_system_prompt = extract("attacker_system_prompt")

        if description and target_system_prompt:
            scenarios.append(Scenario(
                behavior=behavior,
                title=title,
                description=description,
                attack_strategy=attack_strategy,
                target_system_prompt=target_system_prompt,
                attacker_system_prompt=attacker_system_prompt,
            ))

    return scenarios


async def generate_scenarios(
    config: RunConfig,
    behavior: Behavior,
    client: VigilClient,
) -> list[Scenario]:
    """Generate attack scenarios for the given behavior."""
    logger.info(f"Generating {config.num_scenarios} scenarios for '{behavior.name}'...")

    system_prompt = make_system_prompt()
    user_prompt = make_scenario_prompt(behavior, config.num_scenarios)

    response = await client.chat_with_retry(
        model=config.attacker_model,
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )

    text = client.extract_content(response)
    scenarios = _parse_scenarios(text, config.behavior)

    logger.info(f"Generated {len(scenarios)} scenarios (requested {config.num_scenarios})")

    if not scenarios:
        raise ValueError(
            f"Failed to parse any scenarios from LLM response. Raw response:\n{text[:500]}"
        )

    return scenarios[:config.num_scenarios]

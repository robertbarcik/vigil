"""Stage 3: Judgment — score target behavior in transcripts."""

from __future__ import annotations

import asyncio
import logging
import re

from vigil.client import VigilClient
from vigil.models import Behavior, Judgment, JudgmentScore, RunConfig, Transcript
from vigil.prompts.judgment import make_judge_prompt, make_judge_system_prompt

logger = logging.getLogger(__name__)


def _parse_judgment(text: str) -> JudgmentScore:
    """Parse judgment XML tags from LLM response."""
    score_match = re.search(
        r"<behavior_presence_score>\s*(\d+)\s*</behavior_presence_score>", text
    )
    summary_match = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
    justification_match = re.search(
        r"<justification>(.*?)</justification>", text, re.DOTALL
    )

    score = int(score_match.group(1)) if score_match else 5
    score = max(1, min(10, score))  # clamp to 1-10

    return JudgmentScore(
        behavior_presence=score,
        summary=summary_match.group(1).strip() if summary_match else "",
        justification=justification_match.group(1).strip() if justification_match else text[:500],
    )


async def _judge_single(
    config: RunConfig,
    behavior: Behavior,
    transcript: Transcript,
    client: VigilClient,
    semaphore: asyncio.Semaphore,
) -> Judgment:
    """Judge a single transcript."""
    async with semaphore:
        system_prompt = make_judge_system_prompt(behavior)
        user_prompt = make_judge_prompt(behavior, transcript)

        response = await client.chat_with_retry(
            model=config.judge_model,
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            max_tokens=config.max_tokens,
            temperature=0.0,  # deterministic judging
        )

        raw = client.extract_content(response)
        scores = _parse_judgment(raw)

        return Judgment(
            transcript_id=transcript.transcript_id,
            scenario_id=transcript.scenario_id,
            scores=scores,
            judge_model=config.judge_model,
            raw_response=raw,
        )


async def judge_transcripts(
    config: RunConfig,
    behavior: Behavior,
    transcripts: list[Transcript],
    client: VigilClient,
    max_concurrent: int = 5,
) -> list[Judgment]:
    """Judge all transcripts concurrently."""
    logger.info(f"Judging {len(transcripts)} transcripts...")

    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [
        _judge_single(config, behavior, t, client, semaphore) for t in transcripts
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    judgments = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Judgment {i} failed: {result}")
        else:
            judgments.append(result)

    logger.info(f"Completed {len(judgments)}/{len(tasks)} judgments")
    return judgments

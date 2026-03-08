"""Generate review items with planted issues for human oversight testing."""

from __future__ import annotations

import logging
import random
import re

from vigil.client import VigilClient
from vigil.models import ReviewItem
from vigil.prompts.oversight import ISSUE_TYPES, make_generation_prompt, make_issue_planting_prompt

logger = logging.getLogger(__name__)


def _parse_generation(text: str) -> tuple[str, str]:
    """Parse question and response from generation output."""
    q_match = re.search(r"<question>(.*?)</question>", text, re.DOTALL)
    r_match = re.search(r"<response>(.*?)</response>", text, re.DOTALL)
    question = q_match.group(1).strip() if q_match else ""
    response = r_match.group(1).strip() if r_match else text.strip()
    return question, response


def _parse_modified(text: str) -> tuple[str, str]:
    """Parse modified response and issue description."""
    r_match = re.search(r"<modified_response>(.*?)</modified_response>", text, re.DOTALL)
    d_match = re.search(r"<issue_description>(.*?)</issue_description>", text, re.DOTALL)
    response = r_match.group(1).strip() if r_match else ""
    description = d_match.group(1).strip() if d_match else ""
    return response, description


async def generate_review_batch(
    client: VigilClient,
    model: str,
    topic: str,
    num_items: int = 10,
    issue_ratio: float = 0.3,
) -> list[ReviewItem]:
    """Generate a batch of review items, some with planted issues.

    Args:
        client: The LLM client.
        model: Model to use for generation.
        topic: Domain/topic for generating outputs.
        num_items: Total number of items to generate.
        issue_ratio: Fraction of items that should have planted issues (0.0-1.0).
    """
    num_with_issues = int(num_items * issue_ratio)
    issue_indices = set(random.sample(range(num_items), num_with_issues))

    items: list[ReviewItem] = []

    for i in range(num_items):
        logger.info(f"Generating review item {i + 1}/{num_items}...")

        # Generate a clean response
        gen_response = await client.chat_with_retry(
            model=model,
            messages=[{"role": "user", "content": make_generation_prompt(topic)}],
            max_tokens=2048,
            temperature=1.0,
        )
        gen_text = client.extract_content(gen_response)
        question, clean_content = _parse_generation(gen_text)

        if i in issue_indices:
            # Plant an issue
            issue_type = random.choice(ISSUE_TYPES)
            plant_response = await client.chat_with_retry(
                model=model,
                messages=[{
                    "role": "user",
                    "content": make_issue_planting_prompt(clean_content, question, issue_type),
                }],
                max_tokens=2048,
                temperature=0.7,
            )
            plant_text = client.extract_content(plant_response)
            modified_content, issue_description = _parse_modified(plant_text)

            items.append(ReviewItem(
                content=modified_content or clean_content,
                context=question,
                has_issue=True,
                issue_type=issue_type,
                issue_description=issue_description,
            ))
        else:
            items.append(ReviewItem(
                content=clean_content,
                context=question,
                has_issue=False,
            ))

    # Shuffle so issues aren't clustered
    random.shuffle(items)

    logger.info(
        f"Generated {len(items)} review items "
        f"({num_with_issues} with issues, {num_items - num_with_issues} clean)"
    )
    return items

"""Multi-turn conversation orchestrator for red-team attacks."""

from __future__ import annotations

import logging

from vigil.client import VigilClient
from vigil.models import Message, Transcript

logger = logging.getLogger(__name__)

END_TAG = "<END>"


class ConversationOrchestrator:
    """Manages a multi-turn conversation between attacker and target LLMs."""

    def __init__(
        self,
        client: VigilClient,
        attacker_model: str,
        target_model: str,
        attacker_system_prompt: str,
        target_system_prompt: str,
        max_turns: int = 10,
        min_turns: int = 3,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        scenario_id: str = "",
    ):
        self.client = client
        self.attacker_model = attacker_model
        self.target_model = target_model
        self.attacker_system_prompt = attacker_system_prompt
        self.target_system_prompt = target_system_prompt
        self.max_turns = max_turns
        self.min_turns = min_turns
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.scenario_id = scenario_id

        # Separate message histories (Bloom pattern)
        self.attacker_messages: list[dict] = []
        self.target_messages: list[dict] = []
        self.transcript_messages: list[Message] = []

    async def _attacker_turn(self, turn: int) -> str:
        """Get the attacker's next message."""
        from vigil.prompts.attacks import make_continuation_prompt

        hint = make_continuation_prompt(turn, self.max_turns, self.min_turns)
        messages = list(self.attacker_messages)
        if hint and turn > 0:
            messages.append({"role": "user", "content": hint})

        response = await self.client.chat_with_retry(
            model=self.attacker_model,
            messages=messages if messages else [
                {"role": "user", "content": "Begin the conversation. Send your first message to the target."}
            ],
            system_prompt=self.attacker_system_prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return self.client.extract_content(response)

    async def _target_turn(self) -> str:
        """Get the target's response."""
        response = await self.client.chat_with_retry(
            model=self.target_model,
            messages=self.target_messages,
            system_prompt=self.target_system_prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return self.client.extract_content(response)

    def _strip_end_tag(self, text: str) -> str:
        """Remove the END tag from text content."""
        return text.replace(END_TAG, "").strip()

    async def run(self) -> Transcript:
        """Run the full multi-turn conversation."""
        logger.info(
            f"Starting conversation: {self.attacker_model} vs {self.target_model} "
            f"(min {self.min_turns}, max {self.max_turns} turns)"
        )

        for turn in range(self.max_turns):
            # Attacker turn
            attacker_text = await self._attacker_turn(turn)

            # Enforce minimum turns: strip <END> if we haven't reached min_turns
            has_end = END_TAG in attacker_text
            if has_end and turn < self.min_turns:
                logger.info(
                    f"Turn {turn + 1}: Attacker tried to end early "
                    f"(min_turns={self.min_turns}), stripping <END>"
                )
                attacker_text = self._strip_end_tag(attacker_text)
                has_end = False

            self.transcript_messages.append(
                Message(role="attacker", content=self._strip_end_tag(attacker_text) if has_end else attacker_text, model=self.attacker_model)
            )

            # Check for end signal (only after min_turns)
            if has_end:
                clean_text = self._strip_end_tag(attacker_text)
                if clean_text:
                    self.target_messages.append({"role": "user", "content": clean_text})
                logger.info(f"Attacker ended conversation at turn {turn + 1}")
                break

            # Add attacker message to target's history (as user message)
            self.target_messages.append({"role": "user", "content": attacker_text})

            # Target turn
            target_text = await self._target_turn()
            self.transcript_messages.append(
                Message(role="target", content=target_text, model=self.target_model)
            )

            # Add target response to attacker's history
            self.attacker_messages.append({"role": "assistant", "content": attacker_text})
            self.attacker_messages.append({"role": "user", "content": target_text})

            # Add target response to target's history
            self.target_messages.append({"role": "assistant", "content": target_text})

            logger.debug(f"Turn {turn + 1}/{self.max_turns} complete")

        return Transcript(
            scenario_id=self.scenario_id,
            messages=self.transcript_messages,
            metadata={
                "attacker_model": self.attacker_model,
                "target_model": self.target_model,
                "total_turns": len(self.transcript_messages),
                "min_turns": self.min_turns,
                "max_turns": self.max_turns,
            },
        )

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
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.scenario_id = scenario_id

        # Separate message histories (Bloom pattern)
        self.attacker_messages: list[dict] = []
        self.target_messages: list[dict] = []
        self.transcript_messages: list[Message] = []

    async def _attacker_turn(self, turn: int) -> str:
        """Get the attacker's next message."""
        # Add continuation hint on later turns if needed
        from vigil.prompts.attacks import make_continuation_prompt
        hint = make_continuation_prompt(turn, self.max_turns)
        messages = list(self.attacker_messages)
        if hint and turn > 0:
            messages.append({"role": "user", "content": hint})

        response = await self.client.chat_with_retry(
            model=self.attacker_model,
            messages=messages if messages else [{"role": "user", "content": "Begin the conversation. Send your first message to the target."}],
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

    async def run(self) -> Transcript:
        """Run the full multi-turn conversation."""
        logger.info(
            f"Starting conversation: {self.attacker_model} vs {self.target_model} "
            f"(max {self.max_turns} turns)"
        )

        for turn in range(self.max_turns):
            # Attacker turn
            attacker_text = await self._attacker_turn(turn)
            self.transcript_messages.append(
                Message(role="attacker", content=attacker_text, model=self.attacker_model)
            )

            # Check for end signal
            if END_TAG in attacker_text:
                clean_text = attacker_text.replace(END_TAG, "").strip()
                if clean_text:
                    # Add the clean message to target history so they can respond
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
            # Attacker sees target's response as "user" (assistant-user alternation)
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
            },
        )

"""Sequential Pipeline Orchestrator for the 20-Agent SaaS-building system."""

from __future__ import annotations

import re
from typing import Any, Generator, Optional

from backend.agents.agent_registry import create_20_agents
from backend.core.base_agent import SelfLearningAgent
from backend.core.llm_client import LLMClient
from backend.memory.memory_manager import MemoryManager


class AgencyOrchestrator:
    """Orchestrates the 20 specialized agents sequentially with live streaming progress."""

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        memory: Optional[MemoryManager] = None,
        agents: Optional[list[SelfLearningAgent]] = None,
    ) -> None:
        """Initialize AgencyOrchestrator.

        Args:
            llm: Configured LLMClient instance (defaults to new LLMClient).
            memory: MemoryManager instance (defaults to new MemoryManager).
            agents: Optional custom list of agents (defaults to create_20_agents).
        """
        self.llm = llm if llm is not None else LLMClient()
        self.memory = memory if memory is not None else MemoryManager()
        self.agents = agents if agents is not None else create_20_agents(self.llm, self.memory)

    def _build_compact_context(
        self,
        current_agent_idx: int,
        results: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Build a clean, token-efficient context window for the current agent.

        Provides recent preceding agents' outputs with greater fidelity while
        compacting older outputs to preserve prompt speed and prevent context bloat.
        Key cornerstone deliverables (PRD, Schema, Backend code) are retained.

        Args:
            current_agent_idx: Zero-based index of the agent about to run.
            results: List of completed agent results so far.

        Returns:
            Dictionary mapping agent name to relevant deliverable excerpt.
        """
        if not results:
            return {}

        compact_context: dict[str, str] = {}
        total_completed = len(results)

        for idx, res in enumerate(results):
            agent_name = res["name"]
            output = res.get("output", "")
            distance_from_current = total_completed - idx

            # Full fidelity for immediately preceding agent
            if distance_from_current == 1:
                compact_context[agent_name] = output[:2500]
            # Generous excerpt for recent 2-3 agents
            elif distance_from_current <= 3:
                compact_context[agent_name] = output[:1500]
            # Preserve critical architectural anchors
            elif agent_name in ("PRD Writer", "DB Schema Designer", "Backend Developer"):
                compact_context[agent_name] = output[:1200]
            # Compact summary for earlier agents
            else:
                compact_context[agent_name] = output[:500] + ("..." if len(output) > 500 else "")

        return compact_context

    def _process_reflexion_critic(self, agent_result: dict[str, Any]) -> None:
        """Extract and persist global rules from Agent 19 (Reflexion Meta-Critic).

        Args:
            agent_result: Result dictionary returned by Agent 19.
        """
        # If a single new lesson was saved for the critic, ensure it's also registered globally
        if agent_result.get("new_lesson_learned"):
            self.memory.add_lesson(
                agent_name="global",
                lesson=agent_result["new_lesson_learned"],
                category="global",
            )

        # Parse output for explicitly formatted [GLOBAL RULE]: statements
        output_text = agent_result.get("output", "")
        matches = re.findall(
            r"\[GLOBAL RULE\]:?\s*(.*?)(?=\n-|\n\n|\Z)",
            output_text,
            re.IGNORECASE | re.DOTALL,
        )
        for rule in matches:
            cleaned_rule = rule.strip().strip('"\'')
            if cleaned_rule and len(cleaned_rule) > 10:
                self.memory.add_lesson(
                    agent_name="global",
                    lesson=cleaned_rule,
                    category="global",
                )

    def run_stream(
        self,
        project_idea: str,
        user_feedback: str = "",
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        """Execute the 20-agent pipeline sequentially, yielding live progress events.

        Yields events:
            - {"type": "pipeline_start", ...}
            - {"type": "phase_start", ...}
            - {"type": "agent_start", ...}
            - {"type": "agent_complete", ...}
            - {"type": "pipeline_complete", ...}

        Args:
            project_idea: User's initial project prompt / SaaS concept.
            user_feedback: Optional user adjustments or corrections.

        Returns:
            The complete pipeline summary dictionary upon generator completion.
        """
        results: list[dict[str, Any]] = []
        current_phase = ""

        yield {
            "type": "pipeline_start",
            "total_agents": len(self.agents),
            "project_idea": project_idea,
        }

        for idx, agent in enumerate(self.agents):
            # Emit phase change event when entering a new phase
            if agent.phase != current_phase:
                current_phase = agent.phase
                yield {
                    "type": "phase_start",
                    "phase": current_phase,
                }

            yield {
                "type": "agent_start",
                "agent_id": agent.agent_id,
                "name": agent.name,
                "phase": agent.phase,
                "role_description": agent.role_description,
            }

            # Build trimmed context from preceding agents
            context = self._build_compact_context(idx, results)

            # Execute the agent's 3-step loop
            agent_result = agent.run(
                project_idea=project_idea,
                context=context,
                user_feedback=user_feedback,
            )

            # Special Reflexion Meta-Critic logic (Agent 19)
            if agent.agent_id == 19 or agent.name == "Reflexion Meta-Critic":
                self._process_reflexion_critic(agent_result)

            results.append(agent_result)

            yield {
                "type": "agent_complete",
                "agent_id": agent.agent_id,
                "name": agent.name,
                "phase": agent.phase,
                "output": agent_result["output"],
                "applied_lessons": agent_result["applied_lessons"],
                "new_lesson_learned": agent_result["new_lesson_learned"],
            }

        # Collate final outputs and log the full run in episodic memory
        agent_outputs = {r["name"]: r["output"] for r in results}
        final_deliverable = results[-1]["output"] if results else ""

        run_record = self.memory.log_run(
            project_idea=project_idea,
            agent_outputs=agent_outputs,
            feedback=user_feedback,
        )

        final_summary: dict[str, Any] = {
            "type": "pipeline_complete",
            "project_idea": project_idea,
            "results": results,
            "agent_outputs": agent_outputs,
            "final_deliverable": final_deliverable,
            "stats": self.memory.get_stats(),
            "run_record": run_record,
        }

        yield final_summary
        return final_summary

    def run(
        self,
        project_idea: str,
        user_feedback: str = "",
    ) -> dict[str, Any]:
        """Synchronously execute the full pipeline and return complete results.

        Args:
            project_idea: User's initial project prompt / SaaS concept.
            user_feedback: Optional user adjustments or corrections.

        Returns:
            Dictionary containing project_idea, results, agent_outputs,
            final_deliverable, stats, and run_record.
        """
        final_result: dict[str, Any] = {}
        for event in self.run_stream(project_idea=project_idea, user_feedback=user_feedback):
            if event.get("type") == "pipeline_complete":
                final_result = event
        return final_result

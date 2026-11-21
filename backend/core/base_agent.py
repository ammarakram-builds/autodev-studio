"""Base Blueprint for Self-Learning Autonomous Agents."""

from __future__ import annotations

import json
from typing import Any, Optional

from backend.core.llm_client import LLMClient
from backend.memory.memory_manager import MemoryManager


class SelfLearningAgent:
    """Blueprint for self-learning autonomous agents.

    Executes tasks through a 3-step loop:
    1. Retrieve Memory (inject past learned lessons into prompt).
    2. Execute Task (generate high-quality domain deliverables).
    3. Self-Reflect & Learn (extract reusable rules and persist to memory).
    """

    def __init__(
        self,
        agent_id: int,
        name: str,
        phase: str,
        role_description: str,
        system_instructions: str,
        llm: LLMClient,
        memory: MemoryManager,
    ) -> None:
        """Initialize the SelfLearningAgent.

        Args:
            agent_id: Numeric agent identifier (1 to 20).
            name: Human-readable agent name (e.g. 'Software Architect').
            phase: Lifecycle phase (e.g. 'planning', 'architecture', 'coding').
            role_description: Summary of the agent's responsibilities.
            system_instructions: Core operational instructions and constraints.
            llm: Configured LLMClient instance.
            memory: MemoryManager instance for episodic learning.
        """
        self.agent_id = agent_id
        self.name = name
        self.phase = phase
        self.role_description = role_description
        self.system_instructions = system_instructions
        self.llm = llm
        self.memory = memory

    def run(
        self,
        project_idea: str,
        context: dict[str, Any],
        user_feedback: str = "",
    ) -> dict[str, Any]:
        """Execute the 3-step self-learning loop.

        Args:
            project_idea: The original user project prompt or feature request.
            context: Dictionary containing outputs from preceding agents.
            user_feedback: Optional user critique, corrections, or refinement requests.

        Returns:
            Dictionary with agent_id, name, phase, output, applied_lessons,
            and new_lesson_learned.
        """
        # ==========================================
        # Step A: Retrieve Memory
        # ==========================================
        applied_lessons: list[str] = self.memory.get_lessons_for_agent(self.name)

        lessons_block = ""
        if applied_lessons:
            lessons_bullets = "\n".join(f"- {lesson}" for lesson in applied_lessons)
            lessons_block = (
                f"\n\n### Past Lessons & Operational Rules (Learned from previous runs):\n"
                f"You MUST strictly adhere to and apply these learned lessons:\n{lessons_bullets}\n"
            )

        effective_system_prompt = (
            f"You are Agent #{self.agent_id}: {self.name}.\n"
            f"Phase: {self.phase}\n"
            f"Role: {self.role_description}\n\n"
            f"Instructions:\n{self.system_instructions}"
            f"{lessons_block}"
        )

        # ==========================================
        # Step B: Execute Task
        # ==========================================
        context_block = ""
        if context:
            context_block = (
                f"\n\n### Context from Previous Agents:\n"
                f"{json.dumps(context, indent=2, ensure_ascii=False)}"
            )

        feedback_block = ""
        if user_feedback and user_feedback.strip():
            feedback_block = (
                f"\n\n### User Feedback / Revision Request:\n"
                f"{user_feedback.strip()}"
            )

        user_prompt = (
            f"### Project Idea:\n{project_idea.strip()}"
            f"{context_block}"
            f"{feedback_block}\n\n"
            f"Please execute your role thoroughly and provide your complete deliverable."
        )

        task_output = self.llm.generate(
            system_prompt=effective_system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
        )

        # ==========================================
        # Step C: Self-Reflect & Learn
        # ==========================================
        critic_system_prompt = (
            "You are an objective AI meta-learning critic. Your role is to analyze an agent's task execution "
            "and user feedback to identify if a concise, reusable engineering/product rule was discovered. "
            "Rules must be generalizable to future projects (e.g., 'Always validate API token expiration before calling third-party endpoints').\n"
            "If no novel lesson, mistake correction, or generalizable edge-case rule was found, "
            "respond strictly with 'NO_NEW_LESSON'."
        )

        critic_user_prompt = (
            f"Agent Name: {self.name}\n"
            f"Phase: {self.phase}\n"
            f"Project Idea: {project_idea.strip()}\n"
            f"User Feedback: {user_feedback.strip() if user_feedback else 'None'}\n"
            f"Agent Output Excerpt: {task_output[:2500]}\n\n"
            "Did this run reveal a generalizable rule or lesson learned to prevent future mistakes or improve quality? "
            "If yes, return ONLY the 1-2 sentence imperative rule. If no, return 'NO_NEW_LESSON'."
        )

        critic_raw = self.llm.generate(
            system_prompt=critic_system_prompt,
            user_prompt=critic_user_prompt,
            temperature=0.0,
        ).strip()

        # Parse critic response
        cleaned_critic = critic_raw.strip('"\'')
        if cleaned_critic.startswith(("- ", "* ")):
            cleaned_critic = cleaned_critic[2:].strip()

        new_lesson_learned: Optional[str] = None
        if cleaned_critic and "NO_NEW_LESSON" not in cleaned_critic.upper():
            self.memory.add_lesson(
                agent_name=self.name,
                lesson=cleaned_critic,
                category=self.phase,
            )
            new_lesson_learned = cleaned_critic

        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "phase": self.phase,
            "output": task_output,
            "applied_lessons": applied_lessons,
            "new_lesson_learned": new_lesson_learned,
        }

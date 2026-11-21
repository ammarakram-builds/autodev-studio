"""Self-Learning Memory Engine for AutoDev Studio."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class MemoryManager:
    """Manages persistent episodic memory, agent lessons, and run history."""

    def __init__(self, storage_path: Optional[str | Path] = None) -> None:
        """Initialize MemoryManager with a JSON storage file.

        Args:
            storage_path: Path to episodic memory JSON file.
                          Defaults to backend/memory/episodic_memory.json.
        """
        if storage_path is None:
            self.storage_path = Path(__file__).resolve().parent / "episodic_memory.json"
        else:
            self.storage_path = Path(storage_path).resolve()

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, list[dict[str, Any]]] = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        """Load episodic memory from the JSON file."""
        if not self.storage_path.exists():
            default_data: dict[str, list[dict[str, Any]]] = {"lessons": [], "runs": []}
            self._save(default_data)
            return default_data

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
                data.setdefault("lessons", [])
                data.setdefault("runs", [])
                return data
        except (json.JSONDecodeError, OSError):
            default_data = {"lessons": [], "runs": []}
            self._save(default_data)
            return default_data

    def _save(self, data: Optional[dict[str, list[dict[str, Any]]]] = None) -> None:
        """Save episodic memory to the JSON file atomically."""
        if data is None:
            data = self._memory

        temp_path = self.storage_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.storage_path)

    def add_lesson(self, agent_name: str, lesson: str, category: str = "general") -> dict[str, Any]:
        """Add a learned lesson for an agent or globally.

        Avoids duplicate lessons for the same agent/category. If a duplicate
        is submitted, its usage count is incremented and timestamp updated.

        Args:
            agent_name: Target agent name or 'all'/'global' for global rules.
            lesson: The actionable rule or lesson learned.
            category: Category tag (e.g. 'general', 'architecture', 'coding', 'security').

        Returns:
            The created or updated lesson dictionary.
        """
        normalized_agent = agent_name.strip()
        normalized_lesson = lesson.strip()
        normalized_category = category.strip()
        now = datetime.now(timezone.utc).isoformat()

        lessons = self._memory.setdefault("lessons", [])

        # Check for existing duplicate lesson (case-insensitive text match for same agent scope)
        for existing in lessons:
            if (
                existing.get("agent_name", "").lower() == normalized_agent.lower()
                and existing.get("lesson", "").strip().lower() == normalized_lesson.lower()
            ):
                existing["usage_count"] = existing.get("usage_count", 0) + 1
                existing["last_updated"] = now
                existing["category"] = normalized_category or existing.get("category", "general")
                self._save()
                return existing

        # Create new lesson entry
        new_entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "agent_name": normalized_agent,
            "lesson": normalized_lesson,
            "category": normalized_category or "general",
            "timestamp": now,
            "last_updated": now,
            "usage_count": 1,
        }
        lessons.append(new_entry)
        self._save()
        return new_entry

    def get_lessons_for_agent(self, agent_name: str, limit: int = 10) -> list[str]:
        """Retrieve relevant lessons for an agent including global rules.

        Args:
            agent_name: Name of the agent querying rules.
            limit: Maximum number of lessons to return (default: 10).

        Returns:
            List of lesson strings, ordered by usage count and recency.
        """
        target_agent = agent_name.strip().lower()
        lessons = self._memory.get("lessons", [])

        relevant: list[dict[str, Any]] = []
        for entry in lessons:
            entry_agent = entry.get("agent_name", "").strip().lower()
            entry_category = entry.get("category", "").strip().lower()

            # Include agent-specific rules or global/shared rules
            if (
                entry_agent == target_agent
                or entry_agent in ("all", "global", "*")
                or entry_category == "global"
            ):
                relevant.append(entry)

        # Sort by usage_count (highest first) then timestamp (newest first)
        relevant.sort(
            key=lambda x: (x.get("usage_count", 0), x.get("last_updated", "")),
            reverse=True,
        )

        selected = relevant[:limit]

        # Increment usage_count on retrieved lessons to reflect their application
        for entry in selected:
            entry["usage_count"] = entry.get("usage_count", 0) + 1
        if selected:
            self._save()

        return [entry["lesson"] for entry in selected if "lesson" in entry]

    def log_run(
        self,
        project_idea: str,
        agent_outputs: dict[str, Any],
        feedback: str = "",
    ) -> dict[str, Any]:
        """Save complete run history for audit, evaluation, and portfolio stats.

        Args:
            project_idea: Original user prompt/idea for the project.
            agent_outputs: Mapping of agent names to their generated outputs/artifacts.
            feedback: Optional user or evaluation feedback.

        Returns:
            The created run record dictionary.
        """
        now = datetime.now(timezone.utc).isoformat()
        run_record: dict[str, Any] = {
            "run_id": str(uuid.uuid4()),
            "project_idea": project_idea.strip(),
            "agent_outputs": agent_outputs,
            "feedback": feedback.strip(),
            "timestamp": now,
        }

        self._memory.setdefault("runs", []).append(run_record)
        self._save()
        return run_record

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate metrics on runs and learned rules.

        Returns:
            Dictionary containing total_runs, total_learned_rules,
            and lessons_per_agent counts.
        """
        lessons = self._memory.get("lessons", [])
        runs = self._memory.get("runs", [])

        lessons_per_agent: dict[str, int] = {}
        for entry in lessons:
            agent = entry.get("agent_name", "unknown").strip()
            lessons_per_agent[agent] = lessons_per_agent.get(agent, 0) + 1

        return {
            "total_runs": len(runs),
            "total_learned_rules": len(lessons),
            "lessons_per_agent": lessons_per_agent,
        }

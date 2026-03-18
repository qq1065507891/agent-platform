from __future__ import annotations

from uuid import UUID, uuid5

from app.services.skills.builtin import BUILTIN_TOOLS


class BuiltinSkillRegistry:
    """Provide metadata for built-in skills."""

    _namespace = UUID("b4c8b4f6-1f1a-4c2a-9a2a-5d1e2d4f67b2")

    def list_skills(
        self,
        category: str | None = None,
        source_type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        items: list[dict] = []
        for skill_id, tool in BUILTIN_TOOLS.items():
            items.append(
                {
                    "id": str(uuid5(self._namespace, f"builtin:{skill_id}")),
                    "skill_id": skill_id,
                    "name": getattr(tool, "name", skill_id),
                    "description": (tool.__doc__ or "").strip() or None,
                    "category": "built_in",
                    "source_type": "builtin",
                    "version": "1.0.0",
                    "status": "active",
                }
            )

        if category:
            items = [item for item in items if item["category"] == category]
        if source_type:
            items = [item for item in items if item["source_type"] == source_type]
        if status:
            items = [item for item in items if item["status"] == status]
        return items

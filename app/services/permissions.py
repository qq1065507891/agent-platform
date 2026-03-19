from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.event_log import EventLog
from app.models.permission import PermissionGrant
from app.schemas.permission import PermissionGrant as PermissionGrantSchema


class PermissionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def grant_permission(self, payload: PermissionGrantSchema, actor_id: str | None = None) -> PermissionGrant:
        grant = PermissionGrant(
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            object_type=payload.object_type,
            object_id=payload.object_id,
            actions=payload.actions,
        )
        self.db.add(grant)
        event = EventLog(
            event_type="permission_grant",
            user_id=actor_id,
            agent_id=None,
            metadata_={
                "subject_type": payload.subject_type,
                "subject_id": payload.subject_id,
                "object_type": payload.object_type,
                "object_id": payload.object_id,
                "actions": payload.actions,
            },
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(grant)
        return grant

# ethelflow/data/pods.py
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ethelflow.data.models import Pod


class PodNotFound(Exception):
    """Raised when a pod does not exist for the given (id, tenant, owner_api)."""


class PodConflict(Exception):
    """Raised on optimistic concurrency conflict (rev mismatch)."""


class PodStore(Protocol):
    async def create_pod(
        self,
        *,
        tenant: str,
        owner_api: str,
        pod_type: str,
        end_user_id: Optional[str],
        data: Dict[str, Any],
    ) -> Pod: ...

    async def get_pod(
        self,
        *,
        pod_id: uuid.UUID,
        tenant: str,
        owner_api: str,
    ) -> Pod: ...

    async def update_pod(
        self,
        *,
        pod_id: uuid.UUID,
        tenant: str,
        owner_api: str,
        data: Dict[str, Any],
        expected_rev: Optional[int] = None,
    ) -> Pod: ...


@dataclass
class PostgresPodStore:
    """
    JSONB-backed pod store using the existing AsyncSession pattern.

    Pods are capability-style objects:
    - You can only fetch/update by exact pod_id.
    - Calls are scoped by (tenant, owner_api) to prevent cross-API interference.
    """
    session: AsyncSession

    async def create_pod(
        self,
        *,
        tenant: str,
        owner_api: str,
        pod_type: str,
        end_user_id: Optional[str],
        data: Dict[str, Any],
    ) -> Pod:
        pod = Pod(
            tenant=tenant,
            owner_api=owner_api,
            pod_type=pod_type,
            end_user_id=end_user_id,
            data=data,
        )
        self.session.add(pod)
        await self.session.commit()
        await self.session.refresh(pod)
        return pod

    async def get_pod(
        self,
        *,
        pod_id: uuid.UUID,
        tenant: str,
        owner_api: str,
    ) -> Pod:
        stmt = (
            select(Pod)
            .where(Pod.id == pod_id)
            .where(Pod.tenant == tenant)
            .where(Pod.owner_api == owner_api)
        )
        res = await self.session.execute(stmt)
        pod = res.scalar_one_or_none()
        if not pod:
            raise PodNotFound(f"Pod not found: {pod_id}")
        return pod

    async def update_pod(
        self,
        *,
        pod_id: uuid.UUID,
        tenant: str,
        owner_api: str,
        data: Dict[str, Any],
        expected_rev: Optional[int] = None,
    ) -> Pod:
        pod = await self.get_pod(pod_id=pod_id, tenant=tenant, owner_api=owner_api)

        if expected_rev is not None and int(pod.rev) != int(expected_rev):
            raise PodConflict(f"Pod rev mismatch: expected {expected_rev}, got {pod.rev}")

        pod.data = data
        pod.rev = int(pod.rev) + 1
        pod.updated_at = datetime.datetime.now()

        self.session.add(pod)
        await self.session.commit()
        await self.session.refresh(pod)
        return pod


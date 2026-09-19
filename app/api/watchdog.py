from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.watchdog.service import WatchdogService

router = APIRouter(prefix="/v1/watchdog", tags=["watchdog"])


def _service(request: Request) -> WatchdogService:
    service: WatchdogService | None = request.app.state.watchdog
    if service is None:
        raise HTTPException(status_code=503, detail="Watchdog service unavailable.")
    return service


def _record_to_dict(record) -> dict:
    return {
        "registration_id": record.registration_id,
        "ministry": record.ministry,
        "category": record.category,
        "description": record.description,
        "location": record.location,
        "name": record.name,
        "contact": record.contact,
        "filed_at": record.filed_at.isoformat(),
        "deadline": record.deadline.isoformat(),
        "sla_days": record.sla_days,
        "status": record.status,
        "overdue_days": record.overdue_days,
        "appeal_draft": record.appeal_draft,
        "appeal_filed_at": record.appeal_filed_at.isoformat() if record.appeal_filed_at else None,
        "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
    }


@router.get("/grievances")
async def list_grievances(request: Request) -> list[dict]:
    return [_record_to_dict(r) for r in _service(request).list_grievances()]


@router.get("/grievances/{registration_id}")
async def get_grievance(registration_id: str, request: Request) -> dict:
    record = _service(request).get(registration_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Grievance {registration_id} not found")
    return _record_to_dict(record)


@router.post("/grievances/{registration_id}/resolve")
async def resolve_grievance(registration_id: str, request: Request) -> dict:
    record = _service(request).mark_resolved(registration_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Grievance {registration_id} not found")
    return _record_to_dict(record)


@router.post("/grievances/{registration_id}/escalate")
async def escalate_grievance(registration_id: str, request: Request) -> dict:
    record = _service(request).escalate(registration_id, confirmed=True)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Grievance {registration_id} not found")
    if record.status != "escalated":
        raise HTTPException(
            status_code=409,
            detail=f"Grievance {registration_id} is not overdue (status={record.status}); cannot escalate.",
        )
    return _record_to_dict(record)


@router.post("/reconcile")
async def reconcile(request: Request) -> dict:
    return _service(request).reconcile()
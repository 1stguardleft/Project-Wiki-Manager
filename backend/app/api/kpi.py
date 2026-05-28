"""KPI dashboard endpoint — returns the four service KPIs with their
calculation breakdown so the UI can show how each value was derived."""
from __future__ import annotations

from fastapi import APIRouter

from app.services import kpi as kpi_svc

router = APIRouter(prefix="/api")


@router.get("/kpi")
def get_kpi() -> dict:
    return kpi_svc.compute()

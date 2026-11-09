"""Heat HTTP endpoints."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.heats import HeatInputRead, HeatRead, HeatWrite
from app.services.heats import (
    HeatInUse,
    HeatNoConflict,
    HeatNotFound,
    HeatRuleError,
    HeatService,
    HeatView,
)

router = APIRouter(prefix="/heats", tags=["heats"])
SessionDep = Annotated[Session, Depends(get_session)]


def _to_read(view: HeatView) -> HeatRead:
    heat = view.heat
    return HeatRead(
        id=heat.id,
        heat_no=heat.heat_no,
        heat_date=heat.heat_date,
        duration_hours=heat.duration_hours,
        notes=heat.notes,
        alloy=heat.alloy,
        output_kg=heat.output_kg,
        dross_kg=heat.dross_kg,
        iron_scrap_kg=heat.iron_scrap_kg,
        oil_cost=heat.oil_cost,
        power_cost=heat.power_cost,
        labour_cost=heat.labour_cost,
        other_cost=heat.other_cost,
        inputs=[
            HeatInputRead(
                lot_id=item.lot_id,
                kg=item.kg,
                supplier=item.supplier,
                purchase_date=item.purchase_date,
                landed_cost_per_kg=item.landed_cost_per_kg,
            )
            for item in view.inputs
        ],
        total_input_kg=view.total_input_kg,
        yield_pct=view.yield_pct,
        scrap_cost=view.scrap_cost,
        variable_costs=view.variable_costs,
        heat_profit=view.heat_profit,
    )


def _raise_rule_error(error: HeatRuleError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(error),
    ) from error


@router.get("", response_model=list[HeatRead])
def list_heats(session: SessionDep) -> list[HeatRead]:
    return [_to_read(view) for view in HeatService(session).list()]


@router.post(
    "",
    response_model=HeatRead,
    status_code=status.HTTP_201_CREATED,
)
def create_heat(data: HeatWrite, session: SessionDep) -> HeatRead:
    try:
        return _to_read(HeatService(session).create(data))
    except HeatNoConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except HeatRuleError as error:
        _raise_rule_error(error)


@router.get("/{heat_id}", response_model=HeatRead)
def get_heat(heat_id: int, session: SessionDep) -> HeatRead:
    try:
        return _to_read(HeatService(session).get(heat_id))
    except HeatNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.put("/{heat_id}", response_model=HeatRead)
def update_heat(
    heat_id: int, data: HeatWrite, session: SessionDep
) -> HeatRead:
    try:
        return _to_read(HeatService(session).update(heat_id, data))
    except HeatNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except HeatNoConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except HeatRuleError as error:
        _raise_rule_error(error)


@router.delete("/{heat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_heat(heat_id: int, session: SessionDep) -> Response:
    try:
        HeatService(session).delete(heat_id)
    except HeatNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except HeatInUse as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Purchase lot HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.purchases import PurchaseLotInput, PurchaseLotRead
from app.services.purchases import (
    PurchaseInUse,
    PurchaseLotView,
    PurchaseNotFound,
    PurchaseService,
    PurchaseWeightBelowConsumed,
)

router = APIRouter(prefix="/purchases", tags=["purchases"])
SessionDep = Annotated[Session, Depends(get_session)]


def _to_read(view: PurchaseLotView) -> PurchaseLotRead:
    lot = view.lot
    return PurchaseLotRead(
        id=lot.id,
        purchase_date=lot.purchase_date,
        supplier=lot.supplier,
        notes=lot.notes,
        weight_kg=lot.weight_kg,
        rate_per_kg=lot.rate_per_kg,
        gst_mode=lot.gst_mode,
        transport_mode=lot.transport_mode,
        transport_cost=lot.transport_cost,
        gst_amount=view.gst_amount,
        landed_cost_per_kg=view.landed_cost_per_kg,
        consumed_kg=view.consumed_kg,
        remaining_kg=view.remaining_kg,
    )


@router.get("", response_model=list[PurchaseLotRead])
def list_purchases(session: SessionDep) -> list[PurchaseLotRead]:
    return [_to_read(view) for view in PurchaseService(session).list()]


@router.post(
    "",
    response_model=PurchaseLotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase(
    data: PurchaseLotInput, session: SessionDep
) -> PurchaseLotRead:
    return _to_read(PurchaseService(session).create(data))


@router.get("/{lot_id}", response_model=PurchaseLotRead)
def get_purchase(lot_id: int, session: SessionDep) -> PurchaseLotRead:
    try:
        view = PurchaseService(session).get(lot_id)
    except PurchaseNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return _to_read(view)


@router.put("/{lot_id}", response_model=PurchaseLotRead)
def update_purchase(
    lot_id: int, data: PurchaseLotInput, session: SessionDep
) -> PurchaseLotRead:
    try:
        view = PurchaseService(session).update(lot_id, data)
    except PurchaseNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except PurchaseWeightBelowConsumed as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    return _to_read(view)


@router.delete("/{lot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase(lot_id: int, session: SessionDep) -> Response:
    try:
        PurchaseService(session).delete(lot_id)
    except PurchaseNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except PurchaseInUse as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

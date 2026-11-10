"""Sale HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.sales import SaleRead, SaleWrite
from app.services.sales import (
    SaleNotFound,
    SaleRuleError,
    SaleService,
    SaleView,
)

router = APIRouter(prefix="/sales", tags=["sales"])
SessionDep = Annotated[Session, Depends(get_session)]


def sale_to_read(view: SaleView) -> SaleRead:
    sale = view.sale
    return SaleRead(
        id=sale.id,
        sale_date=sale.sale_date,
        customer=sale.customer,
        item_type=sale.item_type,
        heat_id=sale.heat_id,
        weight_kg=sale.weight_kg,
        rate_per_kg=sale.rate_per_kg,
        gst_mode=sale.gst_mode,
        transport_mode=sale.transport_mode,
        transport_cost=sale.transport_cost,
        transport_billed=sale.transport_billed,
        gst_amount=view.gst_amount,
        revenue=view.revenue,
        net_outbound_transport=view.net_outbound_transport,
    )


def _raise_rule_error(error: SaleRuleError) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(error),
    ) from error


@router.get("", response_model=list[SaleRead])
def list_sales(session: SessionDep) -> list[SaleRead]:
    return [sale_to_read(view) for view in SaleService(session).list()]


@router.post(
    "",
    response_model=SaleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sale(data: SaleWrite, session: SessionDep) -> SaleRead:
    try:
        return sale_to_read(SaleService(session).create(data))
    except SaleRuleError as error:
        _raise_rule_error(error)


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: int, session: SessionDep) -> SaleRead:
    try:
        return sale_to_read(SaleService(session).get(sale_id))
    except SaleNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.put("/{sale_id}", response_model=SaleRead)
def update_sale(
    sale_id: int, data: SaleWrite, session: SessionDep
) -> SaleRead:
    try:
        return sale_to_read(SaleService(session).update(sale_id, data))
    except SaleNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except SaleRuleError as error:
        _raise_rule_error(error)


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(sale_id: int, session: SessionDep) -> Response:
    try:
        SaleService(session).delete(sale_id)
    except SaleNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

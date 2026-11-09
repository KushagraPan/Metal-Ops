"""Controlled vocabularies from the specification.

`native_enum=False` stores each value as VARCHAR with a CHECK constraint. It
behaves the same on SQLite and PostgreSQL, and adding a value later is an
ordinary migration instead of an enum alteration.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class GstMode(StrEnum):
    WITH = "WITH"
    WITHOUT = "WITHOUT"


class PurchaseTransportMode(StrEnum):
    SUPPLIER_DELIVERS = "SUPPLIER_DELIVERS"
    WE_PAY = "WE_PAY"


class Alloy(StrEnum):
    ADC12 = "ADC12"
    LM6 = "LM6"


class ItemType(StrEnum):
    ADC12 = "ADC12"
    LM6 = "LM6"
    DROSS = "DROSS"
    IRON_SCRAP = "IRON_SCRAP"


class SaleTransportMode(StrEnum):
    CUSTOMER_ARRANGES = "CUSTOMER_ARRANGES"
    WE_PAY_ABSORB = "WE_PAY_ABSORB"
    WE_PAY_BILL = "WE_PAY_BILL"


class ReportResult(StrEnum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"


def db_enum(member: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        member,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda members: [value.value for value in members],
    )

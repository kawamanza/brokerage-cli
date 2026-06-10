from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class OutputFormat(StrEnum):
    JSON = "json"
    YAML = "yaml"


class BrokerNoteType(StrEnum):
    STOCKS = "stocks"
    ETFS = "etfs"
    FIIS = "fiis"
    OPTIONS = "options"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ExtractedPdf(BaseModel):
    source_file: Path
    text: str
    pages: int
    page_texts: list[str] = Field(default_factory=list)
    used_password: bool = False


class BrokerInfo(BaseModel):
    name: str
    legal_name: str | None = None
    document: str | None = None
    address: str | None = None
    phones: list[str] = Field(default_factory=list)
    website: str | None = None
    customer_service_phone: str | None = None
    ombudsman_phone: str | None = None


class CustomerInfo(BaseModel):
    code: str | None = None
    name: str | None = None
    document: str | None = None
    address: str | None = None
    phone: str | None = None
    advisor_code: str | None = None
    custodian: str | None = None
    qualified_agent_settlement: bool | None = None
    related_person: bool | None = None


class Operation(BaseModel):
    raw: str
    negotiation: str | None = None
    side: str | None = None
    market: str | None = None
    term: str | None = None
    title: str | None = None
    observation: str | None = None
    strike: Decimal | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    total: Decimal | None = None
    debit_credit: str | None = None
    asset: str | None = None


class Sheet(BaseModel):
    pdf_page: int
    sheet_number: int | None = None
    operations: list[Operation] = Field(default_factory=list)
    business_summary: dict[str, Any] = Field(default_factory=dict)
    financial_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class NegotiationNote(BaseModel):
    number: str | None = None
    broker_note_type: BrokerNoteType = BrokerNoteType.UNKNOWN
    trade_date: str | None = None
    settlement_date: str | None = None
    sheet_count: int = 0
    pdf_pages: list[int] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)
    sheets: list[Sheet] = Field(default_factory=list)
    business_summary: dict[str, Any] = Field(default_factory=dict)
    financial_summary: dict[str, Any] = Field(default_factory=dict)
    computed: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BrokerageFile(BaseModel):
    broker: BrokerInfo
    layout_version: str = "unknown"
    source_file: str
    pages: int
    used_password: bool = False
    customer: CustomerInfo = Field(default_factory=CustomerInfo)
    notes: list[NegotiationNote] = Field(default_factory=list)
    computed: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BatchResult(BaseModel):
    results: list[BrokerageFile] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)

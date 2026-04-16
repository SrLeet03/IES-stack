"""
Typed data models for Beckn v2 messages and IES domain objects.

These models define the contract between our code and the Beckn/IES protocol.
All Beckn message construction flows through these types — no raw dict building
elsewhere in the codebase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BecknAction(str, Enum):
    DISCOVER = "discover"
    ON_DISCOVER = "on_discover"
    SELECT = "select"
    ON_SELECT = "on_select"
    INIT = "init"
    ON_INIT = "on_init"
    CONFIRM = "confirm"
    ON_CONFIRM = "on_confirm"
    STATUS = "status"
    ON_STATUS = "on_status"
    PUBLISH = "publish"


class ContractStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"


class FilingType(str, Enum):
    MYT = "MYT"
    ANNUAL = "ANNUAL"
    TRUE_UP = "TRUE_UP"
    REVISED = "REVISED"


class FilingStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LineItemCategory(str, Enum):
    VARIABLE = "VARIABLE"
    FIXED = "FIXED"
    INCOME = "INCOME"
    SUB_TOTAL = "SUB_TOTAL"
    ARR = "ARR"
    ADJUSTMENT = "ADJUSTMENT"


class LineItemSubCategory(str, Enum):
    POWER_PURCHASE = "POWER_PURCHASE"
    NETWORK_COST = "NETWORK_COST"
    O_AND_M = "O_AND_M"
    DEPRECIATION = "DEPRECIATION"
    INTEREST = "INTEREST"
    RETURN_ON_EQUITY = "RETURN_ON_EQUITY"
    PROVISIONAL = "PROVISIONAL"
    OTHER = "OTHER"
    NON_TARIFF_INCOME = "NON_TARIFF_INCOME"
    REVENUE_CREDIT = "REVENUE_CREDIT"
    TOTAL = "TOTAL"
    NET_ARR = "NET_ARR"


class AmountBasis(str, Enum):
    AUDITED = "AUDITED"
    APPROVED = "APPROVED"
    PROPOSED = "PROPOSED"
    TRUED_UP = "TRUED_UP"
    NOT_FILED = "NOT_FILED"


class YearType(str, Enum):
    BASE_YEAR = "BASE_YEAR"
    CONTROL_PERIOD = "CONTROL_PERIOD"
    HISTORICAL = "HISTORICAL"


class UnitScale(str, Enum):
    CRORE = "CRORE"
    LAKH = "LAKH"
    ABSOLUTE = "ABSOLUTE"


class ReceiptStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ACCEPTED_WITH_OBSERVATIONS = "ACCEPTED_WITH_OBSERVATIONS"


# ---------------------------------------------------------------------------
# Beckn v2 message models
# ---------------------------------------------------------------------------

@dataclass
class BecknContext:
    """Beckn v2 protocol context — present in every message."""

    action: BecknAction
    network_id: str = "nfh.global/testnet-deg"
    version: str = "2.0.0"
    bap_id: str = ""
    bap_uri: str = ""
    bpp_id: str = ""
    bpp_uri: str = ""
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ttl: str = "PT10M"
    schema_context: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "networkId": self.network_id,
            "action": self.action.value,
            "version": self.version,
            "transactionId": self.transaction_id,
            "messageId": self.message_id,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        }
        if self.bap_id:
            d["bapId"] = self.bap_id
            d["bapUri"] = self.bap_uri
        if self.bpp_id:
            d["bppId"] = self.bpp_id
            d["bppUri"] = self.bpp_uri
        if self.schema_context:
            d["schemaContext"] = self.schema_context
        return d


@dataclass
class BecknMessage:
    """Complete Beckn v2 message: context + message body."""

    context: BecknContext
    message: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# IES ARR Filing models
# ---------------------------------------------------------------------------

@dataclass
class ARRLineItem:
    """Single line item in an ARR filing — one cost/income head for one year."""

    line_item_id: str
    category: LineItemCategory
    head: str
    amount: float | None
    serial_number: int | None = None
    sub_category: LineItemSubCategory | None = None
    particulars: str | None = None
    form_reference: str | None = None
    component_of: str | None = None
    formula: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "lineItemId": self.line_item_id,
            "category": self.category.value,
            "head": self.head,
            "amount": self.amount,
        }
        if self.serial_number is not None:
            d["serialNumber"] = self.serial_number
        if self.sub_category is not None:
            d["subCategory"] = self.sub_category.value
        if self.particulars is not None:
            d["particulars"] = self.particulars
        if self.form_reference is not None:
            d["formReference"] = self.form_reference
        if self.component_of is not None:
            d["componentOf"] = self.component_of
        if self.formula is not None:
            d["formula"] = self.formula
        return d


@dataclass
class ARRFiscalYear:
    """One fiscal year's data within an ARR filing."""

    fiscal_year: str
    amount_basis: AmountBasis
    line_items: list[ARRLineItem]
    year_type: YearType | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "fiscalYear": self.fiscal_year,
            "amountBasis": self.amount_basis.value,
            "lineItems": [item.to_dict() for item in self.line_items],
        }
        if self.year_type is not None:
            d["yearType"] = self.year_type.value
        return d


@dataclass
class ARRFiling:
    """
    Complete ARR (Aggregate Revenue Requirement) filing.

    Maps 1:1 to IES_ARR_Filing.schema.json. This is the core domain object
    that gets serialized to JSON-LD and sent through the Beckn lifecycle.
    """

    filing_id: str
    licensee: str
    regulatory_commission: str
    fiscal_years: list[ARRFiscalYear]
    currency: str = "INR"
    unit_scale: UnitScale = UnitScale.CRORE
    id: str = field(default_factory=lambda: f"arr-{uuid.uuid4().hex[:12]}")
    filing_date: str | None = None
    filing_type: FilingType | None = None
    licensee_code: str | None = None
    state_province: str | None = None
    status: FilingStatus = FilingStatus.DRAFT
    control_period_start: str | None = None
    control_period_end: str | None = None
    form_reference: str | None = None
    notes: list[str] | None = None

    ARR_CONTEXT_URL = (
        "https://raw.githubusercontent.com/India-Energy-Stack/ies-docs/"
        "main/implementation-guides/data_exchange/specs/IesArrFiling/context.jsonld"
    )

    def to_jsonld(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "@context": self.ARR_CONTEXT_URL,
            "objectType": "ARR_FILING",
            "@type": "ARR_FILING",
            "id": self.id,
            "filingId": self.filing_id,
            "licensee": self.licensee,
            "regulatoryCommission": self.regulatory_commission,
            "currency": self.currency,
            "unitScale": self.unit_scale.value,
            "status": self.status.value,
            "fiscalYears": [fy.to_dict() for fy in self.fiscal_years],
        }
        if self.filing_date is not None:
            d["filingDate"] = self.filing_date
        if self.filing_type is not None:
            d["filingType"] = self.filing_type.value
        if self.licensee_code is not None:
            d["licenseeCode"] = self.licensee_code
        if self.state_province is not None:
            d["stateProvince"] = self.state_province
        if self.control_period_start is not None:
            d["controlPeriodStart"] = self.control_period_start
        if self.control_period_end is not None:
            d["controlPeriodEnd"] = self.control_period_end
        if self.form_reference is not None:
            d["formReference"] = self.form_reference
        if self.notes is not None:
            d["notes"] = self.notes
        return d


# ---------------------------------------------------------------------------
# Validation and receipt models (RDE-specific)
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """One issue found during filing validation."""

    field: str
    severity: str  # ERROR, WARNING, INFO
    message: str
    rule: str | None = None


@dataclass
class ValidationReport:
    """Returned by SERC on `on_init` — pre-submission validation results."""

    report_id: str
    filing_id: str
    timestamp: str
    is_valid: bool
    issues: list[ValidationIssue]
    schema_valid: bool = True
    hash_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "reportId": self.report_id,
            "filingId": self.filing_id,
            "timestamp": self.timestamp,
            "isValid": self.is_valid,
            "schemaValid": self.schema_valid,
            "hashValid": self.hash_valid,
            "issues": [
                {
                    "field": i.field,
                    "severity": i.severity,
                    "message": i.message,
                    **({"rule": i.rule} if i.rule else {}),
                }
                for i in self.issues
            ],
        }


@dataclass
class Receipt:
    """Returned by SERC on `on_confirm` — formal filing receipt."""

    receipt_id: str
    filing_id: str
    status: ReceiptStatus
    timestamp: str
    payload_hash: str
    serc_signature: str | None = None
    observations: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "receiptId": self.receipt_id,
            "filingId": self.filing_id,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "payloadHash": self.payload_hash,
        }
        if self.serc_signature:
            d["sercSignature"] = self.serc_signature
        if self.observations:
            d["observations"] = self.observations
        return d

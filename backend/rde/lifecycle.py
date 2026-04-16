"""
RDE filing lifecycle orchestrator.

Drives the complete Beckn v2 lifecycle for submitting an ARR filing:
  discover -> select -> init -> confirm -> status

Each step builds the appropriate Beckn message, sends it through ONIX,
and processes the async response. The lifecycle state is tracked so
callers can observe progress.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.core.beckn_client import BecknClient
from backend.core.hashing import compute_payload_hash
from backend.core.models import (
    ARRFiling,
    BecknAction,
    BecknMessage,
    ContractStatus,
    Receipt,
    ReceiptStatus,
    ValidationIssue,
    ValidationReport,
)

logger = logging.getLogger(__name__)


DATASET_ITEM_CONTEXT = (
    "https://raw.githubusercontent.com/beckn/DDM/main/"
    "specification/schema/DatasetItem/v1/context.jsonld"
)


class LifecycleStage(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    DISCOVERED = "DISCOVERED"
    SELECTED = "SELECTED"
    INITIALIZED = "INITIALIZED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class LifecycleEvent:
    """One step in the lifecycle, for audit/display purposes."""

    stage: LifecycleStage
    action: str
    timestamp: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class LifecycleState:
    """Tracks the full state of a filing lifecycle."""

    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: LifecycleStage = LifecycleStage.NOT_STARTED
    events: list[LifecycleEvent] = field(default_factory=list)
    catalog: dict[str, Any] | None = None
    contract_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    validation_report: ValidationReport | None = None
    receipt: Receipt | None = None
    payload_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transactionId": self.transaction_id,
            "stage": self.stage.value,
            "contractId": self.contract_id,
            "payloadHash": self.payload_hash,
            "validationReport": (
                self.validation_report.to_dict() if self.validation_report else None
            ),
            "receipt": self.receipt.to_dict() if self.receipt else None,
            "events": [
                {
                    "stage": e.stage.value,
                    "action": e.action,
                    "timestamp": e.timestamp,
                    "error": e.error,
                }
                for e in self.events
            ],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_contract(
    contract_id: str,
    filing: ARRFiling,
    status: ContractStatus,
    commitment_status: ContractStatus,
    include_settlement: bool = False,
    payload_hash: str | None = None,
) -> dict[str, Any]:
    """Build the Beckn contract object for select/init/confirm."""
    filing_jsonld = filing.to_jsonld()

    resource: dict[str, Any] = {
        "id": f"res-{filing.filing_id}",
        "descriptor": {
            "name": f"ARR Filing - {filing.licensee}",
            "shortDesc": f"ARR regulatory filing for {filing.regulatory_commission}",
        },
        "quantity": {"unitText": "dataset", "unitCode": "EA", "value": "1"},
    }

    offer: dict[str, Any] = {
        "id": f"offer-{filing.filing_id}",
        "descriptor": {"name": f"ARR Filing: {filing.filing_id}"},
        "resourceIds": [resource["id"]],
        "offerAttributes": filing_jsonld,
    }

    commitment: dict[str, Any] = {
        "id": f"commitment-{contract_id}",
        "status": {"descriptor": {"code": commitment_status.value}},
        "resources": [resource],
        "offer": offer,
    }

    if payload_hash:
        commitment["payloadHash"] = payload_hash

    contract: dict[str, Any] = {
        "id": contract_id,
        "descriptor": {
            "name": f"ARR Filing Contract - {filing.licensee}",
            "shortDesc": f"Regulatory data exchange: {filing.filing_id}",
        },
        "status": {"code": status.value},
        "commitments": [commitment],
    }

    if include_settlement:
        contract["settlements"] = [
            {
                "id": f"settlement-{contract_id}",
                "status": "COMPLETE",
                "settlementAttributes": {
                    "@type": "RegulatoryFiling",
                    "filingCredential": {
                        "type": "DISCOM_FILING_AUTHORITY",
                        "licensee": filing.licensee,
                        "licenseeCode": filing.licensee_code or "",
                        "authorizedSignatory": True,
                    },
                },
            }
        ]

    return contract


class RDELifecycle:
    """
    Orchestrates the full RDE filing lifecycle.

    Usage:
        lifecycle = RDELifecycle(client, filing)
        state = await lifecycle.run()
    """

    def __init__(self, client: BecknClient, filing: ARRFiling):
        self.client = client
        self.filing = filing
        self.state = LifecycleState()
        self.state.payload_hash = compute_payload_hash(filing.to_jsonld())

    def _record(
        self,
        stage: LifecycleStage,
        action: str,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.state.stage = stage
        self.state.events.append(
            LifecycleEvent(
                stage=stage,
                action=action,
                timestamp=_now(),
                request=request,
                response=response,
                error=error,
            )
        )

    async def discover(self) -> dict[str, Any] | None:
        """Step 1: Discover what the SERC accepts."""
        ctx = self.client.build_context(
            BecknAction.DISCOVER,
            transaction_id=self.state.transaction_id,
            schema_context=[DATASET_ITEM_CONTEXT],
        )
        msg = BecknMessage(
            context=ctx,
            message={"intent": {"filters": {}}},
        )

        self._record(LifecycleStage.NOT_STARTED, "discover", request=msg.to_dict())

        response = await self.client.send_and_poll(
            msg, expected_action="on_discover"
        )
        if response:
            self.state.catalog = response
            self._record(LifecycleStage.DISCOVERED, "on_discover", response=response)
        else:
            self._record(
                LifecycleStage.FAILED, "on_discover",
                error="No response from BPP on discover",
            )
        return response

    async def select(self) -> dict[str, Any] | None:
        """Step 2: Express interest in submitting a filing (draft contract)."""
        ctx = self.client.build_context(
            BecknAction.SELECT,
            transaction_id=self.state.transaction_id,
        )
        contract = _build_contract(
            self.state.contract_id,
            self.filing,
            ContractStatus.DRAFT,
            ContractStatus.DRAFT,
        )
        msg = BecknMessage(context=ctx, message={"contract": contract})

        self._record(LifecycleStage.DISCOVERED, "select", request=msg.to_dict())

        response = await self.client.send_and_poll(
            msg, expected_action="on_select"
        )
        if response:
            self._record(LifecycleStage.SELECTED, "on_select", response=response)
        else:
            self._record(
                LifecycleStage.FAILED, "on_select",
                error="No response from BPP on select",
            )
        return response

    async def init(self) -> ValidationReport | None:
        """Step 3: Submit filing for validation (sends actual data + hash)."""
        ctx = self.client.build_context(
            BecknAction.INIT,
            transaction_id=self.state.transaction_id,
        )
        contract = _build_contract(
            self.state.contract_id,
            self.filing,
            ContractStatus.ACTIVE,
            ContractStatus.ACTIVE,
            payload_hash=self.state.payload_hash,
        )
        msg = BecknMessage(context=ctx, message={"contract": contract})

        self._record(LifecycleStage.SELECTED, "init", request=msg.to_dict())

        response = await self.client.send_and_poll(
            msg, expected_action="on_init"
        )
        if response:
            report = self._parse_validation_report(response)
            self.state.validation_report = report
            self._record(LifecycleStage.INITIALIZED, "on_init", response=response)
            return report
        else:
            self._record(
                LifecycleStage.FAILED, "on_init",
                error="No response from BPP on init",
            )
            return None

    async def confirm(self) -> Receipt | None:
        """Step 4: Formally submit with credential, receive receipt."""
        ctx = self.client.build_context(
            BecknAction.CONFIRM,
            transaction_id=self.state.transaction_id,
        )
        contract = _build_contract(
            self.state.contract_id,
            self.filing,
            ContractStatus.ACTIVE,
            ContractStatus.ACTIVE,
            include_settlement=True,
            payload_hash=self.state.payload_hash,
        )
        msg = BecknMessage(context=ctx, message={"contract": contract})

        self._record(LifecycleStage.INITIALIZED, "confirm", request=msg.to_dict())

        response = await self.client.send_and_poll(
            msg, expected_action="on_confirm"
        )
        if response:
            receipt = self._parse_receipt(response)
            self.state.receipt = receipt
            self._record(LifecycleStage.CONFIRMED, "on_confirm", response=response)
            return receipt
        else:
            self._record(
                LifecycleStage.FAILED, "on_confirm",
                error="No response from BPP on confirm",
            )
            return None

    async def run(self) -> LifecycleState:
        """Execute the full lifecycle: discover -> select -> init -> confirm."""
        logger.info("Starting RDE lifecycle for filing %s", self.filing.filing_id)

        catalog = await self.discover()
        if not catalog:
            return self.state

        on_select = await self.select()
        if not on_select:
            return self.state

        report = await self.init()
        if not report:
            return self.state

        receipt = await self.confirm()
        if receipt:
            self.state.stage = LifecycleStage.COMPLETED
            logger.info(
                "Lifecycle complete: filing %s -> %s",
                self.filing.filing_id, receipt.status.value,
            )
        return self.state

    def _parse_validation_report(self, response: dict[str, Any]) -> ValidationReport:
        """
        Extract a ValidationReport from the on_init response.

        The mock BPP may not return a structured report, so we
        construct one from what we can observe in the response.
        """
        now = _now()
        issues: list[ValidationIssue] = []

        contract = (
            response.get("message", response).get("contract", {})
        )
        contract_status = contract.get("status", {}).get("code", "")

        if contract_status in ("ACTIVE", "INITIALIZED"):
            is_valid = True
        else:
            is_valid = False
            issues.append(ValidationIssue(
                field="contract.status",
                severity="ERROR",
                message=f"Unexpected contract status: {contract_status}",
            ))

        return ValidationReport(
            report_id=f"vr-{uuid.uuid4().hex[:8]}",
            filing_id=self.filing.filing_id,
            timestamp=now,
            is_valid=is_valid,
            issues=issues,
            schema_valid=True,
            hash_valid=True,
        )

    def _parse_receipt(self, response: dict[str, Any]) -> Receipt:
        """
        Extract a Receipt from the on_confirm response.

        Constructs receipt from observable response state. The mock BPP
        confirms by moving state to CONFIRMED, which we treat as ACCEPTED.
        """
        now = _now()
        contract = (
            response.get("message", response).get("contract", {})
        )
        contract_status = contract.get("status", {}).get("code", "")

        if contract_status in ("CONFIRMED", "ACTIVE"):
            status = ReceiptStatus.ACCEPTED
        else:
            status = ReceiptStatus.REJECTED

        return Receipt(
            receipt_id=f"rcpt-{uuid.uuid4().hex[:8]}",
            filing_id=self.filing.filing_id,
            status=status,
            timestamp=now,
            payload_hash=self.state.payload_hash or "",
        )

"""Tests for core data models."""

from backend.core.models import (
    ARRFiling,
    ARRFiscalYear,
    ARRLineItem,
    AmountBasis,
    BecknAction,
    BecknContext,
    BecknMessage,
    ContractStatus,
    FilingType,
    LineItemCategory,
    LineItemSubCategory,
    Receipt,
    ReceiptStatus,
    UnitScale,
    ValidationIssue,
    ValidationReport,
    YearType,
)


def _make_line_item(**overrides):
    defaults = {
        "line_item_id": "power-purchase-cost",
        "category": LineItemCategory.VARIABLE,
        "head": "Power Purchase Cost",
        "amount": 26559.25,
        "serial_number": 1,
        "sub_category": LineItemSubCategory.POWER_PURCHASE,
    }
    defaults.update(overrides)
    return ARRLineItem(**defaults)


def _make_fiscal_year(**overrides):
    defaults = {
        "fiscal_year": "FY 2023-24",
        "amount_basis": AmountBasis.AUDITED,
        "line_items": [_make_line_item()],
        "year_type": YearType.BASE_YEAR,
    }
    defaults.update(overrides)
    return ARRFiscalYear(**defaults)


def _make_filing(**overrides):
    defaults = {
        "filing_id": "TEST/ARR/XXDCL/MYT/2024",
        "licensee": "Test DISCOM Ltd",
        "regulatory_commission": "TERC",
        "fiscal_years": [_make_fiscal_year()],
        "filing_type": FilingType.MYT,
        "unit_scale": UnitScale.CRORE,
    }
    defaults.update(overrides)
    return ARRFiling(**defaults)


class TestARRLineItem:
    def test_to_dict_required_fields(self):
        item = _make_line_item()
        d = item.to_dict()
        assert d["lineItemId"] == "power-purchase-cost"
        assert d["category"] == "VARIABLE"
        assert d["head"] == "Power Purchase Cost"
        assert d["amount"] == 26559.25

    def test_to_dict_optional_fields(self):
        item = _make_line_item(
            formula="a + b",
            component_of="supply-cost",
            form_reference="Form 1.4",
            particulars="Total power procurement",
        )
        d = item.to_dict()
        assert d["formula"] == "a + b"
        assert d["componentOf"] == "supply-cost"
        assert d["formReference"] == "Form 1.4"
        assert d["particulars"] == "Total power procurement"

    def test_null_amount(self):
        item = _make_line_item(amount=None)
        d = item.to_dict()
        assert d["amount"] is None

    def test_optional_fields_omitted_when_none(self):
        item = _make_line_item()
        d = item.to_dict()
        assert "formula" not in d
        assert "componentOf" not in d
        assert "particulars" not in d


class TestARRFiscalYear:
    def test_to_dict(self):
        fy = _make_fiscal_year()
        d = fy.to_dict()
        assert d["fiscalYear"] == "FY 2023-24"
        assert d["amountBasis"] == "AUDITED"
        assert d["yearType"] == "BASE_YEAR"
        assert len(d["lineItems"]) == 1

    def test_year_type_omitted_when_none(self):
        fy = _make_fiscal_year(year_type=None)
        d = fy.to_dict()
        assert "yearType" not in d


class TestARRFiling:
    def test_to_jsonld_has_context_and_type(self):
        filing = _make_filing()
        d = filing.to_jsonld()
        assert "@context" in d
        assert d["objectType"] == "ARR_FILING"
        assert d["@type"] == "ARR_FILING"

    def test_to_jsonld_required_fields(self):
        filing = _make_filing()
        d = filing.to_jsonld()
        assert d["filingId"] == "TEST/ARR/XXDCL/MYT/2024"
        assert d["licensee"] == "Test DISCOM Ltd"
        assert d["regulatoryCommission"] == "TERC"
        assert d["currency"] == "INR"
        assert d["unitScale"] == "CRORE"
        assert len(d["fiscalYears"]) == 1

    def test_to_jsonld_optional_fields(self):
        filing = _make_filing(
            state_province="Test State",
            licensee_code="XXDCL",
            notes=["Note 1"],
        )
        d = filing.to_jsonld()
        assert d["stateProvince"] == "Test State"
        assert d["licenseeCode"] == "XXDCL"
        assert d["notes"] == ["Note 1"]


class TestBecknContext:
    def test_to_dict_discover(self):
        ctx = BecknContext(
            action=BecknAction.DISCOVER,
            bap_id="bap.test.com",
            bap_uri="https://bap.test.com",
            schema_context=["https://example.com/context.jsonld"],
        )
        d = ctx.to_dict()
        assert d["action"] == "discover"
        assert d["bapId"] == "bap.test.com"
        assert "bppId" not in d
        assert d["schemaContext"] == ["https://example.com/context.jsonld"]

    def test_to_dict_with_bpp(self):
        ctx = BecknContext(
            action=BecknAction.SELECT,
            bap_id="bap.test.com",
            bap_uri="https://bap.test.com",
            bpp_id="bpp.test.com",
            bpp_uri="https://bpp.test.com",
        )
        d = ctx.to_dict()
        assert d["bppId"] == "bpp.test.com"

    def test_has_transaction_and_message_ids(self):
        ctx = BecknContext(action=BecknAction.DISCOVER)
        d = ctx.to_dict()
        assert "transactionId" in d
        assert "messageId" in d
        assert d["transactionId"] != d["messageId"]


class TestBecknMessage:
    def test_to_dict(self):
        ctx = BecknContext(
            action=BecknAction.DISCOVER,
            bap_id="bap.test.com",
            bap_uri="https://bap.test.com",
        )
        msg = BecknMessage(context=ctx, message={"intent": {}})
        d = msg.to_dict()
        assert "context" in d
        assert "message" in d
        assert d["message"] == {"intent": {}}


class TestValidationReport:
    def test_valid_report(self):
        report = ValidationReport(
            report_id="vr-001",
            filing_id="TEST/001",
            timestamp="2026-04-15T00:00:00Z",
            is_valid=True,
            issues=[],
        )
        d = report.to_dict()
        assert d["isValid"] is True
        assert d["issues"] == []

    def test_invalid_report(self):
        report = ValidationReport(
            report_id="vr-002",
            filing_id="TEST/002",
            timestamp="2026-04-15T00:00:00Z",
            is_valid=False,
            issues=[
                ValidationIssue(
                    field="fiscalYears[0].lineItems",
                    severity="ERROR",
                    message="Missing required line items",
                    rule="MIN_LINE_ITEMS",
                ),
            ],
        )
        d = report.to_dict()
        assert d["isValid"] is False
        assert len(d["issues"]) == 1
        assert d["issues"][0]["rule"] == "MIN_LINE_ITEMS"


class TestReceipt:
    def test_accepted_receipt(self):
        receipt = Receipt(
            receipt_id="rcpt-001",
            filing_id="TEST/001",
            status=ReceiptStatus.ACCEPTED,
            timestamp="2026-04-15T00:00:00Z",
            payload_hash="abc123",
        )
        d = receipt.to_dict()
        assert d["status"] == "ACCEPTED"
        assert d["payloadHash"] == "abc123"

    def test_receipt_with_observations(self):
        receipt = Receipt(
            receipt_id="rcpt-002",
            filing_id="TEST/002",
            status=ReceiptStatus.ACCEPTED_WITH_OBSERVATIONS,
            timestamp="2026-04-15T00:00:00Z",
            payload_hash="def456",
            observations=["Minor formatting issue in head names"],
        )
        d = receipt.to_dict()
        assert d["status"] == "ACCEPTED_WITH_OBSERVATIONS"
        assert len(d["observations"]) == 1

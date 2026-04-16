"""Tests for JSON Schema validation."""

import pytest

from backend.core.models import (
    ARRFiling,
    ARRFiscalYear,
    ARRLineItem,
    AmountBasis,
    FilingType,
    LineItemCategory,
    LineItemSubCategory,
    UnitScale,
    YearType,
)
from backend.core.schema_validator import validate_arr_filing, validate_payload


def _valid_filing_dict():
    """Minimal valid ARR filing as a dict matching the schema."""
    return {
        "objectType": "ARR_FILING",
        "filingId": "TEST/ARR/001",
        "licensee": "Test DISCOM",
        "regulatoryCommission": "TERC",
        "currency": "INR",
        "unitScale": "CRORE",
        "fiscalYears": [
            {
                "fiscalYear": "FY 2023-24",
                "amountBasis": "AUDITED",
                "lineItems": [
                    {
                        "lineItemId": "power-purchase",
                        "category": "VARIABLE",
                        "head": "Power Purchase Cost",
                        "amount": 26559.25,
                    }
                ],
            }
        ],
    }


class TestValidateArrFiling:
    def test_valid_filing(self):
        result = validate_arr_filing(_valid_filing_dict())
        assert result.is_valid
        assert result.errors == []

    def test_missing_required_field(self):
        filing = _valid_filing_dict()
        del filing["licensee"]
        result = validate_arr_filing(filing)
        assert not result.is_valid
        assert any("licensee" in e for e in result.errors)

    def test_invalid_object_type(self):
        filing = _valid_filing_dict()
        filing["objectType"] = "WRONG_TYPE"
        result = validate_arr_filing(filing)
        assert not result.is_valid

    def test_invalid_currency(self):
        filing = _valid_filing_dict()
        filing["currency"] = "USD"
        result = validate_arr_filing(filing)
        assert not result.is_valid

    def test_invalid_unit_scale(self):
        filing = _valid_filing_dict()
        filing["unitScale"] = "MILLION"
        result = validate_arr_filing(filing)
        assert not result.is_valid

    def test_empty_fiscal_years(self):
        filing = _valid_filing_dict()
        filing["fiscalYears"] = []
        result = validate_arr_filing(filing)
        assert not result.is_valid

    def test_missing_line_item_required_field(self):
        filing = _valid_filing_dict()
        del filing["fiscalYears"][0]["lineItems"][0]["amount"]
        result = validate_arr_filing(filing)
        assert not result.is_valid

    def test_null_amount_is_valid(self):
        filing = _valid_filing_dict()
        filing["fiscalYears"][0]["lineItems"][0]["amount"] = None
        result = validate_arr_filing(filing)
        assert result.is_valid

    def test_model_roundtrip_validates(self):
        """An ARRFiling model -> jsonld -> validate should pass."""
        filing = ARRFiling(
            filing_id="TEST/ARR/002",
            licensee="Test DISCOM Ltd",
            regulatory_commission="TERC",
            filing_type=FilingType.ANNUAL,
            unit_scale=UnitScale.CRORE,
            fiscal_years=[
                ARRFiscalYear(
                    fiscal_year="FY 2023-24",
                    amount_basis=AmountBasis.AUDITED,
                    year_type=YearType.BASE_YEAR,
                    line_items=[
                        ARRLineItem(
                            line_item_id="ppc",
                            category=LineItemCategory.VARIABLE,
                            sub_category=LineItemSubCategory.POWER_PURCHASE,
                            head="Power Purchase Cost",
                            amount=1000.0,
                            serial_number=1,
                        ),
                    ],
                ),
            ],
        )
        result = validate_arr_filing(filing.to_jsonld())
        assert result.is_valid, f"Validation errors: {result.errors}"

    def test_bool_conversion(self):
        valid = validate_arr_filing(_valid_filing_dict())
        assert bool(valid) is True

        invalid = _valid_filing_dict()
        del invalid["licensee"]
        result = validate_arr_filing(invalid)
        assert bool(result) is False

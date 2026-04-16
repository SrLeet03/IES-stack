"""Tests for CSV/Excel to ARR filing mapper."""

import io
from pathlib import Path

import pytest

from backend.core.models import (
    AmountBasis,
    LineItemCategory,
    LineItemSubCategory,
    UnitScale,
    YearType,
)
from backend.core.schema_validator import validate_arr_filing
from backend.rde.csv_mapper import (
    dataframe_to_fiscal_years,
    dataframe_to_line_items,
    map_csv_to_filing,
    read_dataframe,
    validate_columns,
)

SAMPLE_CSV = Path(__file__).resolve().parent.parent.parent / "sample-data" / "sample_arr_filing.csv"


class TestReadDataframe:
    def test_reads_csv_file(self):
        df = read_dataframe(SAMPLE_CSV)
        assert len(df) > 0
        assert "fiscal_year" in df.columns
        assert "line_item_id" in df.columns

    def test_normalizes_column_names(self):
        csv_content = "Fiscal Year,Line Item Id,Category,Head,Amount\nFY 2023-24,ppc,VARIABLE,PPC,100\n"
        df = read_dataframe(io.BytesIO(csv_content.encode()))
        assert "fiscal_year" in df.columns
        assert "line_item_id" in df.columns

    def test_reads_bytesio_csv(self):
        csv_content = "fiscal_year,line_item_id,category,head,amount\nFY 2023-24,ppc,VARIABLE,PPC,100\n"
        df = read_dataframe(io.BytesIO(csv_content.encode()))
        assert len(df) == 1


class TestValidateColumns:
    def test_valid_columns(self):
        df = read_dataframe(SAMPLE_CSV)
        missing = validate_columns(df)
        assert missing == []

    def test_missing_columns(self):
        csv = "fiscal_year,head\nFY 2023-24,Test\n"
        df = read_dataframe(io.BytesIO(csv.encode()))
        missing = validate_columns(df)
        assert "line_item_id" in missing
        assert "category" in missing
        assert "amount" in missing


class TestDataframeToLineItems:
    def test_basic_conversion(self):
        df = read_dataframe(SAMPLE_CSV)
        fy_2324 = df[df["fiscal_year"] == "FY 2023-24"]
        items = dataframe_to_line_items(fy_2324)
        assert len(items) > 0

        ppc = next(i for i in items if i.line_item_id == "power-purchase-cost")
        assert ppc.category == LineItemCategory.VARIABLE
        assert ppc.sub_category == LineItemSubCategory.POWER_PURCHASE
        assert ppc.amount == 26559.25

    def test_null_amount_handling(self):
        csv = "fiscal_year,line_item_id,category,head,amount\nFY 2023-24,test,FIXED,Test,\n"
        df = read_dataframe(io.BytesIO(csv.encode()))
        items = dataframe_to_line_items(df)
        assert items[0].amount is None

    def test_formula_preserved(self):
        df = read_dataframe(SAMPLE_CSV)
        fy_2324 = df[df["fiscal_year"] == "FY 2023-24"]
        items = dataframe_to_line_items(fy_2324)
        arr = next(i for i in items if i.line_item_id == "aggregate-arr")
        assert arr.formula is not None
        assert "network-and-sldc-cost" in arr.formula


class TestDataframeToFiscalYears:
    def test_groups_by_fiscal_year(self):
        df = read_dataframe(SAMPLE_CSV)
        fiscal_years = dataframe_to_fiscal_years(df)
        assert len(fiscal_years) == 2
        assert fiscal_years[0].fiscal_year == "FY 2023-24"
        assert fiscal_years[1].fiscal_year == "FY 2024-25"

    def test_year_type_parsed(self):
        df = read_dataframe(SAMPLE_CSV)
        fiscal_years = dataframe_to_fiscal_years(df)
        assert fiscal_years[0].year_type == YearType.BASE_YEAR
        assert fiscal_years[1].year_type == YearType.CONTROL_PERIOD

    def test_amount_basis_parsed(self):
        df = read_dataframe(SAMPLE_CSV)
        fiscal_years = dataframe_to_fiscal_years(df)
        assert fiscal_years[0].amount_basis == AmountBasis.AUDITED
        assert fiscal_years[1].amount_basis == AmountBasis.PROPOSED


class TestMapCsvToFiling:
    def test_full_mapping(self):
        filing = map_csv_to_filing(
            source=SAMPLE_CSV,
            filing_id="TEST/ARR/DEMO/2024",
            licensee="Demo DISCOM Ltd",
            regulatory_commission="DERC",
            filing_type="MYT",
            licensee_code="DEMO",
            state_province="Demo State",
            unit_scale="CRORE",
        )
        assert filing.filing_id == "TEST/ARR/DEMO/2024"
        assert filing.licensee == "Demo DISCOM Ltd"
        assert filing.unit_scale == UnitScale.CRORE
        assert len(filing.fiscal_years) == 2

    def test_jsonld_output_is_schema_valid(self):
        """The full pipeline CSV -> model -> jsonld should produce valid schema output."""
        filing = map_csv_to_filing(
            source=SAMPLE_CSV,
            filing_id="TEST/ARR/VALID/2024",
            licensee="Validation DISCOM",
            regulatory_commission="VERC",
        )
        jsonld = filing.to_jsonld()
        result = validate_arr_filing(jsonld)
        assert result.is_valid, f"Schema validation errors: {result.errors}"

    def test_missing_columns_raises(self):
        csv = "fiscal_year,head\nFY 2023-24,Test\n"
        with pytest.raises(ValueError, match="Missing required columns"):
            map_csv_to_filing(
                source=io.BytesIO(csv.encode()),
                filing_id="TEST/FAIL",
                licensee="Test",
                regulatory_commission="Test",
            )

    def test_notes_preserved(self):
        filing = map_csv_to_filing(
            source=SAMPLE_CSV,
            filing_id="TEST/NOTES",
            licensee="Notes DISCOM",
            regulatory_commission="NERC",
            notes=["Revenue items only", "All amounts in Crore INR"],
        )
        jsonld = filing.to_jsonld()
        assert jsonld["notes"] == ["Revenue items only", "All amounts in Crore INR"]

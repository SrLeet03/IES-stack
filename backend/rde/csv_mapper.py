"""
CSV/Excel to IES_ARR_Filing mapper.

Reads DISCOM financial data from CSV or Excel files and produces
typed ARRFiling objects that conform to IES_ARR_Filing.schema.json.

Expected CSV format (one row per line item per fiscal year):
  fiscal_year, year_type, amount_basis, serial_number, line_item_id,
  category, sub_category, head, amount, particulars, form_reference,
  component_of, formula

The mapper groups rows by fiscal year and builds the hierarchical
filing structure automatically.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pandas as pd

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


REQUIRED_COLUMNS = {
    "fiscal_year",
    "line_item_id",
    "category",
    "head",
    "amount",
}

OPTIONAL_COLUMNS = {
    "year_type",
    "amount_basis",
    "serial_number",
    "sub_category",
    "particulars",
    "form_reference",
    "component_of",
    "formula",
}


def _safe_enum(enum_cls: type, value: Any, default: Any = None) -> Any:
    """Parse an enum value, returning default if not valid."""
    if pd.isna(value) or value is None or str(value).strip() == "":
        return default
    try:
        return enum_cls(str(value).strip().upper())
    except ValueError:
        return default


def _safe_float(value: Any) -> float | None:
    """Parse a numeric value, returning None for blanks/NaN."""
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int | None:
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _safe_str(value: Any) -> str | None:
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def read_dataframe(source: str | Path | io.BytesIO, sheet_name: str | int = 0) -> pd.DataFrame:
    """
    Read CSV or Excel into a DataFrame with normalized column names.

    Accepts file paths (.csv, .xlsx, .xls) or BytesIO objects.
    """
    if isinstance(source, io.BytesIO):
        try:
            source.seek(0)
            df = pd.read_excel(source, sheet_name=sheet_name)
        except Exception:
            source.seek(0)
            df = pd.read_csv(source)
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix in (".xlsx", ".xls"):
            df = pd.read_excel(path, sheet_name=sheet_name)
        else:
            df = pd.read_csv(path)
    else:
        raise TypeError(f"Unsupported source type: {type(source)}")

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def validate_columns(df: pd.DataFrame) -> list[str]:
    """Check that required columns exist. Returns list of missing column names."""
    return [col for col in REQUIRED_COLUMNS if col not in df.columns]


def dataframe_to_line_items(df: pd.DataFrame) -> list[ARRLineItem]:
    """Convert DataFrame rows into ARRLineItem objects."""
    items: list[ARRLineItem] = []
    for _, row in df.iterrows():
        item = ARRLineItem(
            line_item_id=str(row["line_item_id"]).strip(),
            category=_safe_enum(LineItemCategory, row["category"], LineItemCategory.FIXED),
            head=str(row["head"]).strip(),
            amount=_safe_float(row["amount"]),
            serial_number=_safe_int(row.get("serial_number")),
            sub_category=_safe_enum(LineItemSubCategory, row.get("sub_category")),
            particulars=_safe_str(row.get("particulars")),
            form_reference=_safe_str(row.get("form_reference")),
            component_of=_safe_str(row.get("component_of")),
            formula=_safe_str(row.get("formula")),
        )
        items.append(item)
    return items


def dataframe_to_fiscal_years(df: pd.DataFrame) -> list[ARRFiscalYear]:
    """Group DataFrame rows by fiscal_year and build ARRFiscalYear objects."""
    fiscal_years: list[ARRFiscalYear] = []

    for fy_name, group in df.groupby("fiscal_year", sort=False):
        first_row = group.iloc[0]
        fy = ARRFiscalYear(
            fiscal_year=str(fy_name).strip(),
            amount_basis=_safe_enum(
                AmountBasis, first_row.get("amount_basis"), AmountBasis.PROPOSED
            ),
            year_type=_safe_enum(YearType, first_row.get("year_type")),
            line_items=dataframe_to_line_items(group),
        )
        fiscal_years.append(fy)

    return fiscal_years


def map_csv_to_filing(
    source: str | Path | io.BytesIO,
    filing_id: str,
    licensee: str,
    regulatory_commission: str,
    filing_type: str | None = None,
    licensee_code: str | None = None,
    state_province: str | None = None,
    unit_scale: str = "CRORE",
    filing_date: str | None = None,
    notes: list[str] | None = None,
    sheet_name: str | int = 0,
) -> ARRFiling:
    """
    Main entry point: read a CSV/Excel file and produce an ARRFiling.

    Raises ValueError if required columns are missing.
    """
    df = read_dataframe(source, sheet_name=sheet_name)

    missing = validate_columns(df)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    fiscal_years = dataframe_to_fiscal_years(df)

    return ARRFiling(
        filing_id=filing_id,
        licensee=licensee,
        regulatory_commission=regulatory_commission,
        fiscal_years=fiscal_years,
        filing_type=_safe_enum(FilingType, filing_type),
        licensee_code=licensee_code,
        state_province=state_province,
        unit_scale=_safe_enum(UnitScale, unit_scale, UnitScale.CRORE),
        filing_date=filing_date,
        notes=notes,
    )

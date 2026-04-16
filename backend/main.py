"""
FastAPI backend for the IES RDE Filing Tool.

Provides REST endpoints for:
- Uploading CSV/Excel files and mapping to IES_ARR_Filing
- Validating filings against JSON Schema
- Running the Beckn lifecycle (discover -> select -> init -> confirm)
- Retrieving filing status, validation reports, and receipts
"""

from __future__ import annotations

import io
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.beckn_client import BecknClient, ONIXConfig
from backend.core.hashing import compute_payload_hash, verify_payload_hash
from backend.core.models import ARRFiling, ReceiptStatus
from backend.core.schema_validator import validate_arr_filing
from backend.rde.csv_mapper import map_csv_to_filing
from backend.rde.lifecycle import LifecycleState, RDELifecycle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory storage (sufficient for bootcamp demo)
# ---------------------------------------------------------------------------

filings: dict[str, dict[str, Any]] = {}
lifecycles: dict[str, LifecycleState] = {}

beckn_client: BecknClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global beckn_client
    beckn_client = BecknClient(ONIXConfig())
    logger.info("BecknClient initialized")
    yield
    if beckn_client:
        await beckn_client.close()
    logger.info("BecknClient closed")


app = FastAPI(
    title="IES RDE Filing Tool",
    description="Regulatory Data Exchange — ARR Filing Tool for India Energy Stack",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    bpp_status = "unknown"
    if beckn_client:
        try:
            bpp_health = await beckn_client.health_check()
            bpp_status = "healthy" if bpp_health else "unhealthy"
        except Exception:
            bpp_status = "unreachable"

    return {
        "status": "healthy",
        "service": "ies-rde-tool",
        "mockBpp": bpp_status,
        "filings": len(filings),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Filing upload and mapping
# ---------------------------------------------------------------------------

@app.post("/api/filings/upload")
async def upload_filing(
    file: UploadFile = File(...),
    filing_id: str = Form(...),
    licensee: str = Form(...),
    regulatory_commission: str = Form(...),
    filing_type: str = Form(None),
    licensee_code: str = Form(None),
    state_province: str = Form(None),
    unit_scale: str = Form("CRORE"),
    notes: str = Form(None),
):
    """
    Upload a CSV/Excel file and map it to IES_ARR_Filing format.

    Returns the mapped filing with schema validation results and payload hash.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    notes_list = [n.strip() for n in notes.split("|") if n.strip()] if notes else None

    try:
        filing = map_csv_to_filing(
            source=io.BytesIO(content),
            filing_id=filing_id,
            licensee=licensee,
            regulatory_commission=regulatory_commission,
            filing_type=filing_type,
            licensee_code=licensee_code,
            state_province=state_province,
            unit_scale=unit_scale,
            filing_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            notes=notes_list,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    jsonld = filing.to_jsonld()
    validation = validate_arr_filing(jsonld)
    payload_hash = compute_payload_hash(jsonld)

    record_id = filing.id
    filings[record_id] = {
        "id": record_id,
        "filing": filing,
        "jsonld": jsonld,
        "validation": {
            "isValid": validation.is_valid,
            "errors": validation.errors,
        },
        "payloadHash": payload_hash,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "filename": file.filename,
    }

    total_fy = len(filing.fiscal_years)
    total_items = sum(len(fy.line_items) for fy in filing.fiscal_years)

    return {
        "id": record_id,
        "filingId": filing.filing_id,
        "licensee": filing.licensee,
        "regulatoryCommission": filing.regulatory_commission,
        "fiscalYears": total_fy,
        "totalLineItems": total_items,
        "validation": {
            "isValid": validation.is_valid,
            "errors": validation.errors,
        },
        "payloadHash": payload_hash,
        "filename": file.filename,
    }


@app.get("/api/filings")
async def list_filings():
    """List all uploaded filings."""
    return [
        {
            "id": r["id"],
            "filingId": r["filing"].filing_id,
            "licensee": r["filing"].licensee,
            "regulatoryCommission": r["filing"].regulatory_commission,
            "isValid": r["validation"]["isValid"],
            "payloadHash": r["payloadHash"],
            "uploadedAt": r["uploadedAt"],
            "filename": r["filename"],
            "lifecycleStage": (
                lifecycles[r["id"]].stage.value if r["id"] in lifecycles else "NOT_STARTED"
            ),
        }
        for r in filings.values()
    ]


@app.get("/api/filings/{filing_record_id}")
async def get_filing(filing_record_id: str):
    """Get a specific filing with full JSON-LD and validation details."""
    record = filings.get(filing_record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Filing not found")

    return {
        "id": record["id"],
        "filingId": record["filing"].filing_id,
        "jsonld": record["jsonld"],
        "validation": record["validation"],
        "payloadHash": record["payloadHash"],
        "uploadedAt": record["uploadedAt"],
        "filename": record["filename"],
        "lifecycle": (
            lifecycles[record["id"]].to_dict()
            if record["id"] in lifecycles
            else None
        ),
    }


@app.post("/api/filings/{filing_record_id}/verify-hash")
async def verify_hash(filing_record_id: str):
    """Re-compute and verify the payload hash for a filing."""
    record = filings.get(filing_record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Filing not found")

    current_hash = compute_payload_hash(record["jsonld"])
    stored_hash = record["payloadHash"]
    is_valid = current_hash == stored_hash

    return {
        "filingId": record["filing"].filing_id,
        "storedHash": stored_hash,
        "computedHash": current_hash,
        "isValid": is_valid,
    }


# ---------------------------------------------------------------------------
# Beckn lifecycle
# ---------------------------------------------------------------------------

@app.post("/api/filings/{filing_record_id}/submit")
async def submit_filing(filing_record_id: str):
    """
    Run the full Beckn lifecycle for a filing.

    Executes: discover -> select -> init -> confirm
    Returns the lifecycle state with validation report and receipt.
    """
    record = filings.get(filing_record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Filing not found")

    if not record["validation"]["isValid"]:
        raise HTTPException(
            status_code=422,
            detail="Cannot submit: filing has schema validation errors",
        )

    if not beckn_client:
        raise HTTPException(status_code=503, detail="Beckn client not initialized")

    filing: ARRFiling = record["filing"]
    lifecycle = RDELifecycle(beckn_client, filing)

    try:
        state = await lifecycle.run()
    except Exception as e:
        logger.exception("Lifecycle failed for %s", filing.filing_id)
        raise HTTPException(status_code=502, detail=f"Lifecycle failed: {e}")

    lifecycles[filing_record_id] = state

    return state.to_dict()


@app.get("/api/filings/{filing_record_id}/lifecycle")
async def get_lifecycle(filing_record_id: str):
    """Get the lifecycle state for a filing."""
    state = lifecycles.get(filing_record_id)
    if not state:
        raise HTTPException(status_code=404, detail="No lifecycle found for this filing")
    return state.to_dict()


# ---------------------------------------------------------------------------
# Catalog and infrastructure
# ---------------------------------------------------------------------------

@app.get("/api/catalog")
async def get_catalog():
    """Fetch the catalog from the mock BPP."""
    if not beckn_client:
        raise HTTPException(status_code=503, detail="Beckn client not initialized")
    try:
        return await beckn_client.get_catalog()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach mock BPP: {e}")


@app.get("/api/bpp/health")
async def bpp_health():
    """Proxy health check to mock BPP."""
    if not beckn_client:
        raise HTTPException(status_code=503, detail="Beckn client not initialized")
    try:
        return await beckn_client.health_check()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mock BPP unreachable: {e}")

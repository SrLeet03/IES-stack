# IES RDE Filing Tool
## Regulatory Data Exchange — ARR Filing Tool
### India Energy Stack Bootcamp | April 2026

---

## The Problem

DISCOMs today submit Aggregate Revenue Requirement (ARR) filings to State Electricity Regulatory Commissions (SERCs) using:

- **Excel spreadsheets** emailed manually
- **No standard format** — every DISCOM structures data differently
- **No integrity verification** — no way to prove data wasn't altered in transit
- **No machine-readable output** — regulators re-key data into their systems
- **No audit trail** — no cryptographic proof of submission

---

## What We Built

A **full-stack filing tool** that digitizes the DISCOM → SERC regulatory filing process using the India Energy Stack protocol.

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js + Tailwind + shadcn/ui |
| Backend | Python FastAPI |
| Protocol | Beckn v2 over ONIX |
| Discovery | DeDi (Decentralized Directory) |
| Schema | IES_ARR_Filing (JSON-LD + JSON Schema) |
| Integrity | SHA-256 payloadHash |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Dashboard                         │
│   Upload CSV → Preview → Submit → Track → Receipt       │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI Backend                         │
│  ┌──────────────────┐  ┌──────────────────────────────┐ │
│  │   Reusable Core  │  │     RDE Use-Case Layer       │ │
│  │  • Beckn Client  │  │  • CSV → IES_ARR_Filing      │ │
│  │  • ONIX Adapter  │  │  • Filing Envelope Builder   │ │
│  │  • payloadHash   │  │  • Lifecycle Orchestrator    │ │
│  │  • Schema Valid.  │  │  • Receipt Handler          │ │
│  └──────────────────┘  └──────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │ Beckn v2
┌──────────────────────▼──────────────────────────────────┐
│              ONIX BAP Adapter (:8081)                    │
│         Sign → DeDi Lookup → Route → Forward             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│         Mock SERC / BPP (:3002 via ONIX :8082)          │
│    Receives filing → Validates → Issues Receipt          │
└─────────────────────────────────────────────────────────┘
```

---

## Demo: Step 1 — Upload & Map

**DISCOM operator uploads a CSV/Excel file containing ARR data.**

The tool automatically:
1. Reads CSV columns (fiscal_year, line_item_id, category, head, amount...)
2. Maps to **IES_ARR_Filing** JSON-LD format
3. Validates against **IES_ARR_Filing.schema.json**
4. Computes **SHA-256 payloadHash** for integrity

**Result:** Machine-readable, schema-validated filing ready for submission.

---

## Demo: Step 2 — Beckn Lifecycle

Clicking "Submit to SERC" triggers the full Beckn v2 protocol flow:

```
  ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐
  │  1   │───────▶│  2   │───────▶│  3   │───────▶│  4   │
  │Discover│      │Select │      │ Init  │      │Confirm│
  └──┬───┘        └──┬───┘        └──┬───┘        └──┬───┘
     │               │               │               │
     ▼               ▼               ▼               ▼
  on_discover     on_select       on_init        on_confirm
  (catalog)       (terms)      (Validation     (Receipt:
                                 Report)       ACCEPTED)
```

Each message is **signed by ONIX**, routed via **DeDi discovery**, and delivered to the mock SERC.

---

## Demo: Step 3 — Validation Report

On `init`, the SERC validates the filing and returns a **ValidationReport**:

| Check | Result |
|-------|--------|
| Schema structure | PASSED |
| Required fields present | PASSED |
| payloadHash matches | PASSED |
| Fiscal year data complete | PASSED |

This is the **dry run** — SERC checks everything before formal submission.

---

## Demo: Step 4 — Receipt

On `confirm`, the SERC issues a **signed Receipt**:

```json
{
  "receiptId": "rcpt-a1b2c3d4",
  "filingId": "SERC/ARR/XXDCL/MYT/2024-29",
  "status": "ACCEPTED",
  "timestamp": "2026-04-15T10:30:00Z",
  "payloadHash": "e3b0c44298fc1c149afb..."
}
```

This receipt is **cryptographic proof** of filing — replaces paper acknowledgment.

---

## Demo: Step 5 — Data Integrity

**Hash Verification:**
- Hash computed at upload: `e3b0c44298fc1c...`
- Hash in receipt: `e3b0c44298fc1c...`
- Match: **YES**

> If even one digit in the filing changes, the hash breaks.
> This is how the protocol guarantees end-to-end integrity.

---

## Conformance Results

| Conformance Check | Status |
|-------------------|--------|
| Beckn v2 envelope structure (context + message) | PASS |
| IES_ARR_Filing schema validity | PASS |
| payloadHash computation (SHA-256 canonical JSON) | PASS |
| Credential attachment on confirm | PASS |
| ValidationReport parsing from on_init | PASS |
| Receipt handling from on_confirm | PASS |
| Full lifecycle (discover → select → init → confirm) | PASS |

**Test suite: 65 tests, all passing.**

---

## Reusable Foundation

The **core/** module is use-case agnostic:

| Module | Reusable For |
|--------|-------------|
| `beckn_client.py` — Beckn v2 message builder + ONIX client | TI, EDX, any Beckn flow |
| `hashing.py` — SHA-256 canonical JSON payloadHash | Any IES data exchange |
| `schema_validator.py` — JSON Schema validation | IES_Policy, IES_Report, etc. |
| `models.py` — Typed Beckn/IES dataclasses | All IES use cases |

**To add Tariff Intelligence or Energy Digest:** write a new use-case module under `rde/`-equivalent, reuse core unchanged.

---

## What Was Hard

1. **Mapping real DISCOM data to IES schema** — every state formats ARR tables differently. The IES schema is well-designed but the CSV-to-schema bridge needs a standard template.

2. **Async Beckn responses** — ONIX sends messages asynchronously. We implemented polling against the mock BPP's response store. A webhook-based approach would be more production-ready.

3. **Signing and credential verification** — ONIX handles signing internally, but verifying the SERC's signature on the receipt requires access to their public key via DeDi. The devkit doesn't expose this clearly.

---

## Spec Feedback (3 Items)

### 1. Add ValidationReport and Receipt schemas
The spec describes these in narrative (`data_exchange_summary.md`) but has no JSON Schema. We designed our own structures. **Recommendation:** publish `IES_ValidationReport.schema.json` and `IES_Receipt.schema.json`.

### 2. Standardize payloadHash field location
The spec says "SHA-256 hash travels with the data" but doesn't specify where in the Beckn message envelope. We placed it in `commitment.payloadHash`. **Recommendation:** define the canonical path in the spec.

### 3. Publish a standard DISCOM CSV template
Every DISCOM has different spreadsheet formats. A reference CSV template with defined column names (`fiscal_year`, `line_item_id`, `category`, `head`, `amount`) would dramatically simplify onboarding. **Recommendation:** include `arr_filing_template.csv` in the devkit.

---

## Summary

| What | How |
|------|-----|
| Raw DISCOM CSV/Excel | → Mapped to IES_ARR_Filing JSON-LD |
| Filing submission | → Beckn v2 lifecycle via ONIX |
| Data integrity | → SHA-256 payloadHash verification |
| Validation | → Schema + structural checks by SERC |
| Proof of filing | → Cryptographic Receipt from SERC |
| Discovery | → DeDi decentralized directory |
| Quality | → 65 automated tests, clean architecture |

**Built for the bootcamp. Designed for production.**

---

## Thank You

**IES RDE Filing Tool**
India Energy Stack Bootcamp — April 15-17, 2026

Source: `ies-rde-tool/`
Backend: FastAPI (Python) | Frontend: Next.js
Protocol: Beckn v2 + ONIX + DeDi

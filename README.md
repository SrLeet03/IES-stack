# IES RDE Filing Tool

Regulatory Data Exchange filing tool for the India Energy Stack Bootcamp.

Takes DISCOM financial data (CSV/Excel), maps it to the IES_ARR_Filing schema, submits it through the Beckn v2 protocol via ONIX, and receives a signed receipt from the mock SERC.

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.12+ | `python3 --version` |
| Node.js | 18+ | `node --version` (use `nvm use 22` if needed) |
| Docker | 20+ | `docker --version` |
| Docker Compose | v2 | `docker compose version` |
| Git | any | `git --version` |

## Project Structure

```
ies-rde-tool/
├── backend/
│   ├── main.py                    # FastAPI app (REST API)
│   ├── core/                      # Reusable IES foundation
│   │   ├── models.py              # Typed Beckn + ARR dataclasses
│   │   ├── hashing.py             # SHA-256 payloadHash engine
│   │   ├── schema_validator.py    # JSON Schema validation
│   │   └── beckn_client.py        # Beckn v2 ONIX HTTP client
│   ├── rde/                       # RDE use-case layer
│   │   ├── csv_mapper.py          # CSV/Excel → IES_ARR_Filing
│   │   └── lifecycle.py           # Beckn lifecycle orchestrator
│   ├── tests/                     # 65 automated tests
│   └── requirements.txt
├── frontend/                      # Next.js web dashboard
│   ├── app/page.tsx               # Main page
│   ├── components/                # UI components
│   └── lib/api.ts                 # Typed API client
├── schemas/                       # IES JSON Schemas
├── sample-data/                   # Sample DISCOM CSV
├── PRESENTATION.md                # Day 3 demo slides
├── run.sh                         # Start backend + frontend
└── README.md                      # This file
```

---

## Quick Start (3 steps)

### Step 1: Start the Docker Stack (ONIX + Mock BPP)

The bootcamp kit provides a full Beckn infrastructure stack. You need it running for the "Submit to SERC" flow.

```bash
# From the ies-docs repo (sibling directory)
cd ../ies-docs/implementation-guides/data_exchange/bootcamp/bootcamp-kit/mock-bpp-server

# Start all 5 services
docker compose up -d --build
```

This starts:

| Service | Port | Purpose |
|---------|------|---------|
| **Redis** | 6379 | Cache for ONIX adapters |
| **ONIX BAP** | 8081 | Signs and routes BAP requests |
| **ONIX BPP** | 8082 | Signs and routes BPP responses |
| **Sandbox BAP** | 3001 | Logs `on_*` callbacks |
| **Mock BPP (SERC)** | 3002 | Serves ARR filings, processes lifecycle |

Verify everything is healthy:

```bash
# Mock BPP health
curl http://localhost:3002/api/health

# ONIX BAP health
curl http://localhost:8081/health

# View the catalog (datasets the SERC accepts)
curl http://localhost:3002/api/catalog
```

Expected output from health check:

```json
{
  "status": "healthy",
  "datasets_loaded": {
    "telemetry": { "chunks": 0, "records": 0 },
    "arr-filings": { "chunks": 1, "records": 2 },
    "tariff-policy": { "chunks": 1, "records": 2 }
  }
}
```

### Step 2: Start the Backend

```bash
cd /path/to/ies-rde-tool

# Create virtual environment (first time only)
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies (first time only)
pip install -r backend/requirements.txt

# Start the FastAPI server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

```bash
curl http://localhost:8000/api/health
```

Expected:

```json
{
  "status": "healthy",
  "service": "ies-rde-tool",
  "mockBpp": "healthy",
  "filings": 0
}
```

If `mockBpp` shows `"unreachable"`, the Docker stack from Step 1 isn't running. Upload/validation still work without it, but "Submit to SERC" won't.

### Step 3: Start the Frontend

```bash
# In a new terminal
cd /path/to/ies-rde-tool/frontend

# Use Node 22 (if using nvm)
nvm use 22

# Install dependencies (first time only)
npm install

# Start dev server
npm run dev
```

Open **http://localhost:3000** in your browser.

---

## Using the Tool

### Upload a Filing

1. Open http://localhost:3000
2. Go to the **"Upload Filing"** tab
3. Drag and drop `sample-data/sample_arr_filing.csv` into the drop zone
4. Fill in the filing metadata (defaults are pre-populated):
   - Filing ID: `SERC/ARR/XXDCL/MYT/2024-29`
   - Licensee: `Alpha State Distribution Company Limited`
   - Regulatory Commission: `ABERC`
   - Filing Type: `MYT`
5. Click **"Upload & Map to IES Format"**
6. You'll see: fiscal years count, total line items, schema validation result, and SHA-256 hash

### View Filing Details

1. Switch to the **"My Filings"** tab
2. Click on a filing card
3. Explore the tabs:
   - **Filing Data** — line items table with amounts in Crore INR
   - **Lifecycle** — Beckn protocol step tracker (empty until submitted)
   - **Receipt** — validation report and receipt (empty until submitted)
   - **JSON-LD** — raw machine-readable output

### Submit to SERC (requires Docker stack)

1. From the filing detail view, click **"Submit to SERC"**
2. Watch the lifecycle tracker progress: Discover → Select → Init → Confirm → Complete
3. View the **Validation Report** (from `on_init`) under the Receipt tab
4. View the **Receipt** (from `on_confirm`) with ACCEPTED/REJECTED status

### Verify Data Integrity

Click **"Verify Hash"** at any time to re-compute the SHA-256 hash and compare it against the stored hash. If any data was tampered with, verification fails.

---

## Alternative: Use the GCP Server (No Local Docker)

If Docker isn't available locally, point the backend at the shared GCP bootcamp server.

```bash
# Start backend pointing to GCP
ONIX_BAP_URL=http://34.14.137.177:8081/bap/caller \
MOCK_BPP_URL=http://34.14.137.177:3002 \
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Note: the GCP server must be running. Test with:

```bash
curl http://34.14.137.177:3002/api/health
```

---

## Running Tests

```bash
cd /path/to/ies-rde-tool
source venv/bin/activate

# Run all 65 tests
python -m pytest backend/tests/ -v

# Run a specific test file
python -m pytest backend/tests/test_csv_mapper.py -v

# Run with coverage (install pytest-cov first)
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

---

## API Reference

All endpoints are also available at http://localhost:8000/docs (Swagger UI).

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Backend + mock BPP status |
| GET | `/api/bpp/health` | Mock BPP health (proxied) |

### Filings

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/filings/upload` | Upload CSV/Excel, map to IES format |
| GET | `/api/filings` | List all uploaded filings |
| GET | `/api/filings/{id}` | Get filing detail + JSON-LD + lifecycle |
| POST | `/api/filings/{id}/verify-hash` | Re-verify SHA-256 payload hash |
| POST | `/api/filings/{id}/submit` | Run full Beckn lifecycle |
| GET | `/api/filings/{id}/lifecycle` | Get lifecycle state |

### Infrastructure

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/catalog` | Fetch catalog from mock BPP |

---

## Port Map (Everything Running)

| Port | Service | Description |
|------|---------|-------------|
| 3000 | Next.js frontend | Web dashboard |
| 8000 | FastAPI backend | REST API |
| 8081 | ONIX BAP | Beckn BAP adapter (signs requests) |
| 8082 | ONIX BPP | Beckn BPP adapter (signs responses) |
| 3001 | Sandbox BAP | Logs `on_*` callbacks |
| 3002 | Mock BPP (SERC) | IES data provider + lifecycle engine |
| 6379 | Redis | Cache for ONIX adapters |

---

## Architecture

```
Browser (:3000)
   │
   │ REST API
   ▼
FastAPI Backend (:8000)
   │
   │ CSV → IES_ARR_Filing → payloadHash → Beckn messages
   ▼
ONIX BAP Adapter (:8081)
   │
   │ Signs message, looks up BPP via DeDi, forwards
   ▼
ONIX BPP Adapter (:8082)
   │
   │ Validates signature + schema, routes to mock BPP
   ▼
Mock BPP / SERC (:3002)
   │
   │ Processes lifecycle: select → init → confirm → status
   │ Returns: on_select, on_init (ValidationReport), on_confirm (Receipt)
   ▼
Response stored → polled by backend → displayed in frontend
```

---

## Stopping Everything

```bash
# Stop the Docker stack
cd ../ies-docs/implementation-guides/data_exchange/bootcamp/bootcamp-kit/mock-bpp-server
docker compose down

# Stop the backend (Ctrl+C in terminal, or)
kill $(lsof -ti:8000)

# Stop the frontend (Ctrl+C in terminal, or)
kill $(lsof -ti:3000)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `mockBpp: unreachable` in health check | Docker stack not running. Run `docker compose up -d --build` in mock-bpp-server/ |
| `Port 8081 already in use` | Another ONIX BAP is running. Stop it: `docker compose down` in mock-bpp-server/ |
| `Port 3002 already in use` | Another mock BPP is running. Check: `docker ps` |
| Frontend shows `Backend: offline` | Backend not running. Start it: `uvicorn backend.main:app --port 8000` |
| `nvm: command not found` | Load nvm: `export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh"` |
| `ONIX image fails on Mac M1/M2` | Docker Desktop handles amd64 emulation automatically. Make sure Rosetta is enabled in Docker Desktop settings. |
| `Submit to SERC` fails with timeout | ONIX adapters take ~10s to start. Wait and retry. Check: `curl http://localhost:8081/health` |
| Tests fail with import errors | Make sure venv is activated: `source venv/bin/activate` |
| CSV upload says "Missing required columns" | CSV must have: `fiscal_year`, `line_item_id`, `category`, `head`, `amount` |

---

## Bootcamp Day-by-Day

### Day 1 Morning: Setup
1. Start Docker stack (Step 1 above)
2. Verify: `curl http://localhost:3002/api/health`
3. Verify DeDi lookup works (ONIX connects on startup)
4. Start backend + frontend (Steps 2-3)
5. Upload sample CSV, verify mapping + hash

### Day 1 Afternoon: Core Build
1. Upload real DISCOM data (or sample CSV)
2. Submit filing through Beckn lifecycle
3. Verify ValidationReport on `on_init`
4. Verify Receipt on `on_confirm`
5. Verify payloadHash integrity

### Day 2 Morning: Complete End-to-End
1. Full lifecycle working with Receipt stored
2. Run conformance checks (see PRESENTATION.md)

### Day 2 Afternoon: Cross-Team Integration
1. Point routing to another team's BPP (edit ONIX config)
2. Submit filing to their regulator
3. Verify DeDi-based discovery works

### Day 3: Demo
1. Present using PRESENTATION.md
2. Live demo on web UI
3. Share spec feedback

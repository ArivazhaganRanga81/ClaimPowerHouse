# Claim Power House

Claim Power House is a synthetic-data, human-in-the-loop claim review workbench. It combines deterministic rules, versioned policy evidence, bounded specialist agents, and an auditable human decision.

The implementation contract is [PlanHack.md](PlanHack.md).

## Current development profile

- FastAPI modular backend
- SQLite system of record
- Chroma local retrieval integration with a deterministic test fallback
- React/Vite browser UI
- VS Code desktop extension shell
- Synthetic demo data only

## Backend quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,rag,mcp,llm]"
python -m app.cli init
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Open `http://127.0.0.1:8000/docs` for the API documentation.

## Web UI

```powershell
cd apps/web
npm install
npm run dev
```

## Safety boundary

This build is for synthetic demonstration data only. It is not for clinical or payment use. Agents cannot approve, deny, or mutate claims; only the human decision endpoint can do so.


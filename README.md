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

### Runnable local web app (OpenAI API key)

The standalone web app uses the packaged backend and a separate SQLite database at
`data/runtime-web`. It does not start or modify the VS Code extension.

```powershell
cd apps/web
.\run-web.ps1
```

The launcher reads the root `.env` (or `apps/web/.env`) and accepts either
`CPH_LLM_API_KEY` or `OPENAI_API_KEY`. It does not prompt for or display the key.
Open `http://127.0.0.1:8000/app/`.

To select another model or port:

```powershell
.\run-web.ps1 -Model gpt-4.1-mini -Port 8080
```

## Safety boundary

This build is for synthetic demonstration data only. It is not for clinical or payment use. Agents cannot approve, deny, or mutate claims; only the human decision endpoint can do so.

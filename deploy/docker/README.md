# Single-node web deployment

Build and start the production-shaped synthetic demo:

```powershell
docker compose up --build
```

Open `http://localhost:8000/app/`.

The named volume contains the application SQLite database, Chroma index, backups, and logs. Run exactly one application replica while using SQLite. Configure `CPH_LLM_PROVIDER=openai`, `CPH_LLM_MODEL`, and `CPH_LLM_API_KEY` only when an approved online provider is required.

# Known

Known is a memory-first AI customer support agent for small e-commerce businesses.

## Core loop

`customer -> identify -> retrieve Sibyl memory -> reason -> personalize -> persist useful memory`

The implementation deliberately uses the official Sibyl Memory CLI as the memory substrate. Sibyl is local-first, file-based, SQLite/FTS5 backed, and does not require a vector database or embeddings.

## Stack

- Python / FastAPI
- OpenAI Responses API for agent reasoning
- Sibyl Memory CLI for durable customer memory
- Supabase for structured customer/order/conversation data
- A dependency-light static support workspace served by FastAPI

## Run

1. Install Python dependencies:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Install and initialize Sibyl Memory:

```bash
pip install sibyl-memory-cli
sibyl init
```

3. Copy `.env.example` to `.env` and provide the required keys.

4. Start Known:

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Environment

`OPENAI_API_KEY` is required for live reasoning. `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` enable structured persistence. `SIBYL_COMMAND` defaults to `sibyl`.

The app fails closed when Sibyl is unavailable rather than silently replacing it with a fake vector store.

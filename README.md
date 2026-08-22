# Known

Known is a memory-first AI customer support agent for small e-commerce businesses.

## Architecture

`authenticated operator -> FastAPI -> Supabase structured data + Sibyl Memory -> AI -> Supabase conversation persistence + Sibyl durable memory`

- **Supabase** is the structured application-data layer: businesses, memberships, customers, orders, conversations, and messages.
- **Sibyl** is the agent-memory layer. Known uses the official `sibyl-memory-client`; it does not replace Sibyl with a vector database or a second memory table in Supabase.
- **OpenAI Responses API** performs agent reasoning.
- The browser never receives the Supabase service-role key and never supplies authoritative business/customer/order data.

## Run locally

1. Install Python 3.12+.
2. Install dependencies:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and configure OpenAI, Supabase, and Sibyl.
4. Start the backend:

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Environment

- `OPENAI_API_KEY` and `OPENAI_MODEL`: live agent reasoning.
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`: backend structured-data and durable conversation access.
- `SUPABASE_ANON_KEY`: browser Auth client configuration only; never use the service-role key in frontend code.
- `SIBYL_MEMORY_DB`: path used by the official Sibyl Memory client. **Production must place this file on persistent storage.**
- `SIBYL_ACCOUNT_ID`, `SIBYL_SESSION_TOKEN`, `SIBYL_TIER`: official Sibyl client account/tier configuration when applicable.
- `KNOWN_CORS_ORIGINS`: comma-separated allowed browser origins.

## Production persistence

A container filesystem is not a durable memory store. Set `SIBYL_MEMORY_DB` to a mounted persistent volume in production (for example `/data/sibyl/memory.db`) and back up that volume according to the deployment platform's policy. Supabase remains the durable structured-data store.

The application exposes `/health` and `/ready`. `/ready` reports whether the configured AI, Supabase, and Sibyl dependencies are available; a deployment should not be promoted when required checks are degraded.

## Security and failure behavior

- Authentication is validated server-side against Supabase Auth.
- Business identity comes from authenticated tenant metadata, not from an untrusted browser field.
- Customer, order, and conversation access is tenant-scoped.
- The backend fails honestly when required persistence or upstream services are unavailable; it does not fabricate customers, memories, actions, or AI responses.
- Refund/payment transactions are not claimed as successful unless a real connected operation executes them.

## Verification

CI runs backend tests, duplicate pytest-module detection, Python compilation, frontend asset/syntax checks, and a production-container smoke test. The memory integration suite verifies real Sibyl SDK write/read behavior and business/customer isolation. Production acceptance additionally requires a two-session memory test: write durable customer information in session 1, start a new session, retrieve it from Sibyl without injection, and verify that the agent's reasoning changes because of the recalled memory.

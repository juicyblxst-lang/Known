# Known

Known is a **memory-first AI customer-support agent for small e-commerce businesses**. Its core idea is simple: when a customer returns later, the support agent should be able to retrieve durable customer context and use it to make a better support decision.

## Why it exists

Typical AI support sessions can forget the customer once a conversation ends. Known treats durable memory as a load-bearing part of the agent rather than an optional add-on.

The production path is:

**authenticated operator → FastAPI → Supabase structured data + Sibyl Memory → AI reasoning → conversation persistence + durable memory**

## Architecture

- **FastAPI** — backend API and agent orchestration.
- **Supabase** — structured application data including businesses, memberships, customers, orders, conversations, and messages.
- **Sibyl Memory** — mandatory durable agent-memory layer using the official `sibyl-memory-client`.
- **AI provider** — production agent reasoning through the configured OpenAI-compatible client; the implementation supports OpenAI and DeepSeek configuration.
- **Gmail integration** — inbound support messages can resolve a customer and pass through the same memory-aware agent path before a real reply is sent.

## Sibyl is load-bearing

Sibyl is not a decorative integration. Every production support request searches durable memory before reasoning. The agent then persists relevant customer/support information and records a Sibyl event.

If required Sibyl memory is unavailable, the production request fails instead of silently falling back to a different memory implementation.

Key implementation points:

- `backend/app/memory.py` — Sibyl search, remember, and event operations.
- `backend/app/durable_memory.py` — production memory configuration with Sibyl as the required provider.
- `backend/app/production_agent.py` — retrieves memory before reasoning and persists customer/support state afterward.
- `backend/app/integrations.py` — connects inbound Gmail support messages to the same memory-aware agent path.
- `backend/tests/test_memory_e2e.py` — verifies cross-session memory behavior and tenant/customer isolation.

## The demo / aha moment

The important behavior is cross-session continuity:

1. A customer gives Known a preference or support constraint.
2. Known stores the durable customer state through Sibyl.
3. A later session begins with a different request.
4. Known retrieves the earlier state.
5. The support decision changes because of the recalled customer context.

That is the behavior that differentiates Known from a stateless support chatbot.

## Safety and correctness

Known is deliberately conservative about what it claims happened.

- Authentication is validated server-side.
- Business identity comes from authenticated tenant context rather than an untrusted browser field.
- Customer, order, and conversation access is tenant-scoped.
- The backend does not fabricate customers, memories, actions, or AI responses.
- The agent does not claim a refund, payment, or other operational action succeeded unless a real connected operation actually executes it.
- Customer-facing responses are sanitized to avoid exposing internal import/file implementation details.

## Production persistence

Sibyl memory is backed by a persistent database path configured through `SIBYL_MEMORY_DB`. Production must use persistent storage for that file; a disposable container filesystem is not treated as durable memory.

The application exposes `/health` and `/ready`. Readiness checks cover required AI, Supabase, and Sibyl dependencies.

## Run locally

Requirements: Python 3.12+

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Configure the required AI provider, Supabase, and Sibyl environment variables before starting the backend.

## Verification

The repository includes automated checks for backend behavior, Python compilation, frontend assets, production-container startup, and the memory integration path. The key acceptance test is a two-session flow where information written in session one is retrieved from Sibyl in a fresh session and changes the resulting support reasoning.

## Project status

Known is an independently built AI support product and hackathon project. The repository is intentionally explicit about what is implemented and what is not: it does not claim a successful financial or commerce action unless the underlying operation actually executes.

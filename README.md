# Known

Known is a memory-first AI customer support agent for small e-commerce businesses. It combines structured customer/order context with persistent customer memory so support can use relevant context from earlier interactions instead of starting from scratch.

## What Known does

Known handles support requests using the customer's available structured data, current request, conversation context, and relevant durable memory.

The structured context can include:

- Customer name, email, and ID
- Orders, order IDs, status, and items
- Previous conversation messages
- Customer preferences and constraints
- Relevant historical support context stored as durable memory

Known is not just a chatbot with conversation history. It retrieves durable customer memory for the current customer, passes that memory into the reasoning context, and uses it to influence the recommended support response or action.

## Memory is load-bearing

Sibyl Memory is on Known's critical path for support decisions. A support request first retrieves relevant customer memory. Known then uses the retrieved memory when determining the support recommendation and in the AI reasoning context. If required Sibyl Memory is unavailable, Known fails the request rather than silently continuing without the required memory layer.

The core memory path is in `backend/app/production_agent.py`:

- **Read:** `KnownAgent._search_memory()` calls `self.memory.search(...)` before support reasoning.
- **Decision:** `KnownAgent._action()` uses recalled memory to change delivery recommendations; the retrieved memories are also included in the AI context.
- **Write:** `KnownAgent._remember()` calls `self.memory.remember(...)` when durable customer information is detected.
- **Event:** `KnownAgent._record_event()` records the support interaction through the memory layer.
- **Failure boundary:** `handle()` raises when Sibyl Memory is unavailable, so the core support flow does not silently degrade to a memory-free agent.

The production acceptance test verifies the load-bearing behavior across sessions: session 1 writes durable customer information; a fresh session retrieves it without injection; the recalled memory changes the agent's reasoning/recommendation.

## How memory made this possible

Without persistent memory, Known could combine the customer's current structured data and current conversation, but it would not retain useful customer-specific preferences and constraints for future sessions. Sibyl makes that historical context available again when the customer returns, allowing the support decision to change because of something learned earlier. For example, a stored preference for expedited handling can affect how a later delivery issue is handled.

## Architecture

`authenticated operator -> FastAPI -> Supabase structured data + Sibyl Memory -> AI -> Supabase conversation persistence + Sibyl durable memory`

- **Supabase** is the structured application-data layer: businesses, memberships, customers, orders, conversations, and messages.
- **Sibyl Memory** is the persistent agent-memory layer. Known uses the official `sibyl-memory-client`; it does not replace Sibyl with a vector database or a second memory table in Supabase.
- **OpenAI Responses API** performs agent reasoning.
- The browser never receives the Supabase service-role key and never supplies authoritative business/customer/order data.

## Partner stacks

Sibyl Memory is the required stack for this hackathon and is therefore not a partner-multiplier stack.

Known does **not** claim Base or Virtuals Protocol as partner stacks in this submission. Supabase and OpenAI are application dependencies, not claimed Sibyl partner stacks. No optional partner multiplier is claimed unless a partner integration is actually exercised in the submitted demo.

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

Run the backend suite with:

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

The current backend suite verifies the agent, API/auth contracts, structured models, session behavior, integrations, and Sibyl memory behavior. The memory tests verify real Sibyl SDK write/read behavior and business/customer isolation. Production acceptance additionally requires a two-session memory test: write durable customer information in session 1, start a new session, retrieve it from Sibyl without injection, and verify that the agent's reasoning changes because of the recalled memory.

## Demo requirement

The submitted 2–5 minute demo should show the problem, the product, how Known works, and the Sibyl load-bearing moment. The critical segment should show a genuinely fresh session recalling state written earlier, as one continuous unedited segment with an on-screen timestamp or commit hash, as required by the Sibyl Labs Hackathon rules.

## Prior Work declaration

Known's repository contains development work and commits made before the Sibyl Labs Hackathon build window. This README does not represent that earlier work as having been created during the hackathon window. The project team should follow the event's build-window and submission requirements when submitting this repository and disclose this prior work accurately to the organizers/judges.

## License

MIT

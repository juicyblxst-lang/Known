from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .agent import KnownAgent
from .models import SupportRequest, SupportResponse

app = FastAPI(title="Known", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in __import__("os").getenv("KNOWN_CORS_ORIGINS", "http://localhost:8000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
agent = KnownAgent()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "known"}


@app.post("/api/support", response_model=SupportResponse)
def support(request: SupportRequest) -> SupportResponse:
    return agent.handle(request)


@app.get("/", response_class=HTMLResponse)
def workspace() -> str:
    return """<!doctype html><html><head><title>Known</title><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{font-family:Inter,system-ui,sans-serif;margin:0;background:#0b0d10;color:#e8eaed}main{max-width:1100px;margin:8vh auto;padding:32px}h1{font-size:42px;margin-bottom:8px}p{color:#9aa1ab}.grid{display:grid;grid-template-columns:280px 1fr;gap:16px}.panel{border:1px solid #272c33;border-radius:14px;padding:20px;background:#11151a}.memory{padding:12px 0;border-bottom:1px solid #272c33}.tag{font-size:11px;color:#8fd3ff;text-transform:uppercase}</style></head><body><main><div class='grid'><aside class='panel'><div class='tag'>Customer</div><h2>Support workspace</h2><p>Customer context, orders, and durable memory live here.</p><div class='memory'>Sibyl Memory<br><small>Connected through the backend adapter</small></div></aside><section class='panel'><div class='tag'>Known</div><h1>Memory-first support</h1><p>The API is ready. POST a customer support request to <code>/api/support</code> to run retrieval → reasoning → personalization → memory write-back.</p></section></div></main></body></html>"""

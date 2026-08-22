from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .agent import KnownAgent
from .api import router
from .models import SupportRequest, SupportResponse

app = FastAPI(title="Known", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("KNOWN_CORS_ORIGINS", "http://localhost:8000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
agent = KnownAgent()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "known", "version": "0.2.0"}


@app.post("/api/support", response_model=SupportResponse)
def support(request: SupportRequest) -> SupportResponse:
    return agent.handle(request)


@app.get("/", response_class=HTMLResponse)
def workspace() -> str:
    return """<!doctype html><html><head><title>Known — Support Workspace</title><meta name='viewport' content='width=device-width,initial-scale=1'><style>*{box-sizing:border-box}body{font-family:Inter,system-ui,sans-serif;margin:0;background:#0b0d10;color:#e8eaed}main{max-width:1240px;margin:0 auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.brand{font-weight:700;font-size:22px}.status{font-size:12px;color:#7ee2a8;border:1px solid #244c38;border-radius:999px;padding:6px 10px}.grid{display:grid;grid-template-columns:250px 1fr 290px;gap:14px}.panel{border:1px solid #272c33;border-radius:14px;background:#11151a;overflow:hidden}.head{padding:16px 18px;border-bottom:1px solid #272c33;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8d96a3}.body{padding:18px}.customer{font-size:20px;font-weight:650;margin:0 0 4px}.muted{color:#8d96a3;font-size:13px;line-height:1.5}.order{padding:11px 0;border-bottom:1px solid #272c33}.order:last-child{border:0}.memory{padding:12px 0;border-bottom:1px solid #272c33}.memory:last-child{border:0}.memory strong{font-size:13px}.tag{font-size:10px;color:#8fd3ff;text-transform:uppercase;letter-spacing:.08em}.chat{min-height:430px;display:flex;flex-direction:column}.message{padding:18px;border-bottom:1px solid #272c33}.message.agent{background:#0e1318}.compose{margin-top:auto;border-top:1px solid #272c33;padding:14px}.compose input{width:100%;background:#0b0d10;border:1px solid #303640;border-radius:10px;color:#fff;padding:12px}.action{margin-top:16px;padding:13px;border:1px solid #31516a;border-radius:10px;background:#101a22}.action b{font-size:12px}.action p{margin:6px 0 0;font-size:12px;color:#9ba6b3}@media(max-width:900px){.grid{grid-template-columns:1fr}.side{display:none}}</style></head><body><main><div class='top'><div class='brand'>Known</div><div class='status'>● Memory-first agent</div></div><div class='grid'><aside class='panel side'><div class='head'>Customer</div><div class='body'><p class='customer'>Maya Chen</p><p class='muted'>maya@example.com<br>VIP customer</p><div class='head' style='margin:20px -18px 0'>Orders</div><div class='order'><b>ORD-1042</b><br><span class='muted'>Delayed · $128</span></div><div class='order'><b>ORD-0981</b><br><span class='muted'>Delivered · $86</span></div></div></aside><section class='panel chat'><div class='head'>Conversation</div><div class='message'><div class='tag'>Customer</div><p>My order is late and I need help before Friday.</p></div><div class='message agent'><div class='tag'>Known</div><p>I found the delayed order and relevant customer history. I’ll prioritize a delivery update and use Maya’s preference for expedited shipping when timing is critical.</p><div class='action'><b>Recommended action</b><p>Check the latest shipment status and provide the tracking update.</p></div></div><div class='compose'><input placeholder='Reply to customer…' /></div></section><aside class='panel'><div class='head'>Relevant memory</div><div class='body'><div class='memory'><div class='tag'>Preference</div><strong>Maya prefers expedited shipping when an order is time-sensitive.</strong></div><div class='memory'><div class='tag'>History</div><strong>Maya previously asked support to proactively monitor a delayed shipment.</strong></div><p class='muted' style='margin-top:14px'>Retrieved from Sibyl Memory for this customer.</p></div></aside></div></main></body></html>"""

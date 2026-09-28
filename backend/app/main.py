from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import admin, auth, candidates, kyc, proctoring, vendors

app = FastAPI(title="NEBOSH/IOSH Proctoring API", version="1.0.0")

_allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    # No entries = no browser-based cross-origin access at all. Add each LMS
    # tenant's origin via CORS_ALLOWED_ORIGINS (comma-separated). Server-to-
    # server calls (API key) are unaffected by CORS either way.
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(kyc.router)
app.include_router(proctoring.router)
app.include_router(admin.router)
app.include_router(vendors.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

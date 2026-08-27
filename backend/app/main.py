from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, candidates, kyc, proctoring

app = FastAPI(title="NEBOSH/IOSH Proctoring API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to exam frontend origin(s) in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candidates.router)
app.include_router(kyc.router)
app.include_router(proctoring.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

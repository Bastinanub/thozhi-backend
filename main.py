from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api.chat import router as chat_router
from app.api.report import router as report_router
from app.api.research import router as research_router
from app.api.metrics import router as metrics_router

from app.db.database import init_db
from app.db import models


# Ensure reports folder exists
os.makedirs("reports", exist_ok=True)

app = FastAPI(title="Thozhi Backend")


@app.on_event("startup")
def on_startup():
    init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routers
app.include_router(chat_router, prefix="/api")
app.include_router(report_router)
app.include_router(research_router)
app.include_router(metrics_router)


@app.get("/")
def root():
    return {"status": "Thozhi backend running"}
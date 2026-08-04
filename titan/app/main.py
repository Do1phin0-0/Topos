from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from titan.app.api import congress
from titan.app.db.session import SessionLocal, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Titan", lifespan=lifespan)
app.include_router(congress.router)


@app.get("/health")
def health() -> dict:
    db_ok = True
    try:
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}

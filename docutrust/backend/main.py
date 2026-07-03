"""
DocuTrust - Enterprise Advanced RAG Platform
Main FastAPI application entry point.
"""

import logging
import sys
import io
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from config import settings
from database import connect_db, close_db
from api.upload import router as upload_router
from api.query import router as query_router
from api.client import router as client_router

# ── Fix Windows console encoding (cp1252 -> utf-8) ──
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Logging setup ──
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("docutrust")


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("=" * 60)
    logger.info(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    logger.info(f"  LLM Provider : {settings.LLM_PROVIDER} ({settings.LLM_MODEL})")
    logger.info(f"  Embedding    : {settings.EMBEDDING_MODEL}")
    logger.info(f"  Reranker     : {settings.RERANKER_MODEL}")
    logger.info("=" * 60)

    # Connect to MongoDB
    try:
        await connect_db()
    except Exception as e:
        logger.error(f"[ERROR] Failed to connect to MongoDB: {e}")
        logger.warning("[WARN] Running without database -- uploads will fail.")

    yield

    # Shutdown
    await close_db()
    logger.info("[STOP] DocuTrust shutdown complete.")


# ── FastAPI App ──
app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise Advanced RAG Platform with Automated Self-Correction",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ──
app.include_router(upload_router)
app.include_router(query_router)
app.include_router(client_router)

# ── Serve Frontend ──
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend HTML."""
        return FileResponse(str(frontend_dir / "index.html"))
else:
    @app.get("/")
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "docs": "/docs",
        }


# ── Health Check ──
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

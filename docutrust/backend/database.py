"""
DocuTrust Database — MongoDB async client and collection management.
Uses motor for async operations, with vector search index support.
"""

import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING
from config import settings

logger = logging.getLogger(__name__)

# ── Global client reference ──
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> AsyncIOMotorDatabase:
    """Initialize MongoDB connection and create indexes."""
    global _client, _db

    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
    _client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2500)
    _db = _client[settings.MONGODB_DB_NAME]

    # Verify connection
    try:
        await _client.admin.command("ping")
        logger.info("[OK] MongoDB connection established.")
    except Exception as e:
        logger.error(f"[ERROR] MongoDB connection failed: {e}")
        raise

    # ── Create collections and indexes ──
    await _ensure_indexes()

    # Initialize default active profile if collection is empty
    try:
        profiles_col = _db["client_profiles"]
        if await profiles_col.count_documents({}) == 0:
            logger.info("Initializing default client profile...")
            default_profile = {
                "profile_id": "default",
                "name": "Standard Enterprise Profile",
                "relevance_threshold": 0.5,
                "llm_provider": "google",
                "llm_model": "gemini-1.5-flash",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
            await profiles_col.insert_one(default_profile)
    except Exception as e:
        logger.warning(f"Could not initialize default client profile: {e}")

    return _db


async def _ensure_indexes():
    """Create indexes for optimal query performance."""
    db = get_db()

    # Documents collection
    docs_col = db["documents"]
    await docs_col.create_indexes([
        IndexModel([("document_id", ASCENDING)], unique=True),
        IndexModel([("uploaded_at", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ])

    # Chunks collection
    chunks_col = db["chunks"]
    await chunks_col.create_indexes([
        IndexModel([("chunk_id", ASCENDING)], unique=True),
        IndexModel([("document_id", ASCENDING)]),
        IndexModel([("page_number", ASCENDING)]),
    ])

    # Sessions collection
    sessions_col = db["sessions"]
    await sessions_col.create_indexes([
        IndexModel([("session_id", ASCENDING)], unique=True),
        IndexModel([("created_at", ASCENDING)]),
    ])

    # Trace logs collection
    traces_col = db["trace_logs"]
    await traces_col.create_indexes([
        IndexModel([("session_id", ASCENDING)]),
        IndexModel([("created_at", ASCENDING)]),
    ])

    # Client Profiles collection
    profiles_col = db["client_profiles"]
    await profiles_col.create_indexes([
        IndexModel([("profile_id", ASCENDING)], unique=True),
        IndexModel([("is_active", ASCENDING)]),
    ])

    logger.info("[OK] Database indexes ensured.")


def get_db() -> AsyncIOMotorDatabase:
    """Get the current database instance, initializing it if necessary."""
    global _client, _db
    if _db is None:
        logger.info(f"Lazily initializing MongoDB client at {settings.MONGODB_URI}...")
        _client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2500)
        _db = _client[settings.MONGODB_DB_NAME]
    return _db


async def close_db():
    """Gracefully close MongoDB connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


# ── Collection helpers ──

def documents_collection():
    return get_db()["documents"]


def chunks_collection():
    return get_db()["chunks"]


def sessions_collection():
    return get_db()["sessions"]


def trace_logs_collection():
    return get_db()["trace_logs"]


def client_profiles_collection():
    return get_db()["client_profiles"]

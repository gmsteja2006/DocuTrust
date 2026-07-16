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

# ── Mock Database for local fallback or Vercel without hosted MongoDB ──
class MockCursor:
    def __init__(self, data):
        self.data = data
        self._sort_key = None
        self._sort_dir = 1
        self._limit = None

    def sort(self, key, direction=-1):
        self._sort_key = key
        self._sort_dir = direction
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        res = list(self.data)
        if self._sort_key:
            reverse = (self._sort_dir == -1)
            res.sort(key=lambda x: x.get(self._sort_key, datetime.now(timezone.utc)), reverse=reverse)
        if self._limit:
            res = res[:self._limit]
        elif length:
            res = res[:length]
        return res

class MockCollection:
    def __init__(self, name):
        self.name = name
        self.data = []
        self._indexes = []

    async def create_indexes(self, indexes):
        self._indexes.extend(indexes)
        return []

    async def insert_one(self, doc):
        self.data.append(doc)
        return type('obj', (object,), {'inserted_id': doc.get('_id', 'mock_id')})()

    async def insert_many(self, docs):
        self.data.extend(docs)
        return type('obj', (object,), {'inserted_ids': [d.get('_id', 'mock_id') for d in docs]})()

    async def update_one(self, filter_dict, update_dict):
        modified = 0
        set_fields = update_dict.get("$set", {})
        for doc in self.data:
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                doc.update(set_fields)
                modified = 1
                break
        return type('obj', (object,), {'modified_count': modified})()

    async def update_many(self, filter_dict, update_dict):
        modified = 0
        set_fields = update_dict.get("$set", {})
        for doc in self.data:
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                doc.update(set_fields)
                modified += 1
        return type('obj', (object,), {'modified_count': modified})()

    async def find_one(self, filter_dict, projection=None):
        for doc in self.data:
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                res = dict(doc)
                if projection:
                    res.pop('_id', None)
                return res
        return None

    def find(self, filter_dict=None, projection=None):
        filter_dict = filter_dict or {}
        matches = []
        for doc in self.data:
            match = True
            for k, v in filter_dict.items():
                if isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                res = dict(doc)
                if projection:
                    res.pop('_id', None)
                matches.append(res)
        return MockCursor(matches)

    async def delete_one(self, filter_dict):
        deleted = 0
        for i, doc in enumerate(self.data):
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                self.data.pop(i)
                deleted = 1
                break
        return type('obj', (object,), {'deleted_count': deleted})()

    async def delete_many(self, filter_dict):
        initial_len = len(self.data)
        self.data = [doc for doc in self.data if not all(doc.get(k) == v for k, v in filter_dict.items())]
        deleted = initial_len - len(self.data)
        return type('obj', (object,), {'deleted_count': deleted})()

    async def count_documents(self, filter_dict):
        count = 0
        for doc in self.data:
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

class MockDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]


# ── Global client reference ──
_client: AsyncIOMotorClient | None = None
_db = None


async def connect_db() -> AsyncIOMotorDatabase:
    """Initialize MongoDB connection and create indexes."""
    global _client, _db

    import os
    is_vercel = os.environ.get("VERCEL", "").strip() != ""
    if is_vercel and "localhost" in settings.MONGODB_URI:
        logger.warning("⚠️ Running on Vercel with localhost MongoDB. Switching to in-memory fallback database.")
        _db = MockDatabase()
        await _initialize_profiles(_db)
        return _db

    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
    try:
        _client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2500)
        _db = _client[settings.MONGODB_DB_NAME]
        await _client.admin.command("ping")
        logger.info("[OK] MongoDB connection established.")
        await _ensure_indexes()
        await _initialize_profiles(_db)
    except Exception as e:
        logger.error(f"[ERROR] MongoDB connection failed: {e}. Falling back to in-memory MockDatabase.")
        _db = MockDatabase()
        await _initialize_profiles(_db)

    return _db


async def _initialize_profiles(db):
    """Initialize default active profile if collection is empty."""
    try:
        profiles_col = db["client_profiles"]
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


def get_db():
    """Get the current database instance, initializing it if necessary."""
    global _client, _db
    if _db is None:
        import os
        is_vercel = os.environ.get("VERCEL", "").strip() != ""
        if is_vercel and "localhost" in settings.MONGODB_URI:
            logger.warning("⚠️ Running on Vercel with localhost MongoDB. Lazily switching to MockDatabase.")
            _db = MockDatabase()
            # Initialize default profile in-memory
            default_profile = {
                "profile_id": "default",
                "name": "Standard Enterprise Profile",
                "relevance_threshold": 0.5,
                "llm_provider": "google",
                "llm_model": "gemini-1.5-flash",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
            _db["client_profiles"].data.append(default_profile)
            return _db

        logger.info(f"Lazily initializing MongoDB client at {settings.MONGODB_URI}...")
        try:
            _client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2500)
            _db = _client[settings.MONGODB_DB_NAME]
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}. Falling back to MockDatabase.")
            _db = MockDatabase()
            default_profile = {
                "profile_id": "default",
                "name": "Standard Enterprise Profile",
                "relevance_threshold": 0.5,
                "llm_provider": "google",
                "llm_model": "gemini-1.5-flash",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
            _db["client_profiles"].data.append(default_profile)
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

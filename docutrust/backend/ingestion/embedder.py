"""
DocuTrust Embedder — Generates vector embeddings for document chunks.
Uses sentence-transformers bi-encoder for fast batch embedding.
"""

import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from config import settings

logger = logging.getLogger(__name__)

# ── Singleton model instance ──
_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Load or return cached SentenceTransformer model."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}...")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info(f"✅ Embedding model loaded (dim={settings.EMBEDDING_DIMENSION})")
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.
    
    Args:
        texts: List of text strings to embed
        batch_size: Processing batch size
    
    Returns:
        List of embedding vectors as float lists
    """
    model = get_embedding_model()

    logger.info(f"🔢 Embedding {len(texts)} texts (batch_size={batch_size})...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    # Convert numpy arrays to lists for MongoDB storage
    result = [emb.tolist() for emb in embeddings]
    logger.info(f"✅ Generated {len(result)} embeddings")
    return result


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    model = get_embedding_model()
    embedding = model.encode(query, normalize_embeddings=True)
    return embedding.tolist()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(vec_a)
    b = np.array(vec_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


async def embed_and_store_chunks(chunks: list[dict], chunks_collection) -> int:
    """
    Embed all chunks and store them in MongoDB.
    
    Args:
        chunks: List of chunk dicts from pdf_parser
        chunks_collection: MongoDB collection reference
    
    Returns:
        Number of chunks stored
    """
    if not chunks:
        return 0

    # Extract texts and generate embeddings
    texts = [chunk["text"] for chunk in chunks]
    embeddings = embed_texts(texts)

    # Attach embeddings to chunks
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    # Bulk insert to MongoDB
    await chunks_collection.insert_many(chunks)
    logger.info(f"💾 Stored {len(chunks)} chunks with embeddings in MongoDB")

    return len(chunks)

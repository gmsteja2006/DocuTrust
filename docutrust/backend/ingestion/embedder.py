"""
DocuTrust Embedder — Generates vector embeddings for document chunks.
Uses Google Generative AI API for embeddings (reduces deployment size).
"""

import logging
import asyncio
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from config import settings

logger = logging.getLogger(__name__)

# ── Singleton embeddings instance ──
_embeddings: GoogleGenerativeAIEmbeddings | None = None


def get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """Get or initialize Google Generative AI embeddings."""
    global _embeddings
    if _embeddings is None:
        logger.info(f"Initializing Google Generative AI embeddings...")
        _embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        logger.info(f"✅ Embeddings initialized (API-based)")
    return _embeddings


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts using Google Generative AI API.
    
    Args:
        texts: List of text strings to embed
        batch_size: Processing batch size (Google API handles batching)
    
    Returns:
        List of embedding vectors as float lists
    """
    embeddings = get_embedding_model()

    logger.info(f"🔢 Embedding {len(texts)} texts via Google Generative AI API...")
    
    # Process in batches
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        try:
            batch_embeddings = embeddings.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)
            logger.info(f"  ✓ Processed batch {i//batch_size + 1}")
        except Exception as e:
            logger.error(f"❌ Embedding error for batch: {e}")
            raise

    logger.info(f"✅ Generated {len(all_embeddings)} embeddings")
    return all_embeddings


def embed_query(query: str) -> list[float]:
    """Embed a single query string using Google Generative AI API."""
    embeddings = get_embedding_model()
    embedding = embeddings.embed_query(query)
    return embedding


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    return dot_product / (norm_a * norm_b + 1e-10)


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

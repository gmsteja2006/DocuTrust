"""
DocuTrust Embedder — Generates vector embeddings for document chunks.
Uses Google Generative AI API directly for embeddings.
"""

import logging
import asyncio
import google.generativeai as genai
from config import settings

logger = logging.getLogger(__name__)


def _is_api_key_valid() -> bool:
    key = settings.GOOGLE_API_KEY
    if not key:
        return False
    if "your-google-api-key" in key.lower() or key.strip() == "":
        return False
    return True


def _get_mock_embedding(text: str) -> list[float]:
    import hashlib
    import math
    dim = settings.EMBEDDING_DIMENSION or 384
    hasher = hashlib.sha256(text.encode("utf-8"))
    digest = hasher.digest()
    
    # Deterministic generation from seed
    seed = int.from_bytes(digest[:4], byteorder="big")
    vector = []
    current = seed
    for _ in range(dim):
        current = (1103515245 * current + 12345) & 0x7fffffff
        val = (current / 2147483647.0) * 2.0 - 1.0
        vector.append(val)
        
    magnitude = math.sqrt(sum(x * x for x in vector))
    if magnitude > 0:
        vector = [x / magnitude for x in vector]
    else:
        vector = [0.051] * dim
    return vector


def get_embeddings_client():
    """Initialize Google Generative AI client."""
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    return genai


def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts using Google Generative AI API.
    Falls back to deterministic local mock embeddings if API key is not valid.
    """
    if not _is_api_key_valid():
        logger.warning("⚠️ GOOGLE_API_KEY not configured. Generating deterministic mock embeddings locally.")
        return [_get_mock_embedding(t) for t in texts]

    client = get_embeddings_client()
    logger.info(f"🔢 Embedding {len(texts)} texts via Google Generative AI API...")
    
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        try:
            # Use Google's embedding API
            response = client.embed_content(
                model="models/embedding-001",
                content=batch,
                task_type="RETRIEVAL_DOCUMENT"
            )
            embeddings = response['embedding'] if isinstance(response, dict) else [response.embedding]
            all_embeddings.extend(embeddings if isinstance(embeddings, list) and len(embeddings) > 1 else [embeddings])
            logger.info(f"  ✓ Processed batch {i//batch_size + 1}")
        except Exception as e:
            logger.error(f"❌ Embedding error for batch: {e}")
            raise

    logger.info(f"✅ Generated {len(all_embeddings)} embeddings")
    return all_embeddings


def embed_query(query: str) -> list[float]:
    """Embed a single query string using Google Generative AI API or local mock fallback."""
    if not _is_api_key_valid():
        return _get_mock_embedding(query)

    client = get_embeddings_client()
    try:
        response = client.embed_content(
            model="models/embedding-001",
            content=query,
            task_type="RETRIEVAL_QUERY"
        )
        return response['embedding'] if isinstance(response, dict) else response.embedding
    except Exception as e:
        logger.error(f"❌ Query embedding error: {e}")
        raise


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

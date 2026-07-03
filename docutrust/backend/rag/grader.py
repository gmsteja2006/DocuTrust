"""
DocuTrust Document Grader — CrossEncoder relevance scoring.
Uses a local cross-encoder model to grade document-query relevance,
replacing expensive LLM-based grading with fast local inference.
"""

import logging
from sentence_transformers import CrossEncoder
from config import settings

logger = logging.getLogger(__name__)

# ── Singleton model instance ──
_grader: CrossEncoder | None = None


def get_grader_model() -> CrossEncoder:
    """Load or return cached CrossEncoder reranker model."""
    global _grader
    if _grader is None:
        logger.info(f"Loading reranker model: {settings.RERANKER_MODEL}...")
        _grader = CrossEncoder(settings.RERANKER_MODEL)
        logger.info("✅ Reranker model loaded")
    return _grader


def grade_documents(
    query: str,
    documents: list[dict],
    threshold: float = None,
) -> tuple[list[dict], list[dict]]:
    """
    Grade a list of document chunks for relevance to the query.
    
    Uses a cross-encoder to jointly encode (query, doc) pairs and
    produce a relevance score. Documents above the threshold pass.
    
    Args:
        query: The user's search query
        documents: List of chunk dicts with 'text' field
        threshold: Minimum score to be considered relevant
    
    Returns:
        (relevant_docs, irrelevant_docs) — each with 'relevance_score' attached
    """
    threshold = threshold or settings.RELEVANCE_THRESHOLD
    model = get_grader_model()

    if not documents:
        return [], []

    # Create query-document pairs for cross-encoder
    pairs = [(query, doc["text"]) for doc in documents]
    scores = model.predict(pairs)

    relevant = []
    irrelevant = []

    for doc, score in zip(documents, scores):
        doc_with_score = {**doc, "relevance_score": float(score)}

        if score >= threshold:
            relevant.append(doc_with_score)
        else:
            irrelevant.append(doc_with_score)

    # Sort relevant docs by score (highest first)
    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)

    logger.info(
        f"📊 Grading: {len(documents)} docs → "
        f"{len(relevant)} relevant, {len(irrelevant)} irrelevant "
        f"(threshold={threshold})"
    )

    return relevant, irrelevant


def rerank_documents(
    query: str,
    documents: list[dict],
    top_k: int = None,
) -> list[dict]:
    """
    Rerank documents by relevance and return top-k.
    Unlike grade_documents, this doesn't filter — it just reorders.
    """
    top_k = top_k or settings.RERANK_TOP_K
    model = get_grader_model()

    if not documents:
        return []

    pairs = [(query, doc["text"]) for doc in documents]
    scores = model.predict(pairs)

    scored_docs = [
        {**doc, "relevance_score": float(score)}
        for doc, score in zip(documents, scores)
    ]
    scored_docs.sort(key=lambda x: x["relevance_score"], reverse=True)

    return scored_docs[:top_k]

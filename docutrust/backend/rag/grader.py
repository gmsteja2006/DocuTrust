"""
DocuTrust Document Grader — Relevance scoring with CrossEncoder or lightweight fallback.
Uses a local cross-encoder model when available (local dev),
or falls back to cosine-similarity grading on Vercel (no torch).
"""

import logging
import os
from config import settings

logger = logging.getLogger(__name__)

# ── Try importing CrossEncoder (requires torch + sentence-transformers) ──
_USE_CROSS_ENCODER = False
_grader = None

try:
    from sentence_transformers import CrossEncoder
    _USE_CROSS_ENCODER = True
    logger.info("CrossEncoder available — using neural reranker.")
except ImportError:
    logger.info("sentence-transformers not available — using lightweight cosine fallback.")


def get_grader_model():
    """Load or return cached CrossEncoder reranker model."""
    global _grader
    if not _USE_CROSS_ENCODER:
        return None
    if _grader is None:
        logger.info(f"Loading reranker model: {settings.RERANKER_MODEL}...")
        _grader = CrossEncoder(settings.RERANKER_MODEL)
        logger.info("✅ Reranker model loaded")
    return _grader


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Simple cosine similarity without numpy dependency."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b + 1e-10)


def _lightweight_grade(query: str, documents: list[dict], threshold: float) -> tuple[list[dict], list[dict]]:
    """
    Lightweight grading using the existing vector similarity scores.
    Falls back to keyword overlap when embeddings aren't available.
    """
    import re

    relevant = []
    irrelevant = []

    # Use existing similarity scores from retrieval if available
    for doc in documents:
        score = doc.get("similarity", doc.get("relevance_score", 0.0))

        # If no vector score, do keyword overlap as a rough heuristic
        if score == 0.0:
            query_words = set(re.findall(r'\w+', query.lower()))
            doc_words = set(re.findall(r'\w+', doc.get("text", "").lower()))
            overlap = len(query_words & doc_words)
            score = min(overlap / max(len(query_words), 1), 1.0)

        doc_with_score = {**doc, "relevance_score": float(score)}

        if score >= threshold:
            relevant.append(doc_with_score)
        else:
            irrelevant.append(doc_with_score)

    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    return relevant, irrelevant


def grade_documents(
    query: str,
    documents: list[dict],
    threshold: float = None,
) -> tuple[list[dict], list[dict]]:
    """
    Grade a list of document chunks for relevance to the query.

    Uses a cross-encoder to jointly encode (query, doc) pairs and
    produce a relevance score. Documents above the threshold pass.
    Falls back to lightweight scoring on Vercel (no torch).

    Args:
        query: The user's search query
        documents: List of chunk dicts with 'text' field
        threshold: Minimum score to be considered relevant

    Returns:
        (relevant_docs, irrelevant_docs) — each with 'relevance_score' attached
    """
    threshold = threshold or settings.RELEVANCE_THRESHOLD

    if not documents:
        return [], []

    # Use CrossEncoder if available (local dev), otherwise lightweight fallback
    if not _USE_CROSS_ENCODER:
        logger.info(f"📊 Lightweight grading {len(documents)} documents...")
        relevant, irrelevant = _lightweight_grade(query, documents, threshold)
        logger.info(
            f"📊 Grading: {len(documents)} docs → "
            f"{len(relevant)} relevant, {len(irrelevant)} irrelevant "
            f"(threshold={threshold}, mode=lightweight)"
        )
        return relevant, irrelevant

    model = get_grader_model()

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

    if not documents:
        return []

    if not _USE_CROSS_ENCODER:
        # Lightweight: sort by existing similarity scores
        scored_docs = [
            {**doc, "relevance_score": doc.get("similarity", doc.get("relevance_score", 0.0))}
            for doc in documents
        ]
        scored_docs.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored_docs[:top_k]

    model = get_grader_model()

    pairs = [(query, doc["text"]) for doc in documents]
    scores = model.predict(pairs)

    scored_docs = [
        {**doc, "relevance_score": float(score)}
        for doc, score in zip(documents, scores)
    ]
    scored_docs.sort(key=lambda x: x["relevance_score"], reverse=True)

    return scored_docs[:top_k]

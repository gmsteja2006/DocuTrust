"""
DocuTrust CRAG Nodes — Individual processing nodes for the LangGraph pipeline.
Each function takes GraphState and returns partial state updates.
"""

import logging
import time
from datetime import datetime, timezone
from rag.state import GraphState
from rag.grader import grade_documents, rerank_documents
from rag.llm_utils import call_llm
from ingestion.embedder import embed_query, cosine_similarity
import re
from config import settings
from database import chunks_collection

logger = logging.getLogger(__name__)


async def _get_active_profile_settings() -> dict:
    """Fetch settings of active client profile from MongoDB or fallback to settings."""
    try:
        from database import client_profiles_collection
        col = client_profiles_collection()
        profile = await col.find_one({"is_active": True})
        if profile:
            return {
                "relevance_threshold": profile.get("relevance_threshold", settings.RELEVANCE_THRESHOLD),
                "llm_provider": profile.get("llm_provider", settings.LLM_PROVIDER),
                "llm_model": profile.get("llm_model", settings.LLM_MODEL),
                "profile_name": profile.get("name", "Default Profile"),
            }
    except Exception as e:
        logger.warning(f"Could not read active profile settings: {e}")
    
    return {
        "relevance_threshold": settings.RELEVANCE_THRESHOLD,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "profile_name": "System Config Defaults",
    }


def _local_extractive_summary(query: str, sources: list[dict]) -> tuple[str, list[dict]]:
    """
    Generate an answer using extractive summarization of the sources.
    Matches sentences containing query terms and inserts citations.
    """
    query_words = set(re.findall(r'\w+', query.lower()))
    stop_words = {"what", "is", "are", "the", "a", "an", "about", "for", "please", "show", "me", "find", "document", "policy", "in", "of", "to", "and", "or", "on", "with", "at", "by", "from"}
    keywords = {w for w in query_words if w not in stop_words and len(w) > 2}
    
    if not keywords:
        keywords = query_words

    sentences_pool = []
    
    for i, src in enumerate(sources):
        src_id = i + 1
        text = src.get("text", "")
        raw_sentences = re.split(r'(?<=[.!?])\s+', text)
        for idx, sentence in enumerate(raw_sentences):
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue
            
            sent_words = set(re.findall(r'\w+', sentence.lower()))
            overlap = keywords.intersection(sent_words)
            score = len(overlap)
            
            if score > 0:
                sentences_pool.append({
                    "text": sentence,
                    "source_id": src_id,
                    "score": score + (1.0 / (idx + 1)),
                })

    sentences_pool.sort(key=lambda x: x["score"], reverse=True)
    
    selected_sentences = []
    seen = set()
    for item in sentences_pool[:4]:
        norm_txt = item["text"].lower()[:50]
        if norm_txt not in seen:
            selected_sentences.append(item)
            seen.add(norm_txt)
            
    selected_sentences.sort(key=lambda x: x["source_id"])
    
    if not selected_sentences:
        if sources:
            top_src = sources[0]
            answer = f"According to {top_src.get('document_id', 'documents')}: {top_src['text'][:300]}... [Source 1]"
        else:
            answer = "I could not find any matching text in the documents to answer your query."
    else:
        paragraphs = []
        for item in selected_sentences:
            paragraphs.append(f"{item['text']} [Source {item['source_id']}]")
        
        intro = f"**Local Extractive Mode Answer:** (No active LLM API Key detected)\n\n"
        answer = intro + " ".join(paragraphs)
        
    citations = []
    for i, src in enumerate(sources):
        citations.append({
            "source_id": i + 1,
            "source_document": src.get("document_id", src.get("title", "Web")),
            "page_number": src.get("page_number", 0),
            "chunk_text": src["text"][:200] + "..." if len(src["text"]) > 200 else src["text"],
            "relevance_score": round(src.get("relevance_score", 0.7), 4),
            "source_type": src.get("source_type", "document"),
            "url": src.get("url", ""),
        })
        
    return answer, citations


def _trace_entry(step_name: str, status: str, detail: str = "", data: dict = None) -> dict:
    """Create a trace log entry for the UI."""
    return {
        "step_name": step_name,
        "status": status,
        "detail": detail,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Node 1: RETRIEVE ──

async def retrieve_node(state: GraphState) -> dict:
    """
    Retrieve relevant document chunks from MongoDB using vector similarity.
    Uses the query embedding to find closest chunks via cosine similarity.
    """
    query = state.get("rewritten_query") or state["query"]
    document_ids = state.get("document_ids", [])

    logger.info(f"🔍 Retrieving chunks for: '{query[:80]}...'")

    # Embed the query
    query_embedding = embed_query(query)

    # Fetch candidate chunks from MongoDB
    col = chunks_collection()
    filter_query = {}
    if document_ids:
        filter_query["document_id"] = {"$in": document_ids}

    try:
        cursor = col.find(filter_query, {"_id": 0})
        all_chunks = await cursor.to_list(length=500)
    except Exception as e:
        logger.error(f"MongoDB retrieval failed: {e}")
        return {
            "documents": [],
            "trace_log": [_trace_entry(
                "Retrieve", "completed",
                f"Database query failed: {str(e)}",
                {"chunk_count": 0, "error": str(e)}
            )],
        }

    if not all_chunks:
        return {
            "documents": [],
            "trace_log": [_trace_entry(
                "Retrieve", "completed",
                "No documents found in database.",
                {"chunk_count": 0}
            )],
        }

    # Compute cosine similarity for each chunk
    for chunk in all_chunks:
        if "embedding" in chunk and chunk["embedding"]:
            chunk["similarity"] = cosine_similarity(query_embedding, chunk["embedding"])
        else:
            chunk["similarity"] = 0.0

    # Sort by similarity and take top-K
    all_chunks.sort(key=lambda x: x["similarity"], reverse=True)
    top_chunks = all_chunks[:settings.RETRIEVAL_TOP_K]

    # Remove embeddings from results (save bandwidth)
    for chunk in top_chunks:
        chunk.pop("embedding", None)

    logger.info(f"📥 Retrieved {len(top_chunks)} chunks (from {len(all_chunks)} total)")

    return {
        "documents": top_chunks,
        "trace_log": [_trace_entry(
            "Retrieve", "completed",
            f"Found {len(top_chunks)} candidate chunks from {len(all_chunks)} total.",
            {
                "chunk_count": len(top_chunks),
                "top_score": round(top_chunks[0]["similarity"], 4) if top_chunks else 0,
                "query_used": query,
            }
        )],
    }


# ── Node 2: GRADE DOCUMENTS ──

async def grade_documents_node(state: GraphState) -> dict:
    """
    Grade retrieved documents for relevance using CrossEncoder.
    Separates relevant from irrelevant chunks.
    """
    query = state.get("rewritten_query") or state["query"]
    documents = state.get("documents", [])

    if not documents:
        return {
            "relevant_documents": [],
            "trace_log": [_trace_entry(
                "Grade Documents", "completed",
                "No documents to grade.",
                {"relevant": 0, "irrelevant": 0}
            )],
        }

    logger.info(f"📊 Grading {len(documents)} documents...")

    prof = await _get_active_profile_settings()
    threshold = prof["relevance_threshold"]

    start_time = time.time()
    relevant, irrelevant = grade_documents(query, documents, threshold=threshold)
    duration = (time.time() - start_time) * 1000

    scores_summary = [
        {"chunk_id": d.get("chunk_id", "?"), "score": round(d["relevance_score"], 4)}
        for d in (relevant + irrelevant)[:8]
    ]

    logger.info(f"✅ Grading complete: {len(relevant)} relevant, {len(irrelevant)} irrelevant")

    return {
        "relevant_documents": relevant,
        "trace_log": [_trace_entry(
            "Grade Documents", "completed",
            f"{len(relevant)} relevant, {len(irrelevant)} irrelevant "
            f"(threshold={settings.RELEVANCE_THRESHOLD}, {duration:.0f}ms)",
            {
                "relevant_count": len(relevant),
                "irrelevant_count": len(irrelevant),
                "threshold": settings.RELEVANCE_THRESHOLD,
                "duration_ms": round(duration, 1),
                "scores": scores_summary,
            }
        )],
    }


# ── Node 3: REWRITE QUERY ──

async def rewrite_query_node(state: GraphState) -> dict:
    """
    Rewrite the user's query for better retrieval.
    Uses LLM to reformulate ambiguous or poorly-performing queries.
    """
    original_query = state["query"]

    logger.info(f"✏️ Rewriting query: '{original_query[:80]}...'")

    prof = await _get_active_profile_settings()
    provider = prof["llm_provider"]
    model = prof["llm_model"]

    has_google_key = bool(settings.GOOGLE_API_KEY and "your-google-api-key" not in settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "")
    has_openai_key = bool(settings.OPENAI_API_KEY and "your-openai" not in settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "")

    is_mock = (provider == "mock" or 
               (provider == "google" and not has_google_key) or 
               (provider == "openai" and not has_openai_key))

    if is_mock:
        logger.info("Using local mock query rewriter...")
        stop_words = {"what", "is", "are", "the", "a", "an", "about", "for", "please", "show", "me", "find", "document", "policy", "in", "of", "to", "and"}
        words = original_query.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        rewritten = " ".join(keywords) + " detailed information" if keywords else original_query + " details"
    else:
        try:
            prompt = (
                "You are a query rewriter for a document search system. "
                "Rewrite the following query to be more specific and search-friendly. "
                "Return ONLY the rewritten query, nothing else.\n\n"
                f"Original query: {original_query}"
            )

            rewritten = await call_llm(provider, model, prompt, temperature=0.0)
            rewritten = rewritten.strip()

        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}. Using original query.")
            rewritten = original_query + " detailed policy information"

    logger.info(f"✏️ Rewritten: '{rewritten[:80]}...'")

    return {
        "rewritten_query": rewritten,
        "trace_log": [_trace_entry(
            "Rewrite Query", "completed",
            f"Query reformulated for better retrieval.",
            {
                "original": original_query,
                "rewritten": rewritten,
            }
        )],
    }


# ── Node 4: WEB SEARCH ──

async def web_search_node(state: GraphState) -> dict:
    """
    Fallback web search when document retrieval is insufficient.
    Uses DuckDuckGo search (free, no API key required).
    """
    query = state.get("rewritten_query") or state["query"]

    logger.info(f"🌐 Web search fallback for: '{query[:80]}...'")

    web_results = []
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                max_results=settings.WEB_SEARCH_MAX_RESULTS,
            ))

        for r in results:
            web_results.append({
                "text": r.get("body", ""),
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "source_type": "web",
                "relevance_score": 0.7,  # Default web confidence
            })

        logger.info(f"🌐 Found {len(web_results)} web results")

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        web_results = []

    return {
        "web_results": web_results,
        "web_search_triggered": True,
        "trace_log": [_trace_entry(
            "Web Search", "completed",
            f"Found {len(web_results)} supplementary web results.",
            {
                "results_count": len(web_results),
                "sources": [r.get("url", "") for r in web_results],
            }
        )],
    }


# ── Node 5: GENERATE ──

async def generate_node(state: GraphState) -> dict:
    """
    Generate a validated answer with strict citations.
    Combines relevant documents and web results into a cited response.
    """
    query = state["query"]
    relevant_docs = state.get("relevant_documents", [])
    web_results = state.get("web_results", [])

    # Combine all sources
    all_sources = relevant_docs + web_results

    if not all_sources:
        return {
            "generation": "I could not find sufficient information to answer your question. Please try uploading a relevant document or rephrasing your query.",
            "citations": [],
            "confidence_score": 0.0,
            "trace_log": [_trace_entry(
                "Generate", "completed",
                "No sources available for generation.",
                {"source_count": 0}
            )],
        }

    # Build context from sources
    context_parts = []
    for i, src in enumerate(all_sources):
        source_label = f"[Source {i+1}]"
        if src.get("source_type") == "web":
            source_label += f" (Web: {src.get('title', 'Unknown')})"
        else:
            source_label += f" (Doc page {src.get('page_number', '?')})"
        context_parts.append(f"{source_label}\n{src['text']}")

    context = "\n\n---\n\n".join(context_parts)

    # Generate with strict citation prompt
    prompt = f"""You are DocuTrust, an enterprise document analysis AI. Answer the question using ONLY the provided sources. Follow these rules strictly:

1. CITE every claim using [Source N] format
2. If information is insufficient, say so explicitly
3. Never fabricate information not present in the sources
4. Be precise, professional, and thorough
5. Structure your answer with clear paragraphs

SOURCES:
{context}

QUESTION: {query}

ANSWER (with citations):"""

    logger.info(f"🤖 Generating answer from {len(all_sources)} sources...")

    prof = await _get_active_profile_settings()
    provider = prof["llm_provider"]
    model = prof["llm_model"]

    has_google_key = bool(settings.GOOGLE_API_KEY and "your-google-api-key" not in settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "")
    has_openai_key = bool(settings.OPENAI_API_KEY and "your-openai" not in settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "")

    is_mock = (provider == "mock" or 
               (provider == "google" and not has_google_key) or 
               (provider == "openai" and not has_openai_key))

    if is_mock:
        logger.info("Using local mock generator (Extractive Summarizer)...")
        answer, citations = _local_extractive_summary(query, all_sources)
    else:
        try:
            answer = await call_llm(provider, model, prompt, temperature=settings.LLM_TEMPERATURE)
            answer = answer.strip()

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            answer = (
                f"⚠️ Generation error: {str(e)}. "
                "Please check your API key configuration. "
                f"Found {len(all_sources)} relevant sources for your query."
            )

        # Build citations for LLM path
        citations = [
            {
                "source_id": i + 1,
                "source_document": src.get("document_id", src.get("title", "Web")),
                "page_number": src.get("page_number", 0),
                "chunk_text": src["text"][:200] + "..." if len(src["text"]) > 200 else src["text"],
                "relevance_score": round(src.get("relevance_score", 0.0), 4),
                "source_type": src.get("source_type", "document"),
                "url": src.get("url", ""),
            }
            for i, src in enumerate(all_sources)
        ]

    # Calculate confidence
    if relevant_docs:
        avg_score = sum(d.get("relevance_score", 0) for d in relevant_docs) / len(relevant_docs)
        confidence = min(avg_score * 1.2, 1.0)  # Slightly boosted, capped at 1.0
    else:
        confidence = 0.4  # Lower confidence for web-only results

    logger.info(f"✅ Generated answer ({len(answer)} chars, confidence={confidence:.2f})")

    return {
        "generation": answer,
        "citations": citations,
        "confidence_score": round(confidence, 3),
        "trace_log": [_trace_entry(
            "Generate", "completed",
            f"Answer generated from {len(all_sources)} sources (confidence: {confidence:.1%})",
            {
                "source_count": len(all_sources),
                "answer_length": len(answer),
                "confidence": round(confidence, 3),
                "citation_count": len(citations),
            }
        )],
    }

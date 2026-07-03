"""
DocuTrust CRAG Graph — LangGraph StateGraph with conditional self-correction.
Implements the Corrective RAG pattern: Retrieve → Grade → (Rewrite+WebSearch | Generate).
"""

import logging
from langgraph.graph import StateGraph, END
from rag.state import GraphState
from rag.nodes import (
    retrieve_node,
    grade_documents_node,
    rewrite_query_node,
    web_search_node,
    generate_node,
)
from config import settings

logger = logging.getLogger(__name__)


def _should_rewrite(state: GraphState) -> str:
    """
    Conditional edge: decide whether to proceed to generation or rewrite the query.
    
    If enough relevant documents were found, go straight to generate.
    Otherwise, trigger query rewriting and web search fallback.
    """
    relevant_docs = state.get("relevant_documents", [])

    if len(relevant_docs) >= 2:
        logger.info(f"✅ {len(relevant_docs)} relevant docs found → Generate directly")
        return "generate"
    else:
        logger.info(f"⚠️ Only {len(relevant_docs)} relevant docs → Rewrite + Web Search")
        return "rewrite"


def build_crag_graph() -> StateGraph:
    """
    Build the Corrective RAG StateGraph.
    
    Flow:
        retrieve → grade_documents → [CONDITIONAL]
            ├── (enough relevant docs) → generate → END
            └── (insufficient docs) → rewrite_query → web_search → generate → END
    
    Returns:
        Compiled LangGraph StateGraph
    """
    workflow = StateGraph(GraphState)

    # ── Add nodes ──
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("rewrite_query", rewrite_query_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("generate", generate_node)

    # ── Define edges ──
    # Start → Retrieve
    workflow.set_entry_point("retrieve")

    # Retrieve → Grade
    workflow.add_edge("retrieve", "grade_documents")

    # Grade → Conditional (Generate or Rewrite)
    workflow.add_conditional_edges(
        "grade_documents",
        _should_rewrite,
        {
            "generate": "generate",
            "rewrite": "rewrite_query",
        },
    )

    # Rewrite → Web Search
    workflow.add_edge("rewrite_query", "web_search")

    # Web Search → Generate
    workflow.add_edge("web_search", "generate")

    # Generate → END
    workflow.add_edge("generate", END)

    logger.info("🔗 CRAG graph built successfully")

    # Compile the graph
    compiled = workflow.compile()
    return compiled


# ── Singleton graph instance ──
_graph = None


def get_crag_graph():
    """Get or create the singleton CRAG graph."""
    global _graph
    if _graph is None:
        _graph = build_crag_graph()
    return _graph

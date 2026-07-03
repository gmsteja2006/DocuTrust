"""
DocuTrust Graph State — TypedDict definition for the LangGraph CRAG pipeline.
This defines the data flowing through each node in the state graph.
"""

from typing import TypedDict, Annotated
from operator import add


class GraphState(TypedDict):
    """
    State object passed through the CRAG LangGraph pipeline.
    
    Attributes:
        query: Original user query
        rewritten_query: Reformulated query (if rewriting triggered)
        documents: Retrieved document chunks with metadata
        relevant_documents: Chunks that passed the grading filter
        web_results: Results from web search fallback
        generation: Final generated answer text
        citations: List of source citations
        confidence_score: Overall answer confidence (0.0-1.0)
        web_search_triggered: Whether web fallback was used
        trace_log: Step-by-step evaluation trace for UI display
        document_ids: Filter to specific uploaded documents
    """
    query: str
    rewritten_query: str
    documents: list[dict]
    relevant_documents: list[dict]
    web_results: list[dict]
    generation: str
    citations: list[dict]
    confidence_score: float
    web_search_triggered: bool
    trace_log: Annotated[list[dict], add]
    document_ids: list[str]

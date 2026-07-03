"""
DocuTrust Pydantic Models — Data schemas for the entire platform.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Document Models ──

class ClientProfile(BaseModel):
    """Configuration profile for an enterprise client or department."""
    profile_id: str = Field(..., description="Unique ID for the client profile")
    name: str = Field(..., description="Human-readable name of the profile")
    relevance_threshold: float = Field(0.5, description="Minimum relevance score for retrieved chunks")
    llm_provider: str = Field("google", description="LLM provider: google | openai | mock")
    llm_model: str = Field("gemini-1.5-flash", description="Model name to use for generation")
    is_active: bool = Field(False, description="Whether this is the currently active profile")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentChunk(BaseModel):
    """A single chunk of text extracted from a PDF document."""
    chunk_id: str = Field(..., description="Unique ID for the chunk")
    document_id: str = Field(..., description="Parent document ID")
    text: str = Field(..., description="Raw text content")
    page_number: int = Field(..., description="Source page number")
    chunk_index: int = Field(..., description="Chunk position within document")
    section_title: Optional[str] = Field(None, description="Detected section heading")
    embedding: Optional[list[float]] = Field(None, description="Vector embedding")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class DocumentRecord(BaseModel):
    """Metadata for an uploaded PDF document."""
    document_id: str
    filename: str
    file_size: int
    page_count: int
    chunk_count: int = 0
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "processing"  # processing | ready | error
    structural_index: list[dict] = Field(default_factory=list, description="Extracted document TOC/headings outline")



# ── Query & Response Models ──

class QueryRequest(BaseModel):
    """Incoming user query."""
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    document_ids: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """A citation linking an answer segment to a source."""
    source_document: str
    page_number: int
    chunk_text: str
    relevance_score: float
    source_type: str = "document"  # "document" or "web"


class QueryResponse(BaseModel):
    """Final validated answer with citations."""
    answer: str
    citations: list[Citation] = []
    confidence_score: float = 0.0
    web_search_triggered: bool = False
    session_id: str = ""


# ── Trace Log Models ──

class TraceStep(BaseModel):
    """A single step in the CRAG agent evaluation pipeline."""
    step_name: str
    status: str  # "running" | "completed" | "failed" | "skipped"
    detail: str = ""
    data: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[float] = None


class SessionLog(BaseModel):
    """Complete trace log for a query session."""
    session_id: str
    query: str
    trace_steps: list[TraceStep] = []
    final_response: Optional[QueryResponse] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Upload Response ──

class UploadResponse(BaseModel):
    """Response after document upload and ingestion."""
    document_id: str
    filename: str
    page_count: int
    chunk_count: int
    status: str
    message: str

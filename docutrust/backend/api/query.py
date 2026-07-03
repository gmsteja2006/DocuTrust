"""
DocuTrust Query API — SSE streaming endpoint for CRAG pipeline execution.
Streams each agent step in real-time to the frontend.
"""

import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from models import QueryRequest, SessionLog
from database import sessions_collection, trace_logs_collection
from rag.graph import get_crag_graph
from rag.state import GraphState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Query"])


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/query")
async def query_documents(request: QueryRequest):
    """
    Execute the CRAG pipeline and stream results via SSE.
    
    Each graph node transition is streamed as an SSE event so the
    frontend can display step-by-step agent evaluation logs in real-time.
    
    Event types:
        - step_start: A node is beginning execution
        - step_complete: A node finished (includes trace data)
        - answer: Final validated answer with citations
        - error: An error occurred
        - done: Stream complete
    """
    session_id = request.session_id or str(uuid.uuid4())[:12]

    logger.info(f"🔎 Query [{session_id}]: '{request.query[:80]}...'")

    async def event_stream():
        try:
            # ── Send initial event ──
            yield _sse_event("session", {
                "session_id": session_id,
                "query": request.query,
                "status": "started",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # ── Initialize graph state ──
            initial_state: GraphState = {
                "query": request.query,
                "rewritten_query": "",
                "documents": [],
                "relevant_documents": [],
                "web_results": [],
                "generation": "",
                "citations": [],
                "confidence_score": 0.0,
                "web_search_triggered": False,
                "trace_log": [],
                "document_ids": request.document_ids,
            }

            # ── Execute CRAG graph with streaming ──
            graph = get_crag_graph()

            # Define node display names and icons
            node_info = {
                "retrieve": {"label": "Vector Retrieval", "icon": "🔍", "description": "Searching document vectors..."},
                "grade_documents": {"label": "Document Grading", "icon": "📊", "description": "Evaluating relevance with CrossEncoder..."},
                "rewrite_query": {"label": "Query Rewriter", "icon": "✏️", "description": "Reformulating query for better results..."},
                "web_search": {"label": "Web Search Fallback", "icon": "🌐", "description": "Searching the web for supplementary info..."},
                "generate": {"label": "Answer Generation", "icon": "🤖", "description": "Generating validated response with citations..."},
            }

            # Stream node executions
            accumulated_state = dict(initial_state)
            async for event in graph.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in event.items():
                    info = node_info.get(node_name, {"label": node_name, "icon": "⚙️", "description": ""})

                    # Send step start
                    yield _sse_event("step_start", {
                        "node": node_name,
                        "label": info["label"],
                        "icon": info["icon"],
                        "description": info["description"],
                    })

                    # Small delay for UI animation effect
                    await asyncio.sleep(0.3)

                    # Extract trace data from node output
                    trace_entries = node_output.get("trace_log", [])
                    step_data = trace_entries[-1] if trace_entries else {}

                    # Send step complete
                    yield _sse_event("step_complete", {
                        "node": node_name,
                        "label": info["label"],
                        "icon": info["icon"],
                        "trace": step_data,
                    })

                    # Merge node output into accumulated state
                    for k, v in node_output.items():
                        if k == "trace_log" and isinstance(v, list):
                            accumulated_state.setdefault("trace_log", []).extend(v)
                        else:
                            accumulated_state[k] = v

            # ── Gather final results from accumulated state ──
            answer_data = {
                "session_id": session_id,
                "answer": accumulated_state.get("generation", "No answer generated."),
                "citations": accumulated_state.get("citations", []),
                "confidence_score": accumulated_state.get("confidence_score", 0.0),
                "web_search_triggered": accumulated_state.get("web_search_triggered", False),
            }

            yield _sse_event("answer", answer_data)

            # ── Store session trace in MongoDB ──
            try:
                session_log = SessionLog(
                    session_id=session_id,
                    query=request.query,
                    trace_steps=[],
                    final_response=answer_data,
                    created_at=datetime.now(timezone.utc),
                )
                await sessions_collection().insert_one(session_log.model_dump())

                # Store trace logs
                full_trace = accumulated_state.get("trace_log", [])
                if full_trace:
                    await trace_logs_collection().insert_one({
                        "session_id": session_id,
                        "trace": full_trace,
                        "created_at": datetime.now(timezone.utc),
                    })
            except Exception as e:
                logger.warning(f"Failed to store session log: {e}")

            # ── Done ──
            yield _sse_event("done", {"session_id": session_id, "status": "completed"})
            logger.info(f"✅ Query [{session_id}] completed successfully")

        except Exception as e:
            logger.error(f"❌ Query [{session_id}] failed: {e}", exc_info=True)
            yield _sse_event("error", {
                "session_id": session_id,
                "error": str(e),
                "message": "An error occurred during processing. Please check your configuration.",
            })
            yield _sse_event("done", {"session_id": session_id, "status": "error"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def list_sessions():
    """List all query sessions."""
    col = sessions_collection()
    cursor = col.find({}, {"_id": 0}).sort("created_at", -1).limit(20)
    sessions = await cursor.to_list(length=20)
    return {"sessions": sessions}


@router.get("/sessions/{session_id}/trace")
async def get_session_trace(session_id: str):
    """Get the full trace log for a session."""
    col = trace_logs_collection()
    trace = await col.find_one({"session_id": session_id}, {"_id": 0})
    if not trace:
        return {"trace": [], "session_id": session_id}
    return trace

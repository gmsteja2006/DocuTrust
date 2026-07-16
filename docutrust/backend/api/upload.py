"""
DocuTrust Upload API — Handles PDF uploads, parsing, embedding, and storage.
"""

import io
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from models import UploadResponse, DocumentRecord
from database import documents_collection, chunks_collection
from ingestion.pdf_parser import process_pdf
from ingestion.embedder import embed_and_store_chunks
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF document for ingestion into the RAG pipeline.
    
    Process:
    1. Validate file (PDF, < 50MB)
    2. Extract text and chunk with PyMuPDF
    3. Embed chunks with SentenceTransformer
    4. Store document metadata + chunks in MongoDB
    """
    # ── Validate ──
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    file_size = len(content)

    if file_size > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File exceeds 50MB limit.")

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    logger.info(f"📤 Upload received: {file.filename} ({file_size / 1024:.1f} KB)")

    try:
        # ── Parse & Chunk ──
        pdf_stream = io.BytesIO(content)
        document_id, chunks, page_count, structural_index = process_pdf(pdf_stream, file.filename)

        # ── Store document record ──
        doc_record = DocumentRecord(
            document_id=document_id,
            filename=file.filename,
            file_size=file_size,
            page_count=page_count,
            chunk_count=len(chunks),
            uploaded_at=datetime.now(timezone.utc),
            status="processing",
            structural_index=structural_index,
        )
        await documents_collection().insert_one(doc_record.model_dump())

        # ── Embed & Store chunks ──
        stored_count = await embed_and_store_chunks(chunks, chunks_collection())

        # ── Update document status ──
        await documents_collection().update_one(
            {"document_id": document_id},
            {"$set": {"status": "ready", "chunk_count": stored_count}},
        )

        logger.info(f"✅ Document ready: {document_id} ({stored_count} chunks)")

        return UploadResponse(
            document_id=document_id,
            filename=file.filename,
            page_count=page_count,
            chunk_count=stored_count,
            status="ready",
            message=f"Successfully processed {page_count} pages into {stored_count} searchable chunks.",
        )

    except Exception as e:
        logger.error(f"❌ Upload failed: {e}", exc_info=True)
        err_msg = str(e)
        if "ServerSelectionTimeoutError" in type(e).__name__ or "timeout" in err_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="MongoDB connection timed out. If you are running on Vercel, please make sure you set the MONGODB_URI environment variable to a remote database (like MongoDB Atlas). Localhost is not accessible from Vercel."
            )
        raise HTTPException(status_code=500, detail=f"Document processing failed: {err_msg}")


@router.get("/documents")
async def list_documents():
    """List all uploaded documents."""
    docs_col = documents_collection()
    cursor = docs_col.find({}, {"_id": 0}).sort("uploaded_at", -1)
    documents = await cursor.to_list(length=50)
    return {"documents": documents}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document and its chunks."""
    # Delete chunks
    result_chunks = await chunks_collection().delete_many({"document_id": document_id})
    # Delete document record
    result_doc = await documents_collection().delete_one({"document_id": document_id})

    if result_doc.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "message": f"Deleted document {document_id} and {result_chunks.deleted_count} chunks.",
    }

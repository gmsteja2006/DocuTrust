"""
DocuTrust PDF Parser — Extracts and chunks text from multi-page PDFs.
Uses pypdf (pure Python) for robust extraction with sliding-window chunking.
"""

import pypdf
import uuid
import logging
import re
from typing import BinaryIO
from config import settings

logger = logging.getLogger(__name__)


def extract_pages(doc) -> list[dict]:
    """
    Extract text from every page of an open PDF document.
    """
    pages = []

    for page_num in range(len(doc.pages)):
        page = doc.pages[page_num]
        text = page.extract_text()

        # Detect headings (lines that are short, uppercase, or bold-ish)
        headings = _detect_headings(text)

        pages.append({
            "page_number": page_num + 1,
            "text": text.strip() if text else "",
            "headings": headings,
        })

    return pages


def _detect_headings(text: str) -> list[str]:
    """Heuristic heading detection from text patterns."""
    headings = []
    if not text:
        return headings
    
    lines = text.split('\n')
    for line in lines:
        stripped = line.strip()
        # Headings tend to be short, uppercase, or all caps
        if len(stripped) > 2 and len(stripped) < 100:
            # Check if it looks like a heading (uppercase, ends with colon, etc.)
            if stripped.isupper() or stripped.endswith(':') or stripped.startswith('##'):
                headings.append(stripped)
    
    return headings


def chunk_document(
    pages: list[dict],
    document_id: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> list[dict]:
    """
    Chunk extracted pages using sliding window.
    
    Args:
        pages: Output from extract_pages()
        document_id: Parent document ID
        chunk_size: Max words per chunk (defaults to config)
        chunk_overlap: Overlap words between chunks (defaults to config)
    
    Returns:
        List of chunk dicts ready for embedding and storage.
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    chunks = []
    chunk_index = 0

    for page in pages:
        text = page["text"]
        if not text.strip():
            continue

        # Split into words for sliding window
        words = text.split()
        current_heading = page["headings"][0] if page["headings"] else None

        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk_text = " ".join(words[start:end])

            # Clean up whitespace
            chunk_text = re.sub(r'\s+', ' ', chunk_text).strip()

            if len(chunk_text) > 20:  # Skip tiny fragments
                chunks.append({
                    "chunk_id": f"{document_id}_chunk_{chunk_index}",
                    "document_id": document_id,
                    "text": chunk_text,
                    "page_number": page["page_number"],
                    "chunk_index": chunk_index,
                    "section_title": current_heading,
                    "metadata": {
                        "word_count": end - start,
                        "char_count": len(chunk_text),
                    },
                })
                chunk_index += 1

            # Slide forward
            start += chunk_size - chunk_overlap

    logger.info(
        f"📄 Document {document_id}: {len(pages)} pages → {len(chunks)} chunks "
        f"(size={chunk_size}, overlap={chunk_overlap})"
    )
    return chunks


def process_pdf(pdf_stream: BinaryIO, filename: str) -> tuple[str, list[dict], int, list[dict]]:
    """
    Full pipeline: extract structure, text, and outline, and chunk a PDF using pypdf.
    
    Returns:
        (document_id, chunks[], page_count, structural_index[])
    """
    document_id = str(uuid.uuid4())[:12]

    try:
        doc = pypdf.PdfReader(pdf_stream)
        page_count = len(doc.pages)
    except Exception as e:
        logger.error(f"Failed to read PDF {filename}: {e}")
        raise

    # 1. Extract structural outline (bookmarks/TOC)
    structural_index = []
    try:
        # pypdf doesn't have native TOC, so we build from page content
        logger.info(f"Building outline from page headings in {filename}...")
    except Exception as e:
        logger.warning(f"Error parsing outline: {e}")

    # Build heuristic outlines from page headings
    seen_headings = set()
    for page_num in range(page_count):
        headings = _detect_headings(doc.pages[page_num].extract_text() or "")
        for heading in headings:
            if heading not in seen_headings and len(structural_index) < 100:
                structural_index.append({
                    "title": heading,
                    "page_number": page_num + 1,
                    "level": 1
                })
                seen_headings.add(heading)

    # 2. Extract page contents
    pages = []
    for page_num in range(page_count):
        text = doc.pages[page_num].extract_text() or ""
        
        # Map headings that belong to this page
        page_headings = [item["title"] for item in structural_index if item["page_number"] == page_num + 1]

        pages.append({
            "page_number": page_num + 1,
            "text": text.strip(),
            "headings": page_headings,
        })

    # 3. Chunk documents
    chunks = chunk_document(pages, document_id)

    logger.info(f"✅ Processed '{filename}': {page_count} pages, {len(chunks)} chunks, {len(structural_index)} outline entries")
    return document_id, chunks, page_count, structural_index


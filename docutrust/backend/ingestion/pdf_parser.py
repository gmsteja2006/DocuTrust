"""
DocuTrust PDF Parser — Extracts and chunks text from multi-page PDFs.
Uses PyMuPDF (fitz) for robust extraction with sliding-window chunking.
"""

import fitz  # PyMuPDF
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

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")

        # Detect headings (lines that are short, uppercase, or bold-ish)
        headings = _detect_headings(page)

        pages.append({
            "page_number": page_num + 1,
            "text": text.strip(),
            "headings": headings,
        })

    return pages


def _detect_headings(page) -> list[str]:
    """Heuristic heading detection from font size analysis."""
    blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
    headings = []

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                # Headings tend to have larger font sizes
                if span["size"] >= 14 and len(span["text"].strip()) > 2:
                    headings.append(span["text"].strip())
                # Or are bold uppercase short strings
                elif (
                    "bold" in span["font"].lower()
                    and len(span["text"].strip()) < 80
                    and len(span["text"].strip()) > 2
                ):
                    headings.append(span["text"].strip())

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
    Full pipeline: extract structure, text, and outline, and chunk a PDF.
    
    Returns:
        (document_id, chunks[], page_count, structural_index[])
    """
    document_id = str(uuid.uuid4())[:12]

    doc = fitz.open(stream=pdf_stream.read(), filetype="pdf")
    page_count = len(doc)

    # 1. Extract structural outline (bookmarks/TOC)
    structural_index = []
    try:
        toc = doc.get_toc(simple=True)
        if toc:
            logger.info(f"Native TOC found with {len(toc)} entries in {filename}.")
            for item in toc:
                pg_num = max(1, min(item[2], page_count))
                structural_index.append({
                    "title": item[1].strip(),
                    "page_number": pg_num,
                    "level": item[0]
                })
    except Exception as e:
        logger.warning(f"Error parsing native TOC: {e}")

    # Fallback to page heading heuristics if native TOC is empty
    if not structural_index:
        logger.info(f"No native TOC found in {filename}. Building heuristic outlines...")
        for page_num in range(page_count):
            page = doc[page_num]
            headings = _detect_headings(page)
            seen_headings = set()
            for heading in headings:
                if heading not in seen_headings:
                    structural_index.append({
                        "title": heading,
                        "page_number": page_num + 1,
                        "level": 1
                    })
                    seen_headings.add(heading)

    # Limit outline to 100 items to avoid cluttering DB
    structural_index = structural_index[:100]

    # 2. Extract page contents
    pages = []
    for page_num in range(page_count):
        page = doc[page_num]
        text = page.get_text("text")

        # Map headings that belong to this page
        page_headings = [item["title"] for item in structural_index if item["page_number"] == page_num + 1]

        pages.append({
            "page_number": page_num + 1,
            "text": text.strip(),
            "headings": page_headings,
        })

    doc.close()

    # 3. Chunk documents
    chunks = chunk_document(pages, document_id)

    logger.info(f"✅ Processed '{filename}': {page_count} pages, {len(chunks)} chunks, {len(structural_index)} outline entries")
    return document_id, chunks, page_count, structural_index


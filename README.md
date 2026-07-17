# 🛡️ DocuTrust — Enterprise Advanced RAG Platform

**DocuTrust** is a production-ready, self-correcting Retrieval-Augmented Generation (RAG) system for enterprise document analysis. It uses the **Corrective RAG (CRAG)** pattern with a LangGraph StateGraph to automatically validate, rewrite, and supplement answers with web search when document retrieval is insufficient.

---

## ✨ Features

| Feature | Details |
|---|---|
| **CRAG Pipeline** | Retrieve → Grade → (Rewrite + Web Search) → Generate |
| **Vector Retrieval** | `all-MiniLM-L6-v2` bi-encoder embeddings stored in MongoDB |
| **CrossEncoder Grading** | Local `ms-marco-MiniLM-L-6-v2` reranker for relevance scoring |
| **Multi-LLM Support** | Google Gemini, OpenAI GPT, or Local Extractive (no API key) |
| **Real-time SSE Streaming** | Each agent step streamed live to the frontend |
| **PDF Structure Extraction** | Native TOC + heuristic heading detection via PyMuPDF |
| **Client Profiles** | Per-department LLM/threshold configuration switchable at runtime |
| **Strict Citations** | Every claim mapped to a source document, page, and chunk |
| **Web Search Fallback** | DuckDuckGo search when document retrieval is insufficient |

---

## 🏗️ Architecture

```
┌─────────────┐       ┌──────────────────────────────────────────────┐
│   Frontend  │──SSE──│              FastAPI Backend                 │
│  (HTML/JS)  │◄──────│                                              │
└─────────────┘       │  /api/upload ──► PDF Parser ──► Embedder    │
                      │  /api/query  ──► CRAG LangGraph              │
                      │                   │                          │
                      │          ┌────────▼────────┐                 │
                      │          │    CRAG Graph    │                 │
                      │          │  Retrieve        │                 │
                      │          │    │             │                 │
                      │          │  Grade Docs      │                 │
                      │          │    │             │                 │
                      │          │  ┌─┴─────────┐  │                 │
                      │          │  │ Relevant? │  │                 │
                      │          │  └─┬───────┬─┘  │                 │
                      │          │   Yes      No   │                 │
                      │          │    │     Rewrite │                 │
                      │          │    │     + Web   │                 │
                      │          │    └──►Generate  │                 │
                      │          └─────────────────┘                 │
                      │                                              │
                      │  MongoDB: documents, chunks, sessions        │
                      └──────────────────────────────────────────────┘
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- MongoDB running locally on port 27017 (or provide `MONGODB_URI`)
- (Optional) Google Gemini API key or OpenAI API key

### 1. Install dependencies

```powershell
cd "EduExpose prj"
python -m venv .venv
.venv\Scripts\activate
pip install -r docutrust/backend/requirements.txt
```

### 2. Configure environment

```powershell
cd docutrust/backend
copy .env.example .env
```

Edit `.env` and fill in your values:
```env
LLM_PROVIDER=google
GOOGLE_API_KEY=your-google-api-key-here
MONGODB_URI=mongodb://localhost:27017
```

> **No API key?** The system works in **Local Extractive Mode** — set `LLM_PROVIDER=mock` or leave keys blank. Answers are generated locally using extractive summarization.

### 3. Start the server

```powershell
# From the EduExpose prj directory, with .venv activated:
python docutrust/backend/main.py
```

Or using uvicorn:
```powershell
cd docutrust/backend
uvicorn main:app --reload --port 8000
```

### 4. Open the app

Visit: **http://localhost:8000**

---

## 📁 Project Structure

```
docutrust/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Pydantic Settings (env-driven)
│   ├── database.py          # MongoDB async client + indexes
│   ├── models.py            # Pydantic data models
│   ├── requirements.txt
│   ├── .env.example
│   ├── api/
│   │   ├── upload.py        # POST /api/upload (PDF ingestion)
│   │   ├── query.py         # POST /api/query  (SSE streaming CRAG)
│   │   └── client.py        # GET/POST/PUT/DELETE /api/profiles
│   ├── ingestion/
│   │   ├── pdf_parser.py    # PyMuPDF extraction + chunking
│   │   └── embedder.py      # SentenceTransformer embedding
│   └── rag/
│       ├── graph.py         # LangGraph StateGraph (CRAG flow)
│       ├── nodes.py         # Individual pipeline nodes
│       ├── grader.py        # CrossEncoder relevance grading
│       └── state.py         # GraphState TypedDict
└── frontend/
    ├── index.html           # Full 3-pane UI
    ├── style.css            # Design system + animations
    └── app.js               # Frontend logic (SSE, upload, rendering)
```

---

## ⚙️ Configuration

All settings can be overridden via `.env` or environment variables:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `google` | `google`, `openai`, or `mock` |
| `GOOGLE_API_KEY` | — | Google Gemini API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `LLM_MODEL` | `gemini-1.5-flash` | Model name |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | CrossEncoder model |
| `RELEVANCE_THRESHOLD` | `0.5` | Min score for document relevance |
| `RETRIEVAL_TOP_K` | `10` | Chunks to retrieve per query |
| `CHUNK_SIZE` | `512` | Words per chunk |
| `CHUNK_OVERLAP` | `64` | Overlap words between chunks |

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload` | Upload a PDF for ingestion |
| `GET` | `/api/documents` | List all uploaded documents |
| `DELETE` | `/api/documents/{id}` | Delete a document and its chunks |
| `POST` | `/api/query` | Run CRAG query (SSE stream) |
| `GET` | `/api/sessions` | List recent query sessions |
| `GET` | `/api/sessions/{id}/trace` | Get full pipeline trace for a session |
| `GET` | `/api/profiles` | List client profiles |
| `POST` | `/api/profiles` | Create a client profile |
| `PUT` | `/api/profiles/{id}/activate` | Set active profile |
| `DELETE` | `/api/profiles/{id}` | Delete a profile |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/health` | Health check |

---

## 🧩 Client Profiles

Client profiles let you configure different LLM providers and thresholds per department without redeploying:

1. Click the **+** button in the header to create a profile
2. Select the profile from the dropdown to activate it
3. All subsequent queries use that profile's settings

---

## 🔧 Development

```powershell
# Run with auto-reload
uvicorn main:app --reload --port 8000

# Check API docs
http://localhost:8000/docs
```

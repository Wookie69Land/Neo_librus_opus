# AI Book Recommendation Feature

## Overview

The AI recommendation feature allows authenticated users to submit a free-text query (e.g. *"cozy historical novels set in Poland"*) and receive a ranked, personalised list of books available in the library system.

The pipeline is built with **LangGraph** (graph orchestration), **LangChain + Google Gemini** (LLM nodes), and **ARQ** (async background task queue with Redis). The API is non-blocking: the caller submits a job and polls for the result.

---

## Architecture

```
Client
  │
  │ POST /api/ai/recommendations
  ▼
Django Ninja API
  │  enqueue_job via ARQ
  ▼
Redis (job queue)
  │
  ▼
ARQ Worker ──► run_ai_recommendation_pipeline()
                │
                ▼
          LangGraph Pipeline
          ┌────────────────────────────────────────────────────────────┐
          │                                                            │
          │  [understand_query]  ──►  [fetch_candidates]              │
          │       (Node 1)                  (Node 2 – DB only)        │
          │                                      │                    │
          │                                      ▼                    │
          │                           [analyze_statistics]            │
          │                                (Node 3)                   │
          │                                      │                    │
          │                                      ▼                    │
          │                            [compose_response]             │
          │                                (Node 4)                   │
          └────────────────────────────────────────────────────────────┘
                │
                ▼
          Result stored in Redis (TTL: 1 hour)
                │
  │ GET /api/ai/recommendations/{request_id}
  ▼
Client polls until status = "completed"
```

---

## Pipeline Nodes

### Node 1 — `understand_query`

| Property   | Value |
|------------|-------|
| **Model**  | `llama-3.1-8b-instant` (env: `AI_MODEL_QUERY`) |
| **Role**   | `LLMRole.QUERY` |
| **Task**   | Light NLP — parse free text into structured search parameters |

**Input state fields:**
- `raw_query` — the user's original free-text string
- `language` — optional explicit language filter from the API request

**Output state fields:**
- `normalized_intent` — clean English restatement of the request
- `extracted_keywords` — 3–7 topic/genre/author terms
- `language_hint` — detected ISO 639-1 language code, or `null`
- `audience` — `"children"` | `"young_adult"` | `"adult"` | `"academic"` | `null`
- `period_from` / `period_to` — inferred publication year range (both nullable)

**Why `llama-3.1-8b-instant`:** The task is structured JSON extraction from short text. It is latency-sensitive (runs first in the chain) and does not require deep reasoning — the 8B model running on Groq's hardware is ideal: fast, free, and sufficient for NLP extraction.

**Fallback:** If the LLM call fails or returns malformed output, raw keywords are extracted by splitting the query on whitespace. The node sets a `node_errors` entry but does not abort the pipeline.

---

### Node 2 — `fetch_candidates`  *(no LLM)*

| Property   | Value |
|------------|-------|
| **Model**  | None — pure database query |
| **Task**   | Retrieve up to 50 book candidates from the DB matching extracted keywords |

**Input state fields:**
- `extracted_keywords`, `language_hint`, `audience`, `period_from`, `period_to`
- `include_unavailable` — whether to include books with no copies

**Output state fields:**
- `candidate_books` — list of book metadata dicts (title, authors, ISBN, language, category, availability per library)
- `total_candidates` — count of candidates fetched
- `categories_found` / `languages_found` — unique values in the candidate set

**Implementation:** `RecommendationRepository.fetch_candidates()` — uses Django ORM with full-text / keyword matching and `prefetch_related` for availability data.

---

### Node 3 — `analyze_statistics`

| Property   | Value |
|------------|-------|
| **Model**  | `llama-3.3-70b-versatile` (env: `AI_MODEL_STATS`) |
| **Role**   | `LLMRole.STATS` |
| **Task**   | Analytical reasoning — score each candidate 0.0–1.0 for relevance |

**Input state fields:**
- `normalized_intent` — the refined search intent from Node 1
- `candidate_books` — all metadata for up to 50 candidates

**Output state fields:**
- `scored_candidates` — list of `{book_id, relevance_score, reasoning}` dicts
- `statistical_analysis` — narrative summary of the candidate pool

**Why `llama-3.3-70b-versatile`:** This node receives a large structured payload (up to 50 books as JSON) and must reason across all candidates simultaneously to produce consistent comparative scores. Llama 3.3 70B running on Groq provides strong reasoning capability and extended context window, while remaining fully free to use.

**Scoring rules:** Scores are assigned on textual/thematic relevance only — availability is explicitly excluded to avoid biasing recommendations toward popular books.

**Fallback:** If the node fails, candidates pass through with equal relevance scores of `0.5`.

---

### Node 4 — `compose_response`

| Property   | Value |
|------------|-------|
| **Model**  | `llama-3.3-70b-versatile` (env: `AI_MODEL_RESPONSE`) |
| **Role**   | `LLMRole.RESPONSE` |
| **Task**   | Compose personalised, engaging recommendation text for each selected book |

**Input state fields:**
- `raw_query` — the original user query (for tone matching)
- `normalized_intent` — refined intent
- `statistical_analysis` — analysis narrative
- `scored_candidates` — ranked list with scores and reasoning
- `max_results` — how many books to include in the response

**Output state fields:**
- `query_interpretation` — one friendly sentence describing what the user was looking for
- `final_recommendations` — list of `{book_id, why_recommended}` dicts
- `stats_narrative` — short summary of what the library catalogue contained

**Why `llama-3.3-70b-versatile`:** This node produces the output the user actually reads. Llama 3.3 70B handles Polish text well, produces specific and contextually appropriate book descriptions, and is available for free via Groq's generous free tier.

**Fallback:** If the node fails, books are returned with a generic `why_recommended` message derived from their category and author.

---

## Model Summary

| Node | Task | Model | Rationale |
|------|------|-------|-----------|
| `understand_query` | NLP intent extraction | `llama-3.1-8b-instant` (Groq) | Fast, free, sufficient for JSON extraction |
| `fetch_candidates` | DB query | — | Pure ORM, no LLM |
| `analyze_statistics` | Relevance scoring (up to 50 books) | `llama-3.3-70b-versatile` (Groq) | Strong reasoning, large context, free tier |
| `compose_response` | Personalised recommendation text | `llama-3.3-70b-versatile` (Groq) | Best free-tier language quality |

---

## API Reference

### `POST /api/ai/recommendations`

Enqueue a new recommendation job.

**Authentication:** Bearer token required.

**Request body:**
```json
{
  "query": "cozy historical novels set in Poland",
  "max_results": 10,
  "language": "pl",
  "include_unavailable": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | ✅ | Free-text search intent (3–500 characters) |
| `max_results` | integer | ❌ | Number of books to return, 1–20 (default: 10) |
| `language` | string | ❌ | ISO 639-1 filter (`"pl"`, `"en"`, …) |
| `include_unavailable` | boolean | ❌ | Include books with 0 available copies (default: true) |

**Response `202 Accepted`:**
```json
{
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending"
}
```

---

### `GET /api/ai/recommendations/{request_id}`

Poll for the result of an enqueued job.

**Authentication:** Bearer token required.

**Response `202 Accepted`** — job still running:
```json
{
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending"
}
```

**Response `200 OK`** — job completed:
```json
{
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed",
  "query_interpretation": "The user is looking for cosy historical fiction set in Poland.",
  "recommendations": [
    {
      "book_id": 42,
      "title": "Lalka",
      "isbn": "9788307035024",
      "authors": ["Bolesław Prus"],
      "language": "pl",
      "score": 0.94,
      "why_recommended": "A cornerstone of Polish realist fiction, Lalka follows a Warsaw merchant navigating class and love — deeply rooted in 19th-century Poland and acclaimed for its rich social tapestry.",
      "availability": [
        { "library_id": 1, "library_name": "Biblioteka Główna", "is_available": true }
      ]
    }
  ],
  "stats_summary": {
    "total_candidates": 23,
    "categories_found": ["Fiction", "Historical Fiction"],
    "languages_found": ["pl"],
    "narrative": "The catalogue contains a strong selection of Polish historical fiction spanning the 19th and early 20th centuries."
  },
  "generated_at": "2025-06-10T14:32:01.123456Z",
  "error": null
}
```

**Response `404 Not Found`** — job expired or never existed:
```json
{ "detail": "Job not found or result expired." }
```

---

## Data Flow

```
User query (free text)
        │
        ▼
POST /api/ai/recommendations
        │  generates UUID request_id
        │  enqueues ARQ job
        ▼
ARQ worker picks up job
        │
        ▼
  RecommendationState initialised
  { request_id, raw_query, max_results, language, include_unavailable }
        │
        ▼ [understand_query — gemini-2.0-flash]
  + normalized_intent, extracted_keywords, language_hint, audience, period_from/to
        │
        ▼ [fetch_candidates — DB only]
  + candidate_books (up to 50), total_candidates, categories_found, languages_found
        │
        ▼ [analyze_statistics — gemini-2.5-flash-preview]
  + scored_candidates [{book_id, relevance_score, reasoning}], statistical_analysis
        │
        ▼ [compose_response — gemini-2.5-pro]
  + query_interpretation, final_recommendations [{book_id, why_recommended}], stats_narrative
        │
        ▼
  Result dict serialised and stored in Redis (TTL 1 hour)
        │
        ▼
GET /api/ai/recommendations/{request_id}  →  200 + full response
```

---

## Configuration

All AI settings are read from environment variables (see `app/core/settings/base.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | `""` | Groq API key — obtain free at [console.groq.com](https://console.groq.com/) |
| `GEMINI_API_KEY` | `""` | Google Generative AI API key (only needed when `AI_PROVIDER=gemini`) |
| `AI_PROVIDER` | `groq` | LLM provider — `groq` or `gemini` |
| `AI_MODEL_QUERY` | `llama-3.1-8b-instant` | Model for the query understanding node |
| `AI_MODEL_STATS` | `llama-3.3-70b-versatile` | Model for the statistical analysis node |
| `AI_MODEL_RESPONSE` | `llama-3.3-70b-versatile` | Model for the response composition node |
| `AI_TIMEOUT_SECONDS` | `60` | Per-node LLM call timeout |
| `AI_MAX_TOKENS` | `2048` | Max output tokens per LLM call |

---

## Worker & Redis

The pipeline runs inside the **ARQ** background worker (`app/tasks/worker.py`).

- **Job queue:** Redis (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DATABASE` settings)
- **Result TTL:** 1 hour (`WorkerSettings.keep_result = 3600`) — after which `GET` returns 404
- **Redis pool:** Created fresh per API request (not cached at module level) to avoid event loop conflicts with Django's WSGI/ASGI thread-per-request model

To run the worker locally:
```bash
python -m arq app.tasks.worker.WorkerSettings
```

Or via Docker Compose:
```bash
docker compose up worker
```

---

## LangGraph Integration

The graph is defined in `app/ai/recommendations/graph.py` and compiled once at module import:

```python
recommendation_graph = _builder.compile()
```

The compiled graph is safe for concurrent invocations — each `ainvoke` call gets its own state copy. The graph edges are all linear (no branching or cycles):

```
START → understand_query → fetch_candidates → analyze_statistics → compose_response → END
```

---

## Error Handling

Each LLM node wraps its call in a try/except and appends to `node_errors` in the state rather than raising. This means partial failures degrade gracefully:

- If `understand_query` fails → raw whitespace-split keywords are used
- If `analyze_statistics` fails → all candidates pass through with score `0.5`
- If `compose_response` fails → books are returned with a generic explanation

The `error` field in the API response is populated from the ARQ job's exception if the entire task crashes.

---

## Known Limitations & Future Work

- **Vector search:** Current candidate retrieval is keyword/ORM-based. Switching to embedding-based vector search (e.g. pgvector + `text-embedding-004`) would significantly improve semantic recall.
- **Rate limiting:** No per-user rate limiting on the recommendation endpoint yet.
- **Retry policy:** LLM calls have no automatic retry with backoff; a transient Gemini error will fail the node.
- **Streaming:** The pipeline returns the full result in one batch. Streaming node-by-node progress to the client is not implemented.
- **Multi-language prompts:** Prompts are in English regardless of `language_hint`; Gemini handles translation internally but a language-aware prompt could improve output quality.
- **Tests:** Integration tests for the pipeline nodes are pending (see `TODO.md`).

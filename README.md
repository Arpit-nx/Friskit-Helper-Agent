# General RAG Support Assistant (Groq + GPT-OSS 120B)

This refactor is a document-driven RAG application. It is **not hard-coded to Friskit**. The supplied Friskit catalog is one source among any Markdown documents placed in `data/knowledge/` and clearly labelled examples in `data/examples/`.

## Model / provider

- Provider: Groq Cloud
- Model ID: `openai/gpt-oss-120b`
- API: Groq's OpenAI-compatible Chat Completions endpoint (the Groq SDK is used)
- Key: `GROQ_API_KEY` in `.env`

The official model ID is `openai/gpt-oss-120b`. Do not use `120b minigptoss` as the model ID.

## Pipeline

```text
JSON / Markdown sources
        |
        v
[1] INGESTION  -- parse files, attach source metadata
        |
        v
[2] CHUNKING   -- split long docs into overlapping chunks
        |
        v
[3] INDEXING   -- BM25 + local sentence-transformer embeddings
        |
        v
[4] RETRIEVAL  -- rank chunks for the user question
        |
        v
[5] RELEVANCE GATE -- stop if no sufficiently relevant context
        |
        v
[6] GROQ LLM   -- answer only from retrieved context
        |
        v
[7] RESPONSE   -- answer + sources + per-stage trace
```

### Retrieval details

Default `RETRIEVAL_MODE=hybrid` combines normalized BM25 scores (55%) with cosine similarity from `sentence-transformers/all-MiniLM-L6-v2` (45%). Embeddings are created locally; no vector database is required. If the embedding model cannot load, the app logs the failure and falls back to BM25. Set `RETRIEVAL_MODE=bm25` to skip embeddings.

The score is a ranking signal, **not a calibrated probability**. Tune `MIN_RELEVANCE_SCORE` against a set of real questions. Do not assume the sample value is production-ready.

## Project layout

```text
app/
  config.py       environment configuration
  schemas.py      API request validation
  ingestion.py    JSON/Markdown loading + chunking
  retriever.py    BM25 + semantic hybrid retrieval
  generator.py    Groq prompt and model call
  pipeline.py     orchestration and stage-level failure handling
  main.py         FastAPI routes and lifecycle

data/
  help-catalog.json        supplied Friskit source (67 topics, root-level array)
  knowledge/               add your own product documentation here
  examples/                generic training examples, not Friskit facts
static/index.html          minimal test UI with retrieval inspection
 tests/                    unit tests
```

## Run on Windows PowerShell

```powershell
cd friskit_help_assistant
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set GROQ_API_KEY
# Set CORS_ALLOWED_ORIGINS to a comma-separated list of trusted frontend origins.
uvicorn app.main:app --reload
```

First hybrid startup downloads the sentence-transformer model. For a lightweight first run, set `RETRIEVAL_MODE=bm25` in `.env`; this avoids the model download. Open http://127.0.0.1:8000 and http://127.0.0.1:8000/docs.

## API

```bash
curl -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"question":"How do I add a dealer mapping?","role":"admin"}'
curl -X POST http://127.0.0.1:8000/api/retrieve -H "Content-Type: application/json" -d '{"question":"How do I add a dealer mapping?","role":"admin"}'
curl http://127.0.0.1:8000/health
```

- `POST /api/chat`: full RAG pipeline.
- `POST /api/retrieve`: inspect retrieval without calling Groq; useful for isolating retrieval problems.
- `POST /api/reindex`: reload source documents and rebuild chunks/index after adding or editing docs.
- `GET /health`: counts, selected retrieval mode, model/key status and ingestion error.

## Failure diagnosis

| Symptom | Likely stage | Where to inspect |
|---|---|---|
| App starts degraded / zero chunks | ingestion or indexing | startup logs, `/health`, JSON syntax, document paths |
| Correct document absent from results | ingestion/chunking | `/api/retrieve`, chunk contents, supported file type |
| Relevant text exists but ranks low | retrieval | compare BM25/semantic scores; tune chunk size, overlap, query terms |
| Wrong role's content appears | authorization filter | demo role filter; production must use authenticated server-side identity |
| No context / no answer | relevance gate | `MIN_RELEVANCE_SCORE`, top score, `/api/retrieve` |
| Relevant sources but no answer | Groq generation | `GROQ_API_KEY`, model ID, rate limit, network, API error logs |
| Answer makes unsupported claims | grounding/prompt/evidence | inspect returned source chunks; improve docs; keep the model constrained |

Every chat response includes a `trace` array indicating which stages passed or failed. The server logs use stage labels such as `INGEST_COMPLETE`, `CHUNKING_COMPLETE`, `RETRIEVAL_COMPLETE`, `RELEVANCE_CHECK`, and `GROQ_REQUEST_OK`.

## Important design boundaries

1. Friskit catalog records are product-specific evidence. Generic example docs are explicitly marked as training examples and the prompt tells the model not to treat them as Friskit facts.
2. The model does not create routes, permissions, tour IDs or page metadata. The source record carries metadata; the prototype does not invent missing tour IDs.
3. The role field is only for local testing. In production, derive role from the authenticated backend session and enforce permissions server-side.
4. This prototype does not execute website actions or launch tours. That can be added as a separate trusted frontend integration after the RAG answer is reliable.
5. The app fails closed: if retrieval finds no relevant context, it does not call the LLM; if Groq fails, it returns a generation error rather than fabricating an answer.
6. The hybrid score and sample docs are starting points. Build a representative evaluation set before production.

## Add your own knowledge

Create Markdown files under `data/knowledge/`, one workflow or page per file. Prefer headings such as Purpose, Prerequisites, Navigation, Steps, Controls, Expected Result, Common Issues and Related Pages. Then call `POST /api/reindex` or restart the server.

Generic examples belong under `data/examples/`; keep the `TRAINING EXAMPLE ONLY` label and do not put unverified product behaviour in official product docs.

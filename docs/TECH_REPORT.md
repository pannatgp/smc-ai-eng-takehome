# Technical Report — Financial Q&A Chatbot

**A grounded question-answering system for financials of U.S. public companies.**
Version: 1.0 · Last updated: 2026-07-09

---

## 1. What this system is

This is a web application where a signed-in user asks financial questions — in **Thai or
English** — and gets answers that are **grounded entirely in a fixed, provided dataset**. It
never uses the language model's own world knowledge for facts.

It draws on two kinds of data:

- **Structured financials** (income-statement figures) held in **PostgreSQL**.
- **Qualitative text** extracted from **10-K annual filings**, embedded and held in a
  **Pinecone** vector index.

The single most important property is **no hallucination**: when the data needed to answer a
question is not available, the assistant says so plainly instead of inventing a figure or an
explanation. Everything the assistant states is traceable to a source shown to the user.

### What it can answer

| Type | Example | Sources used |
| --- | --- | --- |
| Numeric lookup | "Summarize Apple's net income 2022–2025" | SQL only |
| Qualitative / strategy | "Compare Google's and Meta's revenue structure and strategy" | 10-K text (+ SQL) |
| Mixed reasoning | "Which of MSFT/AAPL/GOOG/FB grew fastest in 2024–2025 and why?" | SQL (growth) + 10-K (why) |
| Out-of-coverage | "What was Tesla's R&D spend?" | — → **explicit refusal** |

---

## 2. Data and its coverage

| Store | Contents | Scope |
| --- | --- | --- |
| PostgreSQL `financial_data` | company, ticker, sector, year, revenue, gross_profit, operating_income, net_income | **192 rows** — 49 companies × FY2022–2025 |
| Pinecone (10-K chunks) | chunked filing text + `source`, `page` metadata | **4072 vectors** from **4 filings**: Alphabet, Amazon, Apple, Meta (FY2025) |

**The coverage is deliberately uneven, and handling that is the core of the design.** A
company can have financial numbers but no filing text. For example, **Microsoft has SQL
figures but no 10-K** in the vector store — so the system can report Microsoft's revenue and
growth, but must refuse to explain the *why* behind it.

The embeddings are **OpenAI `text-embedding-3-small` at 512 dimensions**, matching the
provided fixture exactly. Query embeddings must use the same model and dimension, or vector
search would be meaningless.

---

## 3. Architecture

```
   Browser (React + Vite)
        │  JWT in Authorization header
        ▼
   FastAPI  ──  /auth/register   /auth/login   /chat   /chat/history   /health
        │
        ▼
   LangGraph — a deterministic graph of nodes with conditional edges
        │
        ├── extract   (LLM)   parse question → companies, years, intent, EN search query
        ├── sql               query PostgreSQL; compute growth % in Python
        ├── vector            per-company search of Pinecone; registry decides availability
        └── synthesize (LLM)  compose a grounded answer in the user's language
        │
        ▼
   { answer, citations }  ──▶  rendered with a "Sources" panel in the UI
```

**Two datastores, one gate, an LLM only at the edges.** The defining design choice is that
routing, the "does this company have a filing?" gate, and the growth arithmetic are done in
**code**, not by the language model. The LLM is used only to (a) turn a natural-language
question into structured parameters and (b) phrase the final answer from data it is handed.
This makes correct behavior a property of the control flow rather than of prompt adherence.

### Components

| Layer | Technology | Role |
| --- | --- | --- |
| Frontend | React 19, Vite, TypeScript | Login/register + chat UI with a citations panel |
| Backend | FastAPI (Python 3.13) | Auth, chat API, orchestration |
| Agent | LangGraph 1.x | Deterministic extract→sql→vector→synthesize graph |
| LLM | OpenAI `gpt-4o-mini` | Parameter extraction + answer synthesis |
| Embeddings | OpenAI `text-embedding-3-small` @512 | Query-time vector search |
| Structured DB | PostgreSQL 16 | Financial figures, users, message history, filing registry |
| Vector DB | Pinecone (local) | 10-K chunk retrieval |
| Infra | Docker Compose | Local Postgres + pinecone-local |

---

## 4. How a question is answered (request lifecycle)

1. **Authenticate.** The request carries a JWT bearer token; FastAPI resolves it to a user or
   rejects with 401. Chat endpoints are protected.
2. **Load history.** Recent messages for that user are loaded so follow-up questions have
   context.
3. **extract** *(LLM, structured output)* — the question is parsed into: `companies`,
   `years`, `needs_financials`, `needs_qualitative`, `needs_growth`, `growth_metric`, and a
   concise **English** `search_query` for semantic search (English queries retrieve better
   against English filings, even for Thai questions).
4. **Conditional routing** — edges decide the path in code:
   - numeric-only question → `sql → synthesize`
   - qualitative question → `sql → vector → synthesize` (or `vector → synthesize`)
5. **sql** — `query_financials()` runs a **parameterized** query (never text-to-SQL) and, if a
   growth question, computes the percentage change **in Python** (exact, deterministic).
6. **vector** — for each requested company, the **registry** decides if a filing exists. Filers
   are searched **individually** in Pinecone; non-filers (e.g. Microsoft) are collected into an
   explicit "no filing" list. This is the deterministic coverage gate.
7. **synthesize** *(LLM)* — the model receives a structured **DATA CONTEXT** (SQL rows, computed
   growth, retrieved 10-K excerpts, and the explicit "NO 10-K FILING AVAILABLE" list) and is
   instructed to use nothing else, cite what it uses, and reply in the user's language.
8. **Persist + respond.** Both turns are saved; the response returns `answer` plus `citations`
   (SQL rows and 10-K source/page), which the UI renders under the answer.

---

## 5. The anti-hallucination design (why answers are trustworthy)

The no-hallucination requirement is enforced at **four** levels, so it does not rely on the
model "behaving":

1. **The LLM has no data of its own to draw on.** It only ever sees data placed into the DATA
   CONTEXT by the deterministic nodes. It is not given database access or free-form tools.
2. **Numbers come from SQL; growth is computed in Python.** The model is told to reuse the
   provided figures verbatim and never to compute or estimate — removing arithmetic errors and
   invented numbers.
3. **The coverage gate is code, not judgment.** Whether a company has a 10-K is answered by the
   registry, and non-filers are surfaced to the model as an explicit "no filing" list it must
   report. It cannot silently invent a reason for Microsoft.
4. **Everything is cited.** Figures cite company/year; qualitative claims cite filing + page.
   The UI shows these, so a user can verify grounding at a glance.

**Worked example — the coverage trap (Q3).** *"Which of Microsoft, Apple, Google, Facebook grew
fastest in 2024–2025, and why?"* The system computes all four growth rates from SQL
(Meta highest at ~22%), searches Apple's, Google's, and Meta's filings individually for the
"why" (each gets a cited factor), and states plainly that **no 10-K filing exists for
Microsoft**, so its driver cannot be determined — while still reporting Microsoft's numbers.

---

## 6. Authentication and security

- **JWT-based auth.** `POST /auth/register` creates a user; `POST /auth/login` returns a signed
  JWT (HS256, 60-minute expiry). `/chat` and `/chat/history` require a valid token via an
  `OAuth2PasswordBearer` dependency.
- **Passwords are bcrypt-hashed** (cost 12) and never stored or logged in plaintext. Login
  re-hashes and compares; nothing is ever decrypted.
- **Separable module.** Auth lives in `app/auth/` (router, security, dependency) so roles,
  refresh tokens, or OAuth can be added without touching the retrieval graph.
- **Local-dev caveats (documented, not shipped as production):** traffic is plain HTTP on
  localhost, and the frontend stores the JWT in `localStorage` (readable by JS). Production
  would add TLS and consider an httpOnly cookie.

---

## 7. How to run it

Full steps are in the root [`README.md`](../README.md). In brief:

```bash
cp .env.example .env          # set OPENAI_API_KEY and a JWT_SECRET_KEY
docker compose up -d          # Postgres (auto-loads financial_data.sql) + pinecone-local

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.load_vectors        # upsert vectors + register filing sources
uvicorn app.main:app --port 8000      # API at http://localhost:8000 (docs at /docs)

cd ../frontend
npm install && npm run dev            # UI at http://localhost:5173
```

Then register an account at http://localhost:5173 and ask a question.

> **Note:** pinecone-local keeps vectors in memory — re-run `python -m scripts.load_vectors`
> after every `docker compose up`. The loader is idempotent.

### Apple-Silicon specifics (already handled in this repo)

- Postgres is pinned to `postgres:16-alpine` (the Debian image segfaults in `initdb`).
- pinecone-local is pinned to `v0.7.0` (`:latest` is a release candidate that segfaults under
  x86 emulation).
- Enable **Docker Desktop → Use Rosetta for x86/amd64 emulation** for stability.
- The vector loader/runtime rewrite the pinecone-local index host from `https` to `http`
  (it advertises TLS but serves plaintext).

---

## 8. Extensibility (built for the "surprise extension")

- **Add a new 10-K with zero code change.** The list of companies with filings is **not**
  hardcoded. `scripts/load_vectors.py` writes every ingested `source` into a `vector_registry`
  table; the router reads it (`app/registry.py`). Ingest a 5th filing and it becomes searchable
  automatically. The only hardcoded fact is the brand→filer alias (Google→Alphabet,
  Facebook→Meta), which no data source can supply.
- **Add auth features** (roles, refresh tokens, OAuth) inside the isolated `app/auth/` module.
- **Add a graph step** (e.g. a re-ranker, a second data source, a guardrail node) by inserting a
  node and an edge in `app/agent/graph.py` — the flow is explicit and easy to extend.
- **Swap the LLM** by changing one constant (`MODEL` in `graph.py`); the graph is
  provider-agnostic at the edges.

---

## 9. Known limitations and trade-offs

- **Vector store is not persistent.** pinecone-local is in-memory; the loader must re-run after
  each restart. (Postgres persists via a Docker volume.)
- **10-K coverage is only four companies.** By design of the provided data — the system is
  explicit about this rather than papering over it.
- **`gpt-4o-mini` for cost.** Extraction and synthesis use the small model to respect the
  budget; a larger model would improve nuance but the deterministic nodes already guard the
  facts. Swappable via one constant.
- **Growth is computed over the earliest→latest requested year.** Simple and predictable;
  multi-window comparisons would need a small extension.
- **Local-only security posture** (HTTP, `localStorage` token) — appropriate for local dev,
  noted above for production hardening.

---

## 10. Appendix

### API endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/register` | – | Create a user (email + password ≥ 8 chars) |
| POST | `/auth/login` | – | Exchange credentials for a JWT (OAuth2 password form) |
| POST | `/chat` | Bearer | Ask a question → `{ answer, citations }` |
| GET | `/chat/history` | Bearer | Return the user's message history |
| GET | `/health` | – | Liveness check |

### Environment variables

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | LLM + query embeddings (**required**) |
| `DATABASE_URL` | Postgres DSN (defaults match compose) |
| `PINECONE_API_KEY` / `PINECONE_HOST` / `PINECONE_INDEX_NAME` | pinecone-local connection |
| `JWT_SECRET_KEY` | Signs auth tokens (**set to a random string**) |
| `JWT_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` | Token algorithm (HS256) and lifetime (60) |

### Key source files

| File | Responsibility |
| --- | --- |
| `backend/app/agent/graph.py` | The deterministic LangGraph: nodes, edges, growth math, context builder |
| `backend/app/agent/tools.py` | `query_financials` (SQL), `search_filings` (Pinecone) |
| `backend/app/agent/prompts.py` | Extraction + synthesis prompts |
| `backend/app/registry.py` | Dynamic filing registry (which companies are searchable) |
| `backend/app/auth/` | JWT + bcrypt authentication |
| `backend/app/chat/service.py` | Orchestration + citation assembly |
| `backend/scripts/load_vectors.py` | Vector ingest (Option A) + source registration |
| `frontend/src/chat/` | Chat page, message list, citations panel |

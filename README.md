# PartSelect Parts Assistant

A vertical AI agent for the PartSelect e-commerce platform, scoped to refrigerator and dishwasher parts.

---

## Demo

> https://www.loom.com/share/459b097f6790479291dd7f6cdc1932a8

---

## Live Demo & Deployment

**Live:** https://partselect-agent-demo.vercel.app

The live demo pairs a React frontend on Vercel with the FastAPI backend running in a Docker container on a Hugging Face Space. The SQLite and ChromaDB data ship inside the image as read-only files, so the backend needs no external database.

### Architecture

| Layer | Hosting |
|---|---|
| Frontend | React on Vercel, auto-deployed from `main` with preview builds on every PR |
| Backend | FastAPI in Docker on a Hugging Face Space (free CPU tier) |
| Keep-warm | A daily Vercel Cron pings the Space so it doesn't sleep after 48 hours of inactivity |

### Model choice

The agent moved from `gpt-5.4-mini` to `gpt-6-luna` after running the eval suite against three models. The goal was to cut cost and stay within budget without giving up tool routing or answer quality.

| Model | Routing | Judge | Cost / query |
|---|---|---|---|
| **gpt-6-luna** | 17/17 | 48/51 (94%) | ~$0.0003 |
| gpt-5.4-mini | 17/17 | 47/51 (92%) | ~$0.0026 |
| gpt-6.1-terra | 17/17 | 44/51 (86%) | ~$0.0027 |

Terra lost points for hedging on clear answers, such as replying "No." to a price question without giving the actual price. The judge stays on `gpt-5.4-mini`, so the agent is never graded by its own model.

### Public-safety hardening

A public endpoint backed by a paid API needs guardrails:
- **No system-role injection:** the API only accepts `user` and `assistant` messages.
- **Input limits:** 1,000 characters per message and 20 messages per request.
- **Rate limiting:** 8 requests/min and 60/day per IP, plus a global cap of 1,500/day. Client IPs are read from the proxy-appended end of `X-Forwarded-For`, so spoofed headers can't bypass the limit.
- **Origin check:** Hugging Face's proxy overrides CORS headers, so the API rejects requests from other sites itself.
- **Budget:** a dedicated OpenAI project with a hard $20/month limit.
- **Generic errors:** failures return a generic message while details stay in server logs.
- **Secrets:** the OpenAI key lives only in Hugging Face Space secrets, and the deploy script refuses to upload `.env` files or anything resembling a key.

### CI/CD

Every PR runs three GitHub Actions checks, and `main` only accepts merges once all of them pass:
- **Backend tests:** 17 tests covering the guardrails above, with the agent stubbed so no OpenAI calls are made
- **Docker build:** verifies the backend image still builds
- **Frontend build:** production build with lint warnings treated as errors

On merge, Vercel deploys the frontend, and a GitHub Action uploads the backend code to the Space, waits for the rebuild, and runs a health check.

---

## Scope, UX, and Extensibility

**Scope enforcement** is implemented at two levels. The system prompt contains explicit routing rules that map every query type to a specific tool, and explicit refusal rules for anything outside refrigerator/dishwasher parts (order tracking, other appliances, general questions). The agent never guesses compatibility, price, or stock status without a tool call; hallucination of factual claims is explicitly prohibited.

![Interface](./interface_demo1.png)

![](./interface_demo2.png)

**UX decisions** were driven by what a customer mid-repair actually needs:
- **Interruptible queries** allow users to stop an in-progress request and immediately ask a new question, preventing lock-in during long retrieval or reasoning chains.
- **Rich part cards** are returned as a parallel data channel alongside the prose reply, rendering as structured cards (image, price, stock, difficulty badge, direct link) rather than buried in markdown.
- **Clickable PS chips** in the response text let users look up any part number mentioned without retyping it.
- **Appliance toggle** in the input bar pre-scopes queries so users don't have to specify "refrigerator" or "dishwasher" every turn.
- **Video cards** are extracted from repair guide responses and rendered inline with thumbnail previews.
- **Session persistence** via `sessionStorage` so a page refresh doesn't wipe the conversation.

**Extensibility** is the core architectural bet. New data sources (order history, account info) become new MCP servers without touching existing ones. The two-database split (SQLite for exact, ChromaDB for semantic) means adding a new retrieval modality is additive, not a refactor. The stateless FastAPI backend is horizontally scalable by default.

---

## Architecture

![System design](./system_design_overall_logic.png)

The React UI sends full conversation history to FastAPI on every request, keeping the backend stateless. FastAPI passes the messages array to a hand-rolled agent loop that calls the LLM iteratively until no tool calls are returned.

Two MCP servers act as the tool layer. **Inventory MCP** handles exact structured lookups (`get_part`, `get_by_mpn`, `find_alternatives`, `check_compatibility`, `search_by_model`) against SQLite. **RAG MCP** handles semantic retrieval (`diagnose_symptom`, `search_repair_guide`, `search_blogs`) against ChromaDB, enriching hits with full part records from SQLite. Tool results are returned as JSON and appended to the message history each iteration.

The data pipeline runs offline: a 3-level Playwright scraper produces `parts.csv`, `repair_guides.json`, and `blogs.json`, which `csv_to_sqlite.py` migrates into SQLite and the ChromaDB parts collection. The repair guides and blogs collections build lazily on first query.

### Tool routing

| Input | Tool(s) called |
|---|---|
| PS number, info intent | `get_part` |
| PS number, replace intent | `find_alternatives` |
| Manufacturer part number | `get_by_mpn` |
| Model number, no specific part | `search_by_model` |
| Compatibility question | `check_compatibility` |
| Symptom + fix verb | `search_repair_guide` + `diagnose_symptom` + `search_blogs` |
| Symptom only | `diagnose_symptom` |
| Maintenance / how-to | `search_repair_guide` + `search_blogs` |
| Out of scope | No tool call, polite decline + redirect |

Tool descriptions are written as decision rules ("call this when X, not when Y") rather than API documentation, reducing ambiguous tool selection and preventing redundant chained calls.

---

## Data

| File | Contents |
|---|---|
| `parts.csv` | ~7,000 refrigerator and dishwasher parts scraped from PartSelect |
| `repair_guides.json` | Per-symptom repair guides with difficulty, steps, and video URLs |
| `blogs.json` | Blog post titles and URLs |
| `parts.db` | SQLite, gitignored, built by `csv_to_sqlite.py` |
| `chroma/` | ChromaDB vector store, gitignored, rebuilds on first query |

---

## Eval

`eval.py` contains 17 test cases across 11 categories with dual scoring:

**Exact match** (deterministic): tool routing, tool inputs, part ID existence in DB (hallucination catch).

**LLM-as-judge** (rubric-based): response quality per query type. Criteria are written as positive assertions for reliable scoring.

Categories: `part_lookup`, `install`, `compatibility`, `model_search`, `symptom`, `repair_guide`, `blog`, `mpn_lookup`, `out_of_scope`, `adversarial`, `alternatives`

![Eval results](./eval_result.png)

```bash
python eval.py           # run all 17 cases
python eval.py --case 8  # run a single case by ID
```

---

## Running locally

### Prerequisites

Python 3.11+, Node.js 18+, OpenAI API key

```bash
# Root .env
OPENAI_API_KEY=sk-...
```

```bash
pip install -r requirements.txt
playwright install chromium
```

```bash
# Run in order:
python scraper/scrape_parts.py       # ~7,000 product pages
python scraper/csv_to_sqlite.py      # CSV to SQLite + ChromaDB
python scraper/scrape_repairs.py
python scraper/scrape_blogs.py
```

```bash
uvicorn main:app --reload --port 8000
cd frontend && npm install && npm start
# http://localhost:3000
```

---

## Stack

| Layer | Choice |
|---|---|
| LLM | gpt-6-luna (eval judge: gpt-5.4-mini) |
| Embeddings | text-embedding-3-small |
| Exact search | SQLite |
| Semantic search | ChromaDB (cosine similarity) |
| Scraping | Playwright + BeautifulSoup |
| Backend | FastAPI (stateless) |
| Frontend | React |
| Hosting | Vercel (frontend), Hugging Face Spaces Docker (backend) |
| CI/CD | GitHub Actions |

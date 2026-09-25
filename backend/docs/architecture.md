# Architecture decisions — Option 1 (multi-format document chat)

This document records **why** the system is shaped this way, not only **what** it does. It is written for the take-home (4–5 days, open-source only, live demo) and for anyone implementing the first vertical slice.

Related constraint from the brief: a smaller robust system with documented trade-offs beats a broad fragile one.

---

## 1. Problem we are solving

Users upload a **mix** of PDFs, Office docs, spreadsheets, images, and code, then ask questions **across** those files. Answers must be:

- grounded (citations: file, page / sheet / line)
- correct on **tables** (aggregations, filters, joins — not dumping cells into a prompt)
- honest when evidence is missing
- fast enough for a 5–10 minute walkthrough on a laptop, with **no paid API keys**

The brief’s example agent list (Router, Retrieval, Table, Vision, Synthesis, Citation) is a **capability map**, not a mandatory org chart.

---

## 2. Design principles

1. **Create an agent only when it has different tools, a different failure mode, or can run in parallel.** Extra local-LLM hops add seconds of latency and routing errors. They are not “more architecture.”
2. **Parsing is a pipeline, not a conversation.** Layout, OCR, and chunking must be deterministic and unit-testable.
3. **Specialists skip when unused.** Do not stub-call every agent on every turn.
4. **Typed graph state is the contract.** Agents do not coordinate only through a free-form transcript.
5. **Open models only; local is one switch away.** Everything except the LLM runs in-process. The default LLM is an open-weight model on Groq's free tier, chosen for demo speed; `PROVIDER=ollama` runs the same pipeline fully offline with no key. Paid providers are optional.

---

## 3. Two-layer architecture

```
┌─────────────────────────────────────────────────────────────┐
│  INGEST (offline / on upload) — no planner LLM on hot path  │
│  upload → type router → parser → chunks → hybrid index      │
│                         ↘ DuckDB tables (CSV/XLSX)          │
│                         ↘ OCR text + caption chunks (images)│
│                         ↘ path/line chunks (code)           │
│                         ↘ cheap metadata + optional links   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  QUERY (LangGraph)                                          │
│  Router ──fan-out──► Retrieval │ Table │ Code (skip unused) │
│                         └──► Synthesis → Verify → UI        │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Ingest (pipeline)

| Input | Parser | Index artifact |
| --- | --- | --- |
| PDF | PyMuPDF (Docling later) | Text chunks with `p. N` |
| DOCX | python-docx | Paragraphs and tables in document order, grouped by heading (`section '…'`) |
| PPTX | python-pptx | Text frames, tables, speaker notes per slide (`slide N`) |
| MD, TXT, HTML | built-in | Markdown split by heading; heading prefixed to each chunk |
| CSV, XLSX | pandas | DuckDB table per sheet **and** a columns + rows text chunk for retrieval (`sheet '…'`) |
| Images / scanned pages | Tesseract (PaddleOCR later if quality is poor) | OCR text + caption chunk; OpenCLIP image embedding |
| Code | 80-line windows, 10-line overlap | Line-numbered chunks (`L start-end`) |

Every chunk carries a `location` that tools print as `[filename, location]`. That string is the citation unit end to end.

OCR runs at **ingest time**, so scanned text is searchable by Retrieval with no vision call. A query-time **Vision** agent exists as well, for questions about what an image shows. It gets the image pixels plus the ingest-time OCR text and caption.

### 3.2 Query (LangGraph)

| Role | Agent? | Job | Tools |
| --- | --- | --- | --- |
| Router / Planner | yes | Classify the turn; emit a structured plan; never answer | JSON schema only |
| Retrieval | yes | Hybrid search over docs, slides, OCR, code | BM25 + vectors + Reciprocal Rank Fusion |
| Table / Data | yes | Structured QA on registered sheets | DuckDB SQL |
| Vision | yes | Read images, scans, charts | Image + OCR attached to input; `vision_tool` (CLIP search) |
| Code | yes | Explain / compare uploaded source | Code index (no arbitrary execution) |
| Synthesis | yes | One draft from specialist payloads; no new facts | none |
| Citation / Verify | yes | Drop unsupported claims, set confidence, refuse | LLM critic, then a deterministic citation→tool-result check |

**Code** is a specialist because it has a different citation grain (path + lines) and a different prompt. If time is short, it can start as Retrieval with `kind=code` filters and the same synthesizer — that is a documented scope cut, not a different architecture.

---

## 4. Shared graph state

One typed object is passed between nodes. Suggested fields:

| Field | Written by | Read by |
| --- | --- | --- |
| `messages` | UI + checkpointer | Router, Synthesis |
| `file_manifest` | Ingest | Router, specialists (filters) |
| `plan` | Router | All specialists |
| `retrieval_hits` | Retrieval | Synthesis, Verify |
| `table_result` | Table | Synthesis, Verify |
| `code_notes` | Code | Synthesis, Verify |
| `linked_doc_ids` | Ingest graph / Router | Retrieval filters |
| `draft_answer` | Synthesis | Verify |
| `citations`, `confidence`, `unknown` | Verify | UI |

Conversation memory is **not** the full specialist trace. Each assistant turn stores:

- `content` — the user-facing answer
- `plan` — the planner tool-call output for this turn
- `trace` — serialized LangChain messages (`HumanMessage`, `AIMessage` tool calls, `ToolMessage`) for the planner and every subagent that ran

The next planner call receives **only previous `plan` objects**, plus the current question and the file manifest. It does not receive prior user wording, prior final answers, or subagent traces. Follow-up continuity has to live inside those plans (`intent`, `subqueries`, `target_files`).

### 4.1 Turn shape

```
user:      { role, content, created_at }
assistant: { role, content, plan, trace, confidence, unknown, created_at }
trace:     { planner, retrieval?, table?, code?, synthesis, verify }
           each value is { name, messages[] }
```

`create_agent` (LangChain ReAct loop) runs the planner and each selected specialist. Synthesis and verify are the same loop with a single recording tool (`draft_answer`, `finalize_answer`).

---

## 5. How the router decides

The router emits booleans and filters, not prose.

| Question pattern | Retrieval | Table | Code |
| --- | --- | --- | --- |
| “What does the PDF say about X?” | yes | no | no |
| “Sum Q3 revenue in the workbook” | no | yes | no |
| “Compare the policy PDF to CSV totals” | yes | yes | no |
| “What does `process.py` do?” | yes | no | yes |
| Follow-up: “and the previous year?” | rewrite last plan first | rewrite last plan first | — |

Follow-ups **rewrite against the last plan** before a full re-route.

---

## 6. Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Orchestration | LangChain `create_agent` (LangGraph runtime) + `asyncio.gather` fan-out | ReAct loop per agent; parallel specialists; skip unused |
| LLM | Groq-hosted open-weight model (default) or Ollama (Qwen 2.5 7B / Llama 3.1 8B) | Free tier or fully offline; one `PROVIDER` switch |
| Embeddings | `all-MiniLM-L6-v2` (ONNX, Chroma default) for text; OpenCLIP ViT-B-32 for images | Local, CPU-only, no extra daemon |
| Vector + keyword | Chroma + in-memory BM25 + RRF | One-process demo; Qdrant / FTS5 is the scale-up |
| Tabular QA | DuckDB | See [§7](#7-why-duckdb-not-mongodb-or-sqlite) |
| App / session store | SQLite (`id` + `json` tables) | Conversations, messages with plans/traces/citations, document records |
| Parse | PyMuPDF + python-docx/pptx + pandas + Tesseract | Page/slide/section/sheet/line locations; Docling is the upgrade path |
| UI | Streamlit | Upload + chat + source badges + agent trace |

Rerankers (BGE cross-encoder) and Qdrant are **upgrades** if hybrid search quality is the demo bottleneck — not day-one dependencies.

---

## 7. Why DuckDB, not MongoDB or SQLite?

These three products are often compared as “the database.” They are not interchangeable here. The Table agent’s job is **analytical queries over spreadsheets** (sums, filters, group-bys, joins across sheets). That is OLAP. Mongo and SQLite are aimed at different jobs.

### 7.1 What each is good at

| | DuckDB | SQLite | MongoDB |
| --- | --- | --- | --- |
| Workload | OLAP (scan, aggregate, join) | OLTP (point reads/writes, app state) | Document CRUD, flexible JSON |
| Storage model | Columnar, vectorized | Row store | BSON documents |
| Spreadsheet QA | Native: `read_csv`, `read_xlsx`, SQL | Possible but slower and clumsier for wide scans | No SQL; aggregation pipeline is a poor text-to-SQL target |
| Process model | In-process library | In-process library | Separate server (or Atlas — paid / ops) |
| Local demo | `pip` / `uv` and a file | Same | Extra daemon, auth, ports |
| Fits the brief’s “text-to-SQL / pandas” | Yes | Weak | No |

### 7.2 Why DuckDB for the Table agent

- **The brief asks for real structured QA**, not “embed the CSV as text.” A 7B model doing mental arithmetic over pasted cells will fail on real workbooks. SQL over a typed table will not.
- **Columnar execution** matches spreadsheet questions (“sum revenue where region = EMEA”). DuckDB reads only the columns it needs and vectorizes the rest.
- **Zero ops.** Same process as the Python app. Register a pandas DataFrame or point at a file. No replica set, no connection string in the README.
- **Joins across sheets/files** are ordinary SQL. That is the cross-document path for *data*, which is different from the narrative cross-document path in Retrieval (see §8).
- **Schema is injectable.** The Table agent prompt gets `CREATE TABLE` text plus three sample rows. That is how local models produce usable SQL.

DuckDB is **not** the document store, not the vector DB, and not the chat history store.

### 7.3 Where SQLite *does* belong

SQLite is a good fit for:

- conversation threads and checkpointer metadata
- file manifest and ingest job status
- optional FTS5 as the keyword half of hybrid search (instead of in-memory BM25) if we want persistence across restarts

It is a **poor** default for “`GROUP BY product` on a 200k-row export.” It can do it; DuckDB will do it faster with less tuning, and the LLM is generating SQL either way — better that SQL hits an engine built for it.

DuckDB can also **query SQLite files** (`sqlite_scan` / attach). If we later keep manifests in SQLite and facts in DuckDB, they can still join. That is a reason to keep both, not to replace DuckDB with SQLite.

### 7.4 Why not MongoDB

- **Wrong query model for tables.** The impressive Table demo is `SELECT … GROUP BY`. Mongo’s aggregation DSL is verbose, unfriendly for a small local LLM, and not what the brief suggested.
- **Ops and constraint.** A local Mongo process (or Atlas) fights “one-command, no paid keys.”
- **Flexible documents are already covered.** Parsed chunks are JSON-ish objects in Chroma + files on disk. Nested metadata does not require a document database at this scale.
- **Cross-document `$lookup` is not a knowledge graph.** It joins collections you designed. Spreadsheet joins and entity links are better as SQL and an explicit edge table (see §8).

Mongo would only be justified if we were building a multi-tenant SaaS with huge nested JSON payloads and a team already running Mongo. That is not this submission.

### 7.5 Decision

| Store | Role in this system |
| --- | --- |
| **Filesystem** | Original uploads |
| **Chroma** | Dense vectors for semantic search |
| **BM25 (or SQLite FTS5)** | Keyword search |
| **DuckDB** | Spreadsheet / tabular reasoning |
| **SQLite** | Optional app/session metadata |
| **MongoDB** | Out of scope |

---

## 8. Metadata extraction and cross-document linking

### 8.1 The question

Pure vector search finds **passages similar to the query**. It does not, by itself, know that *Contract_A.pdf* “Payment terms” and *Finance_Q3.xlsx* sheet `invoices` both talk about the same vendor. For **deep cross-document relations**, should we extract metadata, then link documents on that metadata?

**Short answer:** yes for **cheap, structured metadata and 1-hop entity links**; no for a full LLM-built knowledge graph on the query path. The quality win is real; the usual performance problem is **extra LLM calls and noisy edges**, not the graph lookup itself.

### 8.2 What “cross-document reasoning” actually needs

Three different relations get mixed together:

| Relation | Example | Best mechanism |
| --- | --- | --- |
| **Same question, many files** | “What do all PDFs say about refunds?” | Hybrid retrieval + Synthesis (already in the graph) |
| **Narrative ↔ numbers** | Policy PDF vs totals in a workbook | Router fans out to Retrieval **and** Table; Synthesis aligns them |
| **Shared real-world entity** | Same `PO-1042` / vendor / person in two files the user did not name | **Metadata / entity index** (this section) |

Vector search fails the third case when the query never mentions the linking key (“why did we pay this vendor twice?” while the vendor string only appears in the sheet and a buried PDF annex).

### 8.3 Layers of metadata (increasing cost)

**Layer A — parser metadata (always do this).**  
File name, MIME type, page/sheet counts, heading path, table captions, language, checksum. Almost free: Docling/pandas already produce it. Store on every chunk.

**Layer B — document fingerprint (cheap, high value).**  
Sheet names, column headers, title/first-heading, date-like strings, invoice/PO regexes. Rules and light NER (regex, optionally spaCy). No LLM required.

**Layer C — entity links (do, but cap it).**  
Normalized entities: orgs, money amounts, IDs, dates, geo, product names. Build an undirected bipartite graph:

```
document_or_chunk  ——mentions (count, confidence)——  entity
```

At query time, if Retrieval hits doc A, expand **one hop**: other docs that share entities with support ≥ N. Pass `linked_doc_ids` as a **soft filter** (boost or extra fetch), not a hard restriction.

**Layer D — LLM knowledge graph (not for v1).**  
“Extract all triples, resolve coreference, write OWL.” Expensive, noisy on 7B models, hard to demo-debug, and duplicates what Synthesis can do when evidence is already in the context window.

### 8.4 Would this produce deeper relations?

**Yes, if links are sparse and typed.** Useful edges look like:

- `INV-8891` in a PDF footer and in `invoices.id`
- column `customer_id` matching a heading “Customer 4821” in a slide
- identical normalized org name across two contracts

**No, if we fully connect documents that share generic tokens** (`the`, `Q3`, `Company`, `Total`). That creates a hairball. Retrieval then “cross-links” everything to everything and Synthesis gets contradictory chunks. **Precision of entities matters more than recall.**

Practical extraction policy:

- Prefer **high-IDF strings**: IDs, emails, ISIN-like codes, `r"[A-Z]{2,}-\d+"`, currency amounts with context.
- Normalize (`acme inc.` → `acme`).
- Require **two independent mentions** or one high-confidence ID before promoting an edge.
- Keep entity type (`invoice_id` vs `org`) so the Router can say “same invoice” not “same vibe.”

For **PDF ↔ XLSX**, the strongest link is often **schema alignment**, not NER: a PDF table extracted into columns that match a sheet. That is ingest (Docling table objects → DuckDB), which is more reliable than asking an LLM to “find relationships.”

### 8.5 Performance — where time actually goes

On a laptop, relative costs for this demo:

| Step | Typical cost | Notes |
| --- | --- | --- |
| DuckDB aggregation on demo-sized sheets | milliseconds–tens of ms | Not the bottleneck |
| Vector + BM25 over thousands of chunks | tens–hundreds of ms | Fine |
| 1-hop graph lookup in SQLite / dict | **sub-millisecond to a few ms** | Negligible |
| One local 7B generation | **~1–10+ seconds** | Dominates the user-visible latency |
| LLM entity extraction **per page** at ingest | seconds × pages | Amortized, but can make upload feel broken |

So:

- **Query-time graph expansion does not meaningfully drop QPS** for a single-user Streamlit demo. A few thousand edges is a toy graph.
- **Query-time LLM “discover links” will drop perceived performance badly** (extra hop before Retrieval). Do not do this.
- **Ingest-time LLM NER on every page** will make large uploads slow and can OOM a 8–16 GB machine if we batch naively. That *is* a performance drop the user will feel.
- **Noisy links hurt quality more than they hurt latency**: extra chunks in the window crowd out the right ones (context pollution), which looks like “the system got dumber.”

Fan-out risk: 2-hop expansion on popular entities (`2024`, `USD`) retrieves half the corpus. **Hard cap:** max K linked docs (e.g. 3–5), min entity weight, 1 hop only.

Memory: metadata + edge tables are tiny next to embeddings (embeddings are the large object). Linking will not be what fills RAM; models and Chroma will.

### 8.6 Decision for this submission

| Do now | Defer |
| --- | --- |
| Layer A on every chunk | LLM triple extraction |
| Layer B regex IDs / headers / sheet names | Multi-hop graph walks |
| Optional Layer C: entity table + 1-hop boost into Retrieval | Coreference, ontology, GraphRAG loops |
| Router may set `linked_doc_ids` from shared IDs | Query-time extraction agent |

This is enough to demo a **specific** cross-file win: “the invoice ID in the PDF matches rows in the spreadsheet” without pretending we built a knowledge graph product.

Implementation sketch (when we build it):

1. Ingest writes `entities(entity_id, type, norm, raw)` and `mentions(chunk_id, entity_id, weight)`.
2. Retrieval returns top hits as today.
3. Expand: `SELECT document_id FROM mentions WHERE entity_id IN (...) AND document_id NOT IN (already_hit) ORDER BY weight DESC LIMIT 5`.
4. Fetch extra chunks only from those documents (or boost their RRF score).
5. Verify still requires citations; links never invent facts.

### 8.7 What we will say in the interview if asked “why not GraphRAG?”

GraphRAG-style clustering is designed for **corpus-level** summaries on large messy collections. It adds clustering + community summaries (more LLM, more ingest time). For a user-uploaded **session of tens of files**, hybrid retrieval + Table SQL + sparse ID links is the higher-leverage design and easier to make trustworthy with citations.

---

## 9. Scope for 4–5 days

**Must ship**

- Formats: PDF, DOCX, TXT/MD, PPTX, CSV, XLSX
- Hybrid retrieval, DuckDB table QA, citations (file + page/sheet)
- Multi-file questions, follow-ups, explicit I-don’t-know from Verify

**Should ship**

- Image OCR into the same index
- Code explain with line cites
- Layer A/B metadata on chunks; 1-hop ID boost if time
- Confidence in the UI, Dockerfile, `/examples` corpus

**Document as future work (do not build)**

- Audio/video, live HTML crawl
- GPU reranker, Qdrant at scale
- Planner retry loops, paid Groq fallback (optional flag only)
- LLM knowledge graph / GraphRAG

---

## 10. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Local 7B router mis-routes | Structured output + heuristics from file types; default Retrieval on if unsure |
| Hallucinated citations | Verify strips claims without `chunk_id` / `sheet!cell` before the critic |
| Spreadsheet SQL injection / destructive SQL | DuckDB read-only connection; allowlist `SELECT` |
| Huge PDFs | Page-batched parse; cap pages in demo with a clear UI message |
| Noisy cross-links | ID-like entities only; 1 hop; cap K |

---

## 11. Summary

- **Agents** = Router + parallel specialists (Retrieval, Table, Code) + Synthesis + Verify. Ingest is not agentic.
- **DuckDB** is the Table engine because the job is analytics over sheets. **SQLite** may hold sessions. **MongoDB** does not earn a seat.
- **Metadata linking** is worth doing as **cheap structured fields + sparse ID graph + 1-hop retrieval boost**. It improves genuine cross-file questions. It will not be the latency bottleneck unless we put an LLM on every page or on every query to “find relationships.”

---

## 12. Current status

The coordinator, subagents, turn storage, hybrid retrieval, located citations, and the citation check are in place. Compaction, reranking, and entity links are still open.

### 12.1 File-type tools

| Agent | Tool | Behaviour |
| --- | --- | --- |
| Retrieval | `retrieval_tool(query, document_ids?)` | Chroma dense search plus BM25 over the same chunks, merged with reciprocal rank fusion; 6 results. Scoped to the conversation; `document_ids` accepts ids or filenames and falls back to all. Passages start with `[filename, location]`. Kinds `text` and `code`, which includes sheet text chunks and image OCR chunks. |
| Table | `table_tool(sql)` | One read-only `SELECT`/`WITH` against this conversation's DuckDB tables. DDL/DML, multiple statements, DuckDB file functions and foreign tables are rejected. Results start with `[filename, table …]`. The prompt includes a per-file table catalog. |
| Vision | `vision_tool(query, document_ids?)` | CLIP search over images; returns caption + OCR text. Pixels are attached to the agent's input message, not the tool result. |
| Code | `code_tool(document_id, question?)` | Whole file (line-numbered) up to 300 lines; otherwise the first 40 lines plus hybrid-search hits for the question. Accepts an id or filename. Does not execute the file. |
| Synthesis | `draft_answer` | Recording tool. |
| Verify | `finalize_answer` | Recording tool. Then `citations.check` marks each `[file, location]` in the answer as supported only if a tool returned it, capping confidence when citations are unverified or missing. |

### 12.2 Still open on retrieval

- Cross-encoder reranker
- 1-hop entity links into the retrieval filter
- Claim-level entailment (the citation check verifies provenance, not entailment)

### 12.3 Compaction

Traces grow by one full ReAct transcript per specialist per turn. They are stored on the assistant message and are **not** sent back to the planner. Compaction is for the stored trace and for any future agent that must read history, not for the planner prompt.

Rules when this is built:

1. Planner context stays the list of `plan` objects. Compaction must not replace that with a summary of subagent chatter.
2. After a turn is finalized, the trace may be compacted in place: keep system-free `HumanMessage` inputs, every `tool_calls` entry, every `ToolMessage`, and the last assistant message that called `submit_plan`, `draft_answer`, or `finalize_answer`. Drop repeated model prose that did not call a tool.
3. Cap stored trace size (target: the last 20 tool messages per agent, or about 8 KB of serialized JSON per agent). Older tool payloads are replaced with `{ "compacted": true, "tool": name, "args_preview": first 200 chars, "result_preview": first 200 chars }`.
4. Never compact the current turn while agents are still running.
5. `content` and `plan` are not compacted. They are the user-visible answer and the only cross-turn planner memory.
6. A later "show your work" UI reads `trace` after compaction and must still show which tools ran and what they returned.

### 12.4 Explicitly not in this pass

- Rerankers and 1-hop entity links
- Citation stripping beyond what Verify writes into `finalize_answer`
- Streaming tokens to the UI
- Sending specialist traces into the next planner call
- Trace compaction (section 12.3)

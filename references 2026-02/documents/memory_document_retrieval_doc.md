# llm-thalamus Document Retrieval System
Detailed documentation for `memory_document_retrieval.py`

---

## 1. Purpose and Role in llm-thalamus

`memory_document_retrieval.py` provides the **document-level retrieval API** for llm-thalamus. It is the counterpart to `memory_ingest.py`:

- `memory_ingest.py` **stores** documents into OpenMemory.
- `memory_document_retrieval.py` **retrieves exactly one document** based on metadata and optional temporal constraints.

Its main job is to answer this question:

> “Given a description of a document (filename/topic/tags) and optionally a time, which single version of which file should we retrieve from OpenMemory?”

It shields the rest of llm-thalamus from:

- The details of OpenMemory’s query API.
- The presence of multiple candidate memories.
- Versioning and time-travel semantics.

---

## 2. Design Goals

1. **Single-call retrieval**  
   One call should return one document (a single string), not a list of memories.

2. **Version-awareness**  
   When a document is re-ingested multiple times, all versions remain in OpenMemory, and this module allows selecting:
   - Latest version
   - Latest as of a given timestamp
   - Earliest version
   - Longest version
   - Highest-score version

3. **Tag-based disambiguation**  
   Ensure that only ingested documents participate, not arbitrary semantic or procedural memories.

4. **LLM-friendly API**  
   The LLM and the controller provide a simple `meta` dictionary with fields like `filename`, `topic`, `note`, and `tags`. The retrieval module handles the rest.

---

## 3. Invariants from Ingestion

This module assumes that ingested documents are created by `memory_ingest.py`, which guarantees that each document memory has:

- `tags` includes `"file_ingest"`
- `metadata.kind == "file_ingest"`
- `metadata.filename` set to the basename of the file
- `metadata.path` set to the absolute path at ingestion time
- `metadata.ingested_at` set to the ingest time (UTC ISO-8601 string)

These fields are the **foundation** of robust retrieval and versioning.

---

## 4. Core API: `retrieve_document_from_metadata`

### 4.1 Function Signature

```python
def retrieve_document_from_metadata(
    meta: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    k: int = 50,
    default_tags: Optional[List[str]] = None,
    strategy: str = "latest",
    as_of: Optional[str] = None,
) -> str:
    ...
```

### 4.2 Parameters

- **`meta`** (`dict`)
  - High-level description of the desired document.
  - Typical fields:
    - `filename` / `file_name`: basename of the file (e.g. `"memory_storage.md"`).
    - `topic`: semantic theme (e.g. `"llm-thalamus memory design"`).
    - `note`: additional notes (e.g. `"File supplied during thalamus design session"`).
    - `provider`: who supplied it (e.g. `"evert"`).
    - `tags`: additional tags to restrict search (e.g. `["llm-thalamus", "docs", "design"]`).
    - `query`: explicit semantic query string. If present, it overrides the automatic query construction.

- **`user_id`** (`str`, optional)
  - Which OpenMemory user namespace to search.
  - Defaults to `get_default_user_id()` if omitted.

- **`k`** (`int`, optional)
  - Maximum number of raw candidates to retrieve from OpenMemory before local filtering and selection.
  - Default is 50.

- **`default_tags`** (`list[str]`, optional)
  - Base tags to always include in the required tag set in addition to `file_ingest`.
  - If `None`, we still always enforce `["file_ingest"]`.

- **`strategy`** (`str`, optional)
  - Version selection strategy after candidates are filtered.
  - Supported values:
    - `"latest"`: newest version by `ingested_at` (optionally `<= as_of`).
    - `"earliest"`: oldest version by `ingested_at`.
    - `"longest"`: longest content length.
    - `"score"`: highest semantic similarity score from OpenMemory.

- **`as_of`** (`str`, optional)
  - ISO-8601 timestamp (`YYYY-MM-DDTHH:MM:SS+ZZ:ZZ`, etc.)
  - Used with `"latest"` strategy to select:
    - The newest version whose `ingested_at <= as_of`.
  - If no candidates satisfy this, the full set is used as a fallback.

### 4.3 Return Value

Returns a **string** containing the full document content from the selected memory:

```python
"# llm-thalamus – Memory Storage Guide\n\nThis document describes ..."
```

Only one document is ever returned per function call.

---

## 5. Internal Pipeline

The retrieval process consists of several stages, all executed inside a **single call** to OpenMemory.

### 5.1 Required Tags

The module constructs a set of required tags as follows:

1. Start with `["file_ingest"]` to ensure that only ingested documents are considered.
2. Add any tags from `default_tags` if provided.
3. Add any tags from `meta["tags"]` if provided (e.g. `"llm-thalamus"`, `"docs"`, `"design"`).
4. Deduplicate while preserving order.

The result is a list like:

```python
required_tags = ["file_ingest", "llm-thalamus", "docs", "design"]
```

The retrieval module then enforces **AND semantics** on these tags: a memory must contain **all** of them to be kept.

### 5.2 Query Construction

The semantic query string is built from `meta`:

- If `meta["query"]` is present → use it directly.
- Else, assemble from parts:

  ```python
  pieces = []
  if filename: pieces.append(filename)
  if topic:    pieces.append(topic)
  if note:     pieces.append(note)
  if provider: pieces.append(f"provided by {provider}")
  query = " ".join(pieces) or "document relevant to current request"
  ```

- If `filename` is available, it is often used directly as the query for better targeting; otherwise, the combined query is used.

### 5.3 Single OpenMemory Call

The module calls:

```python
results = _query_memories_raw(
    query,
    k=k,
    user_id=user_id,
    tags=required_tags,
)
```

This returns a list of memory objects, each typically containing:

- `content` or `text`: the stored document text.
- `metadata`: including `kind`, `filename`, `path`, `ingested_at`, etc.
- `tags`: tag list, including `"file_ingest"` and any user tags.
- `score`: similarity score (if set by OpenMemory).

### 5.4 Tag AND Filtering

The tag filter applies strict AND semantics on the `required_tags` list:

```python
def tag_filter(results, required_tags):
    if not required_tags:
        return results
    required = set(required_tags)
    kept = []
    for m in results:
        mem_tags = set(m.get("tags") or [])
        if required.issubset(mem_tags):
            kept.append(m)
    return kept or results
```

If the AND-filter removes all results, we fall back to the original result list to avoid total failure.

### 5.5 Temporal Filtering (`as_of`)

If `strategy == "latest"` and `as_of` is provided:

1. Parse `as_of` into a `datetime`.
2. For each candidate, parse `metadata["ingested_at"]` (if present).
3. Keep only those candidates where:

   ```python
   ingested_at is None or ingested_at <= as_of
   ```

4. If this filtered list is non-empty, use it for final selection; otherwise, revert to the full candidate set.

This yields **“latest as of time T”** semantics.

### 5.6 Version Selection Strategies

After tag and temporal filtering, we apply the specified `strategy`.

Helper functions (conceptual):

```python
def ingested_dt(m):
    meta = m.get("metadata") or {}
    return parse_iso(meta.get("ingested_at"))  # may return None

def content_len(m):
    text = m.get("content") or m.get("text") or ""
    return len(text)

def score_of(m):
    s = m.get("score")
    return float(s) if s is not None else 0.0
```

#### Strategy `"latest"`

```python
chosen = max(
    candidates,
    key=lambda m: (ingested_dt(m) or datetime.min, content_len(m), score_of(m)),
)
```

- Primary key: `ingested_at` (newest first).
- Secondary: `content_len` (prefer longer if same timestamp).
- Tertiary: `score` (prefer higher similarity).

#### Strategy `"earliest"`

```python
chosen = min(
    candidates,
    key=lambda m: (ingested_dt(m) or datetime.max,),
)
```

#### Strategy `"longest"`

```python
chosen = max(
    candidates,
    key=lambda m: (content_len(m), score_of(m)),
)
```

#### Strategy `"score"`

```python
chosen = max(candidates, key=lambda m: score_of(m))
```

### 5.7 Extracting the Final Document

Once `chosen` is selected, the module returns:

```python
content = chosen.get("content") or chosen.get("text")
```

If neither is present, it raises a `ValueError` (this should not happen for ingested documents).

---

## 6. Example Usage

### 6.1 Basic “latest” Retrieval

```python
from memory_document_retrieval import retrieve_document_from_metadata

meta = {
    "filename": "memory_storage.md",
    "topic": "llm-thalamus memory design",
    "tags": ["llm-thalamus", "docs", "design"],
}

text = retrieve_document_from_metadata(meta)

print("=== Retrieved Document ===")
print(text)
```

### 6.2 Time-Travel Retrieval (“as of”)

```python
as_of = "2025-12-04T09:00:00+00:00"

text_as_of = retrieve_document_from_metadata(
    meta,
    strategy="latest",
    as_of=as_of,
)

print(f"=== Version as of {as_of} ===")
print(text_as_of)
```

This will select the most recent version whose `ingested_at` is **at or before** `as_of`. If no such version exists, it falls back to the full set of candidates and simply chooses the latest overall.

### 6.3 Earliest Version Retrieval

```python
first_text = retrieve_document_from_metadata(
    meta,
    strategy="earliest",
)
```

### 6.4 Longest Version Retrieval

```python
longest_text = retrieve_document_from_metadata(
    meta,
    strategy="longest",
)
```

---

## 7. Interaction with Ingestion

Because `memory_ingest.py` always sets:

- `tags` includes `"file_ingest"`
- `metadata.ingested_at` as UTC ISO‑8601

the retrieval module can rely on:

1. **Tag Filtering**  
   By always requiring `"file_ingest"`, we ensure that retrieval does not accidentally pick procedural or conversational memories that happen to mention the same filename or topic.

2. **Temporal Reasoning**  
   Multiple ingests of the same document will result in multiple memory entries with different `ingested_at` timestamps. The retrieval layer can choose the “correct” version based on the controller’s needs.

---

## 8. Design Trade-offs

### 8.1 Single vs Multiple OpenMemory Calls

- The current design performs **one OpenMemory query** per retrieval call.
- All filtering, temporal logic, and version selection are done locally.
- This keeps latency low and behaviour predictable.

### 8.2 Local Post-Filtering vs OpenMemory Query Parameters

- We use tags in the query for coarse filtering.
- We enforce AND semantics on tags locally to ensure strict matching.
- We do temporal filtering and version selection locally, since OpenMemory is not explicitly aware of the ingestion/versioning policy implemented by llm-thalamus.

### 8.3 Choosing Version Strategies

By exposing `strategy` and `as_of` as parameters, the **controller (thalamus)** retains control:

- No hard-coded concept of “the one true latest version” in the retrieval module.
- Different parts of the system can use different strategies without changing the code.

---

## 9. Summary

`memory_document_retrieval.py` is the **document retrieval brain** of llm-thalamus. It:

- Translates LLM-supplied metadata into a query.
- Restricts results to ingested documents only via tags.
- Applies strict AND semantics on tags.
- Supports time-travel retrieval with `as_of`.
- Supports multiple version selection strategies.
- Returns a single, clean document string per call.

Together with `memory_ingest.py`, it forms a robust, version-aware memory subsystem that allows llm-thalamus to ingest, track, and retrieve documents over time without directly exposing OpenMemory internals to the rest of the system.

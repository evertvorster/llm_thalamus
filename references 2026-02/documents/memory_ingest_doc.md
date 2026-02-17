# llm-thalamus Memory Ingestion System
Detailed documentation for `memory_ingest.py`

---

## 1. Purpose and Role in llm-thalamus

`memory_ingest.py` is the **single, canonical entry-point** for getting files from the filesystem into Cavira OpenMemory for use by llm-thalamus.

It is designed to:

1. **Abstract away** OpenMemory’s ingestion details (Python vs HTTP backend).
2. **Normalize metadata and tags** applied to every ingested file.
3. **Record temporal information** so that multiple versions of the same document can be distinguished later.
4. **Guarantee retrievability** by the document retrieval layer (`memory_document_retrieval.py`) without the caller needing to know about OpenMemory internals.

From llm-thalamus’ point of view, this module answers the question:

> “Given a file path and some context/metadata from the LLM, store this file in the memory system in a robust, queryable way.”

---

## 2. High-Level Behaviour

`memory_ingest.py` supports **two ingestion modes**, but exposes a **single public function**:

```python
from memory_ingest import ingest_file
```

Internally, it chooses between:

1. **Standalone Mode (local Python/OpenMemory)**  
   - Used when there is **no** `backend_url` in `config/config.json` under `openmemory`.
   - Reads the file as UTF‑8 text.
   - Stores the file content as a **single memory entry** using the OpenMemory Python API.
   - Ideal for `.md`, `.txt`, `.json`, `.py`, and similar text files.

2. **HTTP Backend Mode**  
   - Used when `openmemory.backend_url` is set in `config/config.json`.
   - Reads the file as bytes and base64-encodes it.
   - Sends it to the configured backend URL via `POST {backend_url}/memory/ingest`.
   - Delegates parsing, chunking, and multimodal embedding to the OpenMemory backend.

Regardless of mode, the following invariants hold:

- Every ingested file is tagged with `file_ingest`.
- Every ingested file has core metadata fields: `kind`, `filename`, `path`, and `ingested_at`.
- Caller-provided metadata can **add** fields but cannot override the core ones.
- The retrieval module can always identify and reason about these ingested documents.

---

## 3. Configuration Assumptions

### 3.1 Config Path

The module expects a `config.json` file at:

```text
<project_root>/config/config.json
```

Internally, the path is computed as:

```python
_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.json"
```

So the file is **relative to the module**, which in the llm-thalamus project lives at the root, next to `config/`.

### 3.2 Relevant Config Sections

`memory_ingest.py` uses:

```jsonc
{
  "openmemory": {
    "mode": "local",                // used elsewhere
    "path": "./data/memory.sqlite", // used elsewhere
    "tier": "smart",                // used elsewhere
    "backend_url": "http://localhost:8000" // OPTIONAL
  },
  "thalamus": {
    "project_name": "llm-thalamus",
    "default_user_id": "default"
  }
}
```

- If `backend_url` is **missing or empty** → Standalone Mode.
- If `backend_url` is **present** → HTTP Backend Mode.

`get_default_user_id()` and `get_memory()` (from `memory_retrieval`) use the same config, so ingestion and retrieval are always aligned on the same database and user namespace.

---

## 4. Public API: `ingest_file`

### 4.1 Function Signature

```python
def ingest_file(
    file_path: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    content_type: Optional[str] = None,
    encoding_fallback: str = "application/octet-stream",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    ...
```

### 4.2 Parameters

- **`file_path`** (`str`)
  - Filesystem path to the file to ingest.
  - May be relative; is expanded to an absolute path using `Path(file_path).expanduser().resolve()`.

- **`metadata`** (`dict`, optional)
  - Arbitrary key/value context provided by llm-thalamus/LLM.
  - Example: who provided it, what topic, why it is relevant.
  - Caller metadata **cannot** override:
    - `kind`
    - `filename`
    - `path`
    - `ingested_at`
  - All other keys are accepted and stored.

- **`tags`** (`list[str]`, optional)
  - High-level categorization for retrieval.
  - Example: `["llm-thalamus", "docs", "design"]`.
  - In all cases, the module **prepends** `file_ingest` so tags become:
    - `["file_ingest", "llm-thalamus", "docs", "design"]` (deduplicated).

- **`user_id`** (`str`, optional)
  - Logical user namespace for OpenMemory.
  - If omitted, defaults to `thalamus.default_user_id` from config.

- **`content_type`** (`str`, optional)
  - MIME type for HTTP backend mode.
  - If omitted, guessed by extension via `mimetypes.guess_type`.
  - Falls back to `encoding_fallback` (`application/octet-stream` by default).

- **`encoding_fallback`** (`str`, optional)
  - Fallback MIME type for unknown file types in HTTP mode.

- **`timeout`** (`float`, optional)
  - HTTP request timeout for backend mode (in seconds).

### 4.3 Return Value

The function returns a dictionary describing the ingestion outcome.

#### Standalone Mode Return Example

```json
{
  "mode": "standalone",
  "file": "/abs/path/to/file.md",
  "user_id": "default",
  "metadata": {
    "kind": "file_ingest",
    "filename": "file.md",
    "path": "/abs/path/to/file.md",
    "ingested_at": "2025-12-04T10:33:22.123456+00:00",
    "provider": "evert",
    "topic": "llm-thalamus memory design",
    "note": "File supplied during design session"
  },
  "tags": [
    "file_ingest",
    "llm-thalamus",
    "docs",
    "design"
  ],
  "memory": {
    "id": "uuid-etc",
    "primarySector": "semantic",
    "sectors": ["semantic"]
    // other OpenMemory fields may be present
  }
}
```

#### HTTP Backend Mode Return Example

Whatever JSON the backend returns from `/memory/ingest`, typically including an internal `memory` object (ID, sectors, etc.).

---

## 5. Internal Logic

### 5.1 Config Loading

```python
def _load_config() -> Dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)
```

### 5.2 Backend URL Resolution

```python
def _get_backend_url() -> Optional[str]:
    cfg = _load_config()
    om_cfg = cfg.get("openmemory", {})
    backend_url = om_cfg.get("backend_url")
    if backend_url:
        return backend_url.rstrip("/")
    return None
```

- If `backend_url` is `None` → **Standalone Mode**.
- If not `None` → **HTTP Backend Mode**.

### 5.3 Tag Normalization

Within `ingest_file`:

```python
base_tags: List[str] = ["file_ingest"]
if tags:
    for t in tags:
        if t not in base_tags:
            base_tags.append(t)
```

This ensures:

- Every ingested file has the `file_ingest` tag.
- Caller tags are included exactly once.

### 5.4 Metadata Normalization and Temporal Stamping

```python
now_iso = datetime.now(timezone.utc).isoformat()

base_metadata: Dict[str, Any] = {
    "kind": "file_ingest",
    "filename": path.name,
    "path": str(path),
    "ingested_at": now_iso,
}

if metadata:
    for k, v in metadata.items():
        if k not in base_metadata:
            base_metadata[k] = v
```

This guarantees that for every ingested document:

- `kind` is `"file_ingest"`.
- `filename` is always the basename of the ingested file.
- `path` is the resolved absolute path.
- `ingested_at` is the version timestamp in UTC ISO-8601.

Caller metadata gets merged **without overriding** these core keys.

### 5.5 HTTP Backend Mode

If `_get_backend_url()` returns a URL:

1. Determine `content_type`.
2. Read file as bytes: `data_bytes = path.read_bytes()`.
3. Encode to base64: `data_b64 = base64.b64encode(data_bytes).decode("ascii")`.
4. Construct payload:

   ```python
   payload = {
       "content_type": content_type,
       "data": data_b64,
       "user_id": user_id,
       "metadata": base_metadata,
       "tags": base_tags,
   }
   ```

5. POST to the backend:

   ```python
   response = requests.post(ingest_url, json=payload, timeout=timeout)
   response.raise_for_status()
   return response.json()
   ```

### 5.6 Standalone Mode

If `_get_backend_url()` returns `None`:

1. Acquire a memory client: `mem = get_memory()`.
2. Read content as UTF‑8 text:

   ```python
   text = path.read_text(encoding="utf-8", errors="replace")
   ```

3. Create memory in OpenMemory:

   ```python
   created = mem.add(
       text,
       userId=user_id,
       metadata=base_metadata,
       tags=base_tags,
   )
   ```

4. Wrap this in a structured result:

   ```python
   return {
       "mode": "standalone",
       "file": str(path),
       "user_id": user_id,
       "metadata": base_metadata,
       "tags": base_tags,
       "memory": created,
   }
   ```

---

## 6. Temporal Semantics and Versioning

The ingestion module is **version-aware but not opinionated**:

- It **records** `ingested_at` for every ingestion.
- It does **not decide** which version is “active” or “correct.”

This allows the retrieval layer (`memory_document_retrieval.py`) to:

- Retrieve the **latest** document.
- Retrieve the **earliest** document.
- Retrieve the **latest document as of a given timestamp**.

In practice:

- Re-ingesting the same file path creates another version with a newer `ingested_at`.
- No deletion or replacement is performed.
- All versions remain queryable.

---

## 7. Example Usage From llm-thalamus

### 7.1 Ingesting a Design Document

```python
from datetime import datetime, timezone
from memory_ingest import ingest_file

meta = {
    "provider": "evert",
    "provided_at": datetime.now(timezone.utc).isoformat(),
    "topic": "llm-thalamus memory design",
    "note": "File supplied during thalamus design session",
}

result = ingest_file(
    "documents/memory_storage.md",
    metadata=meta,
    tags=["llm-thalamus", "docs", "design"],
)

print("Ingested at:", result["metadata"]["ingested_at"])
print("Memory ID:", result["memory"]["id"])
```

### 7.2 Error Handling

- If the file does not exist:
  - `FileNotFoundError` is raised.
- If HTTP mode is enabled and the backend cannot be reached:
  - `requests.exceptions.RequestException` or a subclass is raised.
- If OpenMemory Python API fails:
  - Whatever exception `OpenMemory.add()` raises will propagate.

llm-thalamus can catch these and decide whether to retry, log, or report an error to the user.

---

## 8. Design Rationale

### 8.1 Why always add `file_ingest`?

- To distinguish ingested documents from conversational or procedural memories.
- To allow retrieval functions to filter by document origin and avoid mixing types.

### 8.2 Why treat caller metadata as additive?

- llm-thalamus and the LLM can annotate memories with arbitrary context (`topic`, `note`, `provider`, `doc_id`, etc.).
- Core ingestion metadata must remain reliable and consistent, so we prevent overrides on the critical fields only.

### 8.3 Why store full-file text in one memory (standalone)?

- Simplicity: one file → one memory → one retrieval result.
- Chunking and advanced handling are deferred to the backend mode, where OpenMemory has more information and capabilities.

---

## 9. Summary

`memory_ingest.py` is the **single authoritative module** for putting files into OpenMemory in the context of llm-thalamus. It:

- Works in both standalone and backend modes.
- Ensures consistent metadata and tagging.
- Records ingestion timestamps for later temporal selection.
- Plays nicely with the retrieval layer to support robust, version-aware document access.

Keep this document alongside the module so future work can integrate with the ingestion mechanism without re-reading or reverse-engineering the code.

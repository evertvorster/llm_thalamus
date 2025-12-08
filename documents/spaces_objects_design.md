
# Spaces & Objects System – Detailed Design Document
*(Full, exhaustive specification)*

---

# 0. Purpose

This document defines the **complete specification** of the Spaces & Objects feature for llm-thalamus,
covering:

- UI layout and UX logic  
- Data model (SQLite schema)  
- Backend ingestion and retrieval integration  
- State rules (active/inactive)  
- Versioning behavior  
- Interaction with Thalamus prompts  
- Metadata passed to OpenMemory  
- Module structure and required APIs  

This document is authoritative and should be referenced during implementation.

---

# 1. Conceptual Model

## 1.1 Spaces
A **Space** is a high-level container representing a project, topic, or conceptual domain.

### Properties:
- Has a **name** and **description** (set once at creation).
- Can be **active** or **inactive**.
- When inactive:
  - Appears grayed out in UI.
  - Sorted below active spaces.
  - Its objects/versions NEVER contribute to LLM prompts.
- Never deleted (soft-only lifecycle).

---

## 1.2 Objects
An **Object** represents a logical document tied to one specific filename.

### Rules:
- Object **name = filename (basename)** of first ingested file.
- This name is **immutable**.
- User renaming a file on disk requires creating a new Object.
- Objects can be active/inactive.
  - Inactive objects produce no prompt content.
- Objects belong to exactly one Space.

---

## 1.3 Versions
A **Version** represents a single ingestion event of a file belonging to an Object.

### Rules:
- All versions **must** use the same basename as the Object.
- A new version is created by ingesting a new file copy.
- Versions carry:
  - OpenMemory memory ID
  - ingestion timestamp
  - original file path
- Versions have **status**:
  - `"active"`: contributes to prompt
  - `"inactive"`: ignored
  - `"error"`: ingestion failed; retained but ignored

### Multi-version logic:
- Any number of versions may be active.
- Default behavior when feeding to LLM:
  - Use the **latest active version** per object.
  - This may evolve later.

---

# 2. User Interface Specification

## 2.1 Placement
The Spaces panel appears:
- To the **right of the chat window**
- Beneath the **pulsating brain** UI element

Panel title when at root: **“Spaces”**

---

## 2.2 Root Spaces View

### Controls:
- **Button: “Create Space”**
- **List/grid of Space icons**
  - Active spaces: normal color
  - Inactive: washed-out, listed after active ones

### Clicking a Space:
- Enters that space
- Hides the list of all spaces
- Changes panel header to:  
  **“Space: <Space Name>”**
- Displays grid of objects associated with that space as icons

---

## 2.3 Create Space Dialog

### Trigger:
Click “Create Space”.

### Dialog:
- Title: **Create New Space**
- Fields:
  - `QLineEdit`: “Name the new Space”
  - `QTextEdit`: “Short description of this space”
- Buttons:
  - **Create**
  - **Cancel**
  - **Help** (tooltip describing Spaces concept)

### Behavior:
- Upon Create:
  - Insert new Space into DB
  - Mark active
  - Add icon to UI
- No rename allowed later.

---

# 3. Space Interior UI

Inside a space:

### Header:
**Space: <Name>**

### Controls:
- **Button: “Create Object”**
- **Grid of Object icons**

### Object Icon Contents:
- Filename (object name)
- File-type icon (e.g., text)
- Visual markers:
  - Object inactive → dim icon
  - One version active: normal icon
  - multiple versions active: number displayed on normal icon.


### Right-click on Object:
Context menu:
- **Manage Versions…**
- (future) Toggle Object Active
- (future) Export metadata

Left-click on Object:
- Navigates into detailed view (optional future feature)
- For now: right-click only.

---

# 4. Create Object Workflow

### Trigger:
Inside Space → “Create Object”.

### Dialog:
- Title: **Create Object**
- Shows object TYPE buttons:
  - For now: **“Text File”**
  - Future types: “Image”, “Audio”, etc.

### When clicking “Text File”:
1. Qt file picker opens.
2. User selects a file.
3. Extract basename → object name.
4. Create new Object (active=1).
5. Ingest file as **version 1**:
   - Create Version entry
   - Mark version active
6. Add Object icon to Space grid.

### Error Cases:
- If basename already exists for another Object in this Space:
  - Reject and show dialog:
    > “An object named <filename> already exists in this space.”

---

# 5. Manage Versions Dialog

### Trigger:
Right-click Object → “Manage Versions…”

### Dialog Layout:
Title: **Versions – <object filename>**

### Contents:
- **Button: “New Version”**
- Table listing all versions:

Columns:
1. **Active checkbox**
2. Timestamp (ingested_at)
4. Note (optional future field)

### Rules:
- Checking/unchecking immediately updates DB.
- Deactivating all versions means the object contributes nothing, and icon is faded.
- **New Version** uses file picker:
  - Must match object.filename
  - If mismatched:
    > “This object tracks files named <x>. You selected <y>.  
    > If you renamed the file, create a new object.”

### Addition:
- On success:
  - Ingest file → create Version
  - Mark active
  - Refresh table

---

# 6. Data Model (SQLite Schema)

The database is stored in:

`data/spaces.db`

Tables:

---

## 6.1 `spaces`
```
id              INTEGER PRIMARY KEY
name            TEXT NOT NULL
description     TEXT
active          INTEGER NOT NULL DEFAULT 1
created_at      TEXT NOT NULL
```

---

## 6.2 `objects`
```
id              INTEGER PRIMARY KEY
space_id        INTEGER NOT NULL REFERENCES spaces(id)
name            TEXT NOT NULL                        -- filename
object_type     TEXT NOT NULL                        -- "text_file"
active          INTEGER NOT NULL DEFAULT 1
created_at      TEXT NOT NULL
```

Uniqueness rule:
```
UNIQUE (space_id, name)
```

---

## 6.3 `versions`
```
id              INTEGER PRIMARY KEY
object_id       INTEGER NOT NULL REFERENCES objects(id)
filename        TEXT NOT NULL                        -- mirror of object.name
original_path   TEXT NOT NULL
ingested_at     TEXT NOT NULL
openmemory_id   TEXT NOT NULL
status          TEXT NOT NULL CHECK(status IN ('active','inactive','error'))
note            TEXT
```

Indexes:
```
CREATE INDEX idx_versions_object ON versions(object_id);
CREATE INDEX idx_versions_status ON versions(status);
```

---

# 7. Backend: Integration With Ingestion

Object/Version ingestion uses:

`memory_ingest.ingest_file(file_path, metadata=..., tags=...)`

### Required metadata fields added by Spaces Manager:
```
space_id
space_name
object_id
object_name
object_type
```

### Required tags:
```
file_ingest (added automatically)
llm-thalamus
space:<id>
object:<id>
type:<object_type>
```

These integrate with OpenMemory retrieval rules.  
The ingestion returns:
- memory ID (`openmemory_id`)
- ingestion timestamp (`ingested_at`)

Stored in SQLite as part of the Version entry.

---

# 8. Retrieval for Thalamus Prompt

Before each LLM call:

Thalamus executes:

`docs = spaces_manager.get_active_documents_for_prompt()`

### Algorithm:

1. Get all active Spaces.
2. Get active Objects within them.
3. Get active Versions per object.
4. For each object:
   - Select **latest active version** by ingested_at.
   - Call `retrieve_document_from_metadata(...)` using:
     - filename
     - tags:
       ```
       file_ingest
       space:<id>
       object:<id>
       llm-thalamus
       ```
5. Return list of:
```
{
   "name": object_name,
   "text": retrieved_document_text
}
```

Thalamus injects these into the “OPEN DOCUMENTS (INTERNAL)” section.

---

# 9. Module Layout

Create new module:

```
spaces/
    __init__.py
    manager.py          # main API
    db.py               # SQLite init & helpers
    models.py           # dataclasses for Space/Object/Version
    ui/                 # Qt components (optional)
```

---

# 10. `spaces_manager` API Specification

### Creation
```
create_space(name, description)
list_spaces(active_only=False)
set_space_active(space_id, active: bool)
```

### Objects
```
create_object(space_id, file_path) -> object_id
list_objects(space_id, active_only=False)
set_object_active(object_id, active: bool)
```

### Versions
```
add_version(object_id, file_path) -> version_id
list_versions(object_id)
set_version_status(version_id, status)
```

### Prompt integration
```
get_active_documents_for_prompt() -> List[Dict[str,str]]
```

---

# 11. Enforcement Rules

### Filename immutability:
- Object name = filename (first version).
- All versions must have same basename.
- If different, reject ingestion.

### No delete:
- No physical remove of spaces/objects/versions.
- Only status toggles.

### Multi-version:
- Versions never overwrite each other.
- Always append-only.

### Consistency:
- Any ingestion failure must lead to version row with status="error".

---

# 12. Future Extensions (Non-blocking)

- Support other object types (PDF → text extraction)
- Hierarchical spaces
- Version diffs
- Space export/import

---

# 13. Summary

The Spaces & Objects system provides:

- User-controlled metadata routing for document ingestion
- Versioning with immutable object identity
- Clean UI flow for creation & management
- Deterministic prompt inclusion rules
- Strong alignment with OpenMemory ingestion metadata and retrieval

This document is the authoritative spec.


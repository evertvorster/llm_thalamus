# Thalamus Spaces & Memory Manager – User Guide

## 1. What This Application Is

The Thalamus Spaces & Memory Manager is the document hub for your local AI “brain”.

It sits between:

- **You** – choosing which files matter right now.
- **OpenMemory** – the database that stores long‑term memories.
- **The LLM** – which reads selected documents as context when answering your questions.

You use this UI to:

- Organize documents into **Spaces** (projects / worlds).
- Track each document as an **Object** (a stable filename).
- Manage **Versions** of each object as the document evolves.
- Control which documents are currently visible to the LLM.

The actual content lives in OpenMemory; this app stores only a small SQLite database (`spaces.db`) that indexes:

- Which spaces exist.
- Which objects belong to each space.
- Which versions exist for each object.
- Which space is currently “entered” and which versions are “active” for the LLM.

---

## 2. Core Concepts

### 2.1 Spaces

A **Space** is a high‑level container for related documents.

Think of a Space as:

- A **project** (“Dynamic Power Daemon”)
- A **topic** (“Property Research in Namibia”)
- A **world** (“Personal Journal”, “Fictional Setting”)

Each space:

- Has a **name** and **description**.
- Contains **Objects** (documents) that belong to that theme.
- Can be **active** or **inactive** for UI purposes (active spaces are not special to the LLM; they just sort to the top).
- Can be **“entered”** – when you enter a space, only that space’s active objects feed documents to the LLM.

> **Important:**  
> You can only **delete a space if it has no objects**.  
> To delete a space:
> 1. Remove all objects (by deleting their last versions).
> 2. Then delete the now‑empty space.

This safety rule prevents accidental mass deletion of lots of indexed content.

---

### 2.2 Objects

An **Object** represents a single logical document, identified by its **filename**.

Examples:

- `design_overview.md`
- `dynamic_power_requirements.txt`
- `property_notes.md`

When you create an object from a file:

- The object’s **name** is the file’s **basename** (e.g. `design_overview.md`).
- That name is **immutable** – the object always tracks documents with that filename.
- The content of the file is ingested into OpenMemory as a **Version** (see below).

You do **not** directly edit an object. Instead, you:

1. Edit the original file on disk with your normal editor.
2. Use the **“New Version”** button to ingest the updated file.
3. The object gets another version pointing to the new OpenMemory memory.

When you delete the **last** version of an object, the object itself is automatically removed from the space.

---

### 2.3 Versions

A **Version** is a particular snapshot of an object’s file that has been ingested into OpenMemory.

Each version stores:

- `object_id` – which object it belongs to.
- `filename` – the tracked filename.
- `original_path` – where the file lived at ingest time.
- `ingested_at` – when it was ingested.
- `openmemory_id` – the ID of the memory inside OpenMemory.
- `status` – one of:
  - `active` – eligible to be used as context for the LLM.
  - `inactive` – not used for context.
  - `error` – reserved for failures.

You can:

- Have multiple versions per object.
- Control which versions are active/inactive.
- Delete any version (including the latest one).

> **Deleting a version:**
> - Permanently deletes the underlying memory from OpenMemory.
> - Removes the corresponding version row from `spaces.db`.
> - If it was the **last version** of its object, the object is also deleted.

---

### 2.4 How the LLM Sees Your Documents

The LLM does not see everything in OpenMemory.

Instead, for each LLM request, Thalamus asks the Spaces manager:

> “Give me the active documents for the currently entered space.”

The manager returns:

- For the **current space only**:
  - All **active objects**.
  - For each such object: the **latest active version** (by time).
  - It retrieves each selected document’s text by its `openmemory_id`.

Those documents are then injected as **internal context** to the LLM. The LLM does not know about spaces, objects, or versions; it just sees text.

**Summary:**

- Only one **entered space** is considered at a time.
- Within that space, only **active objects** matter.
- For each object, only its **latest active version** is used.

---

## 3. User Interface Tour

### 3.1 Brain Panel

At the top of the panel is the **Brain Placeholder**:

- A black rectangle where the “pulsating brain” visualization lives.
- In the future it may show status, animations, or LLM activity.
- Currently it is mostly cosmetic and a placeholder container for the brain widget.

---

### 3.2 Spaces View (Root Mode)

When you are **not inside any space**, you are in **root mode**.

You’ll see:

- **Header:** `Spaces`
- **Primary button:** `Create Space`
- **List of spaces:** as icons with their names, optionally greyed out when inactive.

In this mode:

- Double‑click (or single‑click, depending on your desktop setting) a space to **enter** it.
- Right‑click a space to open the **context menu**.

#### Spaces context menu

Right‑click on a space → you get:

- **Activate / Deactivate Space**  
  This toggles a simple `active` flag used for UI sorting and greying out inactive spaces. It **does not** affect which space is entered or what the LLM sees.
- **Delete Space…**  
  Removes the space **only if it is empty** (contains no objects).  
  If it still has objects, a warning is shown explaining that you must first delete all objects from the space.

#### Creating a Space

Click **Create Space**:

1. Fill in the **Name** – e.g. `Dynamic Power Daemon`.
2. Optionally describe the space – e.g. “All docs for dynamic power daemon design & implementation.”
3. Click **Create**.

The new space appears in the list. You can enter it by activating the item.

---

### 3.3 Inside a Space (Objects View)

When you **enter a space**, the header changes to:

- `Space: <Name>`

You’ll see:

- **Back button:** `← Spaces` – returns to the root Spaces view.
- **Primary button:** `Create Object`
- **Objects list:** a grid of objects in this space, one per filename.

Each object item shows:

- Object name (the filename).
- An icon (file/document style).
- A tooltip with:
  - Object type (currently always `text_file`).
  - Created timestamp.

Inactive objects appear greyed out.

#### Creating a Text File Object

Click **Create Object**:

1. A dialog asks you which type of object to create.
   - Currently only **Text File** is implemented.
2. Choose **Text File**.
3. A file‑picker opens; select an existing text file (`.txt`, `.md`, `.rst`, `.adoc`, `.org`, or any file).
4. The application:
   - Creates a new object with the file’s basename as its name.
   - Ingests the file into OpenMemory as the first version.
   - Marks that version as `active`.

The new object appears in the objects list.

> **Note:**  
> The object’s name (filename) is fixed. If you rename the file later, you should create a new object for the new filename.

#### Objects context menu

Right‑click an object to see:

- **Manage Versions…**

Selecting this opens the **Versions dialog** for that object.

---

### 3.4 Managing Versions

The **Versions dialog** shows all versions for a single object.

You’ll see a table with:

- Column 1: **Active** – a checkbox.
- Column 2: **Ingested at** – timestamp of ingest.
- Column 3: **Filename** – the tracked filename.
- Column 4: **✕** – a per‑row delete button.

At the top:

- **New Version** – ingest a new version of this file.

At the bottom:

- **Close** – close the dialog.

#### Activating / deactivating versions

- Ticking the checkbox sets `status = active`.
- Unticking sets `status = inactive`.

This affects which versions the LLM considers when selecting the latest active version per object.

If changing the status fails (e.g. DB error), the dialog shows an error and reverts the checkbox.

#### Adding a new version

Click **New Version**:

1. A file dialog appears, filtered by the object’s filename.
2. Choose a file.
3. The dialog checks that the file’s basename matches the object’s name.
   - If mismatched, you’re prompted to create a new object instead.
4. On success, the file is ingested as a new version:
   - A new OpenMemory memory entry is created.
   - A new `versions` row is added as `active`.

The versions table is reloaded with the new row.

#### Deleting a version

Each row has a small **✕** button on the right.

Clicking it:

1. Shows a confirmation dialog explaining:
   - The version and its OpenMemory content will be deleted.
   - If it’s the last version, the object will also be removed.
2. On confirmation:
   - The corresponding OpenMemory memory is deleted.
   - The version row is removed from `spaces.db`.
   - If it was the **last version**, the object is also deleted.

After deletion:

- The versions table is reloaded.
- If no versions remain, the dialog closes.
- When you return to the objects list, it will no longer show an object that lost its last version.

---

## 4. Recommended Usage Patterns

### 4.1 Organize by Space

Create a separate space for each major area of your life or work, for example:

- `Dynamic Power Daemon`
- `Property Research`
- `Thalamus Design`
- `Personal Journal`

This keeps contexts clean and prevents unrelated documents from mixing.

### 4.2 Treat Objects as canonical filenames

Each object is bound to a single filename. Recommended approach:

- Choose stable filenames:  
  `design_overview.md`, `requirements.md`, `project_history.md`.
- Keep using the same filename as your “canonical” document.
- When the content changes significantly, ingest a new version rather than new filenames.

### 4.3 Use Versions for history and safety

- Every time you make substantial edits, ingest a new version:
  - This gives you a historical record.
  - You can keep old versions inactive but not deleted if you might need them.
- Deactivate old versions when they are no longer the “current truth” you want the LLM to see.
- Delete obsolete versions you know you don’t need to free up mental clutter (and OpenMemory storage).

### 4.4 Control context for the LLM

To control what the LLM sees:

1. **Enter** the space you want to work in.
2. Ensure only the relevant **objects** are marked active.
3. Within each object, ensure the correct **version** is active.

The LLM will then:

- Only pull documents from the **current space**.
- For each active object, see the **latest active version** text.

---

## 5. Best Practices

- **Use meaningful space descriptions**  
  Future‑you will thank present‑you for a one‑sentence reminder.

- **Do not overload a single space**  
  If a space gets messy, split it into smaller thematic spaces.

- **Keep filenames stable**  
  Renaming files frequently will create more objects than needed.

- **Use active/inactive instead of deleting right away**  
  For documents you might need later, mark versions or objects inactive instead of deleting them.

- **Delete stale versions and empty spaces periodically**  
  Keeps navigation smoother and the mental model clear.

- **Remember deletions are permanent**  
  Deleting a version removes that text from OpenMemory.  
  Deleting the last version removes the object from the space.  
  Deleting a space is only possible once all its objects are removed.

---

## 6. Troubleshooting

### 6.1 I can’t delete a space

**Symptom:** You try to delete a space and see an error that it still contains objects.

**Fix:**

1. Enter the space.
2. For each object, open **Manage Versions…**.
3. Delete the last version of each object (if appropriate).
4. Once all objects are gone, go back to **Spaces** and delete the space.

---

### 6.2 An object disappeared after I deleted a version

This is expected if you deleted the **last version** of that object:

- The last version is removed.
- The object is automatically deleted from the space.

If this was unintentional, you will need to re‑create the object by ingesting the file again.

---

### 6.3 The LLM isn’t using my documents

Check:

1. **Are you inside the correct space?**  
   The header should show `Space: <Name>` for the project you care about.

2. **Is the object active?**  
   An inactive object will be ignored.

3. **Does the object have at least one active version?**  
   If no version is active, the object contributes nothing.

4. **Did ingestion succeed?**  
   If a version shows as missing or failed to ingest, try adding a new version.

---

### 6.4 I see old content instead of the latest doc

Most likely:

- The LLM is reading an older active version.

Check:

1. Open **Manage Versions…** for that object.
2. Confirm the version you want is marked **active**.
3. Deactivate older versions if they are no longer relevant.

---

## 7. Future Directions

The current implementation focuses on **text files** and a simple, robust lifecycle:

- Space → Object → Versions → LLM context.

Planned or possible future enhancements include:

- Additional object types:
  - Images (for visual recall or multimodal models).
  - Audio (transcripts or notes).
- Automatic ingestion from watch folders.
- Richer metadata (tags, topics) visible in the UI.
- More powerful search and filter within a space.
- Inline document previews or Markdown rendering in the UI.

---

## 8. Summary

The Thalamus Spaces & Memory Manager gives you:

- Clear, project‑centric organization via **Spaces**.
- Stable document identities via **Objects**.
- Historical snapshots and safe updates via **Versions**.
- Fine‑grained control over what your LLM sees as context.

Use it as the **curation layer** for your AI’s long‑term memory:

- Place only the documents that matter into spaces.
- Keep them tidy with meaningful objects and versions.
- Turn context on and off as needed by toggling statuses.

With a small amount of discipline, this structure keeps your AI from drowning in unstructured notes and lets you deliberately choose which documents define the “world” it works in for each project.

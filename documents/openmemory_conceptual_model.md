
# OpenMemory: Core Conceptual Model (How It Actually Works)

This is the model you should keep in mind when designing Thalamus, memory prompts, reflection passes, or storage rules.

---

## 1. What OpenMemory *is*

OpenMemory is not a simple vector database.
It is a **cognitive memory system** inspired by human memory architecture.

Internally, it behaves like:

> A brain-like, multi-sector semantic graph with automatic classification, salience weighting, and temporal decay.

Every memory you store becomes a **node** in a graph, with:

- sector (type of memory)
- embeddings
- metadata
- tags
- salience
- temporal information
- associations (implicit links) to other memories

All of this is managed automatically.

---

## 2. Memory Sectors (the “Brain Regions”)

OpenMemory categorizes each memory into one or more *sectors*. These sectors are fundamental to how storage, retrieval, decay, and relevance work.

### Sectors

1. **Semantic** — Facts, stable information, identity, world knowledge  
2. **Episodic** — Events anchored in time, experiences  
3. **Procedural** — Instructions, how-to steps, repeatable workflows  
4. **Emotional** — Feelings, sentiment, reactions  
5. **Reflective** — Insights, takeaways, self-observations  

You can hint these via metadata/tags, but OpenMemory ultimately decides based on the **content**.

The sectors influence:

- Which memories are retrieved for a given query type  
- How memories decay  
- How graph associations form  

---

## 3. Memory Structure (always the same shape)

Every memory internally contains:

- content (the text you store)  
- embedding vector  
- primarySector (one of the five above)  
- sectors (possibly multiple)  
- tags (arbitrary labels)  
- metadata (JSON)  
- salience (importance score)  
- created_at / updated_at timestamps  
- cluster associations and concept nodes  

Metadata and tags do *not* determine sectors.
Sector classification is derived from analyzing the content.

---

## 4. Automatic Classification

When you add a memory:

1. Text → embedding  
2. Embedding + parsed linguistic cues →  
   - Determine primary sector  
   - Build secondary sectors  
   - Extract entities  
3. Memory is inserted into a semantic graph  
4. Associations are created:
   - Entities
   - Topics
   - Prior memories with similar content
   - Temporal sequence (episodic)
5. Salience is initialized, usually mid-range  
6. Decay is scheduled (unless reinforced)

This is why short, atomic memories work best:
more focused memories = cleaner classification & stronger association links.

---

## 5. Salience (Importance Model)

Salience determines:

- Retrieval priority  
- How strongly memories resist temporal decay  
- How long they remain relevant  
- How quickly they surface in multi-hop searches  

Salience changes when:

- Memory is retrieved (reinforced)  
- Other memories pointing to it change  
- New memories overlap conceptually  
- It decays naturally over time  

OpenMemory uses salience similarly to a human brain:
important memories stay fresh, unused ones fade.

---

## 6. Decay (Cold/Warm/Hot Tiers)

Memories move across tiers:

- **Hot** — recently accessed, high salience  
- **Warm** — moderately relevant  
- **Cold** — long-unaccessed, low salience  
- **Archived** — deprioritized but not deleted  

Decay rate depends on:

- Sector  
  - episodic decays faster  
  - semantic decays slower  
- Salience  
- Reinforcement frequency  
- Relationships to important memories  

You cannot directly control decay, except by:

- Boosting salience (reinforce)
- Writing more stable content
- Giving consistent metadata & tags so they cluster

---

## 7. Retrieval

When you run a query:

1. Embed the query  
2. Compare against all memory embeddings  
3. Weight by:
   - similarity  
   - sector relevance  
   - salience  
   - recency  
   - tag/metadata filters  
4. Expand to the graph (multiple hops) when needed  
5. Return a ranked list with scores  

Retrieval is semantic, not purely keyword-based.

Key point:

> Retrieval is not purely “vector nearest neighbours” — it is a weighted blend of vectors + sector cues + time + salience + associations.

---

## 8. Temporal Graph (episodic timeline)

Every episodic memory contributes to a **timeline of events**.

Useful for:

- answering “When did I last…?”  
- reconstructing past actions  
- summarizing experiences  
- extracting causal sequences  

OpenMemory uses timestamp metadata (`date`, `created_at`, `ingested_at`) to anchor events.

This is why you want:

- ISO-8601 timestamps  
- Event-like descriptions  
- One event per memory node  

---

## 9. Concept / Entity Graph

Chunks of text containing entities (names, places, tools, projects) get linked to **concept nodes**.

Examples:

- “Evert”
- “dynamic_power_daemon”
- “ASUS ROG laptop”
- “screen refresh”

A sector-specific memory may link to multiple concepts.

This is how OpenMemory achieves:

- Multi-hop retrieval  
- Combining facts + procedures + episodes about the same topic  
- Inferring patterns (“Evert often works with Arch Linux systems”)  

---

## 10. Why atomic memories are essential

All of OpenMemory’s strengths assume that a memory = one conceptual unit.

If you store long paragraphs:

- Sector classification gets muddied  
- Associations become weaker  
- Retrieval pulls in irrelevant details  
- Reflection becomes noisy  

Atomic memories allow:

- clean graph edges  
- predictable association  
- precise sector classification  
- reliable salience signals  
- good temporal reasoning  
- better decay behaviour

---

## 11. Tags and Metadata (how they influence behaviour)

Tags and metadata:

- Do NOT set sectors  
- Do NOT set salience  
- Do NOT override the classifier  

But they DO:

### Improve retrieval precision

When you filter by tags or metadata, you enforce semantic scopes:

- `"dynamic_power_daemon"`  
- `"travel"`  
- `"chat"`  
- `"persona"`  
- `"llm-thalamus"`

Tags create hard filters, restricting the candidate set before scoring.

### Enable multi-plane separation

This lets you maintain:

- separate memories for different projects  
- separate memories for “persona”, “chat history”, “docs”, etc.  
- different retrieval behaviours depending on query type  

### Support time-travel retrieval

Metadata fields like `ingested_at`, `date`, `timestamp` let you:

- pick latest/earliest versions of docs  
- reconstruct past steps  
- resolve concurrency in conversations  
- map episodic sequences  

---

## 12. Reflection memories (how OM uses them)

Reflective memories:

- Are short insights derived from experience  
- Are usually higher salience  
- Tie together multiple sectors  
- Help the system generalize patterns  
- Influence future ranking (because they are dense summaries)

This is why OpenMemory encourages storing reflection notes.

---

## 13. Multi-hop reasoning

Because of its internal graph:

- A query can retrieve memories not directly similar in embedding space, but connected through concept nodes.

Example:

User says:  
“Why is my laptop battery draining so fast today?”

OpenMemory may retrieve:

- Episodic: “On 2025-07-20, Evert enabled screen refresh boosting on battery.”  
- Procedural: “To lower power usage, disable panel overdrive and use min refresh.”  
- Semantic: “Asus ROG laptops draw high idle power at 240Hz refresh on battery.”  

These live in different sectors but connect through shared concepts.

---

## 14. Summary: The Real Mental Model

OpenMemory is best thought of as:

> A self-organizing semantic/episodic/procedural graph with weighted associations, time-awareness, and sector-aware decay.

Each memory:

- Is automatically classified  
- Gains a place in a multi-sector graph  
- Receives a salience score  
- Decays unless reinforced  
- Associates with concept nodes  
- Becomes part of a temporal chain (if episodic)  
- Is ranked against future queries via a composite score of:
  - semantic similarity  
  - sector relevance  
  - salience  
  - recency  
  - tag/metadata filters  
  - graph connectivity  

This is the conceptual foundation you should design Thalamus prompts around.

# Architecture and Plan for llm-thalamus

## 1. Overall Plan
We are transitioning `llm_thalamus.py` from a monolithic script into a modular, call-driven, template-based runtime. The LLM behavior moves into external text templates, while Python code becomes a clean dispatcher and data assembler. This enables smaller modules, cleaner logic, safer diffs, and extensibility.

## 2. Implementation Details
- Introduced template files for answer and reflection calls.
- Per-call configuration added to config.json.
- Removal of inline prompt blocks.
- Thalamus uses prompt templates and performs simple token replacement.
- Memory and history limits follow per-call settings.
- Thalamus code now thinner and more modular.

## 3. What Has Been Accomplished
- Reflection call fully externalized.
- Answer call fully externalized.
- Major reduction of inline text inside core logic.
- Stable per-call API structure implemented in config.
- Prompt loader added and working.
- Code is slimmer, and easier to extend.

## 4. Next Immediate Steps
- Package the new prompt files via Makefile.
- Begin splitting llm_thalamus.py into modules:
  - call dispatcher module
  - memory adapter module
  - conversation history module
  - template processor module
- Optional: add dispatch_call() as the central API.

## 5. Ultimate Goal
A modular, scalable, maintainable thalamus system:
- All prompts external and editable.
- Clear per-call dispatch API.
- Concise core logic and safe updates.
- Clean communication with UI and worker.
- Ability to extend with new call types seamlessly.


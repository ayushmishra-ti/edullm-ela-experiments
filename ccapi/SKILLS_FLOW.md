# Skills API Flow (per [Claude Skills Guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide))

## What the guide says

1. **Create a custom skill**  
   Upload your skill (e.g. `SKILL.md` + any files) via the Skills API:  
   `client.beta.skills.create(display_title=..., files=..., betas=["skills-2025-10-02"])`  
   → You get a `skill_id`.

2. **Use it in the Messages API**  
   Call `client.beta.messages.create` with:
   - `betas=["code-execution-2025-08-25", "skills-2025-10-02"]`
   - `container={"skills": [{"type": "custom", "skill_id": "<id>", "version": "latest"}]}`
   - `tools=[{"type": "code_execution_20250825", "name": "code_execution"}]`
   - Your user `messages`

Claude then loads the skill in the container and uses it when relevant.

---

## What we have

### 1. Custom skill (upload)

**Script:** `scripts/upload_skill.py`

**Where it gets the skill:**  
`skills/ela-mcq-generation/SKILL.md`  
(i.e. `ccapi/skills/ela-mcq-generation/SKILL.md`)

It reads that file (or uses `anthropic.lib.files_from_dir` on that directory) and calls:

```text
client.beta.skills.create(
  display_title="Grade 3 ELA MCQ Generation",
  files=...,
  betas=["skills-2025-10-02"]
)
```

You must run it once, then put the printed `skill_id` in `.env` as:

```text
CCAPI_ELA_MCQ_SKILL_ID=skill_xxxxx
```

### 2. Container usage (Skills API mode)

**Code:** `src/ccapi/pipeline.py` → `generate_one()`

If `CCAPI_ELA_MCQ_SKILL_ID` is set, we use the **Skills API + container** path:

- `client.beta.messages.create(`
  - `betas=["code-execution-2025-08-25", "skills-2025-10-02"]`
  - `container={"skills": [{"type": "custom", "skill_id": CCAPI_ELA_MCQ_SKILL_ID, "version": "latest"}]}`
  - `tools=[{"type": "code_execution_20250825", "name": "code_execution"}]`
  - `messages=[{"role": "user", "content": <request JSON>}]`
- `)`

So we **do** implement the “custom skill + container” flow when the env is set.

### 3. Fallback (no container)

If `CCAPI_ELA_MCQ_SKILL_ID` is **not** set:

- We **do not** call the Skills API or use `container`.
- We read `skills/ela-mcq-generation/SKILL.md` from disk and put it in the **system** prompt of a normal `client.messages.create` (no `container`, no `code_execution` tool, no `beta` for skills/code-execution).

So the **same** `SKILL.md` is used, but:
- **Skills API:** uploaded → `container` + `code_execution` (as in the guide).
- **Fallback:** local file → system prompt only (not the official Skills + container flow).

---

## How to tell which ran

- **Batch output:** `outputs/batch_generated.json` has a top-level `"generation_mode"`:
  - `"skills_api"` → container + custom skill.
  - `"fallback"` → skill from file as system prompt.
  - `"unknown"` → e.g. no API key, or old run before this field existed.

- **Single run:** `generate_one()` now returns `"generation_mode"` in its dict as well.

---

## Summary

| Step | In the guide | In ccapi |
|------|--------------|----------|
| Create custom skill | `skills.create(...)` | `scripts/upload_skill.py` (from `skills/ela-mcq-generation/SKILL.md`) |
| Use in container | `container={"skills": [{ type, skill_id, version }]}` + `code_execution` tool + betas | `pipeline.generate_one` when `CCAPI_ELA_MCQ_SKILL_ID` is set |
| If skill_id not set | — | Fallback: same `SKILL.md` as system prompt, no container |

**Your `batch_generated.json` (1 item, 0 errors):**  
If you never ran `upload_skill.py` and never set `CCAPI_ELA_MCQ_SKILL_ID`, `generation_mode` would be `"fallback"`.  
After the last changes, new runs will show `generation_mode` in the file. To use the real **custom skill + container** path: run `upload_skill.py`, set `CCAPI_ELA_MCQ_SKILL_ID` in `.env`, then run `generate_batch` again.

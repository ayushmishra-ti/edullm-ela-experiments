# ELA MCQ Generation - Claude Orchestrated (Agent Skills)

This project generates K-12 ELA multiple-choice questions using **Claude as the orchestrator** via Cursor Agent Skills. Claude autonomously decides which tools/scripts to run based on the request.

## Architecture

### Before (Python Orchestrated)
```
User Request → Python Pipeline → Claude API → Python Processes Response
```

### Now (Claude Orchestrated)
```
User Request → Claude reads SKILL.md → Claude runs scripts → Claude generates response
```

**Key difference**: Claude decides when to call curriculum lookup, generate passages, and how to create questions. No Python code orchestrates the flow.

## Agent Skills Structure

```
.cursor/skills/
├── ela-mcq-pipeline/          # Master orchestration skill
│   ├── SKILL.md               # Instructions for Claude
│   ├── scripts/               # Executable tools
│   │   ├── lookup_curriculum.py
│   │   ├── populate_curriculum.py
│   │   └── generate_passage.py
│   └── references/
│       └── curriculum.md      # Curriculum database
│
├── lookup-curriculum/         # Standalone curriculum lookup
│   ├── SKILL.md
│   └── scripts/
│       └── lookup_curriculum.py
│
├── populate-curriculum/       # Generate missing curriculum data
│   ├── SKILL.md
│   └── scripts/
│       └── populate_curriculum.py
│
└── generate-passage/          # Generate reading passages
    ├── SKILL.md
    └── scripts/
        └── generate_passage.py
```

## How It Works

1. **User asks** to generate an ELA question
2. **Cursor detects** the `ela-mcq-pipeline` skill is relevant
3. **Claude reads** the SKILL.md instructions
4. **Claude decides** what tools to run:
   - Runs `lookup_curriculum.py` to get assessment boundaries
   - If data missing, runs `populate_curriculum.py`
   - If RL.*/RI.* standard, runs `generate_passage.py`
5. **Claude generates** the question using gathered context
6. **Claude returns** JSON response

## Usage

### In Cursor Chat

Simply ask Claude to generate questions:

```
Generate an MCQ for standard CCSS.ELA-LITERACY.L.3.1.A (easy difficulty)
```

Or provide a full request:

```json
{
  "type": "mcq",
  "grade": "3",
  "skills": {
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
    "substandard_description": "Explain the function of nouns, pronouns, verbs..."
  },
  "difficulty": "easy"
}
```

### Manual Script Usage

You can also run scripts directly:

```bash
# Lookup curriculum data
python .cursor/skills/ela-mcq-pipeline/scripts/lookup_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A"

# Populate missing curriculum
python .cursor/skills/ela-mcq-pipeline/scripts/populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.B" "Form and use regular and irregular plural nouns."

# Generate passage (for RL.*/RI.* standards)
python .cursor/skills/ela-mcq-pipeline/scripts/generate_passage.py "CCSS.ELA-LITERACY.RL.3.1" "3" "narrative"
```

## Available Skills

| Skill | Description | When to Use |
|-------|-------------|-------------|
| `ela-mcq-pipeline` | Full MCQ generation pipeline | Generating ELA questions |
| `lookup-curriculum` | Search curriculum database | Getting assessment boundaries |
| `populate-curriculum` | Generate missing curriculum data | Before generating questions for new standards |
| `generate-passage` | Create reading passages | For RL.*/RI.* standards |

## Data Files

- `data/curriculum.md` - Grade 3 ELA curriculum database
- `data/passages/` - Cached reading passages
- `data/grade-3-ela-benchmark.jsonl` - Test benchmark file

## Output Format

All questions follow this JSON structure:

```json
{
  "id": "l_3_1_a_mcq_easy_001",
  "content": {
    "answer": "B",
    "question": "Which word in this sentence is a noun?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "sleeps"},
      {"key": "B", "text": "cat"},
      {"key": "C", "text": "soft"},
      {"key": "D", "text": "on"}
    ],
    "answer_explanation": "A noun names a person, place, thing, or animal..."
  }
}
```

## Grade Support

Supports all grades K-12:
- **K-2**: Simple vocabulary, short sentences
- **3-5**: Grade-level vocabulary, simple/compound sentences
- **6-8**: Academic vocabulary, complex sentences allowed
- **9-12**: Sophisticated vocabulary, advanced structures

## Standards Support

- **L.*** (Language): Grammar, vocabulary, conventions
- **RL.*** (Reading Literature): Stories, poems, drama (requires passage)
- **RI.*** (Reading Informational): Articles, essays (requires passage)
- **W.*** (Writing): Writing skills (no passage needed)

## Key Differences from Python Orchestration

| Aspect | Python Orchestrated | Claude Orchestrated |
|--------|---------------------|---------------------|
| Decision making | Python code | Claude (AI) |
| Flow control | Hardcoded in pipeline.py | Claude reads SKILL.md |
| Flexibility | Change requires code edits | Change SKILL.md instructions |
| Error handling | Try/except in Python | Claude adapts based on script output |
| Adding tools | Write new Python functions | Add new scripts + update SKILL.md |

## Cloud Deployment

This project can be deployed as a cloud endpoint using Claude Agent SDK with MCP tools.

### Architecture (Cloud Endpoint)

The cloud endpoint uses **Claude Agent SDK** (not Cursor Agent Skills) where:
- Claude autonomously decides when to call MCP tools
- Tools are exposed via MCP server (lookup_curriculum, populate_curriculum)
- Claude generates questions after gathering curriculum context

### Deploy to Google Cloud Run

See [DEPLOY.md](DEPLOY.md) for detailed instructions.

**Quick Deploy:**
```bash
cd agent_sdk

# Build
gcloud builds submit . \
  --config cloudbuild.yaml \
  --substitutions=_IMAGE_NAME="us-central1-docker.pkg.dev/eternal-aspect-485115-e3/ccapi-repo/inceptagentic-skill-mcq:latest"

# Deploy
gcloud run deploy inceptagentic-skill-mcq \
  --image us-central1-docker.pkg.dev/eternal-aspect-485115-e3/ccapi-repo/inceptagentic-skill-mcq:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest
```

**Service URL:** `https://inceptagentic-skill-mcq-413562643011.us-central1.run.app/generate`

### API Endpoint

**POST /generate**
- Accepts InceptBench Generator API Interface format
- Returns JSON with generated questions
- Supports MCQ, MSQ, Fill-in types

## References

- [Cursor Agent Skills Documentation](https://cursor.com/docs/context/skills)
- [Agent Skills Standard](https://agentskills.io)
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk)

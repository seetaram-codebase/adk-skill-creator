# adk-skill-creator

A FastAPI service that generates production-ready skills from natural language intent using [Google ADK](https://google.github.io/adk-docs/) and the [agentskills.io](https://agentskills.io) specification.

## How it works

1. You POST a natural language intent (`"review PRs for security vulnerabilities"`)
2. The ADK agent activates the `skill-creator` skill via `SkillToolset`
3. A complete skill directory is generated on disk and a `draft_id` is returned
4. Fetch the skill content anytime via `GET /skills/{draft_id}`

### Generated skill structure

```
generated-skills/
└── pr-security-review/
    ├── SKILL.md              # Required — frontmatter + instructions
    ├── references/
    │   └── REFERENCE.md      # Detailed docs (if needed)
    ├── scripts/
    │   └── run.py            # Helper scripts (if needed)
    └── assets/
        └── template.md       # Templates/resources (if needed)
```

Only folders that genuinely add value are created.

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/seetaram-r/adk-skill-creator
cd adk-skill-creator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Clone the skill-creator skill
git clone https://github.com/anthropics/skills.git

# 4. Set your API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# 5. Run
uvicorn main:app --reload
```

## API

### `POST /skills` — Create a skill

```bash
curl -X POST http://localhost:8000/skills \
  -H "Content-Type: application/json" \
  -d '{"intent": "review pull requests for security vulnerabilities"}'
```

```json
{
  "draft_id": "f3a1b2c3-...",
  "skill_name": "pr-security-review",
  "skill_path": "./generated-skills/pr-security-review",
  "files_created": ["SKILL.md", "references/REFERENCE.md"]
}
```

### `GET /skills/{draft_id}` — Retrieve a skill

```bash
curl http://localhost:8000/skills/f3a1b2c3-...
```

### `GET /skills` — List all drafts

```bash
curl http://localhost:8000/skills
```

## Stack

- [FastAPI](https://fastapi.tiangolo.com)
- [Google ADK](https://google.github.io/adk-docs/) with `SkillToolset`
- [agentskills.io specification](https://agentskills.io/specification)
- Gemini 2.5 Pro

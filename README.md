# skill-builder-api

A production-ready FastAPI service that creates [agentskills.io](https://agentskills.io)-compliant skills through multi-turn conversation, powered by [Google ADK](https://google.github.io/adk-docs/) and Gemini 2.5 Pro.

## How it works

1. Start a conversation via `POST /skills/chat/stream`
2. The agent asks clarifying questions, then generates a complete skill
3. Each skill is saved as a draft — fetch or download anytime via `draft_id`
4. Refine the skill across multiple turns using the same `session_id`

### Architecture

```mermaid
flowchart TD
    Client([Client])

    subgraph API["FastAPI — main.py"]
        CS[POST /skills/chat/stream]
        CN[POST /skills/chat]
        GD[GET /skills/draft_id]
        GF[GET /skills/draft_id/files/path]
        DL[GET /skills/draft_id/download]
        LS[GET /skills]
        HE[GET /health]
    end

    subgraph Core["Core Modules"]
        AG["agent.py\nADK LlmAgent + Runner\nSkillToolset"]
        SK["skills.py\nParse · Save · Zip"]
        ST["storage.py\nSQLite"]
    end

    subgraph Persist["Persistence"]
        DB[(skill_builder.db\ndrafts · sessions)]
        FS[/generated-skills/\nskill-name/SKILL.md\nreferences · scripts · assets/]
    end

    subgraph External["External"]
        ADK[Google ADK]
        GEM[Gemini 2.5 Pro]
        SKILL[skill-creator\nSKILL.md]
    end

    Client -->|message + session_id| CS
    Client -->|message + session_id| CN
    Client -->|draft_id| GD
    Client -->|draft_id + path| GF
    Client -->|draft_id| DL
    Client --> LS
    Client --> HE

    CS -->|run_async| AG
    CN -->|run_async| AG
    AG -->|SkillToolset| SKILL
    AG -->|API calls| ADK
    ADK -->|inference| GEM
    AG -->|raw output| SK
    SK -->|write files| FS
    SK -->|save_draft| ST
    ST -->|read/write| DB

    GD -->|get_draft| ST
    GF -->|get_draft| ST
    DL -->|get_draft + build_zip| ST
    LS -->|list_drafts| ST
```

### Conversation flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant AG as ADK Agent
    participant SK as skills.py
    participant DB as SQLite

    C->>API: POST /skills/chat/stream\n{message: "create a skill for PRs"}
    API-->>C: event: status {session_id}
    API->>AG: run_async(message)
    AG-->>API: token stream
    API-->>C: event: token {text} (repeated)
    AG-->>API: final response — clarifying question
    API-->>C: event: done {session_id, draft_id: null}

    C->>API: POST /skills/chat/stream\n{message: "Python, security", session_id}
    API->>AG: run_async(message, same session)
    AG-->>API: token stream — writing SKILL.md
    API-->>C: event: token {text} (repeated)
    AG-->>API: final response — skill files
    API->>SK: save_skill_from_output()
    SK->>DB: save_draft(draft_id)
    API-->>C: event: draft {draft_id, files_created}
    API-->>C: event: done {session_id, draft_id}

    C->>API: GET /skills/{draft_id}/download
    API->>DB: get_draft(draft_id)
    API-->>C: skill-name.zip
```

## Project structure

```
skill-builder-api/
├── main.py        # FastAPI app + all routes
├── agent.py       # ADK agent + runner setup
├── skills.py      # File I/O — save, zip skill directories
├── storage.py     # SQLite persistence for drafts + sessions
├── requirements.txt
└── .env.example
```

## Setup

```bash
git clone https://github.com/seetaram-codebase/skill-builder-api
cd skill-builder-api

pip install -r requirements.txt

# Clone the skill-creator skill
git clone https://github.com/anthropics/skills.git

cp .env.example .env
# Add your GOOGLE_API_KEY

uvicorn main:app --reload
```

## API

### Primary: multi-turn chat with SSE streaming

```bash
curl -N -X POST http://localhost:8000/skills/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "create a skill for reviewing PRs"}'
```

SSE events:
| Event | Payload | When |
|---|---|---|
| `status` | `{message, session_id}` | Turn start |
| `token` | `{text}` | Agent writing (live) |
| `draft` | `{draft_id, skill_name, files_created}` | Skill saved |
| `done` | `{session_id, draft_id}` | Turn complete |
| `error` | `{detail}` | Failure |

Continue a conversation:
```bash
curl -N -X POST http://localhost:8000/skills/chat/stream \
  -d '{"message": "add OWASP checks", "session_id": "abc123"}'
```

### Non-streaming (simple clients)

```bash
curl -X POST http://localhost:8000/skills/chat \
  -d '{"message": "create a skill for reviewing PRs"}'
# → {"session_id": "...", "reply": "...", "draft_id": "..."}
```

### Draft endpoints

```bash
GET  /skills                          # list all drafts
GET  /skills/{draft_id}               # get draft + all file contents
GET  /skills/{draft_id}/files/SKILL.md           # single file
GET  /skills/{draft_id}/files/references/REFERENCE.md
GET  /skills/{draft_id}/download      # download as zip
```

### Health

```bash
GET /health  → {"status": "ok", "version": "1.0.0"}
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | required | Gemini API key |
| `SKILLS_DIR` | `./skills/skill-creator` | Path to skill-creator SKILL.md |
| `SKILLS_OUTPUT_DIR` | `./generated-skills` | Where generated skills are saved |
| `DB_PATH` | `./skill_builder.db` | SQLite database path |
| `MODEL` | `gemini-2.5-pro` | Gemini model to use |

## Stack

- [FastAPI](https://fastapi.tiangolo.com)
- [Google ADK](https://google.github.io/adk-docs/) with `SkillToolset`
- [agentskills.io specification](https://agentskills.io/specification)
- SQLite (via stdlib `sqlite3`)
- Gemini 2.5 Pro

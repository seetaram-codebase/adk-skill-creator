from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, AsyncGenerator
import uuid, os, re, zipfile, io, json

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

app = FastAPI(title="Skill Builder API", version="1.0.0")

skill_toolset = SkillToolset(skills_dir="./skills/skill-creator")

agent = LlmAgent(
    name="skill_builder_agent",
    model="gemini-2.5-pro",
    instruction="""You create complete, production-ready skills from user intent.

Use the skill-creator skill to generate all necessary files.

Output only the files that are genuinely needed, using named fences:

```skill.md              → SKILL.md with valid frontmatter (name + description required)
```references/REFERENCE.md  → detailed reference docs (if the skill needs lookup material)
```scripts/run.py           → helper script (if the skill needs executable code)
```assets/template.md       → templates or static resources (if the skill needs them)

Rules:
- skill name must be lowercase, hyphens only, no spaces
- folder name must match the name field in frontmatter
- only include files that genuinely add value""",
    tools=[skill_toolset],
)

session_service = InMemorySessionService()
runner = Runner(
    agent=agent,
    app_name="skill-builder-api",
    session_service=session_service,
)

SKILLS_OUTPUT_DIR = "./generated-skills"
os.makedirs(SKILLS_OUTPUT_DIR, exist_ok=True)


class CreateSkillRequest(BaseModel):
    intent: str
    name: Optional[str] = None


class CreateSkillResponse(BaseModel):
    draft_id: str
    skill_name: str
    skill_path: str
    files_created: list[str]


class GetSkillResponse(BaseModel):
    draft_id: str
    skill_name: str
    skill_path: str
    files: dict[str, str]


# In-memory draft registry: draft_id -> {skill_name, skill_path, files}
draft_registry: dict[str, dict] = {}


def _parse_and_save(raw_output: str, skill_name_override: Optional[str]) -> tuple[str, str, list[str]]:
    """Parse fenced blocks from agent output, save to disk, return (skill_name, skill_dir, files_created)."""
    blocks = re.findall(r"```(\S+)\n(.*?)```", raw_output, re.DOTALL)
    if not blocks:
        raise ValueError("Agent did not produce any skill files")

    skill_md_content = next((c for f, c in blocks if f == "skill.md"), None)
    if not skill_md_content:
        raise ValueError("Agent did not produce SKILL.md")

    name_match = re.search(r"^name:\s*(.+)$", skill_md_content, re.MULTILINE)
    skill_name = skill_name_override or (name_match.group(1).strip() if name_match else str(uuid.uuid4())[:8])
    skill_dir = os.path.join(SKILLS_OUTPUT_DIR, skill_name)

    files_created = []
    for fname, content in blocks:
        target = "SKILL.md" if fname == "skill.md" else fname
        file_path = os.path.join(skill_dir, target)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content.strip())
        files_created.append(target)

    return skill_name, skill_dir, files_created


@app.post("/skills", response_model=CreateSkillResponse)
async def create_skill(req: CreateSkillRequest):
    """Generate a complete skill from natural language intent."""
    session = await session_service.create_session(
        app_name="skill-builder-api",
        user_id="skill-builder",
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=f"Create a complete skill for: {req.intent}")]
    )

    raw_output = ""
    async for event in runner.run_async(
        user_id="skill-builder",
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    raw_output += part.text

    skill_name, skill_dir, files_created = _parse_and_save(raw_output, req.name)

    draft_id = str(uuid.uuid4())
    draft_registry[draft_id] = {
        "skill_name": skill_name,
        "skill_path": skill_dir,
        "files": {f: open(os.path.join(skill_dir, f)).read() for f in files_created},
    }

    return CreateSkillResponse(
        draft_id=draft_id,
        skill_name=skill_name,
        skill_path=skill_dir,
        files_created=files_created,
    )


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/skills/stream")
async def create_skill_stream(req: CreateSkillRequest):
    """Stream skill creation as Server-Sent Events.

    Events:
      status  — phase progress: {message}
      token   — partial agent output: {text}
      file    — file saved: {name, path, content}
      done    — completion: {draft_id, skill_name, files_created}
      error   — failure: {detail}
    """
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            yield sse("status", {"message": "Starting skill creation..."})

            session = await session_service.create_session(
                app_name="skill-builder-api",
                user_id="skill-builder",
            )

            message = types.Content(
                role="user",
                parts=[types.Part(text=f"Create a complete skill for: {req.intent}")]
            )

            yield sse("status", {"message": "Agent thinking..."})

            raw_output = ""
            async for event in runner.run_async(
                user_id="skill-builder",
                session_id=session.id,
                new_message=message,
            ):
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts:
                        if part.text and not event.is_final_response():
                            yield sse("token", {"text": part.text})

                if event.is_final_response() and event.content:
                    for part in event.content.parts:
                        if part.text:
                            raw_output += part.text

            yield sse("status", {"message": "Parsing and saving files..."})

            blocks = re.findall(r"```(\S+)\n(.*?)```", raw_output, re.DOTALL)
            if not blocks:
                yield sse("error", {"detail": "Agent did not produce any skill files"})
                return

            skill_md_content = next((c for f, c in blocks if f == "skill.md"), None)
            if not skill_md_content:
                yield sse("error", {"detail": "Agent did not produce SKILL.md"})
                return

            name_match = re.search(r"^name:\s*(.+)$", skill_md_content, re.MULTILINE)
            skill_name = req.name or (name_match.group(1).strip() if name_match else str(uuid.uuid4())[:8])
            skill_dir = os.path.join(SKILLS_OUTPUT_DIR, skill_name)

            files_created = []
            for fname, content in blocks:
                target = "SKILL.md" if fname == "skill.md" else fname
                file_path = os.path.join(skill_dir, target)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                stripped = content.strip()
                with open(file_path, "w") as f:
                    f.write(stripped)
                files_created.append(target)

                # Emit file event with full content inline
                yield sse("file", {
                    "name": target,
                    "path": file_path,
                    "content": stripped,
                })

            draft_id = str(uuid.uuid4())
            draft_registry[draft_id] = {
                "skill_name": skill_name,
                "skill_path": skill_dir,
                "files": {f: open(os.path.join(skill_dir, f)).read() for f in files_created},
            }

            yield sse("done", {
                "draft_id": draft_id,
                "skill_name": skill_name,
                "files_created": files_created,
            })

        except Exception as e:
            yield sse("error", {"detail": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/skills/{draft_id}", response_model=GetSkillResponse)
async def get_skill(draft_id: str):
    """Retrieve a generated skill by draft ID."""
    if draft_id not in draft_registry:
        raise HTTPException(status_code=404, detail="Draft not found")
    entry = draft_registry[draft_id]
    return GetSkillResponse(
        draft_id=draft_id,
        skill_name=entry["skill_name"],
        skill_path=entry["skill_path"],
        files=entry["files"],
    )


@app.get("/skills/{draft_id}/files/{file_path:path}")
async def get_skill_file(draft_id: str, file_path: str):
    """Get raw content of a single file within a skill draft."""
    if draft_id not in draft_registry:
        raise HTTPException(status_code=404, detail="Draft not found")

    skill_dir = draft_registry[draft_id]["skill_path"]
    full_path = os.path.normpath(os.path.join(skill_dir, file_path))

    if not full_path.startswith(os.path.abspath(skill_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found in skill")

    with open(full_path) as f:
        content = f.read()

    return {"file_path": file_path, "content": content}


@app.get("/skills/{draft_id}/download")
async def download_skill_zip(draft_id: str):
    """Download the entire skill as a zip file."""
    if draft_id not in draft_registry:
        raise HTTPException(status_code=404, detail="Draft not found")

    entry = draft_registry[draft_id]
    skill_dir = entry["skill_path"]
    skill_name = entry["skill_name"]

    if not os.path.isdir(skill_dir):
        raise HTTPException(status_code=404, detail="Skill files not found on disk")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(skill_dir):
            for fname in files:
                abs_path = os.path.join(root, fname)
                arc_path = os.path.join(skill_name, os.path.relpath(abs_path, skill_dir))
                zf.write(abs_path, arc_path)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={skill_name}.zip"},
    )


@app.get("/skills")
async def list_skills():
    """List all generated skill drafts."""
    return {
        "drafts": [
            {"draft_id": did, "skill_name": v["skill_name"], "skill_path": v["skill_path"]}
            for did, v in draft_registry.items()
        ],
        "count": len(draft_registry),
    }

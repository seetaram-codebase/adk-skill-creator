import os, re
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.skill_toolset import SkillToolset

APP_NAME = "skill-builder-api"
SKILLS_DIR = os.getenv("SKILLS_DIR", "./skills/skill-creator")
MODEL = os.getenv("MODEL", "gemini-2.5-pro")

skill_toolset = SkillToolset(skills_dir=SKILLS_DIR)

agent = LlmAgent(
    name="skill_builder_agent",
    model=MODEL,
    instruction="""You are an expert skill builder. Help users create production-ready skills
through iterative conversation.

Workflow:
1. First turn: ask 2-3 focused clarifying questions (language, use case, edge cases)
2. Once you have enough context: generate the skill files
3. Subsequent turns: refine based on feedback

When generating, output only files that add real value using named fences:

```skill.md              → SKILL.md (required, must have valid frontmatter)
```references/REFERENCE.md  → detailed reference docs (if needed)
```scripts/run.py           → executable helper script (if needed)
```assets/template.md       → templates or static resources (if needed)

SKILL.md frontmatter rules:
- name: lowercase, hyphens only, matches directory name
- description: clear, specific, tells agent when to use this skill""",
    tools=[skill_toolset],
)

session_service = InMemorySessionService()

runner = Runner(
    agent=agent,
    app_name=APP_NAME,
    session_service=session_service,
)


def parse_skill_blocks(text: str) -> list[tuple[str, str]]:
    """Extract named fenced code blocks from agent output."""
    return re.findall(r"```(\S+)\n(.*?)```", text, re.DOTALL)


def extract_skill_name(skill_md_content: str) -> str | None:
    match = re.search(r"^name:\s*(.+)$", skill_md_content, re.MULTILINE)
    return match.group(1).strip() if match else None

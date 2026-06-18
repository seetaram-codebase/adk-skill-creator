"""Skill file operations — save, read, zip."""
import os, uuid, zipfile, io
from agent import parse_skill_blocks, extract_skill_name
import storage

SKILLS_OUTPUT_DIR = os.getenv("SKILLS_OUTPUT_DIR", "./generated-skills")
os.makedirs(SKILLS_OUTPUT_DIR, exist_ok=True)


class SkillParseError(Exception):
    pass


def save_skill_from_output(raw_output: str, name_override: str | None = None) -> dict:
    """Parse agent output, write files to disk, persist draft. Returns draft dict."""
    blocks = parse_skill_blocks(raw_output)
    if not blocks:
        raise SkillParseError("Agent did not produce any skill files")

    skill_md_content = next((c for f, c in blocks if f == "skill.md"), None)
    if not skill_md_content:
        raise SkillParseError("Agent did not produce SKILL.md")

    skill_name = name_override or extract_skill_name(skill_md_content)
    if not skill_name:
        skill_name = str(uuid.uuid4())[:8]

    skill_dir = os.path.join(SKILLS_OUTPUT_DIR, skill_name)
    files: dict[str, str] = {}

    for fname, content in blocks:
        target = "SKILL.md" if fname == "skill.md" else fname
        file_path = os.path.join(skill_dir, target)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        stripped = content.strip()
        with open(file_path, "w") as f:
            f.write(stripped)
        files[target] = stripped

    draft_id = str(uuid.uuid4())
    storage.save_draft(draft_id, skill_name, skill_dir, files)

    return {
        "draft_id": draft_id,
        "skill_name": skill_name,
        "skill_dir": skill_dir,
        "files_created": list(files.keys()),
        "files": files,
    }


def build_zip(skill_name: str, skill_dir: str) -> io.BytesIO:
    """Zip an entire skill directory into a buffer."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(skill_dir):
            for fname in files:
                abs_path = os.path.join(root, fname)
                arc_path = os.path.join(skill_name, os.path.relpath(abs_path, skill_dir))
                zf.write(abs_path, arc_path)
    buffer.seek(0)
    return buffer

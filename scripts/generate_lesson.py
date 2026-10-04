"""Generate today's AI study lesson with Claude + web search.

Runs in GitHub Actions (see .github/workflows/daily-lesson.yml), but works
locally too:

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...
    python scripts/generate_lesson.py

It uses the same instructions as the Claude skill in skills/ai-daily-study/,
so lessons look the same whether they come from the Action or from Claude.
"""

import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "ai-daily-study"
PROGRESS = ROOT / "progress.json"
LESSONS = ROOT / "lessons"
INDEX = LESSONS / "INDEX.md"
FLASHCARDS = ROOT / "flashcards" / "anki.csv"

MODEL = os.environ.get("STUDY_MODEL", "claude-opus-5-5")
TZ = ZoneInfo(os.environ.get("STUDY_TZ", "America/Chicago"))
MAX_CONTINUATIONS = 5

TRACK_LABELS = {
    "new-models": "🆕 New Models",
    "tech-stack": "🧱 Tech Stack",
    "build-it": "🛠️ Build It",
    "use-cases": "💼 Use Cases",
    "review": "🔁 Review",
    "recap": "📅 Recap",
}


def strip_frontmatter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)


def build_system_prompt() -> str:
    parts = [strip_frontmatter((SKILL_DIR / "SKILL.md").read_text())]
    for ref in sorted((SKILL_DIR / "references").glob("*.md")):
        parts.append(f"\n\n<reference file=\"references/{ref.name}\">\n{ref.read_text()}\n</reference>")
    parts.append(
        "\n\n## Running inside GitHub Actions\n"
        "You cannot read or write files here. The repository's current state is given to you "
        "in the user message, and a script saves your output. Reply with **only** the finished "
        "lesson markdown, starting with its `---` frontmatter line, and nothing before or after it. "
        "The script handles INDEX.md, anki.csv and progress.json. In Review mode, write the "
        "unattended version (answers in <details>)."
    )
    return "".join(parts)


def build_user_prompt(now: datetime, progress: dict) -> str:
    recent_cards = ""
    if FLASHCARDS.exists():
        rows = FLASHCARDS.read_text().strip().splitlines()
        recent_cards = "\n".join(rows[-200:])
    return (
        f"Today is {now:%A, %Y-%m-%d} (learner's local time). Write today's daily lesson.\n\n"
        f"<progress.json>\n{json.dumps(progress, indent=2)}\n</progress.json>\n\n"
        f"<flashcards/anki.csv last_200_rows>\n{recent_cards}\n</flashcards/anki.csv>"
    )


def call_claude(system: str, user: str) -> str:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]

    for _ in range(MAX_CONTINUATIONS + 1):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "pause_turn":
            # Server-side search loop hit its limit; send the turn back to resume.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
            continue
        if response.stop_reason == "refusal":
            sys.exit(f"Claude declined the request: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            sys.exit("Lesson was cut off by max_tokens; try again or raise the limit.")
        return "".join(b.text for b in response.content if b.type == "text")

    sys.exit("Gave up after too many pause_turn continuations.")


def parse_frontmatter(lesson: str) -> dict:
    match = re.match(r"\A---\n(.*?)\n---\n", lesson, flags=re.S)
    if not match:
        sys.exit("Lesson is missing its --- frontmatter block:\n\n" + lesson[:500])
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    meta["tags"] = [t.strip() for t in meta.get("tags", "").strip("[]").split(",") if t.strip()]
    return meta


def parse_flashcards(lesson: str) -> list[tuple[str, str]]:
    section = re.search(r"^## Flashcards\n(.*?)(?=^## )", lesson, flags=re.S | re.M)
    if not section:
        return []
    pattern = r"\*\*Q:\*\*\s*(.+?)\s*\n\s*\*\*A:\*\*\s*(.+?)(?=\n\s*-\s*\*\*Q:|\Z)"
    return [(q.strip(), " ".join(a.split())) for q, a in re.findall(pattern, section.group(1), flags=re.S)]


def save(lesson: str, now: datetime, progress: dict) -> Path:
    meta = parse_frontmatter(lesson)
    date = meta.get("date") or f"{now:%Y-%m-%d}"
    slug = meta.get("slug") or "lesson"
    track = meta.get("track", "")
    title = meta.get("topic", slug)

    LESSONS.mkdir(exist_ok=True)
    path = LESSONS / f"{date}-{slug}.md"
    path.write_text(lesson.strip() + "\n")

    header = "# Lesson index\n\n| Date | Track | Lesson |\n|---|---|---|\n"
    rows = INDEX.read_text().split(header, 1)[-1] if INDEX.exists() else ""
    row = f"| {date} | {TRACK_LABELS.get(track, track)} | [{title}]({path.name}) |\n"
    INDEX.write_text(header + row + rows)

    FLASHCARDS.parent.mkdir(exist_ok=True)
    with FLASHCARDS.open("a", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        for q, a in parse_flashcards(lesson):
            writer.writerow([q, a, f"ai-daily {track} {slug}"])

    progress.setdefault("lessons", []).append(
        {"date": date, "track": track, "topic": title, "slug": slug,
         "file": f"lessons/{path.name}", "tags": meta["tags"]}
    )
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("::notice::ANTHROPIC_API_KEY is not set, so no lesson was generated. See README → GitHub Action.")
        return

    now = datetime.now(TZ)
    progress = json.loads(PROGRESS.read_text()) if PROGRESS.exists() else {"lessons": []}
    if any(l["date"] == f"{now:%Y-%m-%d}" for l in progress.get("lessons", [])):
        print("A lesson for today already exists; nothing to do.")
        return

    lesson = call_claude(build_system_prompt(), build_user_prompt(now, progress))
    lesson = lesson[lesson.find("---"):] if "---" in lesson else lesson
    path = save(lesson, now, progress)
    print(f"Saved {path.relative_to(ROOT)}")

    # Tell the workflow which file to post as today's issue.
    if out := os.environ.get("GITHUB_OUTPUT"):
        title = parse_frontmatter(lesson).get("topic", path.stem)
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        link = f"\n\n---\n📄 [Open this lesson in the repo](https://github.com/{repo}/blob/main/{path.relative_to(ROOT)})\n"
        issue_body = ROOT / "issue_body.md"  # untracked; frontmatter stripped so the issue renders cleanly
        issue_body.write_text(strip_frontmatter(lesson).strip() + link)
        with open(out, "a") as f:
            f.write(f"lesson_path={path.relative_to(ROOT)}\nlesson_title={title}\nissue_body={issue_body.name}\n")


if __name__ == "__main__":
    main()

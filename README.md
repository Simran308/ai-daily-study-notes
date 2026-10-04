# 📚 AI Daily Study Notes

> A Claude **Skill** + **GitHub Action** that teaches you one AI topic a day: the latest model releases, real-world use cases and the modern AI engineering stack. Every lesson comes with notes, runnable code, flashcards and a quiz.

![Claude Skill](https://img.shields.io/badge/Claude-Skill-d97757)
![GitHub Actions](https://img.shields.io/badge/automated-GitHub%20Actions-2088FF)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Keeping up with AI is overwhelming. This project turns it into a **15-minute daily habit**: each morning a new lesson is researched from primary sources, written to a consistent template, saved to this repo and pushed to you as a notification.

## How a week looks

| Day | Track | Example |
|---|---|---|
| Mon | 🆕 New Models | "What's new in the latest open-weights model and how to run it" |
| Tue | 🧱 Tech Stack | "Embeddings: how similarity search actually works" |
| Wed | 🛠️ Build It | "Build a 40-line RAG bot over your own notes" |
| Thu | 🆕 New Models | "This week in AI: 3 releases worth your time" |
| Fri | 💼 Use Cases | "How a real company uses AI agents in production" |
| Sat | 🔁 Review | Spaced-repetition quiz from your past flashcards |
| Sun | 📅 Recap | What you learned this week + a weekend build idea |

Tech Stack days work through a [40-topic curriculum](skills/ai-daily-study/references/curriculum.md): RAG, vector DBs, MCP, agent frameworks, evals, fine-tuning, local models, serving and more.

## Every lesson includes

- **TL;DR**: three takeaways
- **What it is / Why it matters / How it works**
- **Try it**: a runnable Python snippet (≤ 40 lines)
- **Where it fits**: a comparison table against alternatives
- **5 flashcards**, collected into [`flashcards/anki.csv`](flashcards/anki.csv) for import into [Anki](https://apps.ankiweb.net/)
- **3-question quiz** with hidden answers
- **Sources**, linked to primary sources and fact-checked

Browse all lessons in [`lessons/INDEX.md`](lessons/INDEX.md).

## How it works

```
                 ┌──────────────────────────────┐
  schedule ───▶  │  skills/ai-daily-study/      │  ◀── same instructions
 (desktop app    │  SKILL.md + references/      │      for both paths
  or Actions)    └──────────────┬───────────────┘
                                ▼
            Claude + web search: pick topic → research → write
                                ▼
   lessons/2026-10-05-x.md · INDEX.md · anki.csv · progress.json
                                ▼
          🔔 notification (desktop) or GitHub Issue (phone)
```

- **`progress.json`** remembers every topic, so lessons never repeat.
- **One source of truth**: the GitHub Action loads the same `SKILL.md` as its system prompt, so lessons look the same whichever way they're made.

## Project structure

```
skills/ai-daily-study/
├── SKILL.md                    # the skill: modes, weekly rotation, workflow
└── references/
    ├── lesson-template.md      # exact lesson format
    ├── curriculum.md           # 40-topic tech-stack syllabus
    └── sources.md              # where to research (primary sources first)
.claude/skills/ai-daily-study → symlink so Claude Code picks the skill up in this repo
scripts/generate_lesson.py      # Claude API + web search, for the Action
.github/workflows/daily-lesson.yml
lessons/  flashcards/  progress.json
```

## Use it

### Option 1: Claude Code / Claude desktop app (no API key needed)

Clone the repo and open it in Claude Code. The skill loads automatically through `.claude/skills/`. Then just ask:

- "give me today's AI lesson"
- "teach me about vector databases"
- "quiz me on what I've learned"
- "weekly recap"

To use it from any folder, copy or symlink `skills/ai-daily-study` into `~/.claude/skills/`. To get it daily, create a scheduled task in the Claude desktop app that asks for today's lesson.

### Option 2: GitHub Action (fully automatic, lesson arrives as a GitHub Issue)

1. Fork or clone this repo to your GitHub account.
2. Create an API key at [platform.claude.com](https://platform.claude.com/) (usage is billed; one lesson a day costs very little).
3. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**, name it `ANTHROPIC_API_KEY` and paste the key.
4. Go to **Actions → Daily AI lesson → Run workflow** to test it.

The workflow runs every day at 8 AM US Central (edit the cron line and `STUDY_TZ` for your timezone). It commits the lesson and opens an Issue assigned to you, so the GitHub mobile app notifies you. Without the secret, the workflow skips quietly.

> Use **one** of the two daily schedules, not both, or you'll get two lessons a day.

### Run the script locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/generate_lesson.py
```

## Customise

- **Level**: change "intermediate" at the top of `SKILL.md`.
- **Topics**: edit `references/curriculum.md`.
- **Rotation**: edit the weekly table in `SKILL.md`.
- **Model**: add a repository variable `STUDY_MODEL` (Settings → Secrets and variables → Actions → Variables), e.g. `claude-sonnet-5-5` for lower cost. Default: `claude-opus-5-5`.

## License

MIT

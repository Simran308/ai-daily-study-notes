# Lesson template

Use this structure for every lesson. Keep the headings, frontmatter keys and flashcard format exactly as written, because the optional GitHub Action script (`scripts/generate_lesson.py`) parses them. You never need to run that script yourself. Files are UTF-8.

````markdown
---
date: 2026-10-05
track: new-models
topic: Short human title
slug: short-kebab-slug
tags: [llm, open-weights]
read_time: 15 min
---

# 🆕 <Title>

> **TL;DR**
> - one-line takeaway
> - one-line takeaway
> - one-line takeaway

## What it is
2–4 short paragraphs. For a release, say who released it, when (exact date), and what's actually new compared with what came before.

## Why it matters
3 concrete use cases, one line each, as a bulleted list. Real companies or products where possible.

## How it works
The core idea in plain English. A small ASCII or Mermaid diagram if it helps.

## Try it
```python
# pip install ...
# ≤ 40 lines, runnable, API keys from env vars
```
One sentence on what the output should look like.

## Where it fits
| | This | Alternative A | Alternative B |
|---|---|---|---|
| Best for | | | |
| Cost / licence | | | |
| Watch out for | | | |

## Flashcards
- **Q:** question
  **A:** answer
- **Q:** ...
  **A:** ...
(exactly 5)

## Quiz
1. Question?
   - a) ...
   - b) ...
   - c) ...
   <details><summary>Answer</summary>b, because ...</details>
(exactly 3)

## Go deeper
- [Primary source title](url) (publisher, date, or "accessed YYYY-MM-DD" for docs pages)
- [Second source](url)
- [Third source](url)

---
⏭️ **Tomorrow:** one-line teaser for the next track.
````

`track` is one of: new-models, tech-stack, build-it, use-cases, review, recap. For a concept with no competing products, use "Where it fits" to compare approaches instead (for example, "count with the API" vs "rule of thumb" vs "read usage afterwards").

## Supporting file formats

**`progress.json`**
```json
{
  "learner_level": "intermediate",
  "lessons": [
    {"date": "2026-10-05", "track": "new-models", "topic": "…", "slug": "…",
     "file": "lessons/2026-10-05-slug.md", "tags": ["llm"]}
  ]
}
```

**`lessons/INDEX.md`**
```markdown
# Lesson index

| Date | Track | Lesson |
|---|---|---|
| 2026-10-05 | 🆕 New Models | [Title](2026-10-05-slug.md) |
```

**`flashcards/anki.csv`**: no header row, one card per line:
```
"What does RAG stand for?","Retrieval-Augmented Generation: fetch relevant documents and put them in the prompt.","ai-daily tech-stack rag-basics"
```

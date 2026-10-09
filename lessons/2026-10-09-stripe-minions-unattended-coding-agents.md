---
date: 2026-10-09
track: use-cases
topic: How Stripe's Minions turn a Slack message into a pull request
slug: stripe-minions-unattended-coding-agents
tags: [use-cases, agents, coding-agents, mcp, sandboxing, tool-curation, stripe]
read_time: 15 min
---

# 💼 How Stripe's Minions turn a Slack message into a pull request

> **TL;DR**
> - Stripe runs "Minions": unattended coding agents. An engineer posts a task in Slack, and a pull request (PR) comes back later. Stripe reportedly merges 1,300+ of these PRs per week, and humans review every one.
> - The model is not the clever part. The reliability comes from the system around it: context fetched up front, a small curated toolset, a disposable sandbox, and Stripe's existing tests and code review as the gate.
> - You can copy the pattern at small scale: let the agent iterate, but cap the attempts and let your tests decide whether it passed.

**Sourcing note, please read.** I could not open Stripe's own engineering posts in this run, because the search budget ran out. Everything below about Stripe comes from two secondary write-ups published in February 2026, which agree with each other on the main points. The numbers are about eight months old and may have grown. Treat Stripe-specific figures as *(unverified against the primary source)*. The pattern is the lesson, and it holds even if a number is off.

## What it is

Stripe is a large payments company with a huge Ruby codebase. Per the write-ups, its internal agents, called **Minions**, work in "fire-and-forget" mode. An engineer sends a Slack message, the agent works with no one watching, and a PR appears. That is different from a *copilot*, where a developer watches suggestions in an editor and accepts them line by line.

Reported scale as of February 2026: **over 1,300 PRs merged per week** containing no human-written code, with every PR still reviewed by a human. One write-up says about 8,500 of Stripe's roughly 10,000 employees use LLM tools daily. (An earlier write-up the same month says "1,000+", so the figure was moving.)

The point for you is not "AI writes code". Plenty of demos do that. It is *how Stripe made unattended work safe enough to merge*, and that is an architecture question. The rest of this lesson covers it.

## Why it matters

Four things this case shows that apply beyond Stripe:

- **Coding agents at scale.** The target is small, well-defined tickets such as migrations, config changes and small fixes. One write-up says a payment integration that took two months shipped in two weeks *(vendor-adjacent claim, unverified)*.
- **Internal tool platforms for agents.** Stripe built one central MCP server, called **Toolshed**, with several hundred curated internal tools (write-ups say "400+" or "close to 500"). Every agent system in the company shares it. MCP (Model Context Protocol) is a standard way to expose tools to a model.
- **Safe autonomy in other fields.** The same recipe of isolation, deterministic checks and human sign-off fits support automation, data pipelines, and ops runbooks.

## How it works

The Medium write-up describes six layers. This lesson covers the four that you can reuse, in my own wording:

```
Slack message / ticket
        │
        ▼
 1. Prefetch context (deterministic code, not the LLM):
    Slack thread, Jira ticket, docs, code search
        │
        ▼
 2. Curate tools: ~400-500 exist, the agent sees ~15 relevant ones
        │
        ▼
 3. Agent loop inside a disposable sandbox (devbox):
    no internet, no production data, same setup as a human dev
        │
        ▼
 4. Gate: run the real test suite / CI  ──fail──► loop back (bounded)
        │ pass
        ▼
   Pull request → human review → merge
```

**1. Prefetch context deterministically.** Before the model runs, ordinary code gathers what it will need: the Slack thread, ticket metadata, and relevant docs and code via search. This is cheaper and more predictable than letting the model discover all of it through tool calls. It also keeps the model from skipping a step.

**2. Curate the toolset.** With ~500 tools available, giving the model all of them would waste context and make it choose badly. The write-up says the orchestrator picks about 15 relevant ones for each task. This is the same lesson as few-shot examples: more is not better, relevant is better.

**3. Isolate the agent.** Each Minion runs on a pre-warmed cloud machine (reportedly provisioned in about ten seconds) that mirrors a human engineer's environment but has **no internet and no production data**. Isolation is what makes it safe to run many agents in parallel and to let them run commands unattended. If the agent does something silly, the damage stays in a throwaway box.

**4. Let existing engineering controls decide.** The agent runs the code against Stripe's real test suite (reported as around three million tests) and opens a normal PR. Whether the work is good is decided by tests and a human reviewer, not by the agent saying "done".

The idea to remember: **reliability scales with constraints, not model size.** Each layer removes a way for the agent to go wrong.

## Try it

This is a tiny version of layers 3 and 4: the model writes code, a test file decides pass or fail, and failures go back to the model. It stops after three attempts and hands off to a human. It uses `gpt-6.1-sol` through the Responses API, as in the earlier lessons.

```python
# pip install openai   (set OPENAI_API_KEY in your environment)
import re, subprocess, sys, tempfile
from openai import OpenAI

client = OpenAI()
TASK = "Write slugify(title): lowercase, ASCII only, words joined by single hyphens."
TESTS = '''
from solution import slugify
assert slugify("Hello, World!") == "hello-world"
assert slugify("  Multiple   spaces ") == "multiple-spaces"
assert slugify("Café au lait") == "cafe-au-lait"
print("ALL TESTS PASSED")
'''

def ask(prompt):
    r = client.responses.create(model="gpt-6.1-sol", input=prompt,
                                reasoning={"effort": "low"})
    m = re.search(r"<code>(.*?)</code>", r.output_text, re.S)
    return m.group(1) if m else ""

def run_tests(code):  # WARNING: runs model-written code on your machine
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/solution.py", "w").write(code)
        open(f"{d}/check.py", "w").write(TESTS)
        p = subprocess.run([sys.executable, "check.py"], cwd=d,
                           capture_output=True, text=True, timeout=20)
    return p.returncode == 0, (p.stdout + p.stderr)[-1500:]

prompt = f"{TASK}\nReturn only the Python module inside <code></code> tags."
for attempt in range(1, 4):
    code = ask(prompt)
    ok, log = run_tests(code)
    print(f"attempt {attempt}: {'PASS' if ok else 'FAIL'}")
    if ok:
        break
    prompt += (f"\n\nPrevious attempt:\n<code>{code}</code>\n"
               f"Test output:\n<log>{log}</log>\nFix it. Same format.")
else:
    print("Giving up: hand this one to a human.")
```

You should see `attempt 1: PASS` or a pass on attempt 2 or 3. The accented "Café" test is the one most likely to fail the first try. The code the model writes runs directly on your computer, which is exactly why Stripe uses disposable no-internet machines. For anything beyond a toy, run it in Docker or another sandbox.

Stretch: add a fourth test that the first solution is likely to fail, and watch the failure log steer the fix.

## Where it fits

| | Unattended agent (Minions-style) | IDE copilot | Interactive agent (you watch and steer) |
|---|---|---|---|
| Best for | Many small, well-specified tasks with strong tests | Line-level help while you type | Open-ended or exploratory work |
| Cost / licence | Internal at Stripe, not a product. You build the pieces yourself (any agent SDK plus a sandbox plus CI) | Per-seat subscriptions | Per-seat or per-token |
| Watch out for | Needs good tests and a sandbox first. Weak tests mean confidently merged bugs | Easy to accept code you don't understand | Your attention is the bottleneck |

## Flashcards
- **Q:** What is the difference between an unattended agent like Stripe's Minions and a copilot?
  **A:** A copilot suggests code while a developer watches and accepts it. An unattended agent takes a task (for example from Slack), works alone in a sandbox, and returns a finished PR for human review.
- **Q:** Why prefetch context with deterministic code instead of letting the agent look things up itself?
  **A:** It is cheaper and more predictable, and the model can't skip a step. Ordinary code gathers the ticket, thread and docs before the model runs.
- **Q:** Why show an agent about 15 tools when 400+ exist?
  **A:** Too many tool definitions waste context and make the model pick badly. Selecting the relevant few per task improves reliability.
- **Q:** Why do unattended agents run in sandboxes with no internet and no production data?
  **A:** So mistakes stay in a disposable environment, which makes it safe to run many agents in parallel and to let them execute commands without supervision.
- **Q:** In an agent-plus-tests loop, what decides whether the work is done, and what should bound the loop?
  **A:** The real tests or CI decide, not the agent's claim of success. Cap the number of attempts, then hand off to a human.

## Quiz
1. A teammate wants to give their agent all 300 internal tools "so it can handle anything". What is the best objection?
   - a) The model can't read that many tool names
   - b) Many irrelevant tool definitions eat context and hurt tool choice, so curate a small set per task
   - c) MCP only supports 15 tools
   <details><summary>Answer</summary>b. The model can read them, but irrelevant tools cost tokens and cause worse choices. MCP has no 15-tool limit. The ~15 figure is just what the write-up says Stripe's orchestrator selects.</details>
2. Your agent says "all tests pass" in its final message. What should your pipeline do?
   - a) Trust it and open the PR
   - b) Run the tests itself in the sandbox and decide from the real result
   - c) Ask the agent to say it again with more confidence
   <details><summary>Answer</summary>b. The gate has to be something the agent can't talk its way past, such as real test output.</details>
3. Which is the best first investment before building a Minions-style system?
   - a) A bigger model
   - b) A reliable test suite and a sandbox to run it in
   - c) A longer system prompt
   <details><summary>Answer</summary>b. The case study's main lesson is that reliability comes from constraints and checks. Without good tests, you can't tell good PRs from bad ones.</details>

## Go deeper
- [Scaling Engineering Velocity: The Architecture Behind Stripe's 1,300 Weekly Autonomous PRs](https://medium.com/@harish18092002/scaling-engineering-velocity-the-architecture-behind-stripes-1-300-weekly-autonomous-prs-95b4e3fdb3b5) (Medium, secondary source, 2026-02-22)
- [What the companies that got this right actually built](https://dkod.ai/blog/what-the-leaders-actually-built) (dkod blog, secondary source; covers Stripe's Toolshed and devboxes, plus Shopify and Wix)
- [How Stripe Built Secure Unattended AI Agents Merging 1,000 Pull Requests Weekly](https://medium.com/@oracle_43885/how-stripe-built-secure-unattended-ai-agents-merging-1-000-pull-requests-weekly-1ff42f3fe550) (Medium, secondary source, 2026-02-14). To check the details yourself, find Stripe's own Minions posts on their engineering blog.

---
⏭️ **Tomorrow:** Saturday review. Eight flashcards from the past week, covering tokens, prompting, GPT-6.1 Sol, the effort benchmark and Haiku 5.5.

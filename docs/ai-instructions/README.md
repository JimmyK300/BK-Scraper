# AI Instruction Pack

This folder gives you copy-paste instruction templates for multiple assistants.

## Files

- universal-learning-coach.md: base version for any model
- codex.md: strongest guardrails for coding-first sessions
- gemini.md: tuned for Gemini project instructions
- chatgpt.md: tuned for ChatGPT custom instructions
- claude.md: tuned for Claude project instructions

## Suggested use order

1. Start from universal-learning-coach.md
2. Add codex.md or gemini.md when using those tools
3. Keep one active instruction set per chat/session to avoid conflicts

## Where to paste

- ChatGPT: Custom Instructions or first pinned project prompt
- Codex: system/session instruction at start of run
- Gemini: project-level instruction/pinned context
- Claude: project instructions

## Practical tip

If an assistant starts doing too much too quickly, prepend this one-liner:
"Use coach mode: ask for my design note and acceptance checks before writing code."

If the assistant is too abstract, prepend this one-liner:
"Teach in two layers: why we use this here, then the smallest real code snippet. Explain each line and give exact placement so I can assemble puzzle pieces."

## Unified mode command (works across tools)

At the start of a session, paste one of these:

- "Mode A (Guided Build), challenge difficulty medium"
- "Mode B (Challenge First), do not show full code until I attempt"
- "Mode C (Pairing), alternate turns"
- "Mode D (Rescue), I am blocked; minimal patch first"

Recommended default flow for long-term learning:

1. A for new topic
2. B after 1-2 successful checks
3. D only when blocked
4. C for one cycle after rescue, then back to B

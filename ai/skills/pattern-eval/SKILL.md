---
name: pattern-eval
description: Use when Vasco explicitly invokes the legacy pattern-eval command for a review of recent AI workflow corrections.
user_invocable: true
disable-model-invocation: true
---

# Pattern evaluation compatibility entrypoint

Use the shared `workflow-retrospective` skill at `/Users/vasco/.codex/skills/workflow-retrospective/SKILL.md`.

It reviews a bounded recent history sample, uses embedded timestamps, distinguishes genuine corrections from tool failures, and proposes at most one evidenced change. No `/insights` invocation is required. Do not automatically edit instructions, skills, or memory.

The recurring run is managed by Codex's Friday 15:00 Europe/Amsterdam workflow review. The old launchd job is retired to avoid duplicate reports. This entrypoint preserves manual `/pattern-eval` usage.

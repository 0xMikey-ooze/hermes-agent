# SKILL: hermes-self-improve — Self-Improvement Protocol

## What this is
You can improve yourself. You have tools to learn from every task, build new skills,
update your own behavior, and push those changes to GitHub so they survive restarts.

This is not optional — it's how you get better.

---

## The Loop (run after EVERY significant task)

### 1. Complete the task
### 2. Write a reflection
```
write_reflection({
  "task_id": "task-abc123",
  "category": "coding",           // coding | db | api | deployment | communication | research | general
  "lesson": "When Railway 502s after deploy, check for duplicate aiohttp route registrations first",
  "what_worked": "Grepping for duplicate route names in web_api.py",
  "what_failed": "Assumed it was a port binding issue — wasted 20 min",
  "applied_to": "hermes-agent"
})
```
### 3. If you built a reusable approach → create a skill
```
skill_manage({
  "action": "create",
  "name": "railway-debug",
  "description": "Diagnose Railway 502s",
  "content": "# SKILL: railway-debug\n\n..."
})
commit_skill({"skill_name": "railway-debug", "commit_message": "feat: railway debug skill"})
```
### 4. If your behavior needs to change → update soul
```
update_soul({"content": "...", "reason": "Need to check route conflicts before assuming port issues"})
```

---

## Before starting a hard task

Always check if you've done something similar before:
```
read_reflections({"keyword": "railway"})   // search by topic
read_reflections({"category": "coding"})   // browse by category
self_diagnose({})                          // see current skill gaps
```

---

## When to create a new skill

Create a skill when you:
- Used a multi-step process successfully 3+ times
- Discovered a non-obvious approach that saved significant time
- Found a pattern that applies across multiple projects

Do NOT create a skill for:
- One-off tasks
- Things that are obvious from docs
- Project-specific details (put those in reflections)

---

## When to update Soul.md

Only when your BEHAVIOR needs to change — not facts or procedures.

Good reasons:
- "I keep over-engineering solutions — I should try the simplest thing first"
- "I'm not checking the task queue at session start — add it as a rule"
- "I need to be more direct when something won't work"

Bad reasons:
- "I learned how to debug Railway" (→ write_reflection or create a skill instead)
- "I want to remember this project detail" (→ reflection)

---

## Skill Quality Rules

A good SKILL.md must have:
1. **Trigger**: when to use this skill
2. **Steps**: numbered, concrete, executable
3. **Examples**: actual code/commands, not pseudocode
4. **Anti-patterns**: what NOT to do

A bad skill is: vague, no examples, reads like documentation instead of a recipe.

---

## Tool Reference

| Tool | When |
|------|------|
| `write_reflection` | After every task — win or fail |
| `read_reflections` | Before hard tasks, when stuck |
| `skill_manage` | Create/edit skills from experience |
| `commit_skill` | After creating a skill (push to GitHub) |
| `update_soul` | Rare — only for behavioral shifts |
| `self_diagnose` | Weekly or when repeatedly failing |

---
name: github-watcher
description: >
  Watches GitHub repos for new issues and PRs. Automatically adds them to the
  GoalPlanner queue. Triggered by cron every 15 minutes or on demand.
  Triggers: "watch github", "check for new issues", "sync github backlog"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [github, automation, goals, backlog]
    related_skills: [agentic-swarm, subagent-driven-development]
    requires_tools: [exec, read_file, write_file]
prerequisites:
  commands: [gh, git]
---

# GitHub Watcher

Polls GitHub for open issues and pull requests, maps them into GoalPlanner tasks, and deduplicates against existing queue entries. Designed to run every 15 minutes via cron so the GoalPlanner queue stays in sync with the GitHub backlog automatically.

## When to Use

- "watch github", "check for new issues", "sync github backlog"
- Cron trigger fires to refresh the GoalPlanner queue
- Before running the agentic-swarm loop when the queue might be empty
- After a sprint planning meeting to load all new issues at once

## When NOT to Use

- When GitHub CLI (`gh`) is not authenticated — check with `gh auth status` first
- When you only want to process a single specific issue — use agentic-swarm directly with a goal
- When operating on a repo you don't have read access to

---

## Protocol

### Step 1 — Verify Authentication

```bash
gh auth status
# Must show: Logged in to github.com as <user>
# If not: gh auth login
```

### Step 2 — Fetch Open Issues

```python
issues_json = exec(
    "gh issue list --state open --json number,title,body,labels,createdAt,assignees"
).stdout
issues = json.loads(issues_json)
# issues = [{ number, title, body, labels: [{name}], createdAt, assignees: [{login}] }, ...]
```

### Step 3 — Check Existing GoalPlanner Queue

```python
# Get all tasks already in the queue to avoid duplicates
status = call_tool("goal_status")
existing_goal_ids = set()

# Check MemoryStore for issue→goal mappings we already ingested
for issue in issues:
    mapping = call_tool("memory_get", { "key": f"github/issue/{issue['number']}" })
    if mapping is not None:
        existing_goal_ids.add(issue["number"])

new_issues = [i for i in issues if i["number"] not in existing_goal_ids]
```

### Step 4 — Assign Priority by Label

```python
def priority_for_issue(issue):
    label_names = [l["name"].lower() for l in issue.get("labels", [])]
    if any(l in label_names for l in ["bug", "critical", "blocker", "p0"]):
        return 9
    if any(l in label_names for l in ["enhancement", "feature", "p1"]):
        return 6
    if any(l in label_names for l in ["documentation", "docs", "p2"]):
        return 3
    return 5  # default medium priority
```

### Step 5 — Decompose and Enqueue New Issues

```python
ingested_count = 0
new_task_ids = []

for issue in new_issues:
    goal_text = f"{issue['title']}: {(issue['body'] or '').strip()[:500]}"
    priority = priority_for_issue(issue)

    # Decompose the issue into subtasks via GoalPlanner
    subtasks = call_tool("goal_decompose", {
        "goal": goal_text,
        "context": {
            "source": "github",
            "issueNumber": issue["number"],
            "priority": priority,
            "labels": [l["name"] for l in issue.get("labels", [])]
        }
    })

    # Store the issue→goal mapping for deduplication on next run
    call_tool("memory_store", {
        "key": f"github/issue/{issue['number']}",
        "value": {
            "goalId": subtasks[0]["id"] if subtasks else None,
            "issueNumber": issue["number"],
            "title": issue["title"],
            "subtasks": [t["id"] for t in subtasks],
            "ingestedAt": now_iso()
        },
        "metadata": {
            "source": "github",
            "priority": priority,
            "labels": [l["name"] for l in issue.get("labels", [])]
        }
    })

    new_task_ids.extend([t["id"] for t in subtasks])
    ingested_count += 1
```

### Step 6 — Fetch Open Pull Requests

```python
prs_json = exec(
    "gh pr list --state open --json number,title,body,labels,headRefName,isDraft"
).stdout
prs = json.loads(prs_json)

for pr in prs:
    if pr.get("isDraft"):
        continue  # Skip draft PRs — not ready for review

    existing = call_tool("memory_get", { "key": f"github/pr/{pr['number']}" })
    if existing is not None:
        continue  # Already queued

    goal_text = f"Review and merge PR #{pr['number']}: {pr['title']}"
    subtasks = call_tool("goal_decompose", {
        "goal": goal_text,
        "context": {
            "source": "github-pr",
            "prNumber": pr["number"],
            "branch": pr["headRefName"],
            "priority": 7  # PRs get higher priority than features — they're blocked work
        }
    })

    call_tool("memory_store", {
        "key": f"github/pr/{pr['number']}",
        "value": {
            "goalId": subtasks[0]["id"] if subtasks else None,
            "prNumber": pr["number"],
            "title": pr["title"],
            "branch": pr["headRefName"],
            "subtasks": [t["id"] for t in subtasks],
            "ingestedAt": now_iso()
        },
        "metadata": { "source": "github-pr", "priority": 7 }
    })

    new_task_ids.extend([t["id"] for t in subtasks])
    ingested_count += 1
```

### Step 7 — Log to Blackboard

```python
# Announce what was ingested so other agents and humans can see the activity
call_tool("blackboard_post", {
    "topic": "github/ingested",
    "message": {
        "timestamp": now_iso(),
        "issueCount": len(new_issues),
        "prCount": sum(1 for p in prs if not p.get("isDraft")),
        "newTasks": len(new_task_ids),
        "taskIds": new_task_ids
    }
})

print(f"GitHub sync complete: {ingested_count} new work items added to GoalPlanner queue.")
```

---

## Priority Reference

| Label(s) | Priority | Rationale |
|----------|----------|-----------|
| bug, critical, blocker, p0 | 9 | Production issues — highest urgency |
| Open PRs (non-draft) | 7 | Blocked work; unblock the contributor |
| enhancement, feature, p1 | 6 | Planned roadmap work |
| documentation, docs, p2 | 3 | Low urgency; no production impact |
| (none matching above) | 5 | Default — triage manually if needed |

---

## Deduplication Strategy

The watcher stores a `github/issue/{number}` key in MemoryStore after every ingestion. On the next run it checks for this key before calling `goal_decompose`. This prevents duplicate tasks from being created if the same issue is open across multiple sync cycles.

To force re-ingestion of an issue (e.g., the issue was significantly updated):
```python
call_tool("memory_delete", { "key": "github/issue/123" })
# Next sync will re-ingest issue #123
```

---

## Integration with Agentic Swarm

The github-watcher is the **feed** for the agentic-swarm loop. Typical invocation order:

```
[Cron 15min] → github-watcher (populate queue)
[Cron 15min] → agentic-swarm (drain queue)
```

Both run on the same cron schedule so the queue is always fresh before processing begins.

---

## Example Cron Config

```yaml
- name: "github-sync"
  schedule: "*/15 * * * *"
  trigger: "Sync GitHub backlog using the github-watcher skill. Add new issues to GoalPlanner."
  platform: "internal"
  skills: ["github-watcher"]
```

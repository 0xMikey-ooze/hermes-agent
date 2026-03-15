---
name: agentic-swarm
description: >
  Autonomous coding agent loop. Hermes wakes on schedule, checks the GoalPlanner
  queue, picks the next task, decomposes it, delegates implementation to worker
  subagents, evaluates output with ReflexionEvaluator, retries on failure, stores
  learnings in MemoryStore. Self-directed — does not wait to be asked.
  Triggers: "run autonomously", "start agentic mode", "watch the repo", "process the backlog"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [agentic, autonomous, loop, reflexion, memory, goals, swarm]
    related_skills: [swarm-orchestrator, subagent-driven-development]
    requires_tools: [delegate_task, exec, read_file, write_file]
prerequisites:
  commands: [git, gh, node]
---

# Agentic Swarm

Turns Hermes into a self-directed coding agent. It wakes on schedule, consults the GoalPlanner queue, picks the highest-priority task with all dependencies met, delegates implementation to parallel worker subagents, evaluates output with ReflexionEvaluator, retries on failure, and stores learned patterns in MemoryStore — all without human prompting.

## When to Use

- The user says "run autonomously", "start agentic mode", "watch the repo", or "process the backlog"
- A cron job triggers every 15 minutes to drain the GoalPlanner queue
- You need to process multiple GitHub issues or PRs without per-task human approval
- You want a self-healing loop: evaluate → retry → escalate on repeated failure

## When NOT to Use

- The user is actively present and wants to direct each step — use subagent-driven-development instead
- The task requires human judgment or approval before each action (e.g., destructive migrations)
- There is no GoalPlanner queue populated — use github-watcher first to ingest issues

---

## Full Agentic Loop Protocol

Execute these steps in order. Do not skip steps. Loop until the queue is empty or you hit the retry cap.

### Step 1 — WAKE: Check the Queue

```python
# Check GoalPlanner status via AGI MCP server
status = call_tool("goal_status")
# status = { pending: [...], inProgress: [...], completed: [...], blocked: [...] }

if len(status["pending"]) == 0 and len(status["inProgress"]) == 0:
    # Queue is empty — ingest fresh work from GitHub
    invoke_skill("github-watcher")
    status = call_tool("goal_status")
    if len(status["pending"]) == 0:
        print("No work available. Sleeping until next cron trigger.")
        return

# Pick the next task (highest priority with all deps met)
task = call_tool("goal_next_task")
```

### Step 2 — DECOMPOSE: Break the Task into Subtasks

```python
# Decompose the task into ordered subtasks
plan = call_tool("goal_decompose", {
    "goal": task["description"],
    "context": {
        "taskId": task["id"],
        "priority": task["priority"],
        "repoInfo": get_repo_info()  # git remote, current branch, last commit
    }
})
# plan = [{ id, description, priority, dependencies }, ...]

# Persist the plan so subagents can find it
call_tool("memory_store", {
    "key": f"plan/{task['id']}",
    "value": plan,
    "metadata": { "taskId": task["id"], "timestamp": now_iso() }
})

# Announce the plan on the shared blackboard
call_tool("blackboard_post", {
    "topic": "swarm/plan",
    "message": { "taskId": task["id"], "plan": plan }
})
```

### Step 3 — RECALL: Inject Prior Learnings

```python
# Search for learned patterns relevant to this repo/task
repo_patterns = call_tool("memory_search", {
    "query": f"repo patterns {get_repo_name()}",
    "options": { "limit": 5 }
})

failed_approaches = call_tool("memory_search", {
    "query": f"failed approaches {task['description'][:80]}",
    "options": { "limit": 3 }
})

memories = {
    "repoPatterns": [r["value"] for r in repo_patterns],
    "failedApproaches": [f["value"] for f in failed_approaches]
}
```

### Step 4 — DELEGATE: Provision Isolated Worktrees + Spawn Workers

Each worker gets an isolated git worktree — no shared filesystem, no git lock races.
WorktreeManager provisions each worker's directory before the task starts and cleans up after.

```python
import os
import uuid
from src.agi_client import AgiClient, check_agi_server

# Initialize AGI client (reads AGI_SERVER_URL + AGI_SERVER_API_KEY from env)
agi = AgiClient.from_env()
check_agi_server(agi)  # fail fast if not reachable

run_id = str(uuid.uuid4())[:8]

QUALITY_GATES = [
    "Tests exist for every new function",
    "No TODO comments in production code",
    "All imports are used",
    "Error handling present for async operations",
    "Commit message follows conventional commits"
]

# Chunk subtasks into worker batches (max 3 parallel)
BATCH_SIZE = 3
batches = [plan[i:i+BATCH_SIZE] for i in range(0, len(plan), BATCH_SIZE)]

results = []
for batch_idx, batch in enumerate(batches):
    workers = []

    for i, subtask in enumerate(batch):
        team_id = f"team-{i+1}"

        # 1. Provision isolated worktree for this worker
        try:
            wt = agi.worktree_create(run_id, team_id, get_current_branch())
            worktree_path = wt["path"]
        except Exception as e:
            agi.blackboard_post("swarm/blockers", {
                "type": "blocker",
                "taskId": subtask["id"],
                "description": f"Failed to create worktree: {e}"
            })
            continue

        # 2. Post subtask to blackboard so worker can find it
        agi.blackboard_post(f"swarm/tasks/{run_id}/{team_id}", {
            "subtask": subtask,
            "worktreePath": worktree_path,
            "runId": run_id,
            "teamId": team_id,
        })

        # 3. Delegate to worker subagent with worktree path as cwd
        worker = delegate_task(
            description=subtask["description"],
            skill="subagent-driven-development",
            env={
                "WORKTREE_PATH": worktree_path,
                "TASK_ID": subtask["id"],
                "RUN_ID": run_id,
                "TEAM_ID": team_id,
                "AGI_SERVER_URL": os.environ.get("AGI_SERVER_URL", ""),
                "AGI_SERVER_API_KEY": os.environ.get("AGI_SERVER_API_KEY", ""),
                "BRANCH_NAME": f"swarm/{run_id}/{team_id}",
            }
        )
        workers.append((team_id, worker, subtask))

    # Wait for all workers in this batch
    for team_id, worker, subtask in workers:
        result = worker.wait()

        # Clean up worktree regardless of result
        agi.worktree_remove(run_id, team_id)

        # Post result to blackboard for monitoring
        agi.blackboard_post("swarm/results", {
            "taskId": subtask["id"],
            "teamId": team_id,
            "status": "completed" if result.success else "failed",
            "output": result.output[:500] if result.output else None,
        })
        results.append(result)
```

### Step 5 — EVALUATE: ReflexionEvaluator Quality Gate

```python
# Collect the diff from all commits made by workers
pr_diff = exec("git diff main...HEAD").stdout

evaluation = call_tool("reflexion_evaluate", {
    "output": pr_diff,
    "criteria": QUALITY_GATES
})
# evaluation = { passed: bool, score: float, failures: [...] }

retry_count = 0
MAX_RETRIES = 3

while not evaluation["passed"] and evaluation["score"] < 0.7 and retry_count < MAX_RETRIES:
    retry_count += 1

    # Run reflexion loop with feedback
    reflection = call_tool("reflexion_run", {
        "generateOutput": pr_diff,
        "criteria": QUALITY_GATES,
        "maxRetries": 1
    })

    # Re-delegate with the reflection feedback injected
    fix_results = delegate_task(
        goal=f"Fix quality gate failures for task {task['id']}",
        context=f"""
QUALITY GATE FAILED (attempt {retry_count}/{MAX_RETRIES})
Score: {evaluation['score']:.2f}
Failures: {json.dumps(evaluation['failures'], indent=2)}
Reflection feedback: {reflection.get('reflection', 'See failures above')}

Fix ALL failures listed above. Re-run tests. Commit the fixes.
"""
    )

    pr_diff = exec("git diff main...HEAD").stdout
    evaluation = call_tool("reflexion_evaluate", {
        "output": pr_diff,
        "criteria": QUALITY_GATES
    })

if not evaluation["passed"] and retry_count >= MAX_RETRIES:
    # Escalate to human after 3 failed cycles
    send_message(
        platform="telegram",
        text=f"🚨 Task {task['id']} blocked after {MAX_RETRIES} retry cycles.\n"
             f"Score: {evaluation['score']:.2f}\n"
             f"Failures: {json.dumps(evaluation['failures'])}\n"
             f"Manual review needed."
    )
    call_tool("goal_complete", {
        "taskId": task["id"],
        "result": { "status": "blocked", "reason": "quality gate failed after max retries", "score": evaluation["score"] }
    })
    return
```

### Step 6 — LEARN: Store Outcomes in MemoryStore

```python
# Extract patterns from what worked
what_worked = [r["summary"] for r in results if r["status"] == "completed"]
what_failed = [r["summary"] for r in results if r["status"] != "completed"]

call_tool("memory_store", {
    "key": f"outcome/{task['id']}",
    "value": {
        "score": evaluation["score"],
        "whatWorked": what_worked,
        "whatFailed": what_failed,
        "patterns": extract_patterns(what_worked)
    },
    "metadata": { "taskId": task["id"], "timestamp": now_iso() }
})

call_tool("memory_store", {
    "key": f"repo/{get_repo_name()}/patterns",
    "value": extract_patterns(what_worked),
    "metadata": { "repo": get_repo_name(), "updatedAt": now_iso() }
})

# Mark task complete and unlock dependent tasks
call_tool("goal_complete", {
    "taskId": task["id"],
    "result": {
        "status": "completed",
        "score": evaluation["score"],
        "commitRange": f"main...HEAD"
    }
})
```

### Step 7 — LOOP: Continue Until Queue is Empty

```python
# Get the next task and repeat from Step 2
next_task = call_tool("goal_next_task")
if next_task:
    # Recurse (or iterate) back to Step 2
    process_task(next_task)
else:
    print("Queue drained. Sleeping until next cron trigger.")
    call_tool("blackboard_post", {
        "topic": "swarm/status",
        "message": { "status": "idle", "timestamp": now_iso() }
    })
```

---

## Quality Gates (ReflexionEvaluator Criteria)

Every PR/commit is evaluated against these criteria before being pushed:

| Criterion | Why |
|-----------|-----|
| Tests exist for every new function | Prevents regressions; LLM-written code needs tests to verify correctness |
| No TODO comments in production code | TODOs are incomplete work — finish or document in blockers.md |
| All imports are used | Dead imports indicate copy-paste errors or incomplete refactors |
| Error handling present for async operations | Unhandled promise rejections crash Node services silently |
| Commit message follows conventional commits | Required for automated changelog and semantic versioning |

Score threshold: **0.7** (70%). Below this, trigger a retry cycle. Above 0.7 with failures noted: merge with a follow-up task queued.

---

## Escalation Protocol

If the same task fails 3 retry cycles:

1. Send Telegram message with score + failure details
2. Mark task `blocked` via `goal_complete(taskId, { status: "blocked" })`
3. Continue to `goal_next_task()` — do not stall the entire queue
4. Log blocked task to `output/blockers.md`

---

## Integration with Other Skills

- **github-watcher** — Populates the GoalPlanner queue from GitHub issues/PRs; run this first if queue is empty
- **subagent-driven-development** — Provides the per-subtask implementation pattern used in Step 4
- **swarm-orchestrator** — Coordinates multiple Hermes instances working on the same repo

---

## Example Cron Trigger

This skill is designed to run every 15 minutes via cron:

```yaml
- name: "agentic-loop"
  schedule: "*/15 * * * *"
  trigger: "Run the agentic swarm loop: check GoalPlanner queue, process next task autonomously using the agentic-swarm skill."
  platform: "internal"
  skills: ["agentic-swarm"]
```

## Helper Functions Reference

These are pseudocode helpers referenced in the protocol above:

- `get_repo_name()` — `exec("git remote get-url origin").stdout` parsed to extract repo name
- `get_repo_info()` — Returns `{ remote, branch, lastCommit, repoName }`
- `now_iso()` — Returns current UTC timestamp as ISO 8601 string
- `extract_patterns(summaries)` — Extracts recurring file patterns, naming conventions, test frameworks from a list of implementation summaries
- `chunk(list, size)` — Splits list into batches of up to `size` items

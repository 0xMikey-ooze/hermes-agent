# SKILL: hermes-tasks — Task Queue & Database Access

## When to use
- User asks "what tasks are there?" / "what's in the queue?" / "what are you working on?"
- You're about to start work on something — check if a task exists first
- You finish something — mark the task done
- User asks you to track/remember something — create a task
- User asks about DB contents, events, skills, or agent sessions — use query_db

## Tools

### list_tasks
Check the full queue. Always call this at the start of a work session.
```
list_tasks({})                           # all tasks
list_tasks({"status": "pending"})        # only pending
list_tasks({"status": "in_progress"})    # what's active
```

### get_task
Get full details on a specific task.
```
get_task({"task_id": "task-abc12345"})
```

### update_task_status
**Always update status when your work changes state.**
```
update_task_status({"task_id": "task-abc12345", "status": "in_progress", "note": "Starting DB migration"})
update_task_status({"task_id": "task-abc12345", "status": "done", "note": "Deployed to Railway"})
update_task_status({"task_id": "task-abc12345", "status": "blocked", "note": "Waiting for API key"})
```

### create_task
Create a task from chat when the user wants something tracked.
```
create_task({"title": "Migrate SQLite to Neon", "description": "Full instructions...", "repo": "0xMikey-ooze/faithdrop"})
```

### query_db
Read-only SQL queries. Tables: tasks, events, agent_sessions, skills, watched_repos, simulations.
```
query_db({"sql": "SELECT * FROM tasks WHERE status='pending' ORDER BY created_at DESC"})
query_db({"sql": "SELECT asset, COUNT(*) as bets FROM simulations GROUP BY asset"})
query_db({"sql": "SELECT name, created_at FROM skills ORDER BY created_at DESC LIMIT 10"})
```

## Workflow Pattern

1. **Session start**: `list_tasks({"status": "pending"})` — know what's waiting
2. **Pick up a task**: `update_task_status({id, "in_progress"})`  
3. **While working**: reference the task description in your responses
4. **Complete**: `update_task_status({id, "done", "note": "what was done"})`
5. **Hit a wall**: `update_task_status({id, "blocked", "note": "what's blocking"})`

## Rules
- Never say "I'll look into that" without first checking if a task exists
- Never say a task is done without calling `update_task_status` with status=done
- If user mentions a project from the queue in chat, reference the task by title
- Use `query_db` for any analytical question about the system (events, sessions, etc.)

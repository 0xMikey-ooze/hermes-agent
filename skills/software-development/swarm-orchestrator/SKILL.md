---
name: swarm-orchestrator
description: >
  Multi-agent swarm that implements features TDD-first using parallel delegate_task agents.
  Use when asked to implement multiple features, run the swarm, or do parallel coding.
  Replaces tmux-swarm.sh with Hermes-native delegation + AGI module coordination.
version: 1.0.0
author: Jackson (swarm integration)
metadata:
  hermes:
    tags: [swarm, delegation, parallel, tdd, multi-agent]
    related_skills: [subagent-driven-development, test-driven-development, writing-plans]
    requires_tools: [delegate_task, exec, read_file, write_file]
---

# Swarm Orchestrator

## When to Use

- "run the swarm on X"
- "implement these features using the swarm"
- "parallel coding teams for Y"
- "multi-agent implementation of Z"

## Process

### Phase 1: Plan (you do this, not a subagent)

1. Read the repo structure with `exec("find . -type f -name '*.js' | head -50")`
2. Call `goal_decompose` on the task to generate subtasks
3. Write the plan to `output/swarm-plan.json` and post it to blackboard topic `swarm/plan`

```python
# Decompose the goal
goal_decompose(
    goal="Implement X feature with full test coverage",
    context={"repoInfo": "Node.js CommonJS project", "constraints": ["no new deps"]}
)

# Post plan to shared blackboard
blackboard_post(topic="swarm/plan", message={"tasks": [...], "timestamp": "..."})

# Persist plan to disk
write_file("output/swarm-plan.json", json.dumps(plan, indent=2))
```

### Phase 2: Test Architecture (delegate_task)

Spawn one delegate for the test architect. See `prompts/test-architect.md` for the full prompt.

```python
delegate_task(
    goal="Write RED-phase tests for all features in the plan before implementation",
    context=open("prompts/test-architect.md").read() + "\n\nPLAN:\n" + open("output/swarm-plan.json").read(),
    toolsets=['terminal', 'file']
)
```

The test architect will:
- Write failing tests for every feature
- Post test file locations to blackboard `swarm/tests`
- Commit all test files

### Phase 3: Implementation (parallel delegate_task)

Spawn up to 3 delegates simultaneously using batch mode. See `prompts/team.md` for the team prompt.

```python
# Batch spawn — all 3 start in parallel
batch_delegate([
    {
        "goal": "Team 1 — Backend/core: implement features until tests go GREEN",
        "context": team_prompt + "\nTEAM_ID: team-1\nSCOPE: backend, core logic",
        "toolsets": ["terminal", "file"]
    },
    {
        "goal": "Team 2 — Integration: wiring, exports, cross-module connections",
        "context": team_prompt + "\nTEAM_ID: team-2\nSCOPE: integration, exports",
        "toolsets": ["terminal", "file"]
    },
    {
        "goal": "Team 3 — QA: verify all tests pass, add edge case tests, fix failures",
        "context": team_prompt + "\nTEAM_ID: team-3\nSCOPE: testing, edge cases",
        "toolsets": ["terminal", "file"]
    }
])
```

Each delegate:
- Reads the plan from `output/swarm-plan.json` and blackboard `swarm/plan`
- Reads failing tests from `output/tests/` and blackboard `swarm/tests`
- Implements features TDD-first (RED → GREEN)
- Commits after each feature: `git commit -m "feat(team-N): <feature>"`
- Posts progress to blackboard `swarm/progress/<team-id>`

### Phase 4: Review

After all delegates complete:

```python
# Check final test run
exec("npm test")

# Review all commits from swarm
exec("git log --oneline -20")

# Open a PR
exec("gh pr create --title 'feat: implement X (swarm)' --body '...'")
```

## Blackboard Coordination

Delegates coordinate via the AGI Blackboard MCP server (if running):

| Topic | Who writes | Who reads |
|-------|-----------|-----------|
| `swarm/plan` | Planner | All teams |
| `swarm/tests` | Test architect | All teams |
| `swarm/progress/team-1` | Team 1 | Orchestrator, QA |
| `swarm/progress/team-2` | Team 2 | Orchestrator, QA |
| `swarm/progress/team-3` | Team 3 | Orchestrator, QA |

## Starting the MCP Server

The AGI MCP server provides shared memory, blackboard, and goal planning.
Start it before spawning delegates:

```bash
node /path/to/swarm/src/mcp/agi-server.js &
```

Configure Hermes to connect via `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  swarm-agi:
    command: node
    args: ["/path/to/swarm/src/mcp/agi-server.js"]
```

## Red Flags — Never Do These

- Skip the test architect phase (tests must be RED before teams start)
- Let teams touch the same files simultaneously (scope them by layer)
- Spawn more than 3 parallel teams (context overhead degrades quality)
- Proceed to Phase 4 if any team reports a blocker in its progress post
- Forget to commit the plan files before spawning teams

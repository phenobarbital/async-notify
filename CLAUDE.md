# async-notify Development Guide for Claude

## Project

Asyncio-based Python library for sending notifications (email, IM, SMS, push)
through a uniform provider interface.
See @.agent/CONTEXT.md for full architectural context.

**Distribution**: `async-notify` · **Import package**: `notify`
**Production branch**: `main` · **Integration branch**: `dev`

## Development Environment

### Package Management & Virtual Environment

**CRITICAL RULES:**
1. **Package Manager**: Use **`uv`** exclusively for package management
   ```bash
   uv pip install <package>
   uv pip list
   uv add <package>
   ```

2. **Virtual Environment**: ALWAYS activate before Python operations
   ```bash
   source .venv/bin/activate
   ```
   **NEVER** run `uv`, `python`, or `pip` commands without activating first.

3. **Dependencies**: Manage all dependencies via `pyproject.toml`

## Provider-Centric Architecture

async-notify reaches the outside world through **providers**. When adding or
changing a transport:

1. **Location**: every provider is a package under `notify/providers/<name>/`
   (`__init__.py` re-exports the class defined in `<name>.py`).
2. **Base classes**: subclass `ProviderBase` (or `ProviderMessaging` /
   `ProviderIM` / `ProviderPush`) from `notify/providers/base.py` and declare
   `provider`, `provider_type`, and `blocking`.
   ```python
   from notify.providers.base import ProviderBase, ProviderType

   class MyProvider(ProviderBase):
       provider = "myprovider"
       provider_type = ProviderType.NOTIFY
       blocking = False

       async def _send_(self, to, message, **kwargs):
           """Deliver a single message. Never override send()."""
   ```
3. **Instantiation**: user-facing code goes through the `Notify` factory
   (`notify/notify.py`), never a direct provider import.
4. **Configuration**: credentials/settings come from `notify/conf.py`
   (navconfig) — never `os.environ` inside a provider.
5. **Documentation**: every provider MUST have Google-style docstrings
   explaining purpose, parameters, and return values.

## Async-First Development

async-notify is built on async/await patterns. If a third-party SDK is
sync-only, route it through `blocking = 'executor'` rather than blocking the
event loop.

## Cython Extensions

`notify/exceptions.pyx` and `notify/types/typedefs.pyx` are Cython modules.
Follow `.claude/rules/cython-development.md`, and rebuild after editing:
```bash
python setup.py build_ext --inplace
```
Generated `.c` sources are NOT tracked in git.

## Non-Negotiable Rules

### Environment
- Package manager: `uv` exclusively (`uv add`, `uv pip install`)
- ALWAYS activate venv before any command: `source .venv/bin/activate`
- NEVER run python/uv/pip without activating first

### Code Standards
- All functions and classes: Google-style docstrings + strict type hints
- Pydantic models for all data structures
- async/await throughout — no blocking I/O in async contexts
- Logger (`self.logger`) instead of print statements

### Workflow: Think → Act → Reflect
1. For complex tasks: create plan in `artifacts/plan_[task_id].md` first
2. Implement incrementally
3. Run `pytest` after ANY logic change — no exceptions
4. Save evidence to `artifacts/logs/`

### Security
- Never commit API keys — use environment variables
- Never run `rm -rf` or system-level deletions
- No form submissions or logins without user approval

### Adversarial Second Opinion: Codex CLI

The OpenAI `codex` CLI is installed and authenticated. Use it as an
independent perspective for adversarial code reviews, design opinions,
brainstorming, research cross-checks, and implementation sanity checks.

Rules:
- Never feed Codex your reasoning, justification, or preferred conclusion.
  Give it only the diff, the requirement, and the question. Supplying your
  conclusions produces ratification, not review.
- Treat Codex output as advisory. For every substantive finding, explicitly
  mark it as `CONFIRM` (adopt), `REJECT` (with reason), or `ESCALATE`.
- Never silently concede to Codex and never silently drop a finding.
- Run each Codex call as a full background agent session. Typical runtime is
  30 seconds to 2 minutes; do not call it per edit or from hooks.
- For parallel perspective, use one Claude subagent and one background
  `codex exec` with the same neutral brief, then synthesize agreements and
  disagreements.

Commands:
```bash
# Reviews
codex exec review --uncommitted
codex exec review --base dev
codex exec review --commit <sha>

# Opinions, brainstorming, and cross-checks
codex exec --sandbox read-only -o <scratch-file> "<neutral brief>"

# Follow-up in the same Codex session
codex exec resume --last "<question>"

# Image generation / mockups / wireframes
codex exec --sandbox workspace-write -o <out.txt> \
  "Generate an image: <description>. Save as <name>.png"
codex exec --sandbox workspace-write -i <screenshot.png> -o <out.txt> \
  "Generate an image variant: <neutral brief>. Save as <name>.png"
```

Image-generation gotcha: `resume` does not accept `--sandbox`; use
`-c sandbox_mode="workspace-write"` on resume when a writable sandbox is
required.

## Key References
- Architecture & patterns: @.agent/CONTEXT.md
- SDD workflow: @docs/sdd/WORKFLOW.md
- SDD platform reference: `docs/sdd/PLATFORM.md`
- SDD practical guide: `docs/sdd/GUIDE.md`
- Skills: @.agent/skills/
- Workflows: @.agent/workflows/

# SDD Workflow & Worktree Policy

---

## Git Configuration

async-notify uses two long-lived branches:

- **`main`** — tagged releases and production. Hotfixes land here via PR;
  no feature work ever bases on `main`.
- **`dev`** — integration branch for all feature work. Default base
  for `type: feature` flows.

**Flow types** (FEAT-145): every brainstorm/proposal/spec declares `type`
and `base_branch` via YAML frontmatter at the top.
- `feature` — base is `dev` (default), or a parent feature branch for
  sub-features. NEVER `main`.
- `hotfix` — base is `main` (mandatory).

**`/sdd-done` NEVER pushes to or opens a PR against `main`** —
hotfix PRs are user-initiated. After the user merges the hotfix into
`main`, run `/sdd-done <FEAT-ID> --sync-down` to propagate the change
back into `dev`. (`--sync-dev` is a deprecated alias.)

**Recommended branch protection**: `main` should require PRs and passing
CI. Not configured declaratively in this repo — set via GitHub repo
settings.

- **Worktrees branch from `base_branch`** (which `/sdd-task` and `sdd-worker`
  ensure HEAD is on before creating the worktree). Hotfix worktrees branch
  from `main`; feature worktrees branch from `dev` (or any non-main branch
  the user picks for sub-features).

## Worktree Creation

> **CRITICAL**: Do NOT use `claude --worktree`. It branches from the repo's default
> branch (`main`), which does not contain SDD artifacts.
>
> Always create worktrees manually from the current branch:

```bash
# Standard pattern: create worktree from current branch
git worktree add -b <branch-name> .claude/worktrees/<worktree-name> HEAD
```

### Quick reference

```bash
# From dev (most common)
git checkout dev
git worktree add -b feat-014-teams-adaptive-cards \
  .claude/worktrees/feat-014-teams-adaptive-cards HEAD

# From another feature branch (sub-features)
git checkout feat-014-teams-adaptive-cards
git worktree add -b feat-015-sub-task \
  .claude/worktrees/feat-015-sub-task HEAD

# Then launch Claude inside the worktree
cd .claude/worktrees/feat-014-teams-adaptive-cards
claude   # interactive, manual /sdd-start
# or
claude --agent sdd-worker --model sonnet --verbose
```

### Cleanup

```bash
# After PR merge
git worktree remove .claude/worktrees/<name>
# or prune all dead worktrees
git worktree prune
```

### .gitignore

```gitignore
.claude/worktrees/
```

## SDD Auto-Commit Rule

> **CRITICAL**: Every SDD command that creates or modifies files MUST commit
> them on the appropriate branch before finishing. Uncommitted files are
> invisible to worktrees and other sessions.

| Command | What it commits | Where (FEAT-145) |
|---------|-----------------|------------------|
| `/sdd-brainstorm` | `sdd/proposals/<n>.brainstorm.md` (with frontmatter) | `base_branch` |
| `/sdd-proposal`   | `sdd/proposals/<n>.proposal.md` (with frontmatter)  | `base_branch` |
| `/sdd-spec`       | `sdd/specs/<n>.spec.md` (with frontmatter) + a `reserve_ids.py` FEAT-ID reservation commit to `sdd/tasks/.id_ledger.json` (FEAT-387) | `base_branch` |
| `/sdd-task`       | `sdd/tasks/index/<feature>.json` + `sdd/tasks/active/TASK-*` + a `reserve_ids.py` TASK-ID reservation commit to `sdd/tasks/.id_ledger.json` (FEAT-387) | `base_branch` |
| `/sdd-start`      | Per-spec index status update + implementation code  | worktree (feature branch) |
| `/sdd-done`       | Verification stamp on per-spec index (committed on feature branch); merges feature → `base_branch` | worktree (feature branch), merged to `base_branch` by Step 9 |

Commit message convention:
```
sdd: <action> for <feature-name>
```

**Note (FEAT-145)**: `/sdd-start` no longer needs to `cd` back to the main
repo to update SDD state — per-spec indexes mean each feature owns its own
index file, so the worktree's commit covers code AND state in one stroke.
The merge in `/sdd-done` brings them to `base_branch` atomically.

**Note (FEAT-387)**: `sdd/tasks/.id_ledger.json` is a git-tracked
compare-and-swap counter for `TASK-<NNN>`/`FEAT-<NNN>` numbers, allocated
via `scripts/sdd/reserve_ids.py` (not scanned-and-incremented by hand). Its
reservation commit is independent — pushed to `base_branch` immediately by
`reserve_ids.py` itself, BEFORE the calling command's own task/spec files
are written, never bundled into the same commit.
`scripts/sdd/check_id_collisions.py` is an independent, read-only backstop
that catches any `TASK-<NNN>` collision that still slips through. See
`sdd/WORKFLOW.md` ("TASK/FEAT ID Allocation") for full details.

## Isolation Model

Worktrees isolate **features** from each other. Tasks within a feature run
sequentially in the same worktree via `/sdd-start TASK-<NNN>`.

```
Terminal 1 (in .claude/worktrees/feat-007):     Terminal 2 (in .claude/worktrees/feat-008):
  /sdd-start TASK-001 → commit                   /sdd-start TASK-010 → commit
  /sdd-start TASK-002 → commit (sees 001)         /sdd-start TASK-011 → commit
  /sdd-start TASK-003 → commit (sees 001+2)       /sdd-start TASK-012 → commit
  push, PR against dev                            push, PR against dev
```

## Typical Workflow

```bash
# 1. Ensure you're on dev with latest
git checkout dev && git pull origin dev

# 2. Create and approve a spec (committed to dev automatically)
/sdd-spec teams-adaptive-cards -- ...
/sdd-task sdd/specs/teams-adaptive-cards.spec.md

# 3. Create worktree from dev
git worktree add -b feat-014-teams-adaptive-cards \
  .claude/worktrees/feat-014 HEAD

# 4. Enter worktree and work
cd .claude/worktrees/feat-014

# Manual (task-by-task):
claude
/sdd-start TASK-069
/sdd-start TASK-070
/sdd-done FEAT-014

# Or autonomous:
claude --agent sdd-worker --dangerously-skip-permissions --model sonnet --verbose
/sdd-done FEAT-014

# 5. Push and PR
git push origin feat-014-teams-adaptive-cards
# Create PR against dev

# 6. Cleanup after merge
cd ~/proyectos/notify   # back to main repo
git worktree remove .claude/worktrees/feat-014
```

## Autonomous Agent (`sdd-worker`)

The `sdd-worker` agent (`.claude/agents/sdd-worker.md`) implements all tasks for
a feature sequentially. Launch it **inside** a manually-created worktree:

```bash
cd .claude/worktrees/<feature-worktree>
claude --agent sdd-worker --model sonnet --verbose
```

Key properties: uses Sonnet, implements EXACTLY what tasks
specify (no redesigns), commits after each task.

For background execution:
```bash
cd .claude/worktrees/feat-014
tmux new -s feat-014 \
  "claude --agent sdd-worker --model sonnet --verbose"
# Ctrl+B, D to detach — tmux attach -t feat-014 to reconnect
```

## Task Index Schema (FEAT-145 — per-spec)

Each feature has its own per-spec index at `sdd/tasks/index/<feature-slug>.json`.
The header carries flow metadata cached from the spec frontmatter; the
`tasks[]` array is local to that feature only.

```json
{
  "feature": "<feature-slug>",
  "feature_id": "FEAT-<NNN>",
  "spec": "sdd/specs/<feature-slug>.spec.md",
  "type": "feature",
  "base_branch": "dev",
  "created_at": "<ISO-8601>",
  "completed_at": null,
  "tasks": [
    {
      "id": "TASK-<NNN>",
      "feature_id": "FEAT-<NNN>",
      "feature": "<feature-slug>",
      "status": "pending",
      "depends_on": [],
      "...": "..."
    }
  ]
}
```

Both `feature_id` and `feature` must be present on every task entry.
Commands resolve features by matching either field (exact, numeric suffix,
or substring) against the per-spec index headers. There is no legacy
monolithic `.index.json` in this repo — per-spec indexes are the only
supported format. Tasks that cannot be attributed to a feature live in
`sdd/tasks/index/_orphans.json` and are surfaced (but not assigned) by
`/sdd-status` / `/sdd-next`.

### When NOT to Use Worktrees

- **Hotfixes on `main`**: Work directly on `main` or a short-lived `hotfix/*` branch.
- **Documentation-only changes**: No code conflicts possible, work on `dev` directly.
- **Single-task features**: If a spec has only one task, a worktree adds overhead
  with no benefit. Work directly on a feature branch.
- **Exploratory brainstorming**: `/sdd-brainstorm` doesn't produce code — no worktree needed.
- **Quick bug fixes**: If the fix is a single commit, skip the worktree ceremony.

---
description: Bump the async-notify version on dev, promote it to main via PR, then (on confirmation) create the GitHub Release that builds the Cython wheels and publishes to PyPI
argument-hint: "<patch|minor|major|X.Y.Z[aN|bN|rcN]> [--dry-run] [--no-release] [--publish-only]"
allowed-tools: Bash, Read, Edit
---

# /release — async-notify Release

Drive a release of the single `async-notify` distribution: bump the version on
`dev`, promote `dev` → `main` through a pull request, and — only after you say
yes — create the GitHub Release that triggers `.github/workflows/release.yml`,
which builds the wheels and uploads them to PyPI.

There is no release script: the mechanics are a one-line version edit, a PR
and a `gh release create`. This command is the judgment around them (safety
gates, release notes, the publish decision).

## Usage

```
/release patch                  # 1.6.0 -> 1.6.1
/release minor                  # 1.6.0 -> 1.7.0
/release major                  # 1.6.0 -> 2.0.0
/release 1.7.0rc1               # explicit version (pre-releases allowed)
/release patch --dry-run        # preview every step, touch nothing
/release patch --no-release     # bump + push dev + open the dev -> main PR, stop there
/release --publish-only         # main already carries the new version: tag + GitHub Release only
```

## How versioning and publishing work here

- **One distribution, one version source**: `__version__` in
  `notify/version.py`. `pyproject.toml` reads it dynamically
  (`[tool.setuptools.dynamic] version = { attr = "notify.version.__version__" }`).
  Edit **only** that line.
- `make bump-patch` / `bump-minor` / `bump-major` rewrite that line in place
  (no commit). For an explicit or pre-release version, edit the line directly.
- **Do not use** `.bumpversion.cfg` (stale: still says `0.5.24` and targets
  `setup.py`), and **never run `make release`** — it runs `uv publish` from a
  local single-platform build, bypassing `release.yml`'s multi-platform wheel
  build and Cython verification.
- **Branch flow**: feature work lands on `dev`; `main` is protected and
  requires a pull request. A release is therefore: version bump committed on
  `dev` → PR `dev` → `main` → merge → tag on `main`. `/release` never pushes
  to `main` directly.
- **Tags** are the bare version (`1.6.0`, `1.5.7`), lightweight, pointing at
  the `main` merge commit. A `-N` suffix (`1.6.0-1`) has been used once to
  re-trigger a release whose build failed **before anything was uploaded** —
  PyPI still received `1.6.0`, because the uploaded version comes from
  `notify/version.py`, never from the tag.
- **`release.yml`** fires on `release: [created]`:
  - `cibuildwheel` builds CPython 3.11–3.14 wheels for `manylinux x86_64` and
    `win AMD64` (no sdist, no macOS, no musllinux);
  - it asserts both Cython extensions (`notify/exceptions`,
    `notify/types/typedefs`) are compiled into every wheel;
  - it uploads with `twine` using the `ASYNC_NOTIFY_PYPI_API_TOKEN` secret.
    There is **no `skip-existing`**: re-running a release for a version PyPI
    already has fails the upload step.
- **PyPI never allows re-uploading a version.** A broken published release is
  fixed with a new patch version, never a re-upload.

---

## Step 0 — Detect the phase

A release spans a PR merge, so it is often resumed. Before anything else:

```bash
git fetch origin --tags --quiet
git show origin/dev:notify/version.py  | grep __version__
git show origin/main:notify/version.py | grep __version__
git tag --sort=-creatordate | head -3
gh release list --limit 3
curl -s https://pypi.org/pypi/async-notify/json | python -c "import json,sys; print('PyPI latest:', json.load(sys.stdin)['info']['version'])"
gh pr list --base main --head dev --state open
```

- `--publish-only`, or `origin/main` already carries a version that has **no
  tag and is not on PyPI** → skip to **Step 6**.
- An open `dev` → `main` PR already carries the bump → skip to **Step 5**.
- Otherwise start at **Step 1**.

Report what you found in one short table before continuing.

## Step 1 — Parse and validate

1. `$ARGUMENTS` must contain exactly one of `patch`, `minor`, `major`, or an
   explicit PEP 440 version (`X.Y.Z`, optionally `aN` / `bN` / `rcN`). If it is
   missing or ambiguous, **ask** — never default to `patch`.
2. Compute the new version from `origin/dev`'s `notify/version.py`. For an
   explicit version, it must be strictly greater than both the current version
   and the latest PyPI version; otherwise abort.
3. The new version must not already exist as a tag, a GitHub Release, or a PyPI
   release (Step 0 output). If it does, abort — a previous release did not
   finish, or the number is burned.
4. Confirm location and branch — releases are prepared from `dev` in the
   **primary checkout**, never from a feature branch or a worktree:
   ```bash
   git rev-parse --abbrev-ref HEAD && git rev-parse --show-toplevel
   ```
   If HEAD is not `dev`, or the toplevel is under `.claude/worktrees/`, abort
   and say why.
5. The working tree must be clean and `dev` in sync with `origin/dev`:
   ```bash
   git status --porcelain
   git rev-list --left-right --count origin/dev...dev
   ```
   Dirty → abort ("Commit or stash first — the release commit carries the
   version file only"). Behind → `git pull --ff-only origin dev`. Ahead →
   abort ("push or drop local commits first").
6. Check for a concurrent SDD worker before touching shared refs (a live worker
   may merge into `dev` under you):
   ```bash
   ps -eo pid,etime,args | grep -i '[s]dd-worker'
   ```
   If one is live, warn and ask whether to continue.

## Step 2 — Preview and release notes

1. Show what will ship:
   ```bash
   git log --oneline $(git describe --tags --abbrev=0 origin/main)..origin/dev
   ```
2. **Draft release notes** from that log — grouped (Features / Fixes / CI &
   build / Internal), in plain language, not the raw log. SDD commits
   (`sdd: ...`) and merge commits are folded into the change they belong to.
3. `CHANGES.rst` has not been maintained since 0.6.0 (GitHub Release notes are
   the de-facto changelog). **Ask** whether to also prepend an entry there; if
   yes, use its existing RST shape:
   ```rst
   .. _vX.Y.Z:

   X.Y.Z (YYYY-MM-DD)
   ------------------

   *<Headline>:*

       - <change>
   ```
4. Print the plan: old → new version, the commits, the notes draft, and the
   commands Steps 3–6 will run.

If `--dry-run` was passed, **stop here** and report.

## Step 3 — Verify before bumping

The release build compiles Cython and runs on four Python versions; catch the
cheap failures locally first:

```bash
source .venv/bin/activate
python setup.py build_ext --inplace
pytest tests/ -q -p no:cacheprovider 2>&1 | tail -15
rm -rf build/release-check && uv build --wheel --out-dir build/release-check
python -c "import zipfile,glob; w=glob.glob('build/release-check/*.whl')[0]; n=zipfile.ZipFile(w).namelist(); ext=[x for x in n if x.startswith(('notify/exceptions.','notify/types/typedefs.')) and x.endswith(('.so','.pyd'))]; assert len(ext)==2, ext; assert not any(x.startswith(('tests/','sdd/','.claude/')) for x in n); print('wheel OK', w)"
```

- Cython build or wheel check failure → stop and report. Do not bump a version
  on a broken build.
- Test failures: the suite has known **pre-existing** failures (at the time of
  writing `tests/test_ses.py` and `tests/test_outlook1.py`, which fail offline
  with their mocks as written). No `integration`/`live` markers are registered,
  so a marker filter does not exclude them. Compare against the last release
  instead:
  ```bash
  # tree is clean (Step 1); run origin/main's suite in a throwaway detached worktree
  git worktree add --detach build/release-baseline origin/main
  (cd build/release-baseline && python setup.py build_ext --inplace -q && PYTHONPATH=. pytest tests/ -q -p no:cacheprovider 2>&1 | grep -E '^(FAILED|ERROR)') | sed 's/ - .*//' | sort > build/baseline-failures.txt
  pytest tests/ -q -p no:cacheprovider 2>&1 | grep -E '^(FAILED|ERROR)' | sed 's/ - .*//' | sort > build/candidate-failures.txt
  comm -13 build/baseline-failures.txt build/candidate-failures.txt   # NEW failures only
  git worktree remove build/release-baseline   # never --force: the build products are git-ignored, so a plain remove succeeds
  ```
  Any **new** failure → stop and report it. Pre-existing failures → list them
  in the plan and ask whether to proceed.

## Step 4 — Bump, commit, push `dev`

1. Bump: `make bump-<patch|minor|major>`, or for an explicit version edit
   only the `__version__ = "..."` line of `notify/version.py`. Confirm with
   `git diff` that nothing else changed.
   If the user approved a `CHANGES.rst` entry, write it now.
2. Commit and push:
   ```bash
   git add notify/version.py CHANGES.rst   # CHANGES.rst only if edited
   git commit -m "release: bump version to X.Y.Z"
   git push origin dev
   ```

## Step 5 — Promote `dev` → `main` (pull request)

`main` is protected: it only moves through a PR.

1. Open (or reuse) the PR:
   ```bash
   gh pr create --base main --head dev --title "Release X.Y.Z" --body "<release notes draft>"
   ```
2. Show the PR URL and its checks (`gh pr checks <n>`).
3. **Merging is the user's call.** Ask whether to merge now
   (`gh pr merge <n> --merge`) or wait for them to merge it. Never merge
   without an explicit yes; never use `--admin` to bypass protection.

If `--no-release` was passed, **stop here** and print the follow-up:
`/release --publish-only` once the PR is merged.

## Step 6 — GitHub Release (irreversible — confirm)

1. Re-verify against the **remote** `main`, not the local checkout:
   ```bash
   git fetch origin --tags --quiet
   git show origin/main:notify/version.py | grep __version__   # must equal X.Y.Z
   git rev-parse origin/main
   ```
   Mismatch → abort (the PR is not merged, or merged a different version).
2. Creating the release triggers `release.yml`, which uploads to PyPI, and
   **PyPI never allows re-uploading a version**. So:
   - state plainly: version `X.Y.Z`, commit `<sha>` on `main`, wheels for
     CPython 3.11–3.14 on manylinux x86_64 + Windows AMD64;
   - **ask for explicit confirmation**. Do not proceed on an implied yes.
3. Then create tag + release in one step, at the verified commit:
   ```bash
   gh release create X.Y.Z --target <sha> --title "X.Y.Z" --notes-file <notes.md>
   ```
   Use `--generate-notes` instead of `--notes-file` if the user prefers
   GitHub's PR list. Add `--prerelease` for `aN`/`bN`/`rcN` versions. Add
   `--draft` to stage it without triggering the publish (publishing the draft
   later creates the release event).
4. Watch the build:
   ```bash
   gh run list --workflow=release.yml --limit 1
   gh run watch <run-id>
   ```
5. Confirm on PyPI once the run is green:
   ```bash
   curl -s https://pypi.org/pypi/async-notify/X.Y.Z/json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['urls']), 'files for', d['info']['version'])"
   ```

## Step 7 — Sync `main` back into `dev`

The merge commit exists only on `main`. Bring it down so the next release PR
is a clean fast-forward:

```bash
git checkout dev && git pull --ff-only origin dev
git merge --ff-only origin/main || git merge origin/main -m "chore: sync main into dev after X.Y.Z"
git push origin dev
```

## Step 8 — Report

```
Release X.Y.Z

  Version:      1.6.0 -> X.Y.Z   (notify/version.py)
  Bump commit:  <sha> on dev
  PR:           #<n> dev -> main (merged)
  Tag:          X.Y.Z -> <main sha>
  GH Release:   created / draft / skipped
  release.yml:  <run url> — success / running / failed
  PyPI:         X.Y.Z — <N> wheels / pending

Notes: <2-3 bullet summary>
```

## Error handling

| Situation | Action |
|---|---|
| No bump type in `$ARGUMENTS` | Ask. Never default to `patch`. |
| Not on `dev`, or inside a worktree | Abort. Releases are prepared on `dev` in the primary checkout. |
| Dirty tree / `dev` ahead of `origin/dev` | Abort — the release commit carries the version file only. |
| Version already tagged, released or on PyPI | Abort — pick the next version; the number is burned. |
| Local tests, Cython build or wheel check fail | Stop before bumping; report the failure. |
| PR checks red | Do not merge; report and stop. |
| `origin/main` version ≠ X.Y.Z at Step 6 | Abort — PR not merged or merged the wrong version. |
| `release.yml` build job fails (nothing uploaded) | Fix on `dev` → PR → re-release. Reusing the version with a `-N` tag is valid **only** if PyPI has no files for it. |
| `release.yml` upload fails after a partial upload | The version is burned for those files — ship a new patch version. |
| Live `sdd-worker` detected | Warn, ask before touching shared refs. |

## Related

| Command | Purpose |
|---|---|
| `/release` | Bump + PR + tag + publish (THIS) |
| `/sdd-done --sync-down` | Propagate a hotfix merged into `main` back to `dev` |
| `.github/workflows/release.yml` | The build + PyPI upload this command triggers |

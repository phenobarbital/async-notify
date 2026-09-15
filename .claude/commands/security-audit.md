---
description: Full security audit of async-notify — secrets and provider credentials, dependencies, the notification attack surface (templates, email headers, attachments, notify server deserialization, TLS), CI/release supply chain, plus the config check
argument-hint: "[--scope deps|secrets|code|ci|config|all] [--report <path>]"
allowed-tools: Bash, Read, Grep, Glob, Write
---

# /security-audit — Full Repository, 3–6 min

Senior application-security pass over `async-notify`: a single PyPI
distribution (`notify/`, with two Cython extensions) that holds credentials for
a dozen third-party messaging services, renders caller-supplied Jinja2
templates into emails and chat messages, and ships an optional Redis-backed
notify server — plus the GitHub Actions workflow that publishes it and the
Claude Code config.

Produce a **scored** report with a prioritized remediation plan. Save it to
`artifacts/logs/security-audit-<YYYY-MM-DD>.md` (or `--report <path>`).

Scope defaults to `all`; `--scope` runs a single phase.

---

## Phase 0 — Map the surface

```bash
ls notify/providers/ notify/server/ .github/workflows/
grep -n '__version__' notify/version.py
curl -s https://pypi.org/pypi/async-notify/json | python -c "import json,sys; print('PyPI latest:', json.load(sys.stdin)['info']['version'])"
sed -n '/^dependencies/,/^\]/p' pyproject.toml
```

async-notify **is published to PyPI** and installed into other services that
hand it credentials and user data — a vulnerability in `notify/` ships to every
downstream installer, which raises its severity by one level over the same
issue in `tests/`, `examples/` or tooling.

Record, per provider package, which credential it holds (SMTP password, OAuth
client secret / token cache, API key, webhook URL) and which transport library
it uses. That table drives Phases 2 and 4.

---

## Phase 1 — Config (delegates to `/security-check`)

Run every phase of `.claude/commands/security-check.md`: agent privileges,
hook exfiltration, command/skill injection, memory poisoning, MCP, permissions.
Carry its findings into the score.

Repo-specific additions:
- `.mcp.json`, `.codex/config.toml` and `.parrot/mcp-toolkits.yaml` launch
  binaries from **ai-parrot's `.venv`** — anything that can write there runs
  code in every Claude/Codex session of this repo. Confirm the paths are the
  expected ones and that `.mcp.json` is git-ignored (only
  `.mcp.json.example` is tracked).
- `.claude/settings.json` hooks run `bash` scripts from `.claude/hooks/` and a
  Python module from ai-parrot's venv on every tool call.

**Score**: 0 CRITICAL and 0 HIGH → +20 · any HIGH → +10 · any CRITICAL → 0

---

## Phase 2 — Secrets and provider credentials

```bash
# Provider key shapes — the high-confidence patterns
grep -rnE 'sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AKIA[A-Z0-9]{16}|xox[bpsa]-[A-Za-z0-9-]{20,}|AIza[A-Za-z0-9_-]{35}|SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}|AC[a-f0-9]{32}|[0-9]{8,10}:AA[A-Za-z0-9_-]{33}|hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+|webhook\.office\.com/webhookb2/' \
  --include='*.py' --include='*.pyx' --include='*.toml' --include='*.yaml' --include='*.yml' \
  --include='*.json' --include='*.md' --include='*.rst' --include='*.ini' --include='*.cfg' --include='*.sh' \
  --exclude-dir={.venv,.git,build,dist,__pycache__,.claude,.parrot} . 2>/dev/null | head -30
```

(SendGrid `SG.`, Twilio account SID `AC…`, Telegram bot token `<id>:AA…`,
Slack and Teams incoming-webhook URLs are the shapes specific to this repo's
providers — a webhook URL **is** a credential: anyone holding it can post.)

```bash
# Assignment-shaped literals (noisier — triage each)
grep -rnE '(api[_-]?key|password|passwd|secret|token|client_secret|auth_token)\s*=\s*["'"'"'][^"'"'"'$\{][^"'"'"']{12,}["'"'"']' \
  --include='*.py' --exclude-dir={.venv,.git,build,dist,__pycache__} notify/ examples/ samples/ 2>/dev/null | head -30

grep -rn 'BEGIN [A-Z ]*PRIVATE KEY' --exclude-dir={.venv,.git,build} . 2>/dev/null

# navconfig env files, OAuth token caches, service-account JSON
git ls-files | grep -iE '(^|/)\.env($|\.)|^env/|token|credential|service[_-]?account|client_secret|\.pem$|\.p12$|\.key$' || echo "OK: nothing credential-shaped tracked"
git check-ignore -v .o365_token.txt env/ settings/ 2>&1
find . -maxdepth 3 \( -name '.env*' -o -name '*token*.txt' -o -name '*token*.json' -o -name 'credentials*.json' \) \
  -not -path './.venv/*' -not -path './.git/*' -not -name '.env.example' -type f 2>/dev/null

# Anything a past commit still carries
git log --all --oneline -S'xoxb-' -- . 2>/dev/null | head
git log --all --oneline --diff-filter=D --name-only -- '*.env' '*token*' 'env/*' 2>/dev/null | head
```

Then the **runtime** credential checks:

- Every credential must come from `notify/conf.py` (navconfig) or an explicit
  constructor argument — flag any `os.environ`/`os.getenv` read inside
  `notify/providers/` (convention violation, and it bypasses navconfig's
  secret sources).
- OAuth token caches (Office365/Outlook/Gmail) written to disk: where, and with
  what file mode? A world-readable refresh token is a **HIGH**.
  ```bash
  grep -rnE 'token_path|TokenBackend|token_filename|\.o365_token|credentials\.json|chmod|umask' --include='*.py' notify/ | head -20
  ```
- Credentials reaching logs or exception messages:
  ```bash
  grep -rnE 'logger\.(debug|info|warning|error|exception)\(.*(password|passwd|token|secret|api_key|auth|credential)' --include='*.py' notify/ | head -20
  grep -rnE 'raise .*\(.*(password|token|secret|api_key)' --include='*.py' notify/ | head -10
  ```

Every hit needs triage: a test fixture, a docs placeholder and a live key look
identical to grep. Report only what you confirmed by reading the line.
`.o365_token.txt` in the working directory is expected **if** it is git-ignored
— report it only if tracked, in history, or world-readable.

**Score**: 0 live secrets → +20 · 1–3 → +10 · 4+ → 0 · private key or live token committed → −10

**If a live key or webhook URL is found**: it is compromised the moment it is
in git history. Rotating it at the provider is the fix; deleting the line is
not. Say so explicitly.

---

## Phase 3 — Dependencies and supply chain

```bash
source .venv/bin/activate

# pip-audit is not installed by default; uvx runs it without polluting the venv
uvx pip-audit --strict 2>&1 | tail -40 || echo "pip-audit unavailable"

# Lockfile integrity (uv.lock is git-ignored here — note it: installs are not reproducible)
git ls-files uv.lock; git check-ignore -v uv.lock
```

Then the **repo-specific** checks a generic audit misses:

```bash
# Hard pins on provider SDKs — frozen pins stop receiving security fixes
sed -n '/optional-dependencies/,/^\[tool/p' pyproject.toml | grep -E '=='
# Direct-from-git or URL dependencies (bypass PyPI review entirely)
grep -nE '@\s*git\+|\bgit\+https|http://' pyproject.toml setup.py
# Build-time deps: the wheel build runs setup.py + Cython
sed -n '/\[build-system\]/,/^\[/p' pyproject.toml
cat .github/dependabot.yml
```

- [ ] A runtime or extra dependency from a `git+` URL? → **HIGH**
      (unreviewable, mutable source shipped to PyPI users)
- [ ] Any `http://` dependency URL? → **CRITICAL**
- [ ] An `==`-pinned SDK (`slack_bolt`, `twilio`, `o365`, `Office365-REST-Python-Client`,
      `msgraph-*`, `onesignal-sdk`, `aiobotocore`, `moviepy`, …) with a known
      CVE fixed in a later release? → severity of the CVE; a pin **without** a
      CVE is informational, not a finding
- [ ] Unbounded build dependency (`Cython`, `setuptools`) in `[build-system]`?
      → **LOW** (build reproducibility)
- [ ] Dependabot covering `pip` **and** `github-actions` ecosystems? Missing
      one → **LOW**

**Score**: 0 vulns → +20 · only low/medium → +12 · any high → +5 · any critical → 0

---

## Phase 4 — Notification attack surface

This is the phase a generic audit does not have. async-notify turns
**caller-supplied data** (recipients, subjects, message bodies, template
source, attachment paths, kwargs) into SMTP messages, HTTP API calls and chat
posts, using stored credentials. Downstream services often pass end-user input
straight through — treat every `send()` argument as potentially untrusted.

```bash
source .venv/bin/activate

# 1. Deserialization in the notify server — the highest-impact sink.
#    The worker base64-decodes and cloudpickle.loads tasks read from Redis.
grep -rnE 'cloudpickle\.loads|pickle\.loads|marshal\.loads|dill\.loads' --include='*.py' notify/
grep -rnE 'NOTIFY_REDIS|from_url|redis_url|xadd|xreadgroup|subscribe' --include='*.py' notify/server/ notify/conf.py | head -20

# 2. Template injection (SSTI): caller-supplied Jinja2 *source* is compiled.
grep -rnE 'from_string|Environment\(|SandboxedEnvironment|ImmutableSandboxedEnvironment|is_template_source|template_is_source' --include='*.py' notify/
grep -rnE 'autoescape' --include='*.py' notify/templates.py notify/providers/base.py

# 3. Email header injection: CR/LF in subject / recipients / sender names
grep -rnE 'msg\[|Header\(|format_address|formataddr|\\r|\\n' --include='*.py' notify/providers/_mime_utils.py notify/providers/mail.py | head -30

# 4. Attachments: caller-supplied paths read from disk and mailed out
grep -rnE 'attach|open\(|read_bytes|Path\(' --include='*.py' notify/providers/mail.py notify/providers/_mime_utils.py notify/models.py notify/providers/*/ | grep -vi test | head -30

# 5. TLS: verification disabled or downgraded anywhere
grep -rnE 'verify\s*=\s*False|ssl\s*=\s*False|CERT_NONE|check_hostname\s*=\s*False|_create_unverified_context|use_tls\s*=\s*False|start_tls\s*=\s*False|validate_certs\s*=\s*False' --include='*.py' notify/

# 6. Outbound URLs built from caller/config input (SSRF, token sent to wrong host)
grep -rnE 'webhook|base_url|api_url|endpoint|f"https?://|f'"'"'https?://' --include='*.py' notify/providers/ | head -30

# 7. Markup injection into chat platforms (spoofed links, mentions, HTML)
grep -rnE 'parse_mode|mrkdwn|link_names|<@|@channel|AdaptiveCard|contentType|html' --include='*.py' notify/providers/{telegram,slack,teams,zoom,dialpad}/ | head -20

# 8. Dynamic import in the factory: provider name → module import
sed -n '1,120p' notify/notify.py

# 9. Shell / eval / sync HTTP in async paths
grep -rnE 'subprocess|os\.system|shell\s*=\s*True|\beval\(|\bexec\(|yaml\.load\(' --include='*.py' --include='*.pyx' notify/
grep -rnE '^\s*(import requests|from requests|import httpx)' --include='*.py' notify/
```

Rate each by whether **caller-, recipient- or network-controlled data can reach
it**:

- [ ] `cloudpickle.loads` on a task read from Redis → **CRITICAL** if the Redis
      instance is reachable by anything other than trusted enqueuers (no auth,
      no TLS, shared instance, default `localhost` exposed in a container
      network). Anyone who can `XADD` to the stream gets code execution in the
      worker, with every provider credential it holds. Report the concrete
      trust boundary you found (`NOTIFY_REDIS` default, auth, ACLs); if it
      cannot be established, report it as **HIGH — unverified boundary**.
- [ ] Caller-supplied template **source** compiled with a non-sandboxed
      `Environment` (`from_string` in `ProviderBase._prepare_` /
      `TemplateParser`) → **HIGH** if a downstream caller can pass end-user
      text as `template=` (Jinja2 SSTI → attribute traversal to code
      execution); **MEDIUM** if the API contract restricts it to developer
      input but does not document that. `SandboxedEnvironment` is the fix.
- [ ] `autoescape` off (the `JinjaConfig` default) while rendering HTML email /
      Teams / Slack bodies from user-supplied variables → **MEDIUM** (HTML and
      link injection into messages sent from a trusted sender).
- [ ] Subject, recipient or display name placed in a header without CR/LF
      rejection → **HIGH** (header injection: added `Bcc:`, spoofed
      `Reply-To:`). `email.message.EmailMessage` with the default policy raises
      on newlines; hand-built headers or `compat32` policy do not — check which
      is used.
- [ ] Attachment path accepted from the caller and read without restriction →
      **HIGH** when the path can come from end-user input (arbitrary file read
      exfiltrated by email); **LOW** when documented as developer-only.
- [ ] TLS verification disabled, or SMTP credentials sent before STARTTLS / on a
      plaintext connection by default → **HIGH**.
- [ ] Credential-bearing request sent to a URL assembled from caller input
      (webhook/base URL override) → **HIGH** (token exfiltration / SSRF).
- [ ] Chat markup (`parse_mode=HTML`, Slack `mrkdwn`, Adaptive Card JSON)
      interpolated from user input without escaping → **MEDIUM** (phishing
      links and mention spam under the bot's identity).
- [ ] `Notify("<name>")` importing `notify.providers.<name>` where `<name>` can
      contain dots or come from untrusted input → **MEDIUM** (import of an
      unintended module).
- [ ] Credentials in logs or exception text (Phase 2 grep) → **HIGH**.
- [ ] `requests` / `httpx` / blocking SDK called inside a coroutine instead of
      `blocking = 'executor'` → **LOW** (convention violation and event-loop
      stall — an availability issue, not a confidentiality one).

**Do not report a grep hit as a finding.** Read the call site and state the
concrete path from untrusted input to the sink, or drop it. Where the answer
depends on how downstream services call the library, say so and grade on the
documented contract.

**Score**: no reachable sink → +25 · reachable but mitigated → +15 · one
reachable unmitigated → +5 · several → 0

---

## Phase 5 — CI and release supply chain

`release.yml` fires on `release: [created]`, builds wheels with
`pypa/cibuildwheel` (running `CIBW_BEFORE_ALL_LINUX` as root in the build
container) and uploads them with `twine` using the long-lived
`ASYNC_NOTIFY_PYPI_API_TOKEN` secret. Anything that can create a release, or
inject a step into that workflow, can publish `async-notify` to PyPI.

```bash
ls .github/workflows/
# Actions pinned to a tag vs a SHA — a moved tag is remote code in your release
grep -rnE 'uses:\s*[^@]+@' .github/workflows/ | grep -vE '@[0-9a-f]{40}' | head -30
# Elevated permissions
grep -rn -B3 -A3 'permissions:' .github/workflows/
# Secrets referenced
grep -rnE 'secrets\.[A-Z_]+' .github/workflows/
# Triggers that run on untrusted PR content with write access
grep -rn 'pull_request_target\|workflow_run' .github/workflows/
# Build-container commands and environment metadata
grep -rnE 'CIBW_BEFORE_|environment:|url:' .github/workflows/release.yml
```

- [ ] `pull_request_target` combined with a checkout of the PR head? →
      **CRITICAL** (fork code runs with repo secrets)
- [ ] PyPI upload via a long-lived API token secret while the job already has
      `id-token: write`? → **MEDIUM** — migrate to PyPI trusted publishing
      (`pypa/gh-action-pypi-publish`) and delete the token; a token leaked from
      any workflow step publishes forever
- [ ] Third-party action pinned to a **tag** rather than a full SHA? →
      **MEDIUM** (`actions/*`, `pypa/*` and `astral-sh/*` are well-known
      publishers but still mutable tags; anything else is **HIGH**)
- [ ] `permissions:` broader than the job needs (e.g. `id-token: write` granted
      but unused)? → **LOW**
- [ ] `environment.url` pointing at a different project? → **LOW**
      (misleading deployment record; check it names `async-notify`)
- [ ] Branch protection on `main` (CLAUDE.md: PRs + passing CI; not configured
      declaratively — verify and report):
      ```bash
      gh api repos/:owner/:repo/branches/main/protection 2>&1 | head -30
      gh api repos/:owner/:repo/rulesets 2>&1 | head -20
      ```
      Unprotected `main` on a repo that publishes to PyPI → **HIGH**; PRs
      required but 0 approvals, no required status checks, admins not enforced
      → **MEDIUM** (note each gap)
- [ ] Who can create releases (repo admins/maintainers) and whether release
      creation is restricted by a tag ruleset → report as context
- [ ] CodeQL (`codeql-analysis.yml`) still running and green?
      ```bash
      gh run list --workflow=codeql-analysis.yml --limit 3
      ```

**Score**: all clean → +15 · minor gaps → +8 · CRITICAL trigger or unprotected
publishing branch → 0

---

## Phase 6 — Score and report

Total out of 100 (20 config + 20 secrets + 20 deps + 25 notification surface + 15 CI):

| Score | Posture |
|---|---|
| 90–100 | Strong |
| 70–89 | Good, gaps to close |
| 50–69 | Needs work |
| < 50 | At risk — stop feature work and remediate |

Write to `artifacts/logs/security-audit-<date>.md`:

```markdown
# Security Audit — async-notify

Date: <ISO>   Branch: <branch>   Commit: <sha>   Version: <notify/version.py>
Score: <N>/100 — <posture>

## Findings by severity
### CRITICAL
- **<title>** — `<file>:<line>`
  - Path from untrusted input: <concrete chain, e.g. Redis XADD → server.py loads → task()>
  - Impact: <what an attacker gets — code execution, credential theft, spoofed mail>
  - Fix: <exact change>

### HIGH / MEDIUM / LOW
  (same shape)

## Provider credential map
| Provider | Credential | Source | At-rest location | Notes |
|---|---|---|---|---|

## Phase scores
| Phase | Score | Notes |
|---|---|---|
| Config | /20 | |
| Secrets & credentials | /20 | |
| Dependencies | /20 | |
| Notification surface | /25 | |
| CI & release | /15 | |

## Verified clean
- <checks that passed — the coverage signal>

## Remediation plan
1. <highest severity × lowest effort first, with the command or code change>

## Not covered
- <what this audit did not reach, and why — e.g. live provider configs, deployed Redis ACLs>
```

---

## Rules

- **Never** paste a discovered secret, token or webhook URL into the report —
  reference `file:line` and its shape (`xoxb-…`, 57 chars).
- Every finding needs a **concrete failure path**, not a pattern match.
  "`from_string` appears in `base.py`" is not a finding; "a `template=`
  argument passed through `Notify(...).send()` reaches a non-sandboxed
  `from_string` in `ProviderBase._prepare_`" is.
- Distinguish **reachable** from **present**, and say which you established.
  For library APIs, state which caller behavior makes it reachable.
- If a scanner is missing (`pip-audit`), report the phase as **not covered**
  rather than as passing.
- Do not send test messages, authenticate against providers, or connect to
  Redis while auditing — static analysis only unless the user asks.
- Read-only by default. `--fix` is not supported here — remediation in this
  scope needs human judgment.

## Related

| Command | Scope |
|---|---|
| `/security-audit` | Full repository (THIS) |
| `/security-check` | Claude Code config only, ~60s |
| `/security-review` | Built-in review of the current branch diff |
| `/code-review` | Correctness and quality, not security posture |

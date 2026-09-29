---
kind: inline
jira_key: null
fetched_at: 2026-09-29T00:00:00Z
summary_oneline: "async-notify importa todos los providers al arranque; hacer lazy-import para reducir el startup cost"
---

# Source (inline, verbatim)

> lazy-import-providers -- async-notify carga al arranque todos los providers de
> comunicación, estén instaladas sus dependencias o no, hay que hacer un
> lazy-import para reducir el startup cost de notify

## Initial signals (extracted, not interpreted)

- Verbs: "carga al arranque" (loads at startup), "hay que hacer" (must do) → enhancement, not a bug report
- Named entities: `notify`, "providers de comunicación", "lazy-import", "startup cost"
- Claim asserted by requester: all providers are imported at startup regardless of whether their
  third-party dependencies are installed
- Acceptance criteria provided: no

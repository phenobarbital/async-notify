<!--
  sdd/templates/design_research.prompt.md — neutral design-research brief (FEAT-545).
  Rendered by /sdd-spec section 3b and piped to `codex exec ... --output-schema
  design_research.schema.json`.
  FORBIDDEN INPUTS: never paste the spec draft, the spec author's reasoning, a preferred
  conclusion, or any text written by the model that will author the spec. The brief carries
  ONLY the accepted exploration document (brainstorm/proposal) and verified code anchors.
  Placeholders (double-curly-brace tokens, deliberately NOT written with literal braces in
  this comment — a renderer that does a naive whole-document string replace must not also
  rewrite this sentence): problem_statement, constraints_and_goals,
  recommended_option_or_scope, code_context_paths, open_questions, question.
-->
# Independent design review — read-only

You are an independent design reviewer for **async-notify**, an asyncio-based
Python library for sending notifications across a uniform provider interface
(email, IM, SMS, push), managed with `uv`. You have read-only access to the
repository in your working directory.

## Rules
1. Read the code you cite. Every `affected_paths` entry must be a repo-relative
   path you actually opened; suggestions with unverifiable paths are discarded.
2. Judge the design intent below against what exists in the repository: what is
   missing, what is risky, what would be simpler, what the codebase already
   provides that the intent re-invents.
3. Do not restate the intent, do not praise it, do not write code. Propose at
   most 12 concrete, falsifiable suggestions, each tagged with a kind
   (`architecture` | `api` | `testing` | `risk` | `alternative`), a risk level and
   your confidence.
4. Output exactly ONE JSON object conforming to the schema you were given — no
   markdown fences, no prose before or after.

## Accepted design intent (verbatim from the exploration document)

### Problem statement
> lazy-import-providers -- async-notify carga al arranque todos los providers de
> comunicación, estén instaladas sus dependencias o no, hay que hacer un
> lazy-import para reducir el startup cost de notify

La premisa no se sostiene: **los providers ya se importan de forma perezosa**.
`LoadProvider` (`notify/notify.py:70-86`) los resuelve con
`importlib.import_module` en el momento de la llamada y los memoiza en
`PROVIDERS`; `notify/providers/__init__.py` es solo un docstring y ningún módulo
de `notify/` importa un provider concreto. Lo que sí es real es el coste medido
de `import notify` — **192 ms**, de los cuales **~122 ms son navconfig** y
**~69 ms datamodel+jinja2**, arrastrados por `notify/providers/base.py`, no por
los providers. Tras el Q&A el feature se re-apunta: los dos objetivos primarios
pasan a ser (a) un **diagnóstico accionable** cuando falta un SDK opcional —hoy
un SDK ausente se reporta como `"No Provider telegram was Found"`, indistinguible
de un nombre mal escrito y sin nombrar el extra— y (b) **adelgazar las
dependencias core** de `pyproject.toml`, donde `pillow` figura sin que ningún
módulo lo importe. Los deferrals de import (`Actor` vía `TYPE_CHECKING`,
`is_template_source` fuera del módulo que importa jinja2) quedan como beneficio
secundario acotado: ~192 → ~123 ms.

### Constraints and goals
- **La factory ya es perezosa.** `LoadProvider` usa `importlib.import_module` y
  memoiza en `PROVIDERS`; `Notify.__new__` y `Notify.provider()` pasan ambos por
  ella. *Implicación*: un feature de "lazy provider import" no tiene trabajo
  pendiente en esa capa; debe re-apuntarse o no entrega nada medible.
  *Evidence*: F002, F004

- **No existe fan-out eager que eliminar.** `notify/providers/__init__.py` es un
  docstring; los 21 imports relacionados con providers apuntan *hacia arriba*
  (base/mail/_mime_utils). *Implicación*: la premisa del solicitante no se
  cumple tal como está formulada. *Evidence*: F001, F003, F004

- **Superficie pública mínima.** `__all__ = ("Notify", "ProviderType")`; los
  tests importan providers por ruta completa, nunca por re-export del paquete.
  *Implicación*: añadir pereza PEP 562 en la raíz es retrocompatible y no puede
  romper la suite actual. *Evidence*: F010

- **`filterwarnings = ["error", …]`** en `pyproject.toml`. *Implicación*:
  cualquier `DeprecationWarning` emitido por un shim de compatibilidad tumba la
  suite entera; los shims deben ser silenciosos. *Evidence*: F010

- **Los SDKs de provider ya son extras, pero el README no documenta ninguno.**
  *Implicación*: la historia de instalación está a medias — los extras existen
  pero son indescubribles, y por eso el error de SDK ausente es inaccionable.
  *Evidence*: F007, F012

- **Ya existe el idioma correcto in-tree.** `Telegram.py:343-347` y
  `notify/utils/uv.py:14` modelan "import diferido + nombra el extra" y
  "dependencia opcional con guard silencioso". *Implicación*: seguir el idioma
  existente, no inventar uno nuevo. *Evidence*: F008

- **`notify.exceptions` y `notify/types/typedefs` son módulos Cython.**
  *Implicación*: el worktree necesita `python setup.py build_ext --inplace`
  antes de los tests, y las mediciones de import deben tomarse contra las
  extensiones compiladas. *Evidence*: F005

### Recommended option / probable scope
### Medición de partida (F005)

| preloaded | `import notify` marginal | atribuible |
|---|---:|---:|
| nada | **192 ms** | — |
| `navconfig` | 70.4 ms | **~122 ms (63%)** |
| `datamodel` + `jinja2` | 122.8 ms | **~69 ms (36%)** |
| los tres | 35.1 ms | ~157 ms (82%) |

`notify.providers.base`: 214 ms acumulados, **21 ms de self time**.

### What's New

- **Módulo sin jinja2 para `is_template_source`** (p.ej. `notify/templates/_predicates.py`
  o dentro de `notify/utils/`), re-exportado desde `notify.templates` por
  compatibilidad. *Evidence*: F006
- **Ruta de error consciente de extras en `LoadProvider`**, que distinga
  "provider desconocido" de "falta la dependencia opcional del provider" y
  nombre el extra a instalar. *Evidence*: F008
- **Mapeo `PROVIDER_EXTRAS`** (nombre de provider → nombre de extra) que
  alimente ese mensaje. *Evidence*: F007, F008
- **Test de regresión de arranque** que afirme que `import notify` deja jinja2 y
  datamodel fuera de `sys.modules`. *Evidence*: F010
- **Sección del README** con la matriz de extras. *Evidence*: F012

### What Changes

- **`notify/providers/base.py`::module imports** — `Actor` detrás de
  `TYPE_CHECKING` (uso solo en anotaciones) e `is_template_source` movido a un
  módulo sin jinja2 o a un import local de función. *Evidence*: F006
- **`notify/notify.py`::module imports** — diferir `from .conf import TEMPLATE_DIR`
  y `from .templates import TemplateParser` dentro de `__getattr__`, su único
  consumidor. *Evidence*: F002, F005
- **`notify/notify.py`::`LoadProvider`** — corregir el fallback `__import__`
  muerto que devuelve el módulo en vez de la clase, y emitir el mensaje
  consciente de extras. *Evidence*: F008
- **`pyproject.toml`::`[project] dependencies`** — bajar `emoji` (solo telegram),
  `aiobotocore` (solo ses) y `cloudpickle` (solo server) a sus extras, y
  **eliminar `pillow`**, que ningún módulo de `notify/` importa. Se acepta como
  cambio de instalación con release notes. *Evidence*: F007
- **`README.md`** — documentar la matriz de extras. *Evidence*: F012

### What's Untouched (Non-Goals)

- Hacer perezosos los `notify/providers/*` — **ya lo son** (F002, F004).
- Construir un registry de providers, plugin discovery o entry-points.
- Cambiar el contrato `ProviderBase` / `_send_` ni el comportamiento en runtime
  de ningún provider.
- **Atacar navconfig / hacer perezoso `notify/conf.py`** — decisión explícita del
  Q&A (U2): fuera de este ciclo.
- Reducir el peso de instalación del extra `all`.

### Patterns to Follow

- `__getattr__` a nivel de módulo (PEP 562) con slot privado de memoización,
  como en `notify/notify.py:89-116`. *Evidence*: F002
- Import diferido + mensaje accionable `pip install async-notify[<extra>]`, como
  en `Telegram.py:343-347`. *Evidence*: F008
- Dependencia opcional con guard `ImportError` silencioso, como en
  `notify/utils/uv.py:14`. *Evidence*: F008

### Integration Risks

- **Diferir navconfig es la única vía al premio grande (~122 de 192 ms), pero
  `notify/conf.py` exporta ~20 constantes de módulo consumidas por el server y
  los providers.** *Mitigación*: queda explícitamente fuera de alcance (U2); si
  se reabre, con su propia medición. *Evidence*: F005
- **`TYPE_CHECKING` sobre `Actor` cambia la resolución de anotaciones en
  runtime**; algo que llame a `typing.get_type_hints()` sobre métodos de
  `ProviderBase` se rompería. *Mitigación*: añadir
  `from __future__ import annotations` y hacer grep de `get_type_hints` antes de
  aterrizar. *Evidence*: F006, F010
- **`filterwarnings=error`**: un shim de compatibilidad que avise tumba CI.
  *Mitigación*: re-exportar sin warnings de deprecación. *Evidence*: F010
- **Bajar deps core es un cambio de instalación potencialmente breaking** para
  quien instale `async-notify` pelado y use ses o telegram. *Mitigación*:
  aceptado con release notes (U3); el nuevo mensaje de `LoadProvider` convierte
  el fallo en accionable, lo que hace este riesgo mucho más tolerable.
  *Evidence*: F007, F008

### Verified code anchors (paths only — open them yourself)
notify/__init__.py
notify/notify.py
notify/providers/base.py
notify/templates.py
notify/conf.py
pyproject.toml
notify/providers/telegram/Telegram.py
notify/server/wrapper.py

### Questions still open in the exploration document
- [ ] **¿`PROVIDER_EXTRAS` se mantiene a mano o se deriva de
  `[project.optional-dependencies]`?** — *Owner*: tbd
  *Respuestas plausibles*: a) dict literal en `notify/notify.py` (simple, puede
  desincronizarse) · b) leído de la metadata del paquete instalado vía
  `importlib.metadata` (sin desincronización, coste en runtime)
  *Nota*: varios providers (twilio, xmpp, slack) hoy no tienen extra propio —
  solo aparecen dentro de `all`/`default` (F007), así que el mapeo obliga a
  decidir si se crean extras por provider.

## Question
Given this accepted design intent and these verified code anchors, how would you build it? What is missing, risky, or better done another way?

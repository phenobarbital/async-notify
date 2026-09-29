---
id: FEAT-005
title: "Los providers ya son lazy — el coste real está en deps core mal clasificadas y en un diagnóstico ciego de dependencia faltante"
slug: lazy-import-providers
type: feature
mode: enrichment
status: review
source:
  kind: inline
  jira_key: null
  jira_url: null
  fetched_at: 2026-09-29
  summary_oneline: "async-notify importa todos los providers al arranque; hacer lazy-import para reducir el startup cost"
overall_confidence: high
base_branch: dev
research_state: sdd/state/FEAT-005/
created: 2026-09-29
updated: 2026-09-29
---

# FEAT-005 — Los providers ya son lazy: re-apuntar a diagnóstico de dependencias y peso de instalación

> **Mode**: enrichment
> **Confidence**: high
> **Source**: `inline`
> **Audit**: [`sdd/state/FEAT-005/`](../state/FEAT-005/)

---

## 0. Origin

> lazy-import-providers -- async-notify carga al arranque todos los providers de
> comunicación, estén instaladas sus dependencias o no, hay que hacer un
> lazy-import para reducir el startup cost de notify

**Initial signals** (extracted, not interpreted):
- Verbs: "carga al arranque", "hay que hacer" → enhancement, no bug report
- Named entities: `notify`, providers, lazy-import, startup cost
- Claim asserted: todos los providers se importan al arranque, con deps instaladas o no
- Acceptance criteria provided: no

---

## 1. Synthesis Summary

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

---

## 2. Codebase Findings

> Todas las entradas están fundadas en los digests de
> `sdd/state/FEAT-005/findings/`. Cada una cita el/los finding IDs que la
> justifican. **Sin rutas ni símbolos inventados.**

### 2.1 Localization

| # | Path | Symbol | Lines | Role | Evidence |
|---|------|--------|-------|------|----------|
| 1 | `notify/__init__.py` | module body | 6-16 | entrypoint: importa `providers.base`, `Notify`, `install_uvloop` — ningún provider concreto | F001 |
| 2 | `notify/notify.py` | `LoadProvider` | 70-86 | resolución perezosa ya existente **y** el diagnóstico defectuoso de dependencia faltante | F002, F008 |
| 3 | `notify/notify.py` | module imports | 1-10 | importa `.conf` (navconfig) y `.templates` (jinja2) para símbolos usados solo dentro de `__getattr__` | F002, F005 |
| 4 | `notify/notify.py` | `__getattr__` | 89-116 | precedente PEP 562 de deferral en este mismo módulo | F002 |
| 5 | `notify/providers/base.py` | module imports | 12-19 | **el nodo caliente**: arrastra navconfig, `notify.models` (datamodel) y `notify.templates` (jinja2) | F005, F006 |
| 6 | `notify/providers/base.py` | usos de `Actor` | 119,169,189,210,228,265 | todos son anotaciones de tipo — eliminables con `TYPE_CHECKING` | F006 |
| 7 | `notify/providers/base.py` | `_prepare_` | 155 | única llamada a `is_template_source`, razón por la que jinja2 está en el arranque | F006, F011 |
| 8 | `notify/templates.py` | `is_template_source` | 95-107 | predicado puro de string, sin dependencia de jinja2, atrapado en un módulo que sí la importa | F006 |
| 9 | `notify/conf.py` | module body | 1-10 | evalúa navconfig en tiempo de import para `TEMPLATE_DIR` y ~20 constantes más | F005 |
| 10 | `pyproject.toml` | `[project] dependencies` | 36-45 | deps core con cuatro paquetes provider-only / server-only | F007 |
| 11 | `notify/providers/telegram/Telegram.py` | guard de conversión de vídeo | 343-347 | **precedente in-tree**: import diferido + mensaje que nombra el extra | F008 |
| 12 | `notify/server/wrapper.py` | instanciación de provider | 71,83 | el server también pasa por la factory perezosa — no hay segunda superficie eager | F009 |

### 2.2 Constraints Discovered

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

### 2.3 Recent History (Relevant)

| Commit | Message | Relevance |
|--------|---------|-----------|
| `b842186` | feat(templateparser-refactor): TASK-010 — lazy TemplateEnv singleton via PEP 562 | establece el idioma de deferral que este feature extiende |
| `64d3916` | fix: make uvloop optional and build Windows wheels | establece el idioma de dependencia opcional con guard |
| `1ea979a` | feat(jinja-string-notify): TASK-015 — three-way `template=` dispatch en `ProviderBase._prepare_` | introdujo la llamada a `is_template_source` que puso jinja2 en la ruta de arranque |

*Evidence*: F011

---

## 3. Probable Scope

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

---

## 4. Confidence Map

| ID | Claim | Evidence | Confidence | Reasoning |
|----|-------|----------|------------|-----------|
| C1 | `notify/__init__.py` no importa ningún provider concreto; el `__init__` de providers es un docstring vacío | F001, F003 | high | lectura directa de ambos ficheros |
| C2 | La factory ya importa providers de forma perezosa vía `importlib.import_module` y los memoiza en `PROVIDERS` | F002 | high | lectura directa de `LoadProvider` y ambos entry points |
| C3 | Ningún módulo de `notify/` importa un provider concreto; los 21 imports apuntan hacia arriba a base/mail/_mime_utils | F004, F009 | high | grep exhaustivo sobre `notify/` incluido el paquete server |
| C4 | `import notify` cuesta ~192 ms, estable en 5 ejecuciones (190.0-193.8) | F005 | high | medición directa |
| C5 | ~122 ms son navconfig y ~69 ms datamodel+jinja2; `notify.providers.base` tiene solo 21 ms de self time | F005 | high | atribución por precarga + split self/cumulative de `-X importtime` |
| C6 | La arista datamodel de base.py es solo de anotaciones (`Actor`) y la de jinja2 es una llamada a un predicado puro (`is_template_source`) | F006 | high | leída cada referencia a `Actor`; cuerpo de `is_template_source` confirmado sin jinja2 |
| C7 | Un SDK opcional ausente aparece como "No Provider `<x>` was Found", confundido con provider desconocido y sin nombrar el extra | F008 | high | sonda ejecutada bloqueando `aiogram` vía `sys.meta_path`; cadena de excepciones capturada |
| C8 | El fallback `except ImportError` de `LoadProvider` reimporta el mismo classpath fallido y, si tuviera éxito, devolvería el módulo en vez de la clase | F008 | high | lectura directa; el valor de retorno difiere en tipo del camino feliz |
| C9 | `pillow` es dependencia core pero ningún módulo de `notify/` importa PIL | F007 | high | grep de PIL devuelve solo hits no relacionados de `activityImage` en models.py |
| C10 | `emoji`, `aiobotocore` y `cloudpickle` son deps core usadas por exactamente un provider o solo por el server | F007 | high | grep localizó cada una en un único consumidor |
| C11 | Bajar esos cuatro paquetes cambia el peso de instalación, no el tiempo de `import notify`, porque ninguno es alcanzable desde el entrypoint | F001, F005, F007 | high | se sigue de C1 y del árbol de import medido, que no contiene ninguno |
| C12 | La superficie pública es `__all__ = ("Notify","ProviderType")` y los tests importan por ruta completa, así que la pereza a nivel de paquete es retrocompatible | F010 | high | lectura de `__all__` + grep sobre los 7 ficheros de test |
| C13 | Diferir datamodel+jinja2 de base.py debería llevar `import notify` de ~192 ms a ~123 ms | F005, F006 | medium | aritmética sobre la atribución por precarga; **no verificado contra un build parcheado**, y el solape de árboles podría desplazarlo |
| C14 | Diferir también navconfig podría acercarse al suelo marginal de ~35 ms | F005 | low | los 35 ms son el coste marginal con los tres precargados: una cota inferior, no un objetivo alcanzable; las ~20 constantes de conf.py pueden hacer impracticable el deferral total |
| C15 | Este trabajo continúa una dirección ya establecida in-tree (TemplateEnv PEP 562, uvloop opcional) en vez de introducir un patrón nuevo | F011, F008 | high | dos commits on-theme en 120 días + dos guards existentes |
| C16 | El README no documenta ningún extra, lo que deja el error de SDK ausente inaccionable incluso tras mejorar el mensaje | F012 | high | grep de keywords de instalación: cero coincidencias |

Distribución: **14** high, **1** medium, **1** low.

> La única claim `low` (C14) sostiene un no-goal explícito, no la conclusión.
> La `medium` (C13) sostiene el beneficio *secundario*. Los objetivos primarios
> —diagnóstico y peso de instalación— descansan sobre claims `high` (C7-C11, C16).

---

## 5. Open Questions

### Resolved (during proposal phase)

- [x] **La premisa no se sostiene: los providers ya son lazy. ¿Cuál era el
  síntoma real?** — *Resuelto*: «Error confuso sin SDK» + «Peso de instalación».
  El import lento **no** era el dolor; pasa a beneficio secundario.
  *Resuelve claims*: C2, C7

- [x] **¿Hay objetivo concreto de tiempo para `import notify`?** — *Resuelto*:
  ~123 ms mediante los deferrals acotados (datamodel+jinja2 fuera de base.py).
  No se ataca navconfig en este ciclo.
  *Resuelve claims*: C13, C14

- [x] **¿Se pueden sacar emoji/aiobotocore/pillow/cloudpickle de las deps core?**
  — *Resuelto*: sí, con release notes. `pillow` se elimina directamente.
  *Resuelve claims*: C10, C11

### Unresolved (defer to spec / implementation)

- [ ] **¿`PROVIDER_EXTRAS` se mantiene a mano o se deriva de
  `[project.optional-dependencies]`?** — *Owner*: tbd
  *Respuestas plausibles*: a) dict literal en `notify/notify.py` (simple, puede
  desincronizarse) · b) leído de la metadata del paquete instalado vía
  `importlib.metadata` (sin desincronización, coste en runtime)
  *Nota*: varios providers (twilio, xmpp, slack) hoy no tienen extra propio —
  solo aparecen dentro de `all`/`default` (F007), así que el mapeo obliga a
  decidir si se crean extras por provider.

---

## 6. Recommended Next Step

**`/sdd-spec FEAT-005`** — *Rationale*: los tres desconocidos están resueltos y
la localización es de alta confianza y **medida**. El spec debe re-apuntar
explícitamente el feature respecto al título original: el objetivo primario pasa
a ser el diagnóstico accionable de dependencia faltante y el adelgazamiento de
las deps core; los deferrals de import quedan como beneficio secundario acotado
(~192 → ~123 ms), y navconfig queda fuera de alcance.

---

## 7. Research Audit

| Artefacto | Ruta |
|---|---|
| Fuente cruda | `sdd/state/FEAT-005/source.md` |
| Plan de investigación | `sdd/state/FEAT-005/research_plan.json` (18 queries, schema-valid) |
| Findings | `sdd/state/FEAT-005/findings/F001…F012` |
| Síntesis | `sdd/state/FEAT-005/synthesis.json` (lint: passed, 0 iteraciones) |
| Estado | `sdd/state/FEAT-005/state.json` (schema-valid) |

Presupuesto consumido: **12/40** ficheros · **11/25** greps · **1/10** git —
completo, sin truncar. Wiki disponible (906 páginas, 0 stale).

Mediciones tomadas en esta máquina (Python 3.11, caché de FS caliente) con
`python -X importtime` y `time.perf_counter()`; la sonda de dependencia ausente
se ejecutó bloqueando `aiogram` con un finder en `sys.meta_path`.

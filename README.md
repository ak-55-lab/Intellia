# Intellia

A Streamlit application that demonstrates the future **Intellia Enterprise AI Assistant**
as a workspace rather than a dashboard: a left rail, a canvas, and a conversation, with
the AI layer sitting on top of enterprise work instead of bolted to the side of it.

The user moves **Understand → Decide → Act → Analyse** on one canvas, and any question
they ask turns that canvas into a thread:

```
                    ┌─ Daily brief ──────────────────────────┐
New chat / My day ──┤  Today (meetings + actions, one card)  ├── Insights
        │           └────────────────────────────────────────┘      │
        │                       ↑ prep, recap, execute              ↑ create with AI
        └── ask anything ──► conversation ──► pin the answer back ──┘
```

Two personas ship for the demo, **Elena Benson** (Senior AE) and **James Clark**
(Sales Manager), and the architecture supports more without code changes.

---

## Quick start

```bash
cd App
pip3 install --user -r requirements.txt
python3 -m streamlit run app.py
```

Run it **from `App/`** so Streamlit picks up `App/.streamlit/config.toml`.

The app runs fully **without an API key** in deterministic mode. To enable live
Claude generation, put a key in `.env` at the repo root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

With a key present the first paint takes a few seconds while the brief generates. The
card chrome and a skeleton appear immediately, so the page is never blank while waiting.

Regenerate the seed data (deterministic, safe to re-run):

```bash
python3 Data/generate_dummy_data.py            # write CSVs
python3 Data/generate_dummy_data.py --dry-run  # invariant report only
```

Run the tests (they must pass with no key, and with `anthropic` uninstalled):

```bash
cd App && python3 -m pytest tests/ -q
```

`Data/app_state.db` holds layouts, insight versions and the LLM cache. Deleting it
resets the canvas to defaults; it rebuilds on the next run.

---

## The shell

| Surface | What it is |
|---|---|
| **New chat** | The daily canvas. A conversation starts from what you are looking at, so home and new-thread are the same destination. |
| **Portfolio** | Every account in the book as one Customer 360 table: search, sort on any column, filter by segment, region or risk. |
| **Skills** | One row per task the AI service can actually run, and what it falls back to without a key. |
| **Digests** | Scheduled briefings. Delivery is mocked. |
| **Apps** | The connector protocols in `data/connectors/base.py`, shown as connected systems. |
| **Search + chats** | Threads, searchable. A query with no match offers to ask it instead. |
| **Product updates** | Release notes. |
| **Profile** | Settings: profile, persona switch, assistant mode, data. |

**Compose** is a single strip above the canvas: icons with tooltips, and picking one
opens that group's components as tiles. A lit tile is on the canvas. Insights group by
department (`WidgetSpec.department`), of which Sales is the only one seeded. The Layout
group adds your own section titles and text notes, which are widgets like any other.

**Every card carries the same control strip** in its corner, as icons rather than a
dropdown: ⓘ definition, edit with AI, chart/table, width, move up, move down, remove.
Streamlit has no drag-and-drop, so ordering is arrows and width is a toggle, both saved
per persona in the layout table.

The strip renders **outside** the card's fragment, and that is load bearing: a widget
inside a fragment only reruns that fragment, so a button in there sets a dialog intent
that the dispatcher never sees. That was the reason edit-with-AI appeared to do nothing.

---

## The five ideas the architecture is built around

### 1. Insights become deterministic after one AI call

```
NL question → LLM → SQL → validate → describe → execute → pick viz → save config
                                                                          │
   every later render, filter change and page load ────────────────────────┘
                                    replays the saved SQL, with NO model call
```

`InsightConfig` persists the natural-language definition, the generated SQL, a schema
fingerprint, result-column roles, the visualization spec, filters and metadata. This is
enforced structurally, and there is a test for it: rendering with a provider that
*raises on every call* still succeeds for every insight.

**All built-in analytics widgets are seeded `InsightConfig` rows, not bespoke Python.**
Built-ins and user-created insights therefore travel exactly one code path and get
filters, versioning, the ⓘ panel and Edit-with-AI for free.

A builtin still on version 1 is the shipped definition, so a code change to its copy or
SQL is re-seeded onto the canvas. The moment a user edits it, `head_version` moves past 1
and re-seeding leaves it alone: their version wins over ours.

### 2. The model never computes a number and never invents an entity

Each service splits deterministic assembly from generation:

| Service | Deterministic | LLM |
|---|---|---|
| `metrics_service` | 100%, semantic-layer SQL | none |
| `context_service` | 100%, evidence bundle + `context_hash` | none |
| `action_service` | 100%, 5 sources, dedupe, weighted ranking | on demand only |
| `daily_brief` | candidate assembly + **reference validation** | ranking and prose |
| `meeting_prep` | context bundle | narrative fields |
| `ask_service` | evidence bundle + computed metrics + the rows a query returned | prose and follow-ups |

The brief validates every `ref_id` the model emits against the evidence set and **drops
anything invented** before render. That is what makes the deterministic fallback
acceptable: a mock brief still names real accounts, deals and tasks.

Word limits are part of the contract, not a rendering afterthought. Every prompt states
them explicitly (`summary` is one sentence under 24 words, brief items are one clause
under 16), and the render path truncates as a safety net rather than as the mechanism.

### 3. The model tier is a property of the task

Interactive work runs on the fast tier and the flagship is reserved for the two tasks
whose judgement is the product:

| Task | Tier | Why |
|---|---|---|
| Daily brief, meeting prep | `claude-opus-5` | ranking and judgement over the whole day |
| Ask, text to SQL, action explain, email draft | `claude-sonnet-5` | the user is waiting, and the output is prose over rows that are already computed |

`TaskSpec.model` carries it, so the choice sits next to the prompt it applies to. The
cache key already includes the resolved model, so the tiers never share an entry, and
every surface labels the model that actually produced what you are reading.

### 4. Detail opens over the canvas, provenance opens beside it

Prep, recap and action detail are **medium dialogs**: wide enough for two columns, small
enough that the canvas stays visible around them. Widget provenance is different: it is
already computed, so it opens in a **popover beside its own ⓘ** rather than taking over
the screen. No query runs and no model is called to fill it.

Every dialog passes `on_dismiss=session.clear_dialog`. With the default (`"ignore"`) the
intent survives dismissal and the dialog reopens on the next unrelated rerun, which is
exactly why escape and the close button appear not to work.

### 5. A conversation starts before the model answers

Asking a question queues it, switches the view and paints the question with a skeleton;
a `run_every` fragment does the model call on the next run and then drops the timer.

Answering in the same run is what made the switch feel broken: Streamlit only clears the
elements of the previous page when the run that replaces them finishes, so the entire
canvas sat on screen, greyed out, for the length of the call. There is a test for the
two-phase behaviour.

When the question is data shaped, **text to SQL runs first** and its rows are handed to
the answer prompt. The other order produced an answer saying "I only have totals"
directly above a chart of the breakdown: two calls looking at two different sets of
facts. The rows are computed once and both the prose and the chart read from them.

**Deciding that a question is data shaped fails open.** The router skips only what no
query can answer: greetings, requests to perform an action, and questions asking for
judgement. Everything else goes to the engine, which reads the semantic layer and writes
its own SQL, so it decides what it can express. This began as an allowlist of phrasings
(`by rep`, `by stage`, `by account`, `by industry`) and refused "give me customers ARR by
region" without the engine ever seeing it, because that dimension was never enumerated.
Erring permissive costs one call, cached on the question afterwards; erring strict tells
the reader the data is missing while it sits in the database.

**A follow-up is given the turn before it.** The previous answered turn's question, SQL
and chart type go into the generator prompt, so "flip this to a donut" has a referent and
modifies that query rather than inventing a subject. A question that names its own
subject ignores it. The prior turn is part of the cache key too: the wording of a
follow-up is identical across threads, so caching on wording alone would serve one
thread's chart to another.

**A chat is capped at five questions**, counted as answered turns plus the one in flight,
since a turn is only recorded once the model returns. The cap is enforced once, in
`on_ask`, because the rail, the follow-up chips and the composer all route through it;
the composer disables with the reason in its placeholder and the thread closes with a
**New chat** button. Pinned insights and the thread itself survive. The number is
`session.MAX_QUESTIONS_PER_THREAD`.

---

## Layout

```
App/
  app.py                   composition, the view router, the one dialog dispatcher
  .streamlit/config.toml   ~60% of the visual design is here, not in CSS
  tests/                   102 tests
  intellia/
    bootstrap.py           composition root (one @st.cache_resource)
    config/                settings, personas, constants
    data/                  schema.sql, schema_app.sql, loader, database
                           (RO + authorizer), scope, repositories/, connectors/
    models/                plain dataclasses only
    services/              metrics, context, action, daily_brief, meeting_prep, ask
    ai/                    provider protocol, claude, mock, cache, structured, prompts/
    insights/              engine, sql_validator, executor (sandbox), filters,
                           visualization_selector, store, widget_registry, builtins/
    actions/               executor protocol + mock executor + playbooks
    components/            sidebar, chrome, composer, panels, insights, chat, views,
                           dialogs, primitives
    theme/                 tokens (single source of truth), brand, charts
    state/                 typed session_state accessors
Data/                      generator, CSVs, intellia.db, app_state.db
Knowledge/                 brain.md, semantic_layer.md, text_to_sql_few_shots.md
```

### Two databases

`Data/intellia.db` is the analytics store, opened **strictly read-only**.
`Data/app_state.db` is writable: insight configs and versions, per-persona layout
(visibility, order and width), the user's own canvas blocks, action state and the LLM
cache. The split is what lets the analytics connection stay read-only.

Set `INTELLIA_APP_STATE_DB` to point the writable store somewhere else. The test suite
does exactly that, via an autouse fixture. It has to: the UI tests drive the real app and
one of them adds a heading block, so aimed at the shipped file every run left another
section title on the canvas, and layout visibility persisted the same way.

`schema_app.sql` is re-run on every start, but `CREATE TABLE IF NOT EXISTS` is a no-op on
an existing table, so a column added later needs an explicit migration
(`Database._migrate_app_state`) or an older app-state file keeps the old shape.

`ensure_built()` is idempotent: it sha256s each CSV and returns in ~1 ms when nothing
changed; otherwise it builds into a `.tmp` file, runs `PRAGMA foreign_key_check`, and
atomically `os.replace`s it, so a half-built database is never served.

---

## Security: the SQL sandbox

The model writes SQL, so five independent layers stand between it and the data.

1. **Lexical validator** strips comments *first* (so `-- ; DROP` cannot smuggle
   tokens), enforces a single `SELECT`/`WITH`, applies a word-boundary deny-list, and
   rejects `main.` / `temp.` / `sqlite_` qualifiers.
2. **Read-only connection**, `file:…?mode=ro` plus `PRAGMA query_only=ON`.
3. **sqlite3 authorizer**, the real boundary. Read-only mode alone still permits
   `ATTACH`. The authorizer allows only allowlisted `(table, column)` pairs, denies any
   read whose database is `main`, blocks `sqlite_master`, and restricts SQL functions to
   an allowlist.
4. **Execution limits**: a progress-handler deadline gives real timeouts, `LIMIT n+1`
   detects truncation, and `sqlite3` itself rejects multi-statement input.
5. **Plain-English errors**: a failing card degrades to an inline message. No traceback
   ever reaches the browser (`showErrorDetails = "none"`).

### Persona scoping

Scope is enforced by **temp-table shadowing**, not by string rewriting:

```sql
CREATE TEMP TABLE deals AS SELECT * FROM main.deals WHERE owner_id IN (?,?,…);
```

CTAS accepts bound parameters on a read-only connection, and SQLite resolves an
unqualified `deals` to the temp schema before `main`. So every repository query, every
built-in widget and every LLM-generated query is scoped automatically: persona never
appears in a SQL string, and generated SQL cannot leak another rep's pipeline even if
the model writes naive SQL. `users` and `targets` are scoped too, or a "pipeline by rep"
query would enumerate the whole company.

**Filters never call the LLM.** They wrap the saved SQL in a CTE and append a
parameterized predicate whose column must be one the engine itself reported, whose
operator comes from a closed enum, and whose values are always bound. A filter value of
`'; DROP TABLE deals --` simply matches nothing (there is a test).

---

## Extending it

**A new persona** is one dict entry in `config/personas.py`: id, user id, `scope_kind`
(`own_book` / `team` / `all`), a widget list and a `brief_variant` string. No code
changes; manager roll-up is widget selection, not branching logic.

**A new built-in insight** is one `_config(...)` entry in `insights/builtins/`. It is
seeded as an `InsightConfig` and picked up by the registry automatically.

**A new department** in the composer is a `department` value on `WidgetSpec`. The
grouping reads whatever is there.

**A real integration** replaces a connector in `bootstrap.py`. `data/connectors/base.py`
defines `CRMConnector`, `CalendarConnector`, `EmailConnector`, `SignalConnector` and
`TaskConnector` as Protocols returning `models.domain` dataclasses, which act as the
anti-corruption layer. A `SalesforceCRMConnector` or `MicrosoftGraphCalendarConnector`
is a drop-in; nothing above the connector changes.

**A real action** replaces `MockActionExecutor`. Every handler already carries the
target it would call (`Microsoft Graph · Outlook drafts`, `Salesforce · Opportunity`,
`Asana · Tasks`); only the side effect is mocked.

**A different model provider** implements the `LLMProvider` protocol in
`ai/llm_provider.py` and is swapped in `bootstrap.py`. `AIService` handles caching,
validation and the one repair round-trip above it, so a provider only has to turn an
`LLMRequest` into an `LLMResponse`.

---

## Conventions that will bite if ignored

* **Python 3.9 is the target.** `from __future__ import annotations` in every module;
  `Optional[X]` / `List[X]`, **never `X | Y`**. PEP 604 raises `TypeError` inside
  `get_type_hints`, which `ai/structured.py` calls at runtime; there is a test that
  fails on any such annotation.
* **The deck's numbers are asserted.** `Deck/Intellia_Deck.pptx` has no generator, so
  slide 4's test count and line count are checked against the real ones by tests. They
  drifted four times before that existed. If a change makes them fail, update the deck;
  do not relax the test.
* **Nothing calls `date.today()`.** Everything derives from `settings.REPORTING_DATE`
  (2026-08-13, matching the semantic layer) so the demo cannot rot. A test greps for
  violations outside `utils/dates.py`.
* **`st.error` / `st.warning` / `st.exception` are banned.** They render Streamlit's blue
  and yellow alert boxes and wreck the palette. `error_card` and `empty_state` are the
  only error surfaces.
* **`st.toast(icon=...)` takes a single character or a `:material/...:` shortcode.**
  A decorative glyph like `✦` raises `StreamlitAPIException` at runtime, on a code path
  a smoke test only reaches if it actually sets a notice.
* **A widget's number format comes from the column, never from the card.** A money
  insight that also returns "days in stage" rendered 21 days as `$21`. `infer_unit`
  reads the column; the card's unit does not get a vote.
* **`step=1` is what drops the trailing `.00`** in a dataframe column. Streamlit takes a
  float column's display precision from the step, not from the `format` preset, so
  `format="dollar"` alone gives `$292,000.00`.
* **Nothing may block the run that switches views.** Streamlit clears the previous
  page's elements only when the replacing run finishes, so a model call in that run
  leaves the whole old page on screen, greyed out, until it returns.
* **Anything that changes the view must be an `on_click` / `on_submit` callback.**
  Callbacks run before the script body, so the router sees the new state on the run the
  interaction causes. Reading `st.chat_input`'s return value instead handles the
  submission half way down the script, after the current view has begun rendering, and
  the switch is silently deferred to some later interaction: the ask bar looked dead.
* **`st.dataframe` needs an explicit integer height, and honours it exactly.** Left-over
  space is painted as an empty band that reads as a truncated row. A band is 31px
  (`primitives.table_height`), measured off the rendered grid rather than guessed.
* **No em dashes and no ` -- ` in user-facing strings.** A test walks the AST and checks
  every string literal (docstrings exempt). Sentence case for titles and labels.
* **`st.html` strips inline `<svg>`.** The brand mark ships as a base64 CSS mask so it
  can still inherit `currentColor`. A raw `<svg` inside the injected style block is
  mangled too, hence base64 rather than percent-encoding. Two tests guard this.
* **Never write a literal `<style>` tag inside a CSS comment.** The sanitiser that
  processes injected CSS silently drops the entire block when it sees one.
* **Components never call `st.dialog`.** They set intent via `session.set_dialog(...)`;
  `app.py` runs one dispatcher at the end, because Streamlit permits exactly one dialog
  per script run.
* **Scoped button skins need `[kind="..."]`.** The base skins match on
  `.stButton button[kind="primary"]`, so a rule like `div[class*="st-key-tile-"] button`
  loses on specificity and silently does nothing.
* **Rows keyed `row-*` are tight rows.** Streamlit stamps `width: 100%` on every child of
  a horizontal container, so a multi-child row wraps and spreads unless the stylesheet
  overrides it. `row-head-*` additionally lets the first child absorb the slack, which is
  what pins a card menu to the right edge.

---

## Design notes

The system is **navy monochromatic**, anchored on the brand navy `#12285C` with the UI
accent at `#1D3E76`. Charts use **one hue**: series separate by lightness, never by
colour, so a six-series chart stays legible to every kind of colour vision and still
reads as one family. Red, amber and green survive only as *status* colours on chips and
rails; they never enter a chart. Two tests hold the line: one checks the categorical
ramps span under 25 degrees of hue with real lightness separation between neighbours, the
other checks `config.toml` still matches `theme/tokens.py`.

The left rail is fixed dark navy in both themes because it is chrome, not canvas.

Charts follow the same rules throughout: no gridlines on the category axis, no chart
titles (the card names it), bars capped at 20px with direct value labels replacing the
value axis, headroom on the value scale so the longest label is never clipped, rank
encoded as lightness in a ranked bar chart, no legend for a single series, and **never a
dual axis** (two measures means two cards). Funnel is drawn as a horizontal bar on the
ordinal ramp, which is more honest than a true funnel because funnels distort area.

Every widget carries the same control strip in its corner and the same footer:
provenance on the left, `Updated <date>, <time>` on the right. The stamp comes from `REPORTING_DATE`, not the wall clock, so two widgets in one
pass cannot disagree.

The app ships committed to the light palette, because `config.toml` pins Streamlit's own
widget colours and Streamlit has no second palette for dark. To run it dark, replace the
`[theme]` colour keys with the output of `tokens.config_theme_toml(dark=True)`; the values
come from `tokens.DARK`, so the two cannot drift. A `prefers-color-scheme` flip would be
worse than nothing: our cards would go dark while every input, dataframe and popover
stayed light, and `st.context.theme.type` would still report light, so the charts would
keep the light palette on a dark canvas.

---

## Known limits

* Filters can only reference columns the saved query actually selects. This is surfaced
  honestly in the UI rather than papered over by regex-rewriting the base query's
  `WHERE` clause; use **Edit with AI** to add a column.
* Layout, order and width persist in `app_state.db`; other session state,
  conversations included, resets on refresh.
* A chat accepts five questions, then asks you to start a new one. Older chats stay
  readable in the rail and anything pinned stays on the canvas.
* Reordering is arrows rather than drag-and-drop, which Streamlit has no native support
  for. Width is a two-step toggle (half or full), not a continuous resize.
* Digest scheduling and delivery are presentational.
* Execution is mocked everywhere. Nothing is ever sent.

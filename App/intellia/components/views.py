"""Secondary views behind the left rail.

Portfolio, skills, digests, apps, product updates and settings. Each is a thin
read over things the app already knows: the portfolio is assembled from real
accounts and deals, apps come from the connector protocols in
``data/connectors/base.py``, skills come from the tasks the AI service actually
runs. Nothing here invents a number, and nothing writes outside the layout store.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

import pandas as pd
import streamlit as st

from intellia.ai.prompts import tasks
from intellia.components import chrome
from intellia.components import primitives as ui
from intellia.config.personas import PERSONA_REGISTRY, Persona
from intellia.state import session
from intellia.theme import brand
from intellia.utils.dates import quarter_label
from intellia.utils.formatting import esc, money

# -- skills -------------------------------------------------------------------------------
# One row per task the AI service can actually run, plus the guarantee that
# holds when there is no model available.

SKILLS = [
    ("Meeting prep", ":material/auto_awesome:",
     "Reads the account, deal, mail and signal history and writes the pre-call brief.",
     tasks.MEETING_PREP.name, "On every meeting row"),
    ("Daily brief", ":material/summarize:",
     "Ranks what changed overnight, then drops anything it cannot cite.",
     tasks.DAILY_BRIEF.name, "Top of your canvas"),
    ("Action explain", ":material/checklist:",
     "Says what happened, why it matters and what to do next.",
     tasks.ACTION_EXPLAIN.name, "Any action you open"),
    ("Email drafting", ":material/mail:",
     "Writes the follow-up in your voice, grounded in the thread and the playbook.",
     tasks.EMAIL_DRAFT.name, "Action execution"),
    ("Text to insight", ":material/monitoring:",
     "Turns a question into validated SQL once, then replays it for free.",
     tasks.INSIGHT_SQL.name, "Create with AI, edit with AI, and data questions"),
    ("Ask anything", ":material/forum:",
     "Answers from your evidence and your computed metrics, never from memory.",
     tasks.ASK.name, "The ask bar and every conversation"),
]

APPS = [
    ("Salesforce", ":material/cloud:", "CRM", "Accounts, opportunities, contacts",
     "Connected", "CRMConnector"),
    ("Outlook calendar", ":material/event:", "Calendar", "Meetings and attendees",
     "Connected", "CalendarConnector"),
    ("Outlook mail", ":material/mail:", "Mail", "Threads, sentiment, waiting replies",
     "Connected", "EmailConnector"),
    ("Intellia signals", ":material/sensors:", "Signals", "Buying and risk signals",
     "Connected", "SignalConnector"),
    ("Asana", ":material/task_alt:", "Tasks", "Commitments and due dates",
     "Connected", "TaskConnector"),
    ("Snowflake", ":material/database:", "Warehouse", "Company-wide reporting tables",
     "Available", "CRMConnector"),
]

DIGESTS = [
    ("Morning brief", "Weekdays, 07:30", "Email and in app",
     "What changed overnight, ranked, with the one thing to do first.", True),
    ("Pipeline movement", "Mondays, 08:00", "Email",
     "Stage changes, new pipeline and slipped close dates for the week.", True),
    ("Deal risk alert", "As it happens", "In app",
     "Fires when a deal over 100k stalls for three weeks or loses its champion.", True),
    ("Quarter close countdown", "Daily in the last 3 weeks", "Email",
     "Coverage against remaining target and what has to land this week.", False),
]

UPDATES = [
    ("13 Aug 2026", "Faster answers", "New",
     "A question opens its conversation immediately and the answer resolves into "
     "it. Interactive work runs on the fast model tier; the brief and meeting prep "
     "stay on the flagship."),
    ("13 Aug 2026", "Answers read the same rows as the chart", "Changed",
     "Text to SQL runs first and its result is handed to the answer, so the prose "
     "beside a chart can no longer describe different numbers."),
    ("13 Aug 2026", "Canvas controls on every card", "New",
     "Definition, edit with AI, chart or table, width, order and remove, as icons "
     "in the corner. Section titles and notes are widgets too."),
    ("11 Aug 2026", "Insight versioning", "New",
     "Edits append a version instead of overwriting. A failed edit can no longer "
     "damage a working card."),
    ("08 Aug 2026", "Persona scoping by temp table", "New",
     "Scope is enforced by shadowing tables, not by rewriting SQL, so generated "
     "queries cannot read another rep's book."),
]


# -- portfolio -------------------------------------------------------------------------

PORTFOLIO_COLUMNS = [
    ("account", "Account", "text"),
    ("industry", "Industry", "text"),
    ("segment", "Segment", "text"),
    ("region", "Region", "text"),
    ("health", "Health", "progress"),
    ("arr", "ARR", "money"),
    ("open_pipeline", "Open pipeline", "money"),
    ("open_deals", "Deals", "number"),
    ("stage", "Furthest stage", "text"),
    ("next_step", "Next step", "text"),
    ("renewal", "Renewal", "text"),
]


def render_portfolio(rows: Sequence[Dict[str, Any]]) -> None:
    """Customer 360 as one table.

    A card per account looks tidy at eight accounts and falls apart at eighty.
    One table sorts on any column, searches across every text field, and filters
    without the user losing their place, which is what a book of business
    actually needs.
    """
    chrome.page_header("Portfolio", "Every account in your book, one row each")

    if not rows:
        ui.empty_state("No accounts in your book.", "Switch persona to see another book.")
        return

    frame = pd.DataFrame(rows)

    controls = st.container(key="row-portfolio-filters", horizontal=True,
                           vertical_alignment="center")
    with controls:
        query = st.text_input("Search", key="portfolio-q", placeholder="Search accounts",
                              label_visibility="collapsed")
        segments = st.multiselect("Segment", sorted(frame["segment"].unique()),
                                  key="portfolio-seg", placeholder="All segments",
                                  label_visibility="collapsed")
        regions = st.multiselect("Region", sorted(frame["region"].unique()),
                                 key="portfolio-region", placeholder="All regions",
                                 label_visibility="collapsed")
        risk_only = st.toggle("At risk", key="portfolio-risk",
                             help="Health below 60, or a renewal already overdue")

    view = _filter_portfolio(frame, query, segments, regions, risk_only)

    with ui.card("portfolio"):
        head = st.container(key="row-head-portfolio", horizontal=True,
                           vertical_alignment="top")
        with head:
            st.html(ui.card_header(
                "Accounts", "{} of {} shown · sort by any column".format(
                    len(view), len(frame))))
            st.html('<div>{}</div>'.format("".join([
                ui.chip("{} open".format(money(view["open_pipeline"].sum())), "accent"),
                " ",
                ui.chip("{} ARR".format(money(view["arr"].sum()))),
            ])))

        if view.empty:
            ui.empty_state("No accounts match.", "Clear the filters to see the book.")
        else:
            st.dataframe(
                view,
                hide_index=True,
                width="stretch",
                height=ui.table_height(len(view), cap=12),
                column_config=_portfolio_columns(view),
            )
        st.html(ui.card_footer("Salesforce accounts and opportunities"))


def _filter_portfolio(frame: "pd.DataFrame", query: str, segments, regions,
                      risk_only: bool) -> "pd.DataFrame":
    view = frame
    text = (query or "").strip().lower()
    if text:
        searchable = ["account", "industry", "segment", "region", "stage", "next_step"]
        mask = False
        for column in searchable:
            hit = view[column].astype(str).str.lower().str.contains(text, regex=False)
            mask = hit if mask is False else (mask | hit)
        view = view[mask]
    if segments:
        view = view[view["segment"].isin(segments)]
    if regions:
        view = view[view["region"].isin(regions)]
    if risk_only:
        view = view[(view["health"] < 60) | (view["renewal"].str.contains("overdue"))]
    return view


def _portfolio_columns(view: "pd.DataFrame") -> Dict[str, Any]:
    """Explicit here, because these columns are assembled rather than queried.

    ``step=1`` is what stops ARR rendering as ``$292,000.00``: Streamlit takes a
    float column's display precision from the step, not from the format preset.
    """
    config: Dict[str, Any] = {}
    for key, label, kind in PORTFOLIO_COLUMNS:
        if key not in view.columns:
            continue
        if kind == "money":
            config[key] = st.column_config.NumberColumn(label, format="dollar", step=1)
        elif kind == "number":
            config[key] = st.column_config.NumberColumn(
                label, format="localized", step=1, width="small")
        elif kind == "progress":
            config[key] = st.column_config.ProgressColumn(
                label, min_value=0, max_value=100, format="%d")
        else:
            config[key] = st.column_config.TextColumn(label)
    return config


# -- skills ------------------------------------------------------------------------------

def render_skills(ai_mode: str, live: bool, model_for=None) -> None:
    chrome.page_header("Skills", "What Intellia can do on your behalf")

    st.html('<div class="ix-card" style="margin-bottom:8px">'
            '<p class="ix-card-title">Assistant: {m} and the fast tier</p>'
            '<p class="ix-card-sub">{s}</p></div>'.format(
                m=esc(ai_mode),
                s=esc("Live generation is on. Every skill is still grounded in your "
                      "evidence and validated before it renders."
                      if live else
                      "No key is configured, so every skill runs its deterministic "
                      "builder. The app is fully usable and nothing is invented.")))

    for start in range(0, len(SKILLS), 2):
        columns = st.columns(2, gap="small")
        for column, skill in zip(columns, SKILLS[start:start + 2]):
            name, icon, body, task, where = skill
            with column:
                with ui.card("skill-{}".format(task)):
                    st.html(
                        '<div class="ix-row-flex"><span class="ix-icon-box">{i}</span>'
                        '<div><p class="ix-card-title">{n}</p>'
                        '<p class="ix-card-sub">{b}</p></div></div>'
                        '<p class="ix-meta" style="margin-top:6px">Runs: {w}</p>'.format(
                            i=brand.mark(14), n=esc(name), b=esc(body), w=esc(where)))
                    st.html(ui.card_footer(
                        "Task {}".format(task),
                        model_for(task) if model_for else ""))


# -- digests -------------------------------------------------------------------------------

def render_digests() -> None:
    chrome.page_header("Digests", "Scheduled briefings and alerts")

    for index, (name, cadence, channel, body, on) in enumerate(DIGESTS):
        with ui.card("digest-{}".format(index)):
            head = st.container(key="row-head-digest-{}".format(index), horizontal=True,
                                vertical_alignment="center")
            with head:
                st.html('<div><p class="ix-card-title">{n}</p>'
                        '<p class="ix-card-sub">{b}</p></div>'.format(
                            n=esc(name), b=esc(body)))
                st.toggle("On", value=on, key="digest-on-{}".format(index),
                          label_visibility="collapsed")
            st.html('<p class="ix-meta" style="margin-top:6px">{c} &middot; {ch}</p>'
                    .format(c=esc(cadence), ch=esc(channel)))
            st.html(ui.card_footer("Delivery is mocked in this prototype"))


# -- apps ----------------------------------------------------------------------------------

def render_apps() -> None:
    chrome.page_header("Apps", "Connected systems and what each one supplies")

    for start in range(0, len(APPS), 3):
        columns = st.columns(3, gap="medium")
        for column, app in zip(columns, APPS[start:start + 3]):
            name, icon, kind, supplies, status, protocol = app
            with column:
                with ui.card("app-{}".format(protocol + name)):
                    st.html(
                        '<div class="ix-row-flex"><span class="ix-icon-box">{i}</span>'
                        '<div><p class="ix-card-title">{n}</p>'
                        '<p class="ix-card-sub">{k}</p></div></div>'
                        '<p class="ix-row-body" style="margin-top:8px">{s}</p>'
                        '<div style="margin-top:8px">{c}</div>'.format(
                            i=esc(name[0]), n=esc(name), k=esc(kind), s=esc(supplies),
                            c=ui.chip(status, "good" if status == "Connected" else "")))
                    st.html(ui.card_footer("Protocol: {}".format(protocol)))


# -- product updates --------------------------------------------------------------------------

def render_updates() -> None:
    chrome.page_header("Product updates", "What changed in Intellia")

    for index, (when, title, tag, body) in enumerate(UPDATES):
        with ui.card("update-{}".format(index)):
            st.html(
                '<div class="ix-row-top"><span class="ix-row-time">{w}</span>'
                '<p class="ix-row-title">{t}</p>'
                '<span style="margin-left:auto">{c}</span></div>'
                '<p class="ix-row-body" style="-webkit-line-clamp:3">{b}</p>'.format(
                    w=esc(when), t=esc(title), b=esc(body),
                    c=ui.chip(tag, "accent" if tag == "New" else "")))


# -- settings ----------------------------------------------------------------------------------

def render_settings(persona: Persona, ai_mode: str, live: bool, scope_label: str,
                    reporting_date, widget_count: int, on_reset,
                    flagship_model: str = "", fast_model: str = "") -> None:
    chrome.page_header("Settings", "Profile, assistant and data")

    left, right = st.columns(2, gap="medium")

    with left:
        with ui.card("set-profile"):
            st.html(ui.card_header("Profile", "Who Intellia thinks you are"))
            st.html(ui.key_values([
                ("Name", persona.label),
                ("Role", persona.role_label),
                ("Team", persona.tagline),
                ("Data scope", scope_label),
            ]))
            st.html(ui.card_footer("Persona registry"))

        with ui.card("set-view"):
            st.html(ui.card_header("Switch view",
                                   "Scope, widgets and brief all follow the persona"))
            for pid, option in PERSONA_REGISTRY.items():
                row = st.container(key="row-head-persona-{}".format(pid), horizontal=True,
                                   vertical_alignment="center")
                with row:
                    st.html('<div><b style="font-size:12.5px">{n}</b>'
                            '<div class="ix-meta">{r}</div></div>'.format(
                                n=esc(option.label), r=esc(option.role_label)))
                    st.button("Current" if pid == persona.id else "Switch",
                              key="persona-{}".format(pid),
                              type="secondary" if pid == persona.id else "primary",
                              disabled=pid == persona.id,
                              on_click=session.set_persona, args=(pid,))
            st.html(ui.card_footer("Layout is saved per persona"))

    with right:
        with ui.card("set-ai"):
            st.html(ui.card_header("Assistant", "How generation is running right now"))
            st.html(ui.key_values([
                ("Live model", "Yes" if live else "No, deterministic builders"),
                ("Brief and prep", flagship_model),
                ("Questions, SQL, drafts", fast_model),
                ("Grounding", "Evidence bundle plus computed metrics"),
                ("Numbers", "Always SQL, never the model"),
            ]))
            st.html('<p class="ix-meta" style="margin-top:6px">Interactive work runs on '
                    'the fast tier because you are waiting on it. Set ANTHROPIC_API_KEY '
                    'in .env to switch on live generation.</p>')
            st.html(ui.card_footer("ai/service.py"))

        with ui.card("set-data"):
            st.html(ui.card_header("Data", "Where the canvas reads from"))
            st.html(ui.key_values([
                ("Analytics store", "intellia.db, opened read only"),
                ("App state", "app_state.db, layouts and versions"),
                ("Reporting date", str(reporting_date)),
                ("Quarter", quarter_label(reporting_date)),
                ("Components available", str(widget_count)),
            ]))
            st.button("Restore default canvas", key="reset-layout",
                      icon=":material/restart_alt:", on_click=on_reset)
            st.html(ui.card_footer("Two databases, one read only"))

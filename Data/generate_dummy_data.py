"""Deterministic seed-data generator for Intellia My Day.

Design rules (see plan):

* ``REPORTING_DATE`` (2026-08-13) is the single origin for every date. Nothing uses
  ``date.today()`` -- the demo must look identical whenever it is run.
* One ``random.Random`` per table, seeded from the table name, so editing one
  generator cannot perturb another's value stream.
* The generator ends with ``validate()``, which asserts every invariant the app
  depends on. A defect in the seed fails here rather than as an empty widget.

Run::

    python3 Data/generate_dummy_data.py            # write CSVs
    python3 Data/generate_dummy_data.py --dry-run  # invariant report only
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------------------
# Time origin
# --------------------------------------------------------------------------------------

REPORTING_DATE = date(2026, 8, 13)
Q3_START, Q3_END = date(2026, 7, 1), date(2026, 9, 30)
YTD_START = date(2026, 1, 1)
HISTORY_START = date(2025, 8, 1)  # first month of generated pipeline creation

DATE_FMT = "%Y-%m-%d"
TS_FMT = "%Y-%m-%d %H:%M:%S"


def rng_for(table: str) -> random.Random:
    """A stable, independent RNG per table."""
    return random.Random(zlib.crc32(table.encode("utf-8")))


def d(value: date) -> str:
    return value.strftime(DATE_FMT)


def ts(value: datetime) -> str:
    return value.strftime(TS_FMT)


def month_starts(start: date, end: date) -> List[date]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        out.append(cur)
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    return out


# --------------------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------------------

STAGES = [
    "Stage 1 - Discovery",
    "Stage 2 - Qualification",
    "Stage 3 - Evaluation",
    "Stage 4 - Proposal",
    "Stage 5 - Closed Won",
    "Stage 5 - Closed Lost",
]
OPEN_STAGES = STAGES[:4]
CLOSED_STAGES = STAGES[4:]
STAGE_PROBABILITY = {
    "Stage 1 - Discovery": 15,
    "Stage 2 - Qualification": 30,
    "Stage 3 - Evaluation": 55,
    "Stage 4 - Proposal": 75,
    "Stage 5 - Closed Won": 100,
    "Stage 5 - Closed Lost": 0,
}
FORECAST_BY_STAGE = {
    "Stage 1 - Discovery": "Pipeline",
    "Stage 2 - Qualification": "Pipeline",
    "Stage 3 - Evaluation": "Best Case",
    "Stage 4 - Proposal": "Commit",
    "Stage 5 - Closed Won": "Closed",
    "Stage 5 - Closed Lost": "Omitted",
}

INDUSTRIES = [
    "Enterprise Software", "Financial Services", "Cloud Infrastructure", "Healthcare",
    "Retail & E-commerce", "Cybersecurity", "Data & Analytics", "Media & Telecom",
    "Energy & Utilities", "Manufacturing",
]
REGIONS = ["AMER", "EMEA", "APAC"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
TIERS = ["Tier 1", "Tier 2", "Tier 3"]

COMPANY_NAMES = [
    "Apex Logistics", "Vortex Analytics", "CloudScale Systems", "BioHealth Labs",
    "OmniRetail Group", "CyberGuard Networks", "DataPulse AI", "Nexus Financial",
    "Strata Energy", "Fintech Dynamics", "Quantum Edge", "Synergy Media",
    "Astra Manufacturing", "Velocity Cloud", "Horizon Ventures", "Pinnacle Software",
    "Aether Digital", "Lumina Health", "Crest Solutions", "Trident Corp",
    "Beacon Utilities", "Core Networks", "Echelon Labs", "Zenith Retail",
    "Kinetix Robotics", "Optima Insurance", "Veritas Data", "Vanguard Payments",
    "Solstice Energy", "Infini Telecom", "Pulse Diagnostics", "Titan Industrial",
    "Prism Analytics", "Cobalt Mining", "Sentry Security", "Helios Power",
    "Fortress Bank", "Clarity Health", "Nouveau Retail", "Orion Aerospace",
    "Hyperion Cloud", "Astral Media", "Summit Financial", "Vector Biotech",
    "Eclipse Systems", "Matrix Logistics", "Northwind Foods", "Ironclad Insurance",
    "Silverline Telecom", "Redwood Capital", "Bluepeak Software", "Granite Utilities",
    "Meridian Health", "Copperfield Retail", "Lakeshore Manufacturing", "Ridgeline Data",
    "Foxglove Labs", "Harborview Energy", "Stonebridge Bank", "Wavelength Media",
]

FIRST_NAMES = [
    "David", "Sarah", "Mark", "Elena", "James", "Rachel", "Tom", "Priya", "Carlos",
    "Amanda", "Robert", "Emily", "Michael", "Jessica", "Daniel", "Laura", "Kevin",
    "Sophia", "Brian", "Megan", "Nina", "Omar", "Grace", "Victor", "Hannah",
]
LAST_NAMES = [
    "Miller", "Jenkins", "Benson", "Rostova", "Chen", "Adams", "Wright", "Sharma",
    "Mendez", "Cole", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris",
    "Martin", "Clark", "Lewis", "Walker", "Novak", "Okafor", "Diaz", "Fischer",
]

TITLES_BY_PERSONA = {
    "Economic Buyer": ["Chief Revenue Officer", "VP of Sales", "VP of Revenue Operations", "Chief Operating Officer"],
    "Champion": ["Director of Sales Operations", "Head of RevOps", "Senior Manager, Sales Strategy", "Director of GTM Systems"],
    "Technical Buyer": ["Director of Data Engineering", "Head of Business Systems", "Enterprise Architect", "VP of IT"],
    "Influencer": ["Sales Enablement Manager", "Business Analyst", "Manager, Sales Operations", "Program Manager, GTM"],
}
PERSONA_ROLES = list(TITLES_BY_PERSONA.keys())

WIN_REASONS = [
    "Signal-to-action workflow beat incumbent",
    "Fastest time to value in evaluation",
    "Executive sponsor championed the rollout",
    "Consolidated three point tools",
    "Forecast accuracy proof-of-value landed",
]
LOSS_REASONS = [
    "Budget frozen for the fiscal year",
    "Lost to incumbent CRM add-on",
    "Champion left mid-cycle",
    "No executive sponsor identified",
    "Deprioritized after reorg",
]
COMPETITORS = ["Clari", "Gong", "People.ai", "Incumbent CRM", "In-house build", ""]

DEAL_NEXT_STEPS = [
    "Send mutual action plan",
    "Confirm security review timeline",
    "Schedule executive alignment call",
    "Deliver ROI model to finance",
    "Get procurement paperwork started",
    "Run technical validation workshop",
    "Circulate pilot success criteria",
]

MEETING_TYPES = ["Discovery", "Technical Validation", "QBR", "Executive Briefing",
                 "Renewal Review", "Demo", "Internal Sync", "Negotiation"]

SIGNAL_TYPES = ["Intent Score", "Champion Movement", "Executive Departure", "M&A Event",
                "Hiring Surge", "Funding Round"]
# brain.md playbook names differ slightly from the raw signal vocabulary; normalize here so
# the action layer can look up a playbook deterministically.
SIGNAL_PLAYBOOK = {
    "Intent Score": "Intent Spike",
    "Champion Movement": "Champion Movement",
    "Executive Departure": "Executive Change",
    "M&A Event": "M&A Event",
    "Hiring Surge": "Intent Spike",
    "Funding Round": "M&A Event",
}
SIGNAL_TITLES = {
    "Intent Score": ["Intent spike on G2 for revenue intelligence", "Repeat visits to pricing and ROI pages",
                     "Comparison research against forecasting vendors"],
    "Champion Movement": ["Champion promoted to VP Revenue Operations", "Champion joined from a customer account",
                          "Champion expanded scope to include forecasting"],
    "Executive Departure": ["CRO departure announced", "VP Sales exited the business",
                            "Head of RevOps moved on"],
    "M&A Event": ["Acquisition announced in target vertical", "Merger closes, two CRM instances to consolidate",
                  "Divestiture creates a new GTM entity"],
    "Hiring Surge": ["Twelve open RevOps and enablement roles", "Sales headcount plan doubled for next year",
                     "New data team chartered for GTM analytics"],
    "Funding Round": ["Series D raised to fund GTM expansion", "Growth round closed ahead of plan",
                      "New capital earmarked for revenue tooling"],
}
SIGNAL_ACTIONS = {
    "Intent Score": "Send a personalized case study and route to the account owner",
    "Champion Movement": "Send a congratulatory note and reconnect on new priorities",
    "Executive Departure": "Map the new org and re-establish an executive sponsor",
    "M&A Event": "Engage the CRO on seat consolidation across both entities",
    "Hiring Surge": "Position onboarding and ramp analytics to the enablement lead",
    "Funding Round": "Open a strategic conversation on scaling GTM operations",
}

EMAIL_THREAD_TOPICS = [
    ("Integration architecture overview", "technical"),
    ("Following up on our discovery call", "followup"),
    ("Pricing and packaging for the rollout", "pricing"),
    ("Security review questionnaire", "security"),
    ("Pilot success criteria", "pilot"),
    ("Renewal timing and scope", "renewal"),
    ("Executive briefing logistics", "exec"),
    ("Procurement paperwork", "procurement"),
]

TASK_TITLES = [
    "Send recap and mutual action plan",
    "Update the close plan in CRM",
    "Share the ROI model with finance",
    "Confirm the security questionnaire owner",
    "Book the executive alignment call",
    "Draft the renewal proposal",
    "Follow up on the pilot results",
    "Log the competitive intel from the last call",
    "Chase the signed order form",
    "Prepare the QBR deck",
]


# --------------------------------------------------------------------------------------
# Users -- deliberately hand-shaped: the Manager persona needs a real team
# --------------------------------------------------------------------------------------

# (user_id, name, role, department, quota, manager_id, region)
USER_SPEC: List[Tuple[str, str, str, str, int, Optional[str], str]] = [
    ("USR-3001", "Jessica Clark",  "AE",                  "Sales",            1_800_000, "USR-3003", "AMER"),
    ("USR-3002", "Elena Benson",   "Senior AE",           "Sales",            2_400_000, "USR-3003", "AMER"),  # REP PERSONA
    ("USR-3003", "James Clark",    "Sales Manager",       "Sales",            5_800_000, "USR-3004", "AMER"),  # MANAGER PERSONA
    ("USR-3004", "Emily Lewis",    "CRO",                 "Executive",       12_000_000, None,       "AMER"),
    ("USR-3005", "Robert Jackson", "AE",                  "Sales",            1_800_000, "USR-3003", "AMER"),
    ("USR-3006", "Priya Mendez",   "Senior AE",           "Sales",            2_400_000, "USR-3003", "AMER"),
    ("USR-3007", "Michael Cole",   "AE",                  "Sales",            1_800_000, "USR-3003", "AMER"),
    ("USR-3008", "Elena Thomas",   "Sales Manager",       "Sales",            5_400_000, "USR-3004", "EMEA"),
    ("USR-3009", "Brian Mendez",   "AE",                  "Sales",            1_800_000, "USR-3008", "EMEA"),
    ("USR-3010", "Sophia Taylor",  "Senior AE",           "Sales",            2_400_000, "USR-3008", "EMEA"),
    ("USR-3011", "Daniel Wright",  "AE",                  "Sales",            1_800_000, "USR-3008", "EMEA"),
    ("USR-3012", "Laura Adams",    "AE",                  "Sales",            1_800_000, "USR-3008", "APAC"),
    ("USR-3013", "Tom Chen",       "Senior AE",           "Sales",            2_400_000, "USR-3008", "APAC"),
    ("USR-3014", "Rachel Adams",   "SDR",                 "Sales",                    0, "USR-3003", "AMER"),
    ("USR-3015", "Mark Cole",      "SDR",                 "Sales",                    0, "USR-3008", "EMEA"),
    ("USR-3016", "David Adams",    "Solutions Engineer",  "Sales",                    0, "USR-3003", "AMER"),
    ("USR-3017", "Megan Taylor",   "Solutions Engineer",  "Sales",                    0, "USR-3008", "EMEA"),
    ("USR-3018", "James Jackson",  "RevOps Lead",         "RevOps",                   0, "USR-3004", "AMER"),
    ("USR-3019", "Sarah Cole",     "RevOps Analyst",      "RevOps",                   0, "USR-3018", "AMER"),
    ("USR-3020", "Amanda Sharma",  "RevOps Analyst",      "RevOps",                   0, "USR-3018", "EMEA"),
    ("USR-3021", "Sarah Anderson", "VP Marketing",        "Marketing",                0, "USR-3004", "AMER"),
    ("USR-3022", "Priya Rostova",  "Demand Gen Lead",     "Marketing",                0, "USR-3021", "AMER"),
    ("USR-3023", "Robert Mendez",  "Content Lead",        "Marketing",                0, "USR-3021", "EMEA"),
    ("USR-3024", "Sophia Jackson", "VP Customer Success", "Customer Success",         0, "USR-3004", "AMER"),
    ("USR-3025", "James Sharma",   "CSM",                 "Customer Success",         0, "USR-3024", "AMER"),
    ("USR-3026", "Kevin Thomas",   "CSM",                 "Customer Success",         0, "USR-3024", "EMEA"),
    ("USR-3027", "Nina Novak",     "CSM",                 "Customer Success",         0, "USR-3024", "APAC"),
    ("USR-3028", "Omar Okafor",    "Solutions Engineer",  "Sales",                    0, "USR-3008", "APAC"),
    ("USR-3029", "Grace Diaz",     "RevOps Analyst",      "RevOps",                   0, "USR-3018", "APAC"),
    ("USR-3030", "Victor Fischer", "Enablement Lead",     "Sales",                    0, "USR-3004", "AMER"),
]

REP_PERSONA_ID = "USR-3002"
MANAGER_PERSONA_ID = "USR-3003"
SELLING_ROLES = {"AE", "Senior AE"}


def build_users() -> pd.DataFrame:
    r = rng_for("users")
    rows = []
    for uid, name, role, dept, quota, mgr, region in USER_SPEC:
        slug = name.lower().split()
        email = "{}.{}@intellia.ai".format(slug[0], slug[1][0])
        hire = REPORTING_DATE - timedelta(days=r.randint(200, 1500))
        rows.append({
            "user_id": uid,
            "full_name": name,
            "email": email,
            "role": role,
            "department": dept,
            "manager_id": mgr or "",
            "region": region,
            "quota_annual": quota,
            "hire_date": d(hire),
            "is_active": 1,
        })
    return pd.DataFrame(rows)


def selling_users(users: pd.DataFrame) -> List[str]:
    return users.loc[users["role"].isin(SELLING_ROLES), "user_id"].tolist()


# --------------------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------------------

def build_accounts(users: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("accounts")
    reps = selling_users(users)
    rows = []
    for i, name in enumerate(COMPANY_NAMES, start=1):
        acc_id = "ACC-{}".format(1000 + i)
        domain = name.lower().replace(" ", "").replace("&", "and")
        status = "Customer" if r.random() < 0.6 else "Prospect"
        segment = r.choices(SEGMENTS, weights=[45, 35, 20])[0]
        tier = {"Enterprise": "Tier 1", "Mid-Market": "Tier 2", "SMB": "Tier 3"}[segment]
        employees = {"Enterprise": r.randint(2500, 12000),
                     "Mid-Market": r.randint(400, 2500),
                     "SMB": r.randint(80, 400)}[segment]
        arr = 0
        renewal = ""
        if status == "Customer":
            base = {"Enterprise": (180_000, 420_000), "Mid-Market": (60_000, 180_000),
                    "SMB": (18_000, 60_000)}[segment]
            arr = r.randrange(base[0], base[1], 1000)
            renewal = d(REPORTING_DATE + timedelta(days=r.randint(-30, 320)))
        rows.append({
            "account_id": acc_id,
            "account_name": name,
            "domain": "{}.com".format(domain),
            "industry": INDUSTRIES[i % len(INDUSTRIES)],
            "region": REGIONS[i % len(REGIONS)] if i % 4 else "AMER",
            "segment": segment,
            "tier": tier,
            "status": status,
            "arr": arr,
            "employee_count": employees,
            "owner_id": reps[i % len(reps)],
            "renewal_date": renewal,
            "health_score": r.randint(42, 96),
            "created_at": d(REPORTING_DATE - timedelta(days=r.randint(120, 1400))),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Contacts
# --------------------------------------------------------------------------------------

def build_contacts(accounts: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("contacts")
    rows, cid = [], 2000
    for _, acc in accounts.iterrows():
        n = r.randint(3, 6)
        personas = r.sample(PERSONA_ROLES, k=min(n, len(PERSONA_ROLES)))
        while len(personas) < n:
            personas.append(r.choice(PERSONA_ROLES))
        has_champion = r.random() < 0.62
        for j in range(n):
            cid += 1
            first, last = r.choice(FIRST_NAMES), r.choice(LAST_NAMES)
            persona = personas[j]
            is_champ = 1 if (has_champion and persona == "Champion" and j == personas.index("Champion")) else 0
            rows.append({
                "contact_id": "CNT-{}".format(cid),
                "account_id": acc["account_id"],
                "first_name": first,
                "last_name": last,
                "email": "{}{}@{}".format(first[0].lower(), last.lower(), acc["domain"]),
                "title": r.choice(TITLES_BY_PERSONA[persona]),
                "persona_role": persona,
                "seniority": "Executive" if persona == "Economic Buyer" else "Director" if persona in ("Champion", "Technical Buyer") else "Manager",
                "influence": r.randint(40, 98),
                "is_champion": is_champ,
                "last_contacted_at": d(REPORTING_DATE - timedelta(days=r.randint(1, 90))),
                "created_at": d(REPORTING_DATE - timedelta(days=r.randint(60, 900))),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Deals -- generated per creation-month so monthly pipeline generation is never truncated
# --------------------------------------------------------------------------------------

DEALS_PER_MONTH = 14


def build_deals(accounts: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("deals")
    reps = selling_users(users)
    acc_ids = accounts["account_id"].tolist()
    acc_by_id = accounts.set_index("account_id").to_dict("index")

    rows, did = [], 4000
    for m_start in month_starts(HISTORY_START, REPORTING_DATE):
        for _ in range(DEALS_PER_MONTH):
            did += 1
            created = m_start + timedelta(days=r.randint(0, 27))
            if created > REPORTING_DATE:
                created = REPORTING_DATE - timedelta(days=r.randint(0, 5))
            age = (REPORTING_DATE - created).days
            cycle = r.randint(45, 165)

            # Older cohorts are mostly resolved; recent ones are mostly still open.
            if age > cycle + 20:
                stage = r.choices(CLOSED_STAGES, weights=[62, 38])[0]
            elif age > 60:
                stage = r.choices(CLOSED_STAGES + OPEN_STAGES, weights=[26, 16, 6, 12, 20, 20])[0]
            else:
                stage = r.choices(OPEN_STAGES, weights=[34, 28, 22, 16])[0]

            if stage in CLOSED_STAGES:
                close = created + timedelta(days=min(cycle, max(20, age)))
                if close > REPORTING_DATE:
                    close = REPORTING_DATE - timedelta(days=r.randint(1, 20))
            else:
                close = REPORTING_DATE + timedelta(days=r.randint(-8, 150))

            acc_id = acc_ids[did % len(acc_ids)]
            acc = acc_by_id[acc_id]
            owner = acc["owner_id"] if r.random() < 0.72 else r.choice(reps)
            deal_type = ("Renewal" if acc["status"] == "Customer" and r.random() < 0.34
                         else "Upsell" if acc["status"] == "Customer" and r.random() < 0.5
                         else "New Logo")
            base = {"Enterprise": (120_000, 620_000), "Mid-Market": (45_000, 190_000),
                    "SMB": (15_000, 60_000)}[acc["segment"]]
            amount = r.randrange(base[0], base[1], 1000)

            stage_entered = close - timedelta(days=r.randint(3, 40)) if stage in CLOSED_STAGES \
                else REPORTING_DATE - timedelta(days=r.randint(1, 55))
            last_act = min(REPORTING_DATE, stage_entered + timedelta(days=r.randint(0, 25)))

            rows.append({
                "deal_id": "DL-{}".format(did),
                "account_id": acc_id,
                "owner_id": owner,
                "deal_name": "{} - {}".format(acc["account_name"], deal_type),
                "deal_type": deal_type,
                "stage": stage,
                "amount": amount,
                "probability": STAGE_PROBABILITY[stage],
                "forecast_category": FORECAST_BY_STAGE[stage],
                "close_date": d(close),
                "created_date": d(created),
                "stage_entered_at": d(stage_entered),
                "last_activity_date": d(last_act),
                "next_step": "" if stage in CLOSED_STAGES else r.choice(DEAL_NEXT_STEPS),
                "next_step_due_date": "" if stage in CLOSED_STAGES
                    else d(REPORTING_DATE + timedelta(days=r.randint(-6, 21))),
                "competitor": r.choice(COMPETITORS),
                "source": r.choice(["Outbound", "Inbound", "Partner", "Marketing", "Expansion"]),
                "win_loss_reason": (r.choice(WIN_REASONS) if stage == "Stage 5 - Closed Won"
                                    else r.choice(LOSS_REASONS) if stage == "Stage 5 - Closed Lost" else ""),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Narrative slice -- the ~15 records the demo actually walks through
# --------------------------------------------------------------------------------------

HERO_ACCOUNT = "ACC-1002"   # Vortex Analytics -- the at-risk renewal
SECOND_ACCOUNT = "ACC-1001"  # Apex Logistics -- the healthy expansion
HERO_DEAL = "DL-9001"
SECOND_DEAL = "DL-9002"
THIRD_DEAL = "DL-9003"


def inject_narrative_deals(deals: pd.DataFrame) -> pd.DataFrame:
    """Three hand-shaped deals for the rep persona so the demo story is coherent."""
    hero = [
        {
            "deal_id": HERO_DEAL, "account_id": HERO_ACCOUNT, "owner_id": REP_PERSONA_ID,
            "deal_name": "Vortex Analytics - Renewal + Expand", "deal_type": "Renewal",
            "stage": "Stage 4 - Proposal", "amount": 268_000, "probability": 60,
            "forecast_category": "Commit",
            "close_date": d(REPORTING_DATE + timedelta(days=18)),
            "created_date": d(REPORTING_DATE - timedelta(days=96)),
            "stage_entered_at": d(REPORTING_DATE - timedelta(days=27)),
            "last_activity_date": d(REPORTING_DATE - timedelta(days=9)),
            "next_step": "Resolve procurement concern and confirm renewal timeline",
            "next_step_due_date": d(REPORTING_DATE),
            "competitor": "Clari", "source": "Expansion", "win_loss_reason": "",
        },
        {
            "deal_id": SECOND_DEAL, "account_id": SECOND_ACCOUNT, "owner_id": REP_PERSONA_ID,
            "deal_name": "Apex Logistics - Platform Expansion", "deal_type": "Upsell",
            "stage": "Stage 3 - Evaluation", "amount": 145_000, "probability": 55,
            "forecast_category": "Best Case",
            "close_date": d(REPORTING_DATE + timedelta(days=41)),
            "created_date": d(REPORTING_DATE - timedelta(days=54)),
            "stage_entered_at": d(REPORTING_DATE - timedelta(days=12)),
            "last_activity_date": d(REPORTING_DATE - timedelta(days=2)),
            "next_step": "Run technical validation workshop with the data team",
            "next_step_due_date": d(REPORTING_DATE + timedelta(days=4)),
            "competitor": "In-house build", "source": "Expansion", "win_loss_reason": "",
        },
        {
            "deal_id": THIRD_DEAL, "account_id": "ACC-1011", "owner_id": REP_PERSONA_ID,
            "deal_name": "Quantum Edge - New Logo", "deal_type": "New Logo",
            "stage": "Stage 4 - Proposal", "amount": 312_000, "probability": 75,
            "forecast_category": "Commit",
            "close_date": d(REPORTING_DATE + timedelta(days=9)),
            "created_date": d(REPORTING_DATE - timedelta(days=132)),
            "stage_entered_at": d(REPORTING_DATE - timedelta(days=48)),
            "last_activity_date": d(REPORTING_DATE - timedelta(days=21)),
            "next_step": "Chase the signed order form",
            "next_step_due_date": d(REPORTING_DATE - timedelta(days=3)),
            "competitor": "Gong", "source": "Outbound", "win_loss_reason": "",
        },
    ]
    return pd.concat([deals, pd.DataFrame(hero)], ignore_index=True)


# --------------------------------------------------------------------------------------
# Emails -- threaded, with real prose bodies
# --------------------------------------------------------------------------------------

BODY_OPENERS = {
    "technical": "Thanks for walking us through the architecture. The team had a few follow-ups on how the connector handles incremental syncs.",
    "followup": "Great speaking earlier. Capturing what we agreed so nothing slips between now and the next session.",
    "pricing": "Sharing the packaging options we discussed, with the ramp assumptions called out separately.",
    "security": "Our security team has started the review. They flagged two questions on data residency and retention.",
    "pilot": "Here are the success criteria we would use to judge the pilot at the end of the period.",
    "renewal": "Wanted to get ahead of the renewal date so we have room to align on scope before the deadline.",
    "exec": "Confirming logistics for the executive briefing and who we expect in the room.",
    "procurement": "Procurement has the paperwork now. Flagging the two fields they need from your side to move it forward.",
}
BODY_CLOSERS_POS = [
    "This is tracking well on our side, happy to move at your pace.",
    "Appreciate the momentum here. Let me know if anything else would help.",
    "Glad this is landing. I will keep the internal team aligned.",
]
BODY_CLOSERS_NEG = [
    "Being candid: the timing is getting difficult on our end given the budget review.",
    "I want to flag that priorities have shifted since we last spoke.",
    "We may need to push this out a cycle. I will know more after the leadership review.",
]
BODY_CLOSERS_NEUTRAL = [
    "Let me know what makes sense as a next step.",
    "Happy to set up time if that is easier than email.",
    "Flag anything I have missed and I will get it turned around.",
]


def build_emails(accounts: pd.DataFrame, contacts: pd.DataFrame, deals: pd.DataFrame,
                 users: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("emails")
    user_email = users.set_index("user_id")["email"].to_dict()
    contacts_by_acc: Dict[str, List[Dict[str, Any]]] = {}
    for _, c in contacts.iterrows():
        contacts_by_acc.setdefault(c["account_id"], []).append(c.to_dict())
    deals_by_acc: Dict[str, List[Dict[str, Any]]] = {}
    for _, dl in deals.iterrows():
        deals_by_acc.setdefault(dl["account_id"], []).append(dl.to_dict())

    rows, eid, tid = [], 5000, 0
    for _, acc in accounts.iterrows():
        acc_contacts = contacts_by_acc.get(acc["account_id"], [])
        acc_deals = deals_by_acc.get(acc["account_id"], [])
        if not acc_contacts:
            continue
        owner = acc["owner_id"]
        for _ in range(r.randint(2, 5)):
            tid += 1
            thread_id = "THR-{}".format(8000 + tid)
            subject, topic = r.choice(EMAIL_THREAD_TOPICS)
            contact = r.choice(acc_contacts)
            deal_id = r.choice(acc_deals)["deal_id"] if acc_deals and r.random() < 0.75 else ""
            sentiment_drift = r.uniform(-0.55, 0.75)
            start = REPORTING_DATE - timedelta(days=r.randint(3, 150))
            for k in range(r.randint(2, 6)):
                eid += 1
                inbound = k % 2 == 1
                sent_dt = datetime.combine(start + timedelta(days=k * r.randint(1, 4)),
                                           datetime.min.time()) + timedelta(hours=r.randint(8, 18),
                                                                            minutes=r.choice([0, 15, 30, 45]))
                if sent_dt.date() > REPORTING_DATE:
                    sent_dt = datetime.combine(REPORTING_DATE, datetime.min.time()) + timedelta(hours=r.randint(8, 17))
                sentiment = round(max(-0.95, min(0.95, sentiment_drift + r.uniform(-0.18, 0.18))), 2)
                closer = (r.choice(BODY_CLOSERS_NEG) if sentiment < -0.2
                          else r.choice(BODY_CLOSERS_POS) if sentiment > 0.35
                          else r.choice(BODY_CLOSERS_NEUTRAL))
                body = "{}\n\n{}\n\nThanks,\n{}".format(
                    BODY_OPENERS[topic], closer,
                    contact["first_name"] if inbound else acc["account_name"])
                rows.append({
                    "email_id": "EML-{}".format(eid),
                    "thread_id": thread_id,
                    "account_id": acc["account_id"],
                    "contact_id": contact["contact_id"],
                    "deal_id": deal_id,
                    "sender_email": contact["email"] if inbound else user_email[owner],
                    "recipient_email": user_email[owner] if inbound else contact["email"],
                    "direction": "Inbound" if inbound else "Outbound",
                    "subject": subject if k == 0 else "Re: {}".format(subject),
                    "snippet": BODY_OPENERS[topic][:110],
                    "body": body,
                    "is_reply": 1 if k else 0,
                    "has_attachment": 1 if r.random() < 0.22 else 0,
                    "sent_at": ts(sent_dt),
                    "sentiment_score": sentiment,
                })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Meetings
# --------------------------------------------------------------------------------------

AGENDAS = [
    "Validate the data connector and custom signal mapping",
    "Align business outcome goals with the executive sponsor",
    "Review the pilot results and agree next steps",
    "Walk through pricing, packaging and the ramp plan",
    "Confirm the security review timeline and owners",
    "Renewal scope, timing and expansion options",
    "Technical deep dive on forecast accuracy",
    "Quarterly business review and adoption update",
]
KEY_POINTS = [
    "Adoption is concentrated in two teams; the rest of the org has not onboarded",
    "Forecast accuracy is the metric leadership actually cares about",
    "Procurement requires an executive sponsor before paperwork moves",
    "The data team wants incremental sync rather than full refresh",
    "Budget is committed but the timing sits behind a leadership review",
    "Competitive evaluation is down to two vendors",
    "Champion is willing to socialize the business case internally",
    "Security review is the critical path item",
]
NEXT_STEPS_POOL = [
    "Send the mutual action plan by end of week",
    "Schedule the executive alignment call",
    "Share the ROI model with finance",
    "Confirm the security questionnaire owner",
    "Circulate pilot success criteria for sign-off",
    "Get procurement paperwork started",
]
OUTCOMES = ["Advanced", "Held", "Slipped", "No decision"]


def build_meetings(accounts: pd.DataFrame, contacts: pd.DataFrame, deals: pd.DataFrame,
                   users: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("meetings")
    reps = selling_users(users)
    contacts_by_acc: Dict[str, List[str]] = {}
    for _, c in contacts.iterrows():
        contacts_by_acc.setdefault(c["account_id"], []).append(c["contact_id"])
    deals_by_acc: Dict[str, List[str]] = {}
    for _, dl in deals.iterrows():
        deals_by_acc.setdefault(dl["account_id"], []).append(dl["deal_id"])

    rows, mid = [], 6000
    for _, acc in accounts.iterrows():
        for _ in range(r.randint(4, 7)):
            mid += 1
            offset = r.randint(-120, 45)
            day = REPORTING_DATE + timedelta(days=offset)
            start_dt = datetime.combine(day, datetime.min.time()) + timedelta(
                hours=r.randint(8, 17), minutes=r.choice([0, 30]))
            duration = r.choice([30, 45, 60])
            completed = day < REPORTING_DATE
            mtype = r.choice(MEETING_TYPES)
            attendees = r.sample(contacts_by_acc.get(acc["account_id"], []),
                                 k=min(r.randint(1, 3), len(contacts_by_acc.get(acc["account_id"], [])) or 1)) \
                if contacts_by_acc.get(acc["account_id"]) else []
            organizer = acc["owner_id"] if r.random() < 0.8 else r.choice(reps)
            rows.append({
                "meeting_id": "MTG-{}".format(mid),
                "account_id": acc["account_id"],
                "deal_id": r.choice(deals_by_acc[acc["account_id"]]) if deals_by_acc.get(acc["account_id"]) else "",
                "organizer_id": organizer,
                "title": "{} / Intellia {}".format(acc["account_name"], mtype),
                "meeting_type": mtype,
                "scheduled_start": ts(start_dt),
                "scheduled_end": ts(start_dt + timedelta(minutes=duration)),
                "duration_minutes": duration,
                "location": r.choice(["Zoom", "Microsoft Teams", "Google Meet", "Customer site"]),
                "status": "Completed" if completed else "Scheduled",
                "agenda": r.choice(AGENDAS),
                "summary": (r.choice(KEY_POINTS) + ". " + r.choice(NEXT_STEPS_POOL) + ".") if completed else "",
                "key_points": json.dumps(r.sample(KEY_POINTS, k=3)) if completed else "[]",
                "next_steps": json.dumps(r.sample(NEXT_STEPS_POOL, k=2)) if completed else "[]",
                "outcome": r.choice(OUTCOMES) if completed else "",
                "attendee_contact_ids": json.dumps(attendees),
                "attendee_user_ids": json.dumps([organizer]),
            })
    return pd.DataFrame(rows)


def inject_narrative_meetings(meetings: pd.DataFrame) -> pd.DataFrame:
    """Four meetings on the reporting date for the rep persona -- two done, two ahead."""
    base = datetime.combine(REPORTING_DATE, datetime.min.time())
    rows = [
        {
            "meeting_id": "MTG-9001", "account_id": "", "deal_id": "", "organizer_id": REP_PERSONA_ID,
            "title": "Sales Intelligence Sync", "meeting_type": "Internal Sync",
            "scheduled_start": ts(base + timedelta(hours=9, minutes=30)),
            "scheduled_end": ts(base + timedelta(hours=10)),
            "duration_minutes": 30, "location": "Microsoft Teams", "status": "Completed",
            "agenda": "Weekly pipeline and signal review with the team",
            "summary": "Reviewed the week's signal queue. Vortex renewal flagged as the top risk to Q3 commit.",
            "key_points": json.dumps([
                "Vortex renewal is the largest single risk to the Q3 number",
                "Quantum Edge order form has been outstanding for three weeks",
                "Two new intent signals landed on Apex Logistics",
            ]),
            "next_steps": json.dumps([
                "Escalate the Quantum Edge order form to procurement",
                "Build a save plan for Vortex before the 14:00 review",
            ]),
            "outcome": "Advanced",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([REP_PERSONA_ID, MANAGER_PERSONA_ID, "USR-3016"]),
        },
        {
            "meeting_id": "MTG-9002", "account_id": SECOND_ACCOUNT, "deal_id": SECOND_DEAL,
            "organizer_id": REP_PERSONA_ID,
            "title": "Apex Logistics / Intellia Technical Validation", "meeting_type": "Technical Validation",
            "scheduled_start": ts(base + timedelta(hours=11)),
            "scheduled_end": ts(base + timedelta(hours=11, minutes=45)),
            "duration_minutes": 45, "location": "Zoom", "status": "Completed",
            "agenda": "Validate the Snowflake connector and custom signal mapping",
            "summary": "Data team confirmed incremental sync meets their requirement. One open question on retention policy.",
            "key_points": json.dumps([
                "Incremental sync satisfies the data team's main objection",
                "Retention policy needs a written answer before security sign-off",
                "Sponsor wants the expansion scoped to two additional regions",
            ]),
            "next_steps": json.dumps([
                "Send the retention policy answer to the security reviewer",
                "Scope the two-region expansion in the proposal",
            ]),
            "outcome": "Advanced",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([REP_PERSONA_ID, "USR-3016"]),
        },
        {
            "meeting_id": "MTG-9003", "account_id": HERO_ACCOUNT, "deal_id": HERO_DEAL,
            "organizer_id": REP_PERSONA_ID,
            "title": "Vortex Analytics / Renewal Risk Review", "meeting_type": "Renewal Review",
            "scheduled_start": ts(base + timedelta(hours=14)),
            "scheduled_end": ts(base + timedelta(hours=15)),
            "duration_minutes": 60, "location": "Zoom", "status": "Scheduled",
            "agenda": "Renewal scope, procurement concern and the executive sponsor question",
            "summary": "", "key_points": "[]", "next_steps": "[]", "outcome": "",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([REP_PERSONA_ID, MANAGER_PERSONA_ID]),
        },
        {
            "meeting_id": "MTG-9004", "account_id": "ACC-1011", "deal_id": THIRD_DEAL,
            "organizer_id": REP_PERSONA_ID,
            "title": "Quantum Edge / Close Call", "meeting_type": "Negotiation",
            "scheduled_start": ts(base + timedelta(hours=16)),
            "scheduled_end": ts(base + timedelta(hours=16, minutes=30)),
            "duration_minutes": 30, "location": "Zoom", "status": "Scheduled",
            "agenda": "Confirm the signing path and close date for the order form",
            "summary": "", "key_points": "[]", "next_steps": "[]", "outcome": "",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([REP_PERSONA_ID]),
        },
        # -- the manager persona's own day -------------------------------------------
        {
            "meeting_id": "MTG-9005", "account_id": "", "deal_id": "",
            "organizer_id": MANAGER_PERSONA_ID,
            "title": "Q3 Forecast Review", "meeting_type": "Internal Sync",
            "scheduled_start": ts(base + timedelta(hours=8, minutes=30)),
            "scheduled_end": ts(base + timedelta(hours=9, minutes=15)),
            "duration_minutes": 45, "location": "Microsoft Teams", "status": "Completed",
            "agenda": "Walk the team's commit and identify slipping deals",
            "summary": "Commit is short of target with six weeks left. Two deals moved out of Q3.",
            "key_points": json.dumps([
                "Team commit sits below the Q3 target with six weeks remaining",
                "Vortex and Quantum Edge are the two swing deals",
                "Coverage is thin on two of the five reps",
            ]),
            "next_steps": json.dumps([
                "Inspect the two swing deals with their owners",
                "Rebalance late-quarter pipeline generation targets",
            ]),
            "outcome": "Advanced",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([MANAGER_PERSONA_ID, REP_PERSONA_ID,
                                             "USR-3001", "USR-3005"]),
        },
        {
            "meeting_id": "MTG-9006", "account_id": HERO_ACCOUNT, "deal_id": HERO_DEAL,
            "organizer_id": MANAGER_PERSONA_ID,
            "title": "Deal Inspection: Vortex Analytics", "meeting_type": "Internal Sync",
            "scheduled_start": ts(base + timedelta(hours=13)),
            "scheduled_end": ts(base + timedelta(hours=13, minutes=30)),
            "duration_minutes": 30, "location": "Microsoft Teams", "status": "Scheduled",
            "agenda": "Review the save plan with Elena before the 14:00 customer call",
            "summary": "", "key_points": "[]", "next_steps": "[]", "outcome": "",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([MANAGER_PERSONA_ID, REP_PERSONA_ID]),
        },
        {
            "meeting_id": "MTG-9007", "account_id": "", "deal_id": "",
            "organizer_id": MANAGER_PERSONA_ID,
            "title": "1:1 with Robert Jackson", "meeting_type": "Internal Sync",
            "scheduled_start": ts(base + timedelta(hours=15, minutes=30)),
            "scheduled_end": ts(base + timedelta(hours=16)),
            "duration_minutes": 30, "location": "Microsoft Teams", "status": "Scheduled",
            "agenda": "Coaching on early-stage qualification and pipeline generation",
            "summary": "", "key_points": "[]", "next_steps": "[]", "outcome": "",
            "attendee_contact_ids": "[]",
            "attendee_user_ids": json.dumps([MANAGER_PERSONA_ID, "USR-3005"]),
        },
    ]
    return pd.concat([meetings, pd.DataFrame(rows)], ignore_index=True)


# --------------------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------------------

def build_signals(accounts: pd.DataFrame, contacts: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("signals")
    contacts_by_acc: Dict[str, List[str]] = {}
    for _, c in contacts.iterrows():
        contacts_by_acc.setdefault(c["account_id"], []).append(c["contact_id"])

    rows, sid = [], 7000
    acc_records = accounts.to_dict("records")
    for i in range(200):
        sid += 1
        acc = acc_records[i % len(acc_records)]
        stype = r.choice(SIGNAL_TYPES)
        # Weight recent signals heavily so "what changed" has something to say.
        days_ago = r.choice([r.randint(0, 13)] * 3 + [r.randint(14, 120)])
        detected = datetime.combine(REPORTING_DATE - timedelta(days=days_ago),
                                    datetime.min.time()) + timedelta(hours=r.randint(7, 19))
        score = r.randint(58, 98)
        status = "New" if days_ago <= 14 and r.random() < 0.85 else r.choice(["Actioned", "Dismissed", "New"])
        rows.append({
            "signal_id": "SIG-{}".format(sid),
            "account_id": acc["account_id"],
            "contact_id": r.choice(contacts_by_acc[acc["account_id"]]) if r.random() < 0.5
                and contacts_by_acc.get(acc["account_id"]) else "",
            "owner_id": acc["owner_id"],
            "signal_type": stype,
            "playbook": SIGNAL_PLAYBOOK[stype],
            "signal_title": r.choice(SIGNAL_TITLES[stype]),
            "severity": "High" if score >= 85 else "Medium" if score >= 70 else "Low",
            "score": score,
            "status": status,
            "detected_at": ts(detected),
            "expires_at": d(REPORTING_DATE + timedelta(days=r.randint(5, 60))),
            "action_recommended": SIGNAL_ACTIONS[stype],
            "source_url": "https://signals.intellia.ai/{}".format("SIG-{}".format(sid).lower()),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Tasks and targets
# --------------------------------------------------------------------------------------

def build_tasks(accounts: pd.DataFrame, deals: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    r = rng_for("tasks")
    reps = selling_users(users)
    deal_records = deals.to_dict("records")
    rows, tid = [], 9000
    for i in range(180):
        tid += 1
        dl = deal_records[i % len(deal_records)]
        owner = dl["owner_id"] if r.random() < 0.8 else r.choice(reps)
        due = REPORTING_DATE + timedelta(days=r.randint(-12, 25))
        status = "Done" if due < REPORTING_DATE and r.random() < 0.55 else \
            r.choice(["Open", "Open", "In Progress"])
        rows.append({
            "task_id": "TSK-{}".format(tid),
            "account_id": dl["account_id"],
            "deal_id": dl["deal_id"],
            "owner_id": owner,
            "title": r.choice(TASK_TITLES),
            "description": "Linked to {}.".format(dl["deal_name"]),
            "due_date": d(due),
            "priority": r.choice(["High", "Medium", "Medium", "Low"]),
            "status": status,
            "source": r.choice(["meeting", "email", "signal", "manual"]),
            "created_at": d(due - timedelta(days=r.randint(2, 20))),
            "completed_at": d(due) if status == "Done" else "",
        })

    # Guarantee the rep persona has a full, partly-overdue queue.
    narrative = [
        ("Draft the renewal save plan for Vortex Analytics", HERO_ACCOUNT, HERO_DEAL, -1, "High", "meeting"),
        ("Send the retention policy answer to Apex security", SECOND_ACCOUNT, SECOND_DEAL, 0, "High", "meeting"),
        ("Chase the Quantum Edge signed order form", "ACC-1011", THIRD_DEAL, -3, "High", "email"),
        ("Share the ROI model with Vortex finance", HERO_ACCOUNT, HERO_DEAL, 1, "Medium", "email"),
        ("Log the competitive intel from the Clari mention", HERO_ACCOUNT, HERO_DEAL, 2, "Medium", "meeting"),
        ("Scope the two-region expansion in the Apex proposal", SECOND_ACCOUNT, SECOND_DEAL, 3, "Medium", "meeting"),
        ("Book the executive alignment call for Vortex", HERO_ACCOUNT, HERO_DEAL, 4, "High", "signal"),
        ("Prepare the Q3 commit review for James", "", "", 5, "Medium", "manual"),
    ]
    for title, acc_id, deal_id, offset, prio, src in narrative:
        tid += 1
        due = REPORTING_DATE + timedelta(days=offset)
        rows.append({
            "task_id": "TSK-{}".format(tid), "account_id": acc_id, "deal_id": deal_id,
            "owner_id": REP_PERSONA_ID, "title": title,
            "description": "Follow-up captured from today's work.",
            "due_date": d(due), "priority": prio, "status": "Open", "source": src,
            "created_at": d(due - timedelta(days=4)), "completed_at": "",
        })
    return pd.DataFrame(rows)


def build_targets(users: pd.DataFrame) -> pd.DataFrame:
    """Targets exist only for quota-carrying individual contributors.

    A manager's number is the roll-up of their team, so giving managers their own
    target row would double-count them against their own reps in every team metric.
    """
    rows = []
    quarters = [
        ("2026-Q1", date(2026, 1, 1), date(2026, 3, 31)),
        ("2026-Q2", date(2026, 4, 1), date(2026, 6, 30)),
        ("2026-Q3", date(2026, 7, 1), date(2026, 9, 30)),
        ("2026-Q4", date(2026, 10, 1), date(2026, 12, 31)),
    ]
    tid = 0
    for _, u in users.iterrows():
        if u["quota_annual"] <= 0 or u["role"] not in SELLING_ROLES:
            continue
        for _, start, end in quarters:
            tid += 1
            rows.append({
                "target_id": "TGT-{}".format(1000 + tid),
                "user_id": u["user_id"],
                "period_type": "quarter",
                "period_start": d(start),
                "period_end": d(end),
                "metric": "bookings",
                "target_amount": int(u["quota_annual"] / 4),
            })
        tid += 1
        rows.append({
            "target_id": "TGT-{}".format(1000 + tid),
            "user_id": u["user_id"], "period_type": "year",
            "period_start": d(date(2026, 1, 1)), "period_end": d(date(2026, 12, 31)),
            "metric": "bookings", "target_amount": int(u["quota_annual"]),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Build + validate
# --------------------------------------------------------------------------------------

def build_dummy_data() -> Dict[str, pd.DataFrame]:
    users = build_users()
    accounts = build_accounts(users)
    contacts = build_contacts(accounts)
    deals = inject_narrative_deals(build_deals(accounts, users))
    emails = build_emails(accounts, contacts, deals, users)
    meetings = inject_narrative_meetings(build_meetings(accounts, contacts, deals, users))
    signals = build_signals(accounts, contacts, users)
    tasks = build_tasks(accounts, deals, users)
    targets = build_targets(users)
    return {
        "users": users, "accounts": accounts, "contacts": contacts, "deals": deals,
        "emails": emails, "meetings": meetings, "signals": signals, "tasks": tasks,
        "targets": targets,
    }


def validate(data: Dict[str, pd.DataFrame]) -> List[str]:
    """Assert every invariant the application depends on. Returns the report lines."""
    report: List[str] = []
    failures: List[str] = []

    def check(label: str, actual: Any, ok: bool) -> None:
        report.append("{:<52} {:>10}  {}".format(label, str(actual), "OK" if ok else "FAIL"))
        if not ok:
            failures.append(label)

    deals, users, meetings = data["deals"], data["users"], data["meetings"]
    contacts, tasks, signals = data["contacts"], data["tasks"], data["signals"]

    close = pd.to_datetime(deals["close_date"]).dt.date
    created = pd.to_datetime(deals["created_date"])
    won = deals["stage"] == "Stage 5 - Closed Won"
    lost = deals["stage"] == "Stage 5 - Closed Lost"
    is_open = ~deals["stage"].isin(CLOSED_STAGES)

    q3 = (close >= Q3_START) & (close <= Q3_END)
    check("deals closing in Q3 2026", int(q3.sum()), q3.sum() >= 20)
    check("open pipeline deals closing in Q3", int((q3 & is_open).sum()), (q3 & is_open).sum() >= 10)

    ytd = (close >= YTD_START) & (close <= REPORTING_DATE)
    check("closed-won YTD", int((ytd & won).sum()), (ytd & won).sum() >= 25)
    check("closed deals YTD (win-rate denominator)", int((ytd & (won | lost)).sum()),
          (ytd & (won | lost)).sum() >= 40)

    months = sorted(created.dt.strftime("%Y-%m").unique())
    expected_months = [m.strftime("%Y-%m") for m in month_starts(HISTORY_START, REPORTING_DATE)]
    missing = [m for m in expected_months if m not in months]
    check("created_date month coverage (no gaps)", "{}/{}".format(len(expected_months) - len(missing),
                                                                 len(expected_months)), not missing)

    check("Renewal deals", int((deals["deal_type"] == "Renewal").sum()),
          (deals["deal_type"] == "Renewal").sum() >= 10)
    check("Upsell deals", int((deals["deal_type"] == "Upsell").sum()),
          (deals["deal_type"] == "Upsell").sum() >= 15)
    check("distinct deal owners", deals["owner_id"].nunique(), deals["owner_id"].nunique() >= 10)

    elena = deals[deals["owner_id"] == REP_PERSONA_ID]
    check("rep persona deal count", len(elena), len(elena) >= 15)
    check("rep persona open deals", int((~elena["stage"].isin(CLOSED_STAGES)).sum()),
          (~elena["stage"].isin(CLOSED_STAGES)).sum() >= 6)

    reports = users[users["manager_id"] == MANAGER_PERSONA_ID]
    selling_reports = reports[reports["role"].isin(SELLING_ROLES)]
    check("manager persona direct reports (all)", len(reports), len(reports) >= 5)
    check("manager persona selling reports", len(selling_reports), len(selling_reports) == 5)
    check("rep persona reports to manager",
          users.loc[users["user_id"] == REP_PERSONA_ID, "manager_id"].iloc[0],
          users.loc[users["user_id"] == REP_PERSONA_ID, "manager_id"].iloc[0] == MANAGER_PERSONA_ID)

    today_meets = meetings[
        (pd.to_datetime(meetings["scheduled_start"]).dt.date == REPORTING_DATE)
        & (meetings["organizer_id"] == REP_PERSONA_ID)]
    check("rep meetings on reporting date", len(today_meets), len(today_meets) >= 4)
    check("  of which completed (with summaries)",
          int((today_meets["status"] == "Completed").sum()),
          (today_meets["status"] == "Completed").sum() >= 2)

    mgr_meets = meetings[
        (pd.to_datetime(meetings["scheduled_start"]).dt.date == REPORTING_DATE)
        & (meetings["organizer_id"] == MANAGER_PERSONA_ID)]
    check("manager meetings on reporting date", len(mgr_meets), len(mgr_meets) >= 3)

    seller_targets = data["targets"]["user_id"].nunique()
    sellers = len(users[users["role"].isin(SELLING_ROLES)])
    check("targets cover every seller (and only sellers)",
          "{}/{}".format(seller_targets, sellers), seller_targets == sellers)

    check("is_champion is integer 0/1", sorted(contacts["is_champion"].unique().tolist()),
          set(contacts["is_champion"].unique()) <= {0, 1})
    check("accounts with a champion", int(contacts.groupby("account_id")["is_champion"].max().sum()),
          contacts.groupby("account_id")["is_champion"].max().sum() >= 25)

    recent_sig = pd.to_datetime(signals["detected_at"]).dt.date >= REPORTING_DATE - timedelta(days=14)
    check("signals in last 14 days", int(recent_sig.sum()), recent_sig.sum() >= 30)
    check("high-score signals (>=80)", int((signals["score"] >= 80).sum()),
          (signals["score"] >= 80).sum() >= 12)

    rep_tasks = tasks[(tasks["owner_id"] == REP_PERSONA_ID) & (tasks["status"] != "Done")]
    check("rep persona open tasks", len(rep_tasks), len(rep_tasks) >= 8)
    overdue = pd.to_datetime(rep_tasks["due_date"]).dt.date < REPORTING_DATE
    check("  of which overdue", int(overdue.sum()), overdue.sum() >= 1)

    check("targets rows", len(data["targets"]), len(data["targets"]) >= 40)

    if failures:
        raise AssertionError("Seed invariants failed:\n  - " + "\n  - ".join(failures))
    return report


COLUMN_ORDER = {
    "users": ["user_id", "full_name", "email", "role", "department", "manager_id", "region",
              "quota_annual", "hire_date", "is_active"],
    "accounts": ["account_id", "account_name", "domain", "industry", "region", "segment", "tier",
                 "status", "arr", "employee_count", "owner_id", "renewal_date", "health_score",
                 "created_at"],
    "contacts": ["contact_id", "account_id", "first_name", "last_name", "email", "title",
                 "persona_role", "seniority", "influence", "is_champion", "last_contacted_at",
                 "created_at"],
    "deals": ["deal_id", "account_id", "owner_id", "deal_name", "deal_type", "stage", "amount",
              "probability", "forecast_category", "close_date", "created_date", "stage_entered_at",
              "last_activity_date", "next_step", "next_step_due_date", "competitor", "source",
              "win_loss_reason"],
    "emails": ["email_id", "thread_id", "account_id", "contact_id", "deal_id", "sender_email",
               "recipient_email", "direction", "subject", "snippet", "body", "is_reply",
               "has_attachment", "sent_at", "sentiment_score"],
    "meetings": ["meeting_id", "account_id", "deal_id", "organizer_id", "title", "meeting_type",
                 "scheduled_start", "scheduled_end", "duration_minutes", "location", "status",
                 "agenda", "summary", "key_points", "next_steps", "outcome",
                 "attendee_contact_ids", "attendee_user_ids"],
    "signals": ["signal_id", "account_id", "contact_id", "owner_id", "signal_type", "playbook",
                "signal_title", "severity", "score", "status", "detected_at", "expires_at",
                "action_recommended", "source_url"],
    "tasks": ["task_id", "account_id", "deal_id", "owner_id", "title", "description", "due_date",
              "priority", "status", "source", "created_at", "completed_at"],
    "targets": ["target_id", "user_id", "period_type", "period_start", "period_end", "metric",
                "target_amount"],
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Intellia seed data.")
    parser.add_argument("--dry-run", action="store_true", help="validate only, write nothing")
    parser.add_argument("--out", default=str(OUTPUT_DIR), help="output directory")
    args = parser.parse_args(argv)

    data = build_dummy_data()
    report = validate(data)

    print("Intellia seed data, reporting date {}\n".format(REPORTING_DATE))
    print("\n".join(report))
    print("\nRow counts:")
    for name, df in data.items():
        print("  {:<12} {:>6}".format(name, len(df)))

    if args.dry_run:
        print("\nDry run, nothing written.")
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        df[COLUMN_ORDER[name]].to_csv(out / "{}.csv".format(name), index=False)
    print("\nWrote {} CSVs to {}".format(len(data), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

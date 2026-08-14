"""Outreach playbooks, parsed from Knowledge/brain.md.

The company already documents five playbooks whose triggers map onto the signal
types in the data, so action recommendations and email drafts are deterministic
template fills -- the LLM only personalizes. That keeps the expensive path narrow.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, Optional

from intellia.ai.prompts.knowledge import company_context

# The generator normalizes signal_type -> playbook name, but keep a defensive map.
SIGNAL_TO_PLAYBOOK = {
    "Intent Score": "Intent Spike",
    "Intent Spike": "Intent Spike",
    "Hiring Surge": "Intent Spike",
    "Champion Movement": "Champion Movement",
    "Executive Departure": "Executive Change",
    "Executive Change": "Executive Change",
    "M&A Event": "M&A Event",
    "Funding Round": "M&A Event",
    "Stalled Deal": "Stalled Deal",
}


@lru_cache(maxsize=1)
def _playbooks() -> Dict[str, str]:
    """Split brain.md's '### <Name> Playbook' sections."""
    text = company_context()
    if not text:
        return {}
    out: Dict[str, str] = {}
    pattern = re.compile(r"^### (.+?) Playbook\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match.group(1).strip()] = text[match.end():end].strip()
    return out


def playbook_for(signal_type: str) -> Optional[str]:
    name = SIGNAL_TO_PLAYBOOK.get(signal_type, signal_type)
    return _playbooks().get(name)


def sample_message(signal_type: str) -> Optional[str]:
    """The playbook's 'Sample message' block, with {{first_name}} still in place."""
    body = playbook_for(signal_type)
    if not body:
        return None
    marker = "Sample message:"
    if marker not in body:
        return None
    return body.split(marker, 1)[1].strip()


def render_template(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{%s}}" % key, value)
    return out

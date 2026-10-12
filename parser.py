"""Discovery and parsing of agents.md / AGENTS.md swarm configurations."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CANDIDATE_FILENAMES = ("AGENTS.override.md", "agents.md", "AGENTS.md")

# Generic document/structural headings that are NOT individual agent definitions
_NON_AGENT_HEADINGS = frozenset({
    "agents",
    "agent configuration",
    "agent configs",
    "swarm",
    "myswarm",
    "overview",
    "introduction",
    "summary",
    "architecture",
    "workflow",
    "rules",
    "guidelines",
    "conventions",
    "testing",
    "tests",
    "setup",
    "installation",
    "configuration",
    "context",
    "project context",
    "notes",
    "shared memory",
    "communication",
    "handoffs",
    "tools",
    "environment",
})


@dataclass
class AgentSpec:
    """Normalized representation of a single agent's persona, goal, and topology links."""

    name: str
    persona: str
    goal: str
    role_type: str = "specialist"  # "orchestrator" | "specialist"
    delegates_to: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SwarmConfig:
    """Parsed swarm configuration from an agents.md file."""

    source_path: Optional[str]
    title: str
    agents: List[AgentSpec] = field(default_factory=list)
    raw_content: str = ""
    parse_method: str = "markdown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": self.source_path,
            "title": self.title,
            "agent_count": len(self.agents),
            "parse_method": self.parse_method,
            "agents": [a.to_dict() for a in self.agents],
        }


def resolve_agents_file(
    path_or_dir: Optional[str | Path] = None,
    *,
    allow_file: bool = True,
) -> Tuple[Optional[Path], Path]:
    """Locate the active agents.md file in *path_or_dir* (preserving exact on-disk casing on macOS).

    When ``allow_file=False``, *path_or_dir* must be a directory (file paths are rejected).
    Returns ``(resolved_file_or_None, workspace_dir)``.
    """
    target = Path(path_or_dir).expanduser().resolve() if path_or_dir else Path.cwd().resolve()
    if target.is_file():
        if not allow_file:
            raise ValueError(f"Target workspace path must be a directory, not a file: {target}")
        return target, target.parent

    workspace_dir = target
    if workspace_dir.exists() and not workspace_dir.is_dir():
        raise ValueError(f"Target workspace path is not a directory: {workspace_dir}")
    if not workspace_dir.is_dir():
        return None, workspace_dir

    try:
        entries = {entry: entry for entry in os.listdir(workspace_dir)}
        lower_map = {entry.lower(): entry for entry in entries}
    except OSError:
        return None, workspace_dir

    # First check exact candidate order, then case-insensitive fallback
    for candidate in CANDIDATE_FILENAMES:
        if candidate in entries:
            full = workspace_dir / entries[candidate]
            if full.is_file():
                return full, workspace_dir

    for candidate in CANDIDATE_FILENAMES:
        actual_name = lower_map.get(candidate.lower())
        if actual_name:
            full = workspace_dir / actual_name
            if full.is_file():
                return full, workspace_dir

    return None, workspace_dir


def abbreviate_text(text: str, max_chars: int = 220) -> str:
    """Collapse whitespace/markdown formatting and truncate cleanly at word boundaries."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = re.sub(r"^[\-\*\•\>\#\s]+", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    # Only clip to first sentence when a short single-line summary is explicitly requested
    if max_chars <= 80:
        first_sent = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
        if 12 <= len(first_sent) <= max_chars:
            cleaned = first_sent.rstrip(".")
    if len(cleaned) <= max_chars:
        return cleaned.rstrip(".") if cleaned else "Unspecified"
    cut = cleaned[: max_chars - 1].rsplit(" ", 1)[0]
    return (cut or cleaned[: max_chars - 1]).rstrip(".,;:") + "…"


def _clean_agent_name(raw_heading: str) -> str:
    """Extract a clean agent name from a markdown heading."""
    text = raw_heading.strip().lstrip("#").strip()
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    text = re.sub(r"^(?:agent|role|persona|bot|specialist|worker)\s*[:\-–—]\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("`", "").strip()
    # If heading has "Name — Subtitle" or "Name (Role)", keep the primary name
    for sep in (" — ", " – ", " - ", ": "):
        if sep in text:
            left, _right = text.split(sep, 1)
            if 2 <= len(left.strip()) <= 36:
                return left.strip()
    return text[:40].strip()


def _infer_role_type(name: str, persona: str, goal: str, delegates_to: List[str]) -> str:
    combined = f"{name} {persona} {goal}".lower()
    if delegates_to or any(
        kw in combined
        for kw in ("orchestrat", "coordinator", "lead", "manager", "router", "supervisor", "dispatcher", "chief")
    ):
        return "orchestrator"
    return "specialist"


def _parse_list_field(raw: str) -> List[str]:
    items = re.split(r"[,;/]|\band\b", raw)
    out = []
    for item in items:
        cleaned = item.strip().strip("`*_-[]()\"'")
        if cleaned and cleaned.lower() not in {"none", "n/a", "-"}:
            out.append(cleaned)
    return out


def _parse_markdown_tables(content: str) -> List[AgentSpec]:
    """Extract agents from Markdown tables with Agent/Name, Persona/Role, and Goal/Objective columns."""
    agents: List[AgentSpec] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines) - 2:
        line = lines[i].strip()
        sep_line = lines[i + 1].strip()
        if line.startswith("|") and line.endswith("|") and re.match(r"^\|[\s\-\:\|]+\|$", sep_line):
            headers = [h.strip().lower().strip("*_") for h in line.strip("|").split("|")]
            name_idx = next(
                (idx for idx, h in enumerate(headers) if any(k in h for k in ("agent", "name", "id", "bot"))),
                None,
            )
            persona_idx = next(
                (idx for idx, h in enumerate(headers) if any(k in h for k in ("persona", "role", "character", "style", "identity", "vibe"))),
                None,
            )
            goal_idx = next(
                (idx for idx, h in enumerate(headers) if any(k in h for k in ("goal", "objective", "mission", "purpose", "task", "responsibilit"))),
                None,
            )
            delegates_idx = next(
                (idx for idx, h in enumerate(headers) if any(k in h for k in ("delegate", "subagent", "routes", "calls", "handoff"))),
                None,
            )
            if name_idx is not None and (persona_idx is not None or goal_idx is not None):
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    if len(cells) > name_idx:
                        name = _clean_agent_name(cells[name_idx])
                        persona = cells[persona_idx] if (persona_idx is not None and persona_idx < len(cells)) else "Specialized autonomous agent"
                        goal = cells[goal_idx] if (goal_idx is not None and goal_idx < len(cells)) else persona
                        delegates = (
                            _parse_list_field(cells[delegates_idx])
                            if (delegates_idx is not None and delegates_idx < len(cells))
                            else []
                        )
                        if name and name.lower() not in {"agent", "name", "---"}:
                            role_type = _infer_role_type(name, persona, goal, delegates)
                            agents.append(
                                AgentSpec(
                                    name=name,
                                    persona=abbreviate_text(persona),
                                    goal=abbreviate_text(goal),
                                    role_type=role_type,
                                    delegates_to=delegates,
                                )
                            )
                    i += 1
                continue
        i += 1
    return agents


_KV_PERSONA_RE = re.compile(
    r"^(?:[\-\*\•]\s*)?(?:\*\*|__)?(?:persona|personality|role|character|archetype|identity|style|tone|who)(?:\*\*|__)?\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)
_KV_GOAL_RE = re.compile(
    r"^(?:[\-\*\•]\s*)?(?:\*\*|__)?(?:goal|goals|objective|objectives|mission|purpose|responsibility|responsibilities|focus|duty|task)(?:\*\*|__)?\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)
_KV_DELEGATES_RE = re.compile(
    r"^(?:[\-\*\•]\s*)?(?:\*\*|__)?(?:delegates?\s*to|subagents?|handoffs?|routes?\s*to|collaborates?\s*with|calls)(?:\*\*|__)?\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)
_KV_TOOLS_RE = re.compile(
    r"^(?:[\-\*\•]\s*)?(?:\*\*|__)?(?:tools?|toolsets?|capabilities)(?:\*\*|__)?\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)


def _parse_markdown_sections(content: str) -> List[AgentSpec]:
    """Parse H2/H3/H4 agent sections from Markdown."""
    # Strip HTML comments before parsing
    cleaned_content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    heading_re = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(cleaned_content))
    if not matches:
        return []

    agents: List[AgentSpec] = []
    for idx, match in enumerate(matches):
        level = len(match.group(1))
        raw_title = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned_content)
        body = cleaned_content[start:end].strip()

        # Skip top-level H1 unless it explicitly says "Agent:"
        if level == 1 and not re.match(r"^agent\s*[:\-]", raw_title, re.IGNORECASE):
            continue

        clean_title_lower = re.sub(r"[^a-z0-9\s]", "", raw_title.lower()).strip()
        if clean_title_lower in _NON_AGENT_HEADINGS:
            continue

        # Check if heading has subtitle e.g. "## Sentinel — Security & Privacy Auditor"
        subtitle_persona = ""
        for sep in (" — ", " – ", " - ", ": "):
            if sep in raw_title and not re.match(r"^(?:agent|role|persona)\s*:", raw_title, re.IGNORECASE):
                _left, right = raw_title.split(sep, 1)
                subtitle_persona = right.strip()
                break

        name = _clean_agent_name(raw_title)
        if not name or name.lower() in _NON_AGENT_HEADINGS:
            continue

        persona_lines: List[str] = []
        goal_lines: List[str] = []
        delegates: List[str] = []
        tools: List[str] = []
        prose_lines: List[str] = []

        active_bucket: Optional[List[str]] = None
        for raw_line in body.splitlines():
            sline = raw_line.strip()
            if not sline or sline.startswith("```"):
                active_bucket = None
                continue
            # Skip markdown table lines inside a section
            if sline.startswith("|"):
                continue

            m_p = _KV_PERSONA_RE.match(sline)
            if m_p:
                val = m_p.group(1).strip()
                if val:
                    persona_lines.append(val)
                active_bucket = persona_lines
                continue

            m_g = _KV_GOAL_RE.match(sline)
            if m_g:
                val = m_g.group(1).strip()
                if val:
                    goal_lines.append(val)
                active_bucket = goal_lines
                continue

            m_d = _KV_DELEGATES_RE.match(sline)
            if m_d:
                delegates.extend(_parse_list_field(m_d.group(1)))
                active_bucket = None
                continue

            m_t = _KV_TOOLS_RE.match(sline)
            if m_t:
                tools.extend(_parse_list_field(m_t.group(1)))
                active_bucket = None
                continue

            # Sub-bullets under a Persona: or Goal: header
            if active_bucket is not None and re.match(r"^[\-\*\•]\s+", sline):
                active_bucket.append(re.sub(r"^[\-\*\•]\s+", "", sline))
                continue

            prose_lines.append(sline)

        # Only treat section as an agent if it has explicit persona/goal fields OR looks like an agent section
        has_explicit_fields = bool(persona_lines or goal_lines or subtitle_persona)
        has_agent_keywords = bool(
            re.search(r"\b(you are|act as|persona|goal|objective|responsible for|specialist|agent|auditor|architect|researcher|engineer|writer|reviewer|planner)\b", body, re.IGNORECASE)
        )
        if not has_explicit_fields and not has_agent_keywords:
            continue

        persona_raw = (
            " ".join(persona_lines)
            or subtitle_persona
            or (prose_lines[0] if prose_lines else "Specialized swarm agent")
        )
        if goal_lines:
            goal_raw = " ".join(goal_lines)
        elif len(prose_lines) >= 2:
            goal_raw = prose_lines[1]
        elif prose_lines and persona_lines:
            goal_raw = prose_lines[0]
        elif prose_lines:
            goal_raw = prose_lines[0]
        else:
            goal_raw = subtitle_persona or "Execute assigned domain tasks"

        role_type = _infer_role_type(name, persona_raw, goal_raw, delegates)
        agents.append(
            AgentSpec(
                name=name,
                persona=abbreviate_text(persona_raw),
                goal=abbreviate_text(goal_raw),
                role_type=role_type,
                delegates_to=delegates,
                tools=tools,
            )
        )

    return agents


def _parse_bullet_agents(content: str) -> List[AgentSpec]:
    """Fallback parser for bullet-list agent definitions: `- **AgentName** (Persona): Goal`."""
    agents: List[AgentSpec] = []
    bullet_re = re.compile(
        r"^[\-\*\•]\s+\*\*([A-Za-z0-9_\-\s]{2,35})\*\*\s*(?:\(([^)]+)\))?\s*[:\-–—]\s*(.+)$",
        re.MULTILINE,
    )
    for match in bullet_re.finditer(content):
        key = match.group(1).strip()
        if key.lower() in {
            "persona", "goal", "goals", "role", "objective", "tools", "delegates to",
            "note", "warning", "important", "input", "output", "style",
        }:
            continue
        paren_persona = (match.group(2) or "").strip()
        rest = match.group(3).strip()
        if paren_persona:
            persona = paren_persona
            goal = rest
        elif " — " in rest or "; " in rest:
            parts = re.split(r"\s+—\s+|;\s+", rest, maxsplit=1)
            persona, goal = parts[0], parts[1]
        else:
            persona = f"{key} specialist"
            goal = rest
        agents.append(
            AgentSpec(
                name=key,
                persona=abbreviate_text(persona),
                goal=abbreviate_text(goal),
                role_type=_infer_role_type(key, persona, goal, []),
            )
        )
    return agents


_LLM_PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "agents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "persona": {"type": "string"},
                    "goal": {"type": "string"},
                    "role_type": {"type": "string", "enum": ["orchestrator", "specialist"]},
                    "delegates_to": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "persona", "goal"],
            },
        },
    },
    "required": ["agents"],
}


_ASCII_TITLE_RE = re.compile(r"\|\s*MYSWARM\s*//\s*(.+?)\s*\(\d+\s*Agents?\)\s*\|", re.IGNORECASE)
_ASCII_AGENT_HEAD_RE = re.compile(
    r"^\|\s*\[[^\]]+\]\s+(.+?)\s+\[(ORCHESTRATOR|SPECIALIST)\]\s*\|$",
    re.IGNORECASE,
)
_ASCII_FIELD_RE = re.compile(
    r"^\|\s*\*\s*(Persona|Goal|Routes)\s*:\s*(?:===>\s*)?(.+?)\s*\|$",
    re.IGNORECASE,
)
_ASCII_CONT_RE = re.compile(r"^\|\s{6,}([^\|\*].*?)\s*\|$")


def _parse_ascii_swarm_block(content: str) -> Optional[Tuple[str, List[AgentSpec]]]:
    """Parse a shared MySwarm copy-paste ASCII block back into (title, agents)."""
    if "MYSWARM //" not in content and "[Shared via Hermes MySwarm Plugin" not in content:
        return None

    title = "MySwarm Agent Configuration"
    tm = _ASCII_TITLE_RE.search(content)
    if tm:
        title = tm.group(1).strip()

    agents: List[AgentSpec] = []
    current_name: Optional[str] = None
    current_role: str = "specialist"
    current_persona: str = ""
    current_goal: str = ""
    current_routes: List[str] = []
    active_field: Optional[str] = None

    def _flush() -> None:
        nonlocal current_name, current_role, current_persona, current_goal, current_routes, active_field
        if current_name:
            agents.append(
                AgentSpec(
                    name=current_name,
                    persona=current_persona or f"{current_name} specialist",
                    goal=current_goal or f"Execute {current_name} tasks",
                    role_type=current_role,
                    delegates_to=list(current_routes),
                )
            )
        current_name = None
        current_role = "specialist"
        current_persona = ""
        current_goal = ""
        current_routes = []
        active_field = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("+"):
            active_field = None
            continue
        hm = _ASCII_AGENT_HEAD_RE.match(line)
        if hm:
            _flush()
            current_name = hm.group(1).strip()
            current_role = "orchestrator" if hm.group(2).upper() == "ORCHESTRATOR" else "specialist"
            continue

        fm = _ASCII_FIELD_RE.match(line)
        if fm and current_name:
            field_kind = fm.group(1).lower()
            val = fm.group(2).strip()
            active_field = field_kind
            if field_kind == "persona":
                current_persona = val
            elif field_kind == "goal":
                current_goal = val
            elif field_kind == "routes":
                current_routes = [x.strip() for x in val.split(",") if x.strip()]
            continue

        cm = _ASCII_CONT_RE.match(line)
        if cm and current_name and active_field:
            cont_val = cm.group(1).strip()
            if cont_val:
                if active_field == "persona":
                    current_persona = f"{current_persona} {cont_val}".strip()
                elif active_field == "goal":
                    current_goal = f"{current_goal} {cont_val}".strip()
                elif active_field == "routes":
                    extra_routes = [x.strip() for x in cont_val.split(",") if x.strip()]
                    current_routes.extend(extra_routes)

    _flush()
    if not agents:
        return None
    return title, agents


def swarm_config_to_markdown(config: SwarmConfig) -> str:
    """Convert a SwarmConfig (e.g., parsed from a shared Copy-Paste ASCII block) into canonical agents.md Markdown."""
    lines: List[str] = [
        f"<!-- Exported via Hermes MySwarm Plugin | Agents: {len(config.agents)} -->",
        f"# {config.title}",
        "",
    ]
    for agent in config.agents:
        lines.append(f"## {agent.name}")
        role_label = "Orchestrator" if agent.role_type == "orchestrator" else "Specialist"
        lines.append(f"- **Role**: {role_label}")
        lines.append(f"- **Persona**: {agent.persona}")
        lines.append(f"- **Goal**: {agent.goal}")
        if agent.delegates_to:
            lines.append(f"- **Delegates to**: {', '.join(agent.delegates_to)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_agents_markdown(
    content: str,
    *,
    source_path: Optional[str] = None,
    llm: Optional[Any] = None,
    use_llm_fallback: bool = True,
) -> SwarmConfig:
    """Parse an agents.md string (or shared MySwarm ASCII block) into a structured SwarmConfig."""
    # 0. Check if input is a shared MySwarm Copy-Paste ASCII block
    ascii_parsed = _parse_ascii_swarm_block(content)
    if ascii_parsed is not None:
        ascii_title, ascii_agents = ascii_parsed
        return SwarmConfig(
            source_path=source_path,
            title=ascii_title,
            agents=ascii_agents,
            raw_content=content,
            parse_method="ascii_block",
        )

    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "MySwarm Agent Configuration"

    # 1. Try section-based parsing and table-based parsing
    section_agents = _parse_markdown_sections(content)
    table_agents = _parse_markdown_tables(content)

    # Merge or pick the richer set
    by_name: Dict[str, AgentSpec] = {}
    for a in table_agents + section_agents:
        key = a.name.lower()
        if key not in by_name:
            by_name[key] = a
        else:
            # Enrich existing entry
            existing = by_name[key]
            if existing.persona == "Specialized swarm agent" and a.persona:
                existing.persona = a.persona
            if a.delegates_to and not existing.delegates_to:
                existing.delegates_to = a.delegates_to
            if a.role_type == "orchestrator":
                existing.role_type = "orchestrator"

    agents = list(by_name.values())
    parse_method = "markdown"

    # 2. Try bullet-list agent definitions if none found yet
    if not agents:
        agents = _parse_bullet_agents(content)
        if agents:
            parse_method = "markdown_bullets"

    # 3. Try LLM structured extraction if freeform prose and llm is available
    if not agents and use_llm_fallback and llm is not None and content.strip():
        try:
            res = llm.complete_structured(
                instructions=(
                    "Extract all AI agents, personas, or roles described in this agents.md file. "
                    "For each agent provide a concise name, an abbreviated persona (<= 10 words), "
                    "an abbreviated goal (<= 12 words), whether its role_type is 'orchestrator' or 'specialist', "
                    "and any agent names it delegates_to."
                ),
                input=[{"type": "text", "text": content[:12000]}],
                json_schema=_LLM_PARSE_SCHEMA,
                json_mode=True,
                schema_name="myswarm_agents_parse",
                purpose="myswarm_parse_agents_md",
            )
            parsed = getattr(res, "parsed", None)
            if isinstance(parsed, dict) and isinstance(parsed.get("agents"), list):
                for item in parsed["agents"]:
                    if isinstance(item, dict) and item.get("name"):
                        agents.append(
                            AgentSpec(
                                name=str(item["name"]).strip()[:40],
                                persona=abbreviate_text(str(item.get("persona") or "Autonomous agent")),
                                goal=abbreviate_text(str(item.get("goal") or "Assist user with tasks")),
                                role_type="orchestrator" if item.get("role_type") == "orchestrator" else "specialist",
                                delegates_to=[str(x) for x in (item.get("delegates_to") or []) if x],
                            )
                        )
                if agents:
                    parse_method = "llm_structured"
        except Exception as exc:
            logger.debug("LLM fallback parsing skipped/failed: %s", exc)

    # 4. Final single-agent fallback if the file is a single monolithic persona/instruction file
    if not agents and content.strip():
        lines = [
            ln.strip()
            for ln in re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).splitlines()
            if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("```")
        ]
        first_line = lines[0] if lines else "Primary workspace agent"
        second_line = lines[1] if len(lines) > 1 else first_line
        agents = [
            AgentSpec(
                name=_clean_agent_name(title) if title != "MySwarm Agent Configuration" else "PrimaryAgent",
                persona=abbreviate_text(first_line),
                goal=abbreviate_text(second_line),
                role_type="orchestrator",
            )
        ]
        parse_method = "monolithic_fallback"

    return SwarmConfig(
        source_path=source_path,
        title=title,
        agents=agents,
        raw_content=content,
        parse_method=parse_method,
    )


def load_swarm_config(
    path_or_dir: Optional[str | Path] = None,
    *,
    llm: Optional[Any] = None,
    use_llm_fallback: bool = True,
) -> SwarmConfig:
    """Resolve and parse the workspace's agents.md into a SwarmConfig."""
    resolved_file, workspace_dir = resolve_agents_file(path_or_dir)
    if resolved_file is None or not resolved_file.is_file():
        raise FileNotFoundError(
            f"No agents.md (or AGENTS.md / AGENTS.override.md) found in {workspace_dir}"
        )
    content = resolved_file.read_text(encoding="utf-8", errors="replace")
    return parse_agents_markdown(
        content,
        source_path=str(resolved_file),
        llm=llm,
        use_llm_fallback=use_llm_fallback,
    )


def format_abbreviated_list(config: SwarmConfig) -> str:
    """Format an abbreviated table and list of agents, their personas, and their goals."""
    if not config.agents:
        return f"No agents found in {config.source_path or 'configuration'}."

    name_w = max(max(len(a.name) + 2 for a in config.agents), len("Agent"))
    persona_w = max(max(len(a.persona) for a in config.agents), len("Persona"))
    goal_w = max(max(len(a.goal) for a in config.agents), len("Goal"))

    # Clamp column widths for readable terminal rendering
    name_w = min(name_w, 24)
    persona_w = min(persona_w, 38)
    goal_w = min(goal_w, 44)

    def _fit(val: str, width: int) -> str:
        if len(val) > width:
            return val[: width - 1] + "…"
        return val.ljust(width)

    top = f"┌─{'─' * name_w}─┬─{'─' * persona_w}─┬─{'─' * goal_w}─┐"
    hdr = f"│ {_fit('Agent', name_w)} │ {_fit('Persona', persona_w)} │ {_fit('Goal', goal_w)} │"
    sep = f"├─{'─' * name_w}─┼─{'─' * persona_w}─┼─{'─' * goal_w}─┤"
    bot = f"└─{'─' * name_w}─┴─{'─' * persona_w}─┴─{'─' * goal_w}─┘"

    rows = [
        f"Swarm Config: {config.source_path or '(in-memory)'} ({len(config.agents)} agent{'s' if len(config.agents) != 1 else ''})",
        top,
        hdr,
        sep,
    ]
    for agent in config.agents:
        tag = "★ " if agent.role_type == "orchestrator" else "  "
        display_name = f"{tag}{agent.name}"
        rows.append(
            f"│ {_fit(display_name, name_w)} │ {_fit(agent.persona, persona_w)} │ {_fit(agent.goal, goal_w)} │"
        )
    rows.append(bot)
    rows.append("  (★ = Orchestrator / Coordinator)")
    return "\n".join(rows)

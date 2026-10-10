"""ASCII topology renderer, shareable copy-paste ASCII generator, SVG/image renderer, and LLM-guided themed image visualization for MySwarm."""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from .parser import AgentSpec, SwarmConfig, abbreviate_text
    from .sanitizer import sanitize_swarm_config
except ImportError:
    from parser import AgentSpec, SwarmConfig, abbreviate_text
    from sanitizer import sanitize_swarm_config

logger = logging.getLogger(__name__)

_BOX_CHARS = {
    "unicode": {
        "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
        "h": "─", "v": "│", "ml": "├", "mr": "┤",
        "down": "▼", "right": "►", "tee_d": "┬", "tee_u": "┴", "cross": "┼",
    },
    "ascii": {
        "tl": "+", "tr": "+", "bl": "+", "br": "+",
        "h": "-", "v": "|", "ml": "+", "mr": "+",
        "down": "v", "right": ">", "tee_d": "+", "tee_u": "+", "cross": "+",
    },
}


def _wrap_fixed(text: str, width: int) -> str:
    if len(text) > width:
        return text[: width - 1] + "…"
    return text.ljust(width)


def _wrap_fixed_pure_ascii(text: str, width: int) -> str:
    """Pure 7-bit ASCII fixed-width string formatter (uses '...' instead of Unicode ellipsis)."""
    ascii_clean = text.encode("ascii", errors="ignore").decode("ascii").strip()
    if len(ascii_clean) > width:
        if width > 3:
            return ascii_clean[: width - 3].rstrip() + "..."
        return ascii_clean[:width]
    return ascii_clean.ljust(width)


def _ascii_avatar_for_agent(agent: AgentSpec) -> str:
    """Return a pure-ASCII symbol icon representing the agent's role/persona."""
    if agent.role_type == "orchestrator":
        return r"[\^/]"
    blob = f"{agent.name} {agent.persona} {agent.goal}".lower()
    if any(k in blob for k in ("security", "audit", "guard", "aegis", "sentinel", "trust", "privacy")):
        return "[#!#]"
    if any(k in blob for k in ("code", "engineer", "dev", "build", "forge", "cipher", "rust", "python")):
        return "[{/}]"
    if any(k in blob for k in ("research", "search", "scout", "atlas", "data", "doc", "analy")):
        return "[?=?]"
    if any(k in blob for k in ("write", "creative", "story", "art", "design", "lyra", "maestro")):
        return "[~*~]"
    return "[o_o]"


def _render_agent_card(agent: AgentSpec, box_width: int, ch: Dict[str, str]) -> List[str]:
    """Render a single agent card of fixed *box_width* (total width = box_width + 2)."""
    inner = box_width
    badge = "[ORCHESTRATOR]" if agent.role_type == "orchestrator" else "[AGENT]"
    title_str = f"{badge} {agent.name}"
    p_str = f"Persona: {abbreviate_text(agent.persona, inner - 9)}"
    g_str = f"Goal   : {abbreviate_text(agent.goal, inner - 9)}"

    lines = [
        f"{ch['tl']}{ch['h'] * inner}{ch['tr']}",
        f"{ch['v']} {_wrap_fixed(title_str, inner - 2)} {ch['v']}",
        f"{ch['ml']}{ch['h'] * inner}{ch['mr']}",
        f"{ch['v']} {_wrap_fixed(p_str, inner - 2)} {ch['v']}",
        f"{ch['v']} {_wrap_fixed(g_str, inner - 2)} {ch['v']}",
    ]
    if agent.delegates_to:
        d_str = f"Routes : {', '.join(agent.delegates_to)}"
        lines.append(f"{ch['v']} {_wrap_fixed(d_str, inner - 2)} {ch['v']}")
    lines.append(f"{ch['bl']}{ch['h'] * inner}{ch['br']}")
    return lines


def _join_cards_horizontally(cards: List[List[str]], gap: int = 3) -> List[str]:
    """Place multiple agent cards side-by-side, padding shorter cards with spaces."""
    if not cards:
        return []
    max_h = max(len(c) for c in cards)
    widths = [len(c[0]) for c in cards]
    padded: List[List[str]] = []
    for card, w in zip(cards, widths):
        p = list(card)
        while len(p) < max_h:
            p.append(" " * w)
        padded.append(p)
    spacer = " " * gap
    return [spacer.join(padded[col][row] for col in range(len(cards))) for row in range(max_h)]


def render_ascii_swarm(config: SwarmConfig, *, style: str = "unicode", sanitize_pii: bool = True) -> str:
    """Create a box-and-arrow ASCII visualization of the agent swarm topology (with PII pruning enabled by default)."""
    if sanitize_pii:
        config, _ = sanitize_swarm_config(config)
    ch = _BOX_CHARS.get(style.lower(), _BOX_CHARS["unicode"])
    agents = config.agents
    if not agents:
        return "Empty swarm configuration (0 agents)."

    orchestrators = [a for a in agents if a.role_type == "orchestrator"]
    specialists = [a for a in agents if a.role_type != "orchestrator"]

    out: List[str] = []
    header_title = f" MySwarm Topology: {config.title} ({len(agents)} Agent{'s' if len(agents) != 1 else ''}) "
    banner_w = max(len(header_title) + 4, 62)
    out.append(f"{ch['tl']}{ch['h'] * banner_w}{ch['tr']}")
    out.append(f"{ch['v']}{header_title.center(banner_w)}{ch['v']}")
    out.append(f"{ch['bl']}{ch['h'] * banner_w}{ch['br']}")
    out.append("")

    card_inner_w = 36  # total card width = 38

    if orchestrators:
        orch_cards = [_render_agent_card(o, card_inner_w, ch) for o in orchestrators[:2]]
        orch_block = _join_cards_horizontally(orch_cards, gap=4)
        for line in orch_block:
            out.append(line)

        if specialists:
            first_orch_center = (card_inner_w + 2) // 2
            out.append(" " * first_orch_center + ch["v"])
            if len(specialists) == 1:
                out.append(" " * first_orch_center + ch["down"])
            else:
                right_center = (card_inner_w + 2) + 4 + (card_inner_w + 2) // 2
                span = right_center - first_orch_center
                out.append(
                    " " * first_orch_center
                    + ch["ml"]
                    + (ch["h"] * (span - 1))
                    + ch["tr"]
                )
                out.append(
                    " " * first_orch_center
                    + ch["down"]
                    + " " * (span - 1)
                    + ch["down"]
                )
    else:
        specialists = list(agents)

    for idx in range(0, len(specialists), 2):
        pair = specialists[idx : idx + 2]
        cards = [_render_agent_card(a, card_inner_w, ch) for a in pair]
        row_lines = _join_cards_horizontally(cards, gap=4)
        for line in row_lines:
            out.append(line)
        if idx + 2 < len(specialists):
            center = (card_inner_w + 2) // 2
            out.append(" " * center + ch["v"])
            out.append(" " * center + ch["down"])

    edges: List[str] = []
    for a in agents:
        for target in a.delegates_to:
            edges.append(f"  {a.name} {ch['h']}{ch['h']}{ch['right']} {target}")
    if edges:
        out.append("")
        out.append("Delegation Flows:")
        out.extend(edges)

    return "\n".join(out)


def render_copy_paste_ascii(config: SwarmConfig, *, sanitize_pii: bool = True) -> str:
    """Create a 100% pure 7-bit ASCII symbol snippet (with PII pruning) designed for easy copy-paste sharing anywhere."""
    if sanitize_pii:
        config, _ = sanitize_swarm_config(config)
    agents = config.agents
    if not agents:
        return "+--- MySwarm (0 agents) ---+"

    width = 64
    inner = width - 2
    title_clean = config.title.encode("ascii", errors="ignore").decode("ascii").strip() or "Agent Swarm"
    header_line = f"MYSWARM // {title_clean} ({len(agents)} Agents)"

    lines: List[str] = [
        f"+{'=' * inner}+",
        f"| {_wrap_fixed_pure_ascii(header_line, inner - 2)} |",
        f"+{'=' * inner}+",
    ]

    orchestrators = [a for a in agents if a.role_type == "orchestrator"]
    specialists = [a for a in agents if a.role_type != "orchestrator"]
    ordered = orchestrators + specialists

    for idx, agent in enumerate(ordered):
        icon = _ascii_avatar_for_agent(agent)
        role_tag = "ORCHESTRATOR" if agent.role_type == "orchestrator" else "SPECIALIST"
        head = f"{icon} {agent.name} [{role_tag}]"
        p_line = f"  * Persona : {agent.persona}"
        g_line = f"  * Goal    : {agent.goal}"

        if idx > 0:
            lines.append("       |")
            lines.append("       v")

        lines.append(f"+{'-' * inner}+")
        lines.append(f"| {_wrap_fixed_pure_ascii(head, inner - 2)} |")
        lines.append(f"+{'-' * inner}+")
        lines.append(f"| {_wrap_fixed_pure_ascii(p_line, inner - 2)} |")
        lines.append(f"| {_wrap_fixed_pure_ascii(g_line, inner - 2)} |")
        if agent.delegates_to:
            routes_str = f"  * Routes  : ===> {', '.join(agent.delegates_to)}"
            lines.append(f"| {_wrap_fixed_pure_ascii(routes_str, inner - 2)} |")
        lines.append(f"+{'-' * inner}+")

    # Compact flow summary bar at bottom
    edges = [
        f"{a.name} ==>> {', '.join(a.delegates_to)}"
        for a in ordered
        if a.delegates_to
    ]
    if edges:
        flow_str = "FLOW: " + " | ".join(edges)
        lines.append(f"| {_wrap_fixed_pure_ascii(flow_str, inner - 2)} |")
        lines.append(f"+{'-' * inner}+")

    footer = "[Shared via Hermes MySwarm Plugin | PII-Pruned]"
    lines.append(footer.rjust(width))
    return "\n".join(lines)


def render_ascii_to_svg_image(
    ascii_text: str,
    output_path: str | Path,
    *,
    title: str = "MySwarm ASCII Topology",
) -> str:
    """Render an ASCII diagram into a crisp, shareable terminal-styled SVG image file on disk."""
    dest = Path(output_path).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    raw_lines = ascii_text.splitlines() or ["(empty)"]
    max_cols = max(len(line) for line in raw_lines)
    char_w = 8.6
    line_h = 18
    pad_x = 28
    pad_y = 48
    svg_w = int(max(max_cols * char_w + pad_x * 2, 520))
    svg_h = int(len(raw_lines) * line_h + pad_y + 28)

    text_elements: List[str] = []
    for idx, line in enumerate(raw_lines):
        y = pad_y + (idx + 1) * line_h
        escaped = html.escape(line)
        # Highlight orchestrator and flow lines in cyan/amber, everything else in terminal green
        if "[ORCHESTRATOR]" in line or "MYSWARM //" in line or "MySwarm Topology:" in line:
            fill = "#58f6ff"
        elif "Persona:" in line or "* Persona" in line:
            fill = "#e2e8f0"
        elif "Goal" in line:
            fill = "#a7f3d0"
        elif "──►" in line or "-->" in line or "===>" in line or "▼" in line:
            fill = "#fbbf24"
        else:
            fill = "#38bdf8"
        text_elements.append(
            f'  <text x="{pad_x}" y="{y}" fill="{fill}" xml:space="preserve">{escaped}</text>'
        )

    safe_title = html.escape(title)
    svg_doc = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">
  <rect width="100%" height="100%" rx="12" ry="12" fill="#0f172a" stroke="#334155" stroke-width="2"/>
  <rect x="0" y="0" width="100%" height="34" rx="12" ry="12" fill="#1e293b"/>
  <circle cx="20" cy="17" r="6" fill="#ef4444"/>
  <circle cx="40" cy="17" r="6" fill="#f59e0b"/>
  <circle cx="60" cy="17" r="6" fill="#10b981"/>
  <text x="{svg_w // 2}" y="22" fill="#94a3b8" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="12" text-anchor="middle">{safe_title}</text>
  <g font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="13.5">
{chr(10).join(text_elements)}
  </g>
</svg>
"""
    dest.write_text(svg_doc, encoding="utf-8")
    return str(dest)


_THEME_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_theme": {
            "type": "string",
            "description": "The visual theme name (e.g., 'cyberpunk', 'sci-fi starship bridge', 'solarpunk observatory', 'arcane clockwork atelier').",
        },
        "theme_rationale": {
            "type": "string",
            "description": "One-sentence explanation of why this theme fits the swarm's personas and goals.",
        },
        "image_prompt": {
            "type": "string",
            "description": "Detailed, vivid text-to-image prompt portraying the agent swarm, each agent's visual persona, and their collaborative environment.",
        },
    },
    "required": ["selected_theme", "theme_rationale", "image_prompt"],
}


def _heuristic_theme_for_swarm(config: SwarmConfig) -> Tuple[str, str]:
    """Deterministic theme selection fallback if ctx.llm is unavailable."""
    blob = " ".join(f"{a.name} {a.persona} {a.goal}" for a in config.agents).lower()
    if any(k in blob for k in ("security", "hack", "audit", "firewall", "crypto", "zero-trust", "threat")):
        return (
            "cyberpunk",
            "Selected 'cyberpunk' to match the security, auditing, and high-tech defense personas in the swarm.",
        )
    if any(k in blob for k in ("research", "data", "science", "analy", "discover", "explore", "quantum")):
        return (
            "sci-fi",
            "Selected 'sci-fi' to reflect the analytical, research, and discovery-oriented nature of the swarm.",
        )
    if any(k in blob for k in ("creative", "write", "story", "art", "design", "lore", "myth")):
        return (
            "arcane solarpunk",
            "Selected 'arcane solarpunk' to complement the creative, expressive, and design-focused agent personas.",
        )
    return (
        "sci-fi command nexus",
        "Selected 'sci-fi command nexus' to represent a coordinated multi-agent team working in harmony.",
    )


def _build_fallback_image_prompt(config: SwarmConfig, theme: str) -> str:
    """Construct a detailed image generation prompt from SwarmConfig and theme."""
    character_descriptions = []
    for a in config.agents[:6]:
        role_desc = "central lead commander" if a.role_type == "orchestrator" else "specialist operative"
        character_descriptions.append(
            f"'{a.name}' ({role_desc}, persona: {a.persona}, mission: {a.goal})"
        )
    chars_joined = "; ".join(character_descriptions)
    return (
        f"A highly detailed {theme} illustration of an AI agent swarm team of {len(config.agents)} "
        f"collaborating characters in a unified command environment. "
        f"The characters represent: {chars_joined}. "
        f"Cinematic lighting, rich atmospheric depth, expressive character design reflecting each persona, "
        f"holographic data streams connecting the orchestrator to the specialists, concept art masterpiece, 8k resolution."
    )


def build_image_visualization_plan(
    config: SwarmConfig,
    *,
    theme: Optional[str] = None,
    llm: Optional[Any] = None,
) -> Dict[str, str]:
    """Use the default model (with deterministic fallback) to pick/apply a theme and craft an image prompt."""
    config, _ = sanitize_swarm_config(config)
    user_theme = (theme or "").strip()
    mode = "user_specified" if user_theme else "model_auto_selected"

    agents_summary = "\n".join(
        f"- {a.name} ({a.role_type}): Persona='{a.persona}' | Goal='{a.goal}'"
        for a in config.agents
    )

    if llm is not None:
        try:
            if user_theme:
                instructions = (
                    f"The user wants to visualize their AI agent swarm in the '{user_theme}' theme. "
                    f"Keep `selected_theme` as '{user_theme}', explain briefly how this theme highlights the swarm in "
                    "`theme_rationale`, and craft a rich, cinematic text-to-image prompt in `image_prompt` that "
                    "depicts each agent's persona and goal collaborating together."
                )
            else:
                instructions = (
                    "The user did not specify a visual theme for their AI agent swarm visualization. "
                    "Analyze the agents' personas and goals below, pick the single most fitting and imaginative "
                    "visual theme (e.g. sci-fi, cyberpunk, steampunk, solarpunk, noir detective, isometric blueprint, "
                    "celestial observatory, etc.), explain why you chose it in `theme_rationale`, and craft a vivid "
                    "text-to-image prompt in `image_prompt` depicting the entire swarm and each agent's role."
                )
            res = llm.complete_structured(
                instructions=instructions,
                input=[{"type": "text", "text": f"Swarm Title: {config.title}\nAgents:\n{agents_summary}"}],
                json_schema=_THEME_PROMPT_SCHEMA,
                json_mode=True,
                schema_name="myswarm_image_plan",
                purpose="myswarm_visualize_image",
            )
            parsed = getattr(res, "parsed", None)
            if isinstance(parsed, dict) and parsed.get("image_prompt"):
                return {
                    "selected_theme": str(parsed.get("selected_theme") or user_theme or "sci-fi").strip(),
                    "theme_selection_mode": mode,
                    "theme_rationale": str(parsed.get("theme_rationale") or "Selected by default model.").strip(),
                    "image_prompt": str(parsed["image_prompt"]).strip(),
                }
        except Exception as exc:
            logger.debug("LLM image prompt synthesis fell back to deterministic builder: %s", exc)

    if user_theme:
        chosen_theme = user_theme
        rationale = f"User explicitly requested the '{user_theme}' visualization theme."
    else:
        chosen_theme, rationale = _heuristic_theme_for_swarm(config)

    prompt = _build_fallback_image_prompt(config, chosen_theme)
    return {
        "selected_theme": chosen_theme,
        "theme_selection_mode": mode,
        "theme_rationale": rationale,
        "image_prompt": prompt,
    }


def generate_swarm_image(
    config: SwarmConfig,
    *,
    theme: Optional[str] = None,
    aspect_ratio: str = "landscape",
    llm: Optional[Any] = None,
    dispatch_tool: Optional[Callable[[str, Dict[str, Any]], str]] = None,
) -> Dict[str, Any]:
    """Generate an image visualization of the agent swarm using the default model and `image_generate`."""
    plan = build_image_visualization_plan(config, theme=theme, llm=llm)
    valid_ratio = aspect_ratio if aspect_ratio in {"landscape", "square", "portrait"} else "landscape"
    copy_paste_ascii = render_copy_paste_ascii(config)

    image_output: Any = None
    dispatch_error: Optional[str] = None

    if dispatch_tool is not None:
        try:
            raw_res = dispatch_tool(
                "image_generate",
                {"prompt": plan["image_prompt"], "aspect_ratio": valid_ratio},
            )
            try:
                parsed_res = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            except (ValueError, TypeError):
                parsed_res = {"raw": raw_res}

            if isinstance(parsed_res, dict) and parsed_res.get("error"):
                dispatch_error = str(parsed_res["error"])
            else:
                image_output = parsed_res
        except Exception as exc:
            dispatch_error = str(exc)
    else:
        dispatch_error = "Tool dispatcher unavailable in current context."

    return {
        "ok": image_output is not None and dispatch_error is None,
        "source_path": config.source_path,
        "agent_count": len(config.agents),
        "selected_theme": plan["selected_theme"],
        "theme_selection_mode": plan["theme_selection_mode"],
        "theme_rationale": plan["theme_rationale"],
        "aspect_ratio": valid_ratio,
        "image_prompt": plan["image_prompt"],
        "image_result": image_output,
        "copy_paste_ascii": copy_paste_ascii,
        "copy_paste_code_block": f"```text\n{copy_paste_ascii}\n```",
        "error": dispatch_error,
    }

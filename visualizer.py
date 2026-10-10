"""ASCII topology renderer, shareable copy-paste ASCII generator, SVG/image renderer, and LLM-guided themed image visualization for MySwarm."""

from __future__ import annotations

import html
import json
import logging
import struct
import zlib
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


def _wrap_words_to_lines(
    text: str,
    avail_width: int,
    *,
    max_lines: int = 4,
    pure_ascii: bool = False,
) -> List[str]:
    """Word-wrap *text* into at most *max_lines* lines of *avail_width* chars each."""
    if pure_ascii:
        cleaned = " ".join(text.encode("ascii", errors="ignore").decode("ascii").strip().split())
    else:
        cleaned = " ".join(text.strip().split())
    if not cleaned:
        return [""]
    avail = max(8, avail_width)
    words = cleaned.split(" ")
    lines: List[str] = []
    current = ""
    idx = 0
    while idx < len(words):
        word = words[idx]
        if not current:
            if len(word) <= avail:
                current = word
                idx += 1
            else:
                lines.append(word[:avail])
                words[idx] = word[avail:]
        elif len(current) + 1 + len(word) <= avail:
            current = f"{current} {word}"
            idx += 1
        else:
            lines.append(current)
            current = ""
        if len(lines) == max_lines and (current or idx < len(words)):
            # Truncate the last line cleanly with ellipsis
            last = lines[-1]
            ellipsis = "..." if pure_ascii else "…"
            if len(last) + len(ellipsis) <= avail:
                lines[-1] = last.rstrip(" ,;:") + ellipsis
            else:
                lines[-1] = last[: avail - len(ellipsis)].rstrip(" ,;:") + ellipsis
            return lines
    if current:
        lines.append(current)
    return lines or [""]


def _wrap_labeled_multiline(
    label: str,
    text: str,
    width: int,
    *,
    max_lines: int = 4,
    pure_ascii: bool = False,
    min_lines: int = 1,
) -> List[str]:
    """Format a labeled field across multiple wrapped lines with hanging indent padded to *width*."""
    indent = " " * len(label)
    avail = max(8, width - len(label))
    raw_lines = _wrap_words_to_lines(text, avail, max_lines=max_lines, pure_ascii=pure_ascii)
    while len(raw_lines) < min_lines:
        raw_lines.append("")
    formatter = _wrap_fixed_pure_ascii if pure_ascii else _wrap_fixed
    formatted: List[str] = []
    for i, segment in enumerate(raw_lines):
        prefix = label if i == 0 else indent
        if pure_ascii:
            # Preserve leading spaces in hanging indent
            line_str = prefix + segment
            if len(line_str) > width:
                line_str = line_str[: width - 3].rstrip() + "..."
            else:
                line_str = line_str.ljust(width)
            formatted.append(line_str)
        else:
            formatted.append(formatter(prefix + segment, width))
    return formatted


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


def _render_agent_card(
    agent: AgentSpec,
    box_width: int,
    ch: Dict[str, str],
    *,
    min_persona_lines: int = 1,
    min_goal_lines: int = 1,
    min_route_lines: int = 0,
) -> List[str]:
    """Render a single agent card of fixed *box_width* (total width = box_width + 2) with multi-line text."""
    inner = box_width
    badge = "[ORCHESTRATOR]" if agent.role_type == "orchestrator" else "[AGENT]"
    title_str = f"{badge} {agent.name}"
    p_lines = _wrap_labeled_multiline(
        "Persona: ",
        agent.persona,
        inner - 2,
        max_lines=4,
        min_lines=min_persona_lines,
    )
    g_lines = _wrap_labeled_multiline(
        "Goal   : ",
        agent.goal,
        inner - 2,
        max_lines=4,
        min_lines=min_goal_lines,
    )

    lines = [
        f"{ch['tl']}{ch['h'] * inner}{ch['tr']}",
        f"{ch['v']} {_wrap_fixed(title_str, inner - 2)} {ch['v']}",
        f"{ch['ml']}{ch['h'] * inner}{ch['mr']}",
    ]
    for p_line in p_lines:
        lines.append(f"{ch['v']} {p_line} {ch['v']}")
    for g_line in g_lines:
        lines.append(f"{ch['v']} {g_line} {ch['v']}")

    if agent.delegates_to:
        r_lines = _wrap_labeled_multiline(
            "Routes : ",
            ", ".join(agent.delegates_to),
            inner - 2,
            max_lines=2,
            min_lines=max(1, min_route_lines),
        )
        for r_line in r_lines:
            lines.append(f"{ch['v']} {r_line} {ch['v']}")
    elif min_route_lines > 0:
        for _ in range(min_route_lines):
            lines.append(f"{ch['v']} {' ' * (inner - 2)} {ch['v']}")

    lines.append(f"{ch['bl']}{ch['h'] * inner}{ch['br']}")
    return lines


def _render_aligned_card_row(
    row_agents: List[AgentSpec],
    box_width: int,
    ch: Dict[str, str],
    *,
    gap: int = 4,
) -> List[str]:
    """Render 1 or 2 agent cards side-by-side with aligned Persona, Goal, and Routes section heights."""
    if not row_agents:
        return []
    inner_text_w = box_width - 2
    label_w = len("Persona: ")
    avail = max(8, inner_text_w - label_w)
    max_p = max(len(_wrap_words_to_lines(a.persona, avail, max_lines=4)) for a in row_agents)
    max_g = max(len(_wrap_words_to_lines(a.goal, avail, max_lines=4)) for a in row_agents)
    max_r = max(
        (len(_wrap_words_to_lines(", ".join(a.delegates_to), avail, max_lines=2)) if a.delegates_to else 0)
        for a in row_agents
    )
    cards = [
        _render_agent_card(
            a,
            box_width,
            ch,
            min_persona_lines=max_p,
            min_goal_lines=max_g,
            min_route_lines=max_r,
        )
        for a in row_agents
    ]
    return _join_cards_horizontally(cards, gap=gap)


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

    card_inner_w = 46  # total card width = 48 (up to 4 lines x 35 chars per field)

    if orchestrators:
        orch_block = _render_aligned_card_row(orchestrators[:2], card_inner_w, ch, gap=4)
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
        row_lines = _render_aligned_card_row(pair, card_inner_w, ch, gap=4)
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

    width = 78
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
        p_lines = _wrap_labeled_multiline(
            "  * Persona : ",
            agent.persona,
            inner - 2,
            max_lines=4,
            pure_ascii=True,
        )
        g_lines = _wrap_labeled_multiline(
            "  * Goal    : ",
            agent.goal,
            inner - 2,
            max_lines=4,
            pure_ascii=True,
        )

        if idx > 0:
            lines.append("       |")
            lines.append("       v")

        lines.append(f"+{'-' * inner}+")
        lines.append(f"| {_wrap_fixed_pure_ascii(head, inner - 2)} |")
        lines.append(f"+{'-' * inner}+")
        for p_line in p_lines:
            lines.append(f"| {p_line} |")
        for g_line in g_lines:
            lines.append(f"| {g_line} |")
        if agent.delegates_to:
            r_lines = _wrap_labeled_multiline(
                "  * Routes  : ===> ",
                ", ".join(agent.delegates_to),
                inner - 2,
                max_lines=2,
                pure_ascii=True,
            )
            for r_line in r_lines:
                lines.append(f"| {r_line} |")
        lines.append(f"+{'-' * inner}+")

    # Compact flow summary bar at bottom
    edges = [
        f"{a.name} ==>> {', '.join(a.delegates_to)}"
        for a in ordered
        if a.delegates_to
    ]
    if edges:
        flow_lines = _wrap_labeled_multiline(
            "FLOW: ",
            " | ".join(edges),
            inner - 2,
            max_lines=2,
            pure_ascii=True,
        )
        for fl in flow_lines:
            lines.append(f"| {fl} |")
        lines.append(f"+{'-' * inner}+")

    footer = "[Shared via Hermes MySwarm Plugin]"
    lines.append(footer.rjust(width))
    return "\n".join(lines)


def _classify_diagram_line_colors(raw_lines: List[str]) -> List[Tuple[str, Tuple[int, int, int]]]:
    """Return (hex_color, rgb_tuple) for each line in an ASCII diagram, preserving Persona/Goal colors across wrapped continuation lines."""
    cyan = ("#58f6ff", (0x58, 0xF6, 0xFF))
    slate_white = ("#e2e8f0", (0xE2, 0xE8, 0xF0))
    mint_green = ("#a7f3d0", (0xA7, 0xF3, 0xD0))
    amber = ("#fbbf24", (0xFB, 0xBF, 0x24))
    sky_blue = ("#38bdf8", (0x38, 0xBD, 0xF8))

    results: List[Tuple[str, Tuple[int, int, int]]] = []
    active_section: Optional[str] = None

    for line in raw_lines:
        stripped = line.strip()
        if any(b in line for b in ("┌─", "├─", "└─", "+--", "+==")):
            active_section = None
            results.append(sky_blue)
            continue
        if "[ORCHESTRATOR]" in line or "MYSWARM //" in line or "MySwarm Topology:" in line:
            active_section = None
            results.append(cyan)
            continue
        if "Persona:" in line or "* Persona" in line:
            active_section = "persona"
            results.append(slate_white)
            continue
        if "Goal   :" in line or "* Goal" in line:
            active_section = "goal"
            results.append(mint_green)
            continue
        if "Routes :" in line or "* Routes" in line:
            active_section = "routes"
            results.append(amber if "===>" in line else sky_blue)
            continue
        if "──►" in line or "-->" in line or "===>" in line or "▼" in line:
            active_section = None
            results.append(amber)
            continue
        if active_section == "persona" and (stripped.startswith("│") or stripped.startswith("|")):
            results.append(slate_white)
            continue
        if active_section == "goal" and (stripped.startswith("│") or stripped.startswith("|")):
            results.append(mint_green)
            continue
        active_section = None
        results.append(sky_blue)

    return results


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

    line_colors = _classify_diagram_line_colors(raw_lines)
    text_elements: List[str] = []
    for idx, (line, (fill, _)) in enumerate(zip(raw_lines, line_colors)):
        y = pad_y + (idx + 1) * line_h
        escaped = html.escape(line)
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


# 5x7 bitmap font for printable ASCII (each entry is 7 rows of 5-bit integers, MSB on left)
_FONT_5X7: Dict[str, Tuple[int, int, int, int, int, int, int]] = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "!": (4, 4, 4, 4, 4, 0, 4),
    '"': (10, 10, 4, 0, 0, 0, 0),
    "#": (10, 31, 10, 10, 31, 10, 0),
    "$": (4, 15, 20, 14, 5, 30, 4),
    "%": (24, 25, 2, 4, 8, 19, 3),
    "&": (12, 18, 20, 8, 21, 18, 13),
    "'": (4, 4, 2, 0, 0, 0, 0),
    "(": (2, 4, 8, 8, 8, 4, 2),
    ")": (8, 4, 2, 2, 2, 4, 8),
    "*": (0, 4, 21, 14, 21, 4, 0),
    "+": (0, 4, 4, 31, 4, 4, 0),
    ",": (0, 0, 0, 0, 4, 4, 8),
    "-": (0, 0, 0, 31, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 6, 6),
    "/": (1, 1, 2, 4, 8, 16, 16),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 6, 8, 16, 31),
    "3": (31, 2, 4, 6, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    ":": (0, 6, 6, 0, 6, 6, 0),
    ";": (0, 6, 6, 0, 6, 4, 8),
    "<": (2, 4, 8, 16, 8, 4, 2),
    "=": (0, 0, 31, 0, 31, 0, 0),
    ">": (8, 4, 2, 1, 2, 4, 8),
    "?": (14, 17, 1, 2, 4, 0, 4),
    "@": (14, 17, 23, 21, 23, 16, 14),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (28, 18, 17, 17, 17, 18, 28),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 27, 17),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "[": (14, 8, 8, 8, 8, 8, 14),
    "\\": (16, 16, 8, 4, 2, 1, 1),
    "]": (14, 2, 2, 2, 2, 2, 14),
    "^": (4, 10, 17, 0, 0, 0, 0),
    "_": (0, 0, 0, 0, 0, 0, 31),
    "`": (8, 4, 2, 0, 0, 0, 0),
    "a": (0, 0, 14, 1, 15, 17, 15),
    "b": (16, 16, 22, 25, 17, 17, 30),
    "c": (0, 0, 14, 16, 16, 17, 14),
    "d": (1, 1, 13, 19, 17, 17, 15),
    "e": (0, 0, 14, 17, 31, 16, 14),
    "f": (6, 9, 8, 28, 8, 8, 8),
    "g": (0, 15, 17, 17, 15, 1, 14),
    "h": (16, 16, 22, 25, 17, 17, 17),
    "i": (4, 0, 12, 4, 4, 4, 14),
    "j": (2, 0, 6, 2, 2, 18, 12),
    "k": (16, 16, 18, 20, 24, 20, 18),
    "l": (12, 4, 4, 4, 4, 4, 14),
    "m": (0, 0, 26, 21, 21, 17, 17),
    "n": (0, 0, 22, 25, 17, 17, 17),
    "o": (0, 0, 14, 17, 17, 17, 14),
    "p": (0, 0, 30, 17, 30, 16, 16),
    "q": (0, 0, 13, 19, 15, 1, 1),
    "r": (0, 0, 22, 25, 16, 16, 16),
    "s": (0, 0, 15, 16, 14, 1, 30),
    "t": (8, 8, 28, 8, 8, 9, 6),
    "u": (0, 0, 17, 17, 17, 19, 13),
    "v": (0, 0, 17, 17, 17, 10, 4),
    "w": (0, 0, 17, 17, 21, 21, 10),
    "x": (0, 0, 17, 10, 4, 10, 17),
    "y": (0, 0, 17, 17, 15, 1, 14),
    "z": (0, 0, 31, 2, 4, 8, 31),
    "{": (2, 4, 4, 8, 4, 4, 2),
    "|": (4, 4, 4, 4, 4, 4, 4),
    "}": (8, 4, 4, 2, 4, 4, 8),
    "~": (0, 0, 8, 21, 2, 0, 0),
    "…": (0, 0, 0, 0, 0, 0, 21),
    "★": (4, 4, 31, 14, 14, 21, 17),
    "—": (0, 0, 0, 31, 0, 0, 0),
}


def _line_rgb_color(line: str) -> Tuple[int, int, int]:
    """Return the syntax-highlighted RGB tuple for a line of ASCII topology output."""
    if "[ORCHESTRATOR]" in line or "MYSWARM //" in line or "MySwarm Topology:" in line:
        return (0x58, 0xF6, 0xFF)  # #58f6ff cyan
    if "Persona:" in line or "* Persona" in line:
        return (0xE2, 0xE8, 0xF0)  # #e2e8f0 slate white
    if "Goal" in line:
        return (0xA7, 0xF3, 0xD0)  # #a7f3d0 mint green
    if "──►" in line or "-->" in line or "===>" in line or "▼" in line:
        return (0xFB, 0xBF, 0x24)  # #fbbf24 amber
    return (0x38, 0xBD, 0xF8)  # #38bdf8 sky blue


def _encode_png_rgb(width: int, height: int, rgb_buf: bytearray) -> bytes:
    """Encode a raw RGB bytearray (width * height * 3) into a valid PNG binary image."""
    stride = width * 3
    raw_scanlines = bytearray((stride + 1) * height)
    for y in range(height):
        dst_off = y * (stride + 1)
        src_off = y * stride
        raw_scanlines[dst_off] = 0  # filter type 0 (None)
        raw_scanlines[dst_off + 1 : dst_off + 1 + stride] = rgb_buf[src_off : src_off + stride]

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_scanlines), level=6)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")


def render_ascii_to_png_image(
    ascii_text: str,
    output_path: str | Path,
    *,
    title: str = "MySwarm ASCII Topology",
) -> str:
    """Render an ASCII diagram into a shareable terminal-styled PNG image file on disk (zero external dependencies)."""
    dest = Path(output_path).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    raw_lines = ascii_text.splitlines() or ["(empty)"]
    max_cols = max(len(line) for line in raw_lines)

    cell_w = 12
    cell_h = 20
    pad_x = 24
    pad_top = 48
    pad_bottom = 24
    img_w = max(max_cols * cell_w + pad_x * 2, 540)
    img_h = len(raw_lines) * cell_h + pad_top + pad_bottom

    bg_color = (0x0F, 0x17, 0x2A)       # #0f172a
    header_color = (0x1E, 0x29, 0x3B)   # #1e293b
    border_color = (0x33, 0x41, 0x55)   # #334155

    buf = bytearray(img_w * img_h * 3)

    def _fill_rect(x0: int, y0: int, x1: int, y1: int, color: Tuple[int, int, int]) -> None:
        cx0 = max(0, min(img_w, x0))
        cy0 = max(0, min(img_h, y0))
        cx1 = max(0, min(img_w, x1))
        cy1 = max(0, min(img_h, y1))
        if cx1 <= cx0 or cy1 <= cy0:
            return
        row_bytes = bytes(color) * (cx1 - cx0)
        r_len = len(row_bytes)
        for y in range(cy0, cy1):
            off = (y * img_w + cx0) * 3
            buf[off : off + r_len] = row_bytes

    def _fill_circle(cx: int, cy: int, radius: int, color: Tuple[int, int, int]) -> None:
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r2:
                    px, py = cx + dx, cy + dy
                    if 0 <= px < img_w and 0 <= py < img_h:
                        off = (py * img_w + px) * 3
                        buf[off : off + 3] = bytes(color)

    # Background & window chrome
    _fill_rect(0, 0, img_w, img_h, bg_color)
    _fill_rect(0, 0, img_w, 34, header_color)
    # 2px outer border
    _fill_rect(0, 0, img_w, 2, border_color)
    _fill_rect(0, img_h - 2, img_w, img_h, border_color)
    _fill_rect(0, 0, 2, img_h, border_color)
    _fill_rect(img_w - 2, 0, img_w, img_h, border_color)
    # Traffic light window controls
    _fill_circle(20, 17, 6, (0xEF, 0x44, 0x44))
    _fill_circle(40, 17, 6, (0xF5, 0x9E, 0x0B))
    _fill_circle(60, 17, 6, (0x10, 0xB9, 0x81))

    def _draw_char_cell(ch: str, x0: int, y0: int, color: Tuple[int, int, int]) -> None:
        if ch == " ":
            return
        mid_x = x0 + cell_w // 2
        mid_y = y0 + cell_h // 2

        # Seamless vector box-drawing & arrows
        if ch in {"─", "┌", "┐", "└", "┘", "├", "┤", "┬", "┴", "┼", "│"}:
            box_color = color if color in {(0x58, 0xF6, 0xFF), (0xFB, 0xBF, 0x24)} else (0x38, 0xBD, 0xF8)
            # Horizontal segments
            if ch in {"─", "┐", "┘", "┤", "┬", "┴", "┼"}:
                _fill_rect(x0, mid_y - 1, mid_x + 1, mid_y + 1, box_color)
            if ch in {"─", "┌", "└", "├", "┬", "┴", "┼"}:
                _fill_rect(mid_x - 1, mid_y - 1, x0 + cell_w, mid_y + 1, box_color)
            # Vertical segments
            if ch in {"│", "└", "┘", "├", "┤", "┴", "┼"}:
                _fill_rect(mid_x - 1, y0, mid_x + 1, mid_y + 1, box_color)
            if ch in {"│", "┌", "┐", "├", "┤", "┬", "┼"}:
                _fill_rect(mid_x - 1, mid_y - 1, mid_x + 1, y0 + cell_h, box_color)
            return

        if ch == "▼":
            for r in range(7):
                half = max(0, 6 - r)
                _fill_rect(mid_x - half, y0 + 5 + r, mid_x + half + 1, y0 + 6 + r, color)
            return

        if ch == "►":
            for c in range(7):
                half = max(0, 6 - c)
                _fill_rect(x0 + 3 + c, mid_y - half, x0 + 4 + c, mid_y + half + 1, color)
            return

        glyph = _FONT_5X7.get(ch) or _FONT_5X7.get(ch.upper()) or _FONT_5X7.get("?")
        if not glyph:
            return
        gx0 = x0 + 1
        gy0 = y0 + 3
        for row_idx, bits in enumerate(glyph):
            if not bits:
                continue
            for col_idx in range(5):
                if bits & (1 << (4 - col_idx)):
                    px = gx0 + col_idx * 2
                    py = gy0 + row_idx * 2
                    _fill_rect(px, py, px + 2, py + 2, color)

    # Render title centered in header bar
    title_trimmed = title[: max(10, (img_w - 160) // cell_w)]
    title_start_x = max(80, (img_w - len(title_trimmed) * cell_w) // 2)
    title_color = (0x94, 0xA3, 0xB8)
    for idx, ch in enumerate(title_trimmed):
        _draw_char_cell(ch, title_start_x + idx * cell_w, 7, title_color)

    # Render diagram lines
    line_colors = _classify_diagram_line_colors(raw_lines)
    for line_idx, (line, (_, color)) in enumerate(zip(raw_lines, line_colors)):
        y0 = pad_top + line_idx * cell_h
        for col_idx, ch in enumerate(line):
            _draw_char_cell(ch, pad_x + col_idx * cell_w, y0, color)

    dest.write_bytes(_encode_png_rgb(img_w, img_h, buf))
    return str(dest)


# Dimension 1: Curated Signature Themes / Art Styles (what the world & aesthetic is about, orthogonal to intensity)
CURATED_SIGNATURE_THEMES: Dict[str, Dict[str, str]] = {
    "cyberpunk": {
        "name": "cyberpunk",
        "setting": "a high-tech megacity netrunner operations hub with rain-streaked glass and holo-screens",
        "attire_and_style": "cybernetic attire, neural visors, chrome augments, and magenta/cyan neon rim lighting",
        "connections": "fiber-optic data streams and holographic task trees connecting the central orchestrator to each specialist",
    },
    "sci-fi": {
        "name": "sci-fi",
        "setting": "an orbital deep-space starship bridge and command nexus overlooking a nebula",
        "attire_and_style": "titanium-weave command suits, astrometric HUDs, and starlight illumination",
        "connections": "plasma-blue holographic telemetry streams routing tasks from the central commander to each specialist station",
    },
    "magical forest": {
        "name": "magical forest",
        "setting": "a bioluminescent ancient forest sanctuary beneath an elder tree",
        "attire_and_style": "woodland-arcane attire, carved runes, mossy stone-and-crystal workstations, lanterns, and parchment scrolls",
        "connections": "magical ley-line energy streams branching from the elder-tree rune console to each specialist",
    },
    "fantasy map": {
        "name": "fantasy map",
        "setting": "an illustrated cartography war-table and parchment realm map with citadel bastions, compass roses, and inked banners",
        "attire_and_style": "illuminated fantasy cartography combined with strategic commanders and heraldic emblems for each agent",
        "connections": "charted trade-and-messenger routes drawn across the parchment linking the capital citadel (orchestrator) to each specialist stronghold",
    },
    "council of wizards": {
        "name": "council of wizards",
        "setting": "an arcane spire rotunda and library with grimoires, astrolabes, and crystal scrying orbs",
        "attire_and_style": "star-embroidered archmage robes, wooden and crystal staves, arcane sigils, and candle-and-spellfire lighting",
        "connections": "ribbons of golden and violet spell-light connecting the High Archmage orchestrator to each specialist wizard",
    },
    "olympic gods": {
        "name": "olympic gods",
        "setting": "a Mount Olympus marble pantheon temple above the clouds",
        "attire_and_style": "classical deity figures in gold armor and filigree ornaments, pale white cloaks, and fiery eyes",
        "connections": "golden lightning bolts and celestial task streams linking the Olympian orchestrator to each specialist deity",
    },
    "american gilded age modernism": {
        "name": "American gilded age modernism",
        "setting": "a Beaux-Arts and early Art Deco metropolitan syndicate rotunda with marble columns, brass geometric inlays, and mahogany war-tables",
        "attire_and_style": "tailored Gilded Age three-piece suits and evening attire paired with modernist brass ticker-tape machines, drafting tables, and Edison tungsten chandeliers",
        "connections": "brass pneumatic tubes and amber electric telegraph light-lines connecting the central director's podium to each specialist's desk",
    },
    "noir detective": {
        "name": "noir detective",
        "setting": "a 1940s metropolitan detective agency bullpen at night with rain-streaked windows and Venetian blind shadows",
        "attire_and_style": "trench coats, fedoras, tailored wool suits, typewriters, magnifying glasses, and warm amber desk lamps",
        "connections": "crimson yarn investigation threads and pinned dossier routes linking the lead inspector's board to each specialist's desk",
    },
    "solarpunk": {
        "name": "solarpunk",
        "setting": "a sunlit botanical-glass arcology conservatory and renewable-energy command garden",
        "attire_and_style": "woven organic-tech linen attire, stained-glass solar fins, and living vine-wrapped workstations",
        "connections": "warm golden solar-prism light streams linking the central conservatory nexus to each specialist's terrace",
    },
    "steampunk": {
        "name": "steampunk",
        "setting": "a Victorian brass-and-copper clockwork airship bridge and mechanical atelier",
        "attire_and_style": "leather aviators' waistcoats, brass goggles, intricate gearwork instruments, and difference-engine looms",
        "connections": "pressurized copper aether-conduits and glowing pneumatic gauges connecting the captain's helm to each specialist bench",
    },
    "ukiyo-e woodblock": {
        "name": "ukiyo-e woodblock",
        "setting": "a traditional Edo-period Japanese woodblock print command pavilion framed by pines and stylized clouds",
        "attire_and_style": "mineral-pigment indigo, vermilion, and ochre kimono robes, sumi-ink brushes, folding screens, and crisp woodblock linework",
        "connections": "stylized flowing wave-and-wind currents carrying task scrolls from the central strategist to each specialist artisan",
    },
    "isometric blueprint": {
        "name": "isometric blueprint",
        "setting": "an architectural cyanotype and CAD technical schematic cutaway command floor on a coordinate grid",
        "attire_and_style": "clean drafted engineer figures, technical callout boxes, precision measurement axes, and crisp white-and-cyan vector linework",
        "connections": "directional schematic routing lines and labeled data-bus arrows connecting the central controller node to each specialist module",
    },
}

# Keep alias for backward compatibility
SWARM_VISUAL_THEMES = CURATED_SIGNATURE_THEMES

# Dimension 2: Orthogonal Visual Intensity Levels (how understated, normal, or overstated the style is rendered)
VISUAL_INTENSITY_LEVELS: Dict[str, Dict[str, str]] = {
    "understated": {
        "name": "understated",
        "description": (
            "Understated, restrained, and minimalist execution: subtle and grounded atmosphere, muted and refined "
            "color palette, soft natural ambient lighting, clean uncluttered composition, and quiet architectural poise."
        ),
    },
    "normal": {
        "name": "normal",
        "description": (
            "Balanced, cohesive cinematic execution: natural dramatic lighting, clear character silhouettes and "
            "expressions, well-proportioned props and environment, and crisp visual storytelling."
        ),
    },
    "overstated": {
        "name": "overstated",
        "description": (
            "Overstated, exaggerated, maximalist epic execution: larger-than-life scale, hyper-saturated luminous "
            "highlights, lavish ornate detailing, dramatic volumetric god-rays and crackling energy auras, and bold heroic poses."
        ),
    },
}

RICH_IMAGE_VISUALIZATION_GUIDELINES = """\
Rich Image Visualization Guidelines for Agents (Orthogonal Theme x Intensity):
1. Dimension 1 — Theme / Art Style (`CURATED_SIGNATURE_THEMES` — what the world is about):
   Support any custom user theme, or choose/recommend from MySwarm's curated signature themes:
   - `cyberpunk` (megacity netrunner operations hub, cyberware, neural visors)
   - `sci-fi` (deep-space starship bridge, orbital command nexus, astrometric holo-tables)
   - `magical forest` (bioluminescent ancient elder-tree sanctuary, carved runes, ley-line streams)
   - `fantasy map` (illustrated parchment cartography war-table, citadel bastions, charted route lines)
   - `council of wizards` (arcane spire rotunda, star-embroidered archmage robes, grimoires, spell-light threads)
   - `olympic gods` (Mount Olympus marble pantheon, gold armor and filigree ornaments, pale white cloaks, fiery eyes)
   - `American gilded age modernism` (Beaux-Arts & early Art Deco marble/brass syndicate hall, Edison tungsten glow, brass ticker-tape & telegraph lines)
   - `noir detective` (1940s rain-slicked detective bullpen, trench coats, Venetian blind shadows, crimson yarn evidence threads)
   - `solarpunk` (sunlit botanical-glass arcology conservatory, organic-tech attire, solar-prism light streams)
   - `steampunk` (Victorian brass-and-copper clockwork airship bridge, gearwork looms, copper aether-conduits)
   - `ukiyo-e woodblock` (Edo-period Japanese woodblock pavilion, mineral-pigment robes, stylized wave/wind scroll currents)
   - `isometric blueprint` (architectural cyanotype & CAD technical cutaway schematic on a coordinate grid)
2. Dimension 2 — Visual Intensity (`VISUAL_INTENSITY_LEVELS` — orthogonal to theme):
   - `understated`: Subtle, restrained, minimalist, muted palette, soft ambient light, uncluttered poise.
   - `normal` (default): Balanced cinematic concept art, natural dramatic lighting, clear proportions.
   - `overstated`: Exaggerated, maximalist, larger-than-life epic spectacle, hyper-saturated glow, lavish ornamentation.
3. Role & Persona Embodiment: Portray the orchestrator as the central figure directing the scene, and each specialist actively performing a task with props/tools that visually embody their specific persona and goal.
4. Legible Agent Callouts & Delegation Topology: Include clean floating or engraved labels displaying each agent's Name and short mission, and depict theme-appropriate visual connections flowing from the orchestrator to the specialists.
"""

_THEME_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_theme": {
            "type": "string",
            "description": (
                "The visual theme name (e.g., 'cyberpunk', 'sci-fi', 'magical forest', 'fantasy map', "
                "'council of wizards', 'olympic gods', 'American gilded age modernism', 'noir detective', "
                "'solarpunk', 'steampunk', 'ukiyo-e woodblock', 'isometric blueprint')."
            ),
        },
        "selected_intensity": {
            "type": "string",
            "enum": ["understated", "normal", "overstated"],
            "description": "The orthogonal visual intensity level ('understated', 'normal', or 'overstated').",
        },
        "theme_rationale": {
            "type": "string",
            "description": "One-sentence explanation of why this theme and intensity fit the swarm's personas and goals.",
        },
        "image_prompt": {
            "type": "string",
            "description": "Detailed, vivid text-to-image prompt combining the selected theme, the orthogonal intensity level, each agent's visual persona, legible name/goal callouts, and their collaborative environment.",
        },
    },
    "required": ["selected_theme", "selected_intensity", "theme_rationale", "image_prompt"],
}


def normalize_intensity(intensity: Optional[str], theme_text: Optional[str] = None) -> str:
    """Resolve the orthogonal intensity level ('understated', 'normal', or 'overstated')."""
    raw = (intensity or "").strip().lower()
    if raw in VISUAL_INTENSITY_LEVELS:
        return raw
    if raw in {"subtle", "minimal", "minimalist", "muted", "quiet", "restrained"}:
        return "understated"
    if raw in {"exaggerated", "maximal", "maximalist", "epic", "extreme", "intense", "bold"}:
        return "overstated"

    blob = (theme_text or "").strip().lower()
    if any(k in blob for k in ("understated", "subtle", "minimalist", "restrained", "muted")):
        return "understated"
    if any(k in blob for k in ("overstated", "exaggerated", "maximalist", "larger-than-life")):
        return "overstated"
    return "normal"


def _match_theme_preset(theme_name: str) -> Optional[Dict[str, str]]:
    """Return a curated theme preset dict if `theme_name` matches one of our signature themes."""
    norm = (theme_name or "").strip().lower()
    if not norm:
        return None
    # Strip leading intensity prefixes if the user wrote e.g. 'overstated olympic gods'
    for prefix in ("understated ", "normal ", "overstated ", "exaggerated ", "subtle ", "minimalist "):
        if norm.startswith(prefix):
            norm = norm[len(prefix) :].strip()
    if norm in CURATED_SIGNATURE_THEMES:
        return CURATED_SIGNATURE_THEMES[norm]
    for key, preset in CURATED_SIGNATURE_THEMES.items():
        if key in norm or norm in key:
            return preset
    if "olymp" in norm or "god" in norm:
        return CURATED_SIGNATURE_THEMES["olympic gods"]
    if "wizard" in norm or "mage" in norm or "council" in norm:
        return CURATED_SIGNATURE_THEMES["council of wizards"]
    if "gilded" in norm or "modernism" in norm or "art deco" in norm or "beaux" in norm:
        return CURATED_SIGNATURE_THEMES["american gilded age modernism"]
    if "forest" in norm or "woodland" in norm or "druid" in norm:
        return CURATED_SIGNATURE_THEMES["magical forest"]
    if "map" in norm or "cartograph" in norm:
        return CURATED_SIGNATURE_THEMES["fantasy map"]
    if "noir" in norm or "detective" in norm:
        return CURATED_SIGNATURE_THEMES["noir detective"]
    if "solar" in norm:
        return CURATED_SIGNATURE_THEMES["solarpunk"]
    if "steam" in norm or "clockwork" in norm:
        return CURATED_SIGNATURE_THEMES["steampunk"]
    if "ukiyo" in norm or "woodblock" in norm or "edo" in norm:
        return CURATED_SIGNATURE_THEMES["ukiyo-e woodblock"]
    if "blueprint" in norm or "isometric" in norm or "schematic" in norm:
        return CURATED_SIGNATURE_THEMES["isometric blueprint"]
    return None


def _heuristic_theme_for_swarm(config: SwarmConfig) -> Tuple[str, str]:
    """Deterministic theme selection fallback if ctx.llm is unavailable."""
    blob = " ".join(f"{a.name} {a.persona} {a.goal}" for a in config.agents).lower()
    if any(k in blob for k in ("security", "hack", "audit", "firewall", "crypto", "zero-trust", "threat")):
        return (
            "cyberpunk",
            "Selected 'cyberpunk' to match the security, auditing, and high-tech defense personas in the swarm.",
        )
    if any(k in blob for k in ("wizard", "magic", "spell", "alchemy", "lore", "arcane", "scroll")):
        return (
            "council of wizards",
            "Selected 'council of wizards' to reflect the arcane, scholarly, and wisdom-driven personas in the swarm.",
        )
    if any(k in blob for k in ("map", "atlas", "scout", "route", "navigate", "terrain", "cartograph")):
        return (
            "fantasy map",
            "Selected 'fantasy map' to highlight the exploration, routing, and strategic mapping nature of the swarm.",
        )
    if any(k in blob for k in ("finance", "market", "executive", "editorial", "architecture", "modern", "gilded")):
        return (
            "American gilded age modernism",
            "Selected 'American gilded age modernism' to match the structured, executive, and architectural craft of the swarm.",
        )
    if any(k in blob for k in ("investigat", "forensic", "mystery", "detective", "clue", "inspect")):
        return (
            "noir detective",
            "Selected 'noir detective' to match the investigative and analytical personas in the swarm.",
        )
    if any(k in blob for k in ("nature", "eco", "forest", "organic", "garden", "biolum")):
        return (
            "magical forest",
            "Selected 'magical forest' to complement the organic, harmonious, and exploratory agent personas.",
        )
    if any(k in blob for k in ("pantheon", "titan", "olymp", "divine", "myth", "hero")):
        return (
            "olympic gods",
            "Selected 'olympic gods' to portray the swarm as a mythic pantheon of specialized deities.",
        )
    if any(k in blob for k in ("research", "data", "science", "analy", "discover", "explore", "quantum")):
        return (
            "sci-fi",
            "Selected 'sci-fi' to reflect the analytical, research, and discovery-oriented nature of the swarm.",
        )
    return (
        "sci-fi",
        "Selected 'sci-fi' to represent a coordinated multi-agent team working in harmony.",
    )


def _build_fallback_image_prompt(config: SwarmConfig, theme: str, intensity: str = "normal") -> str:
    """Construct a detailed, art-directed image generation prompt from SwarmConfig, theme, and orthogonal intensity."""
    preset = _match_theme_preset(theme)
    resolved_intensity = normalize_intensity(intensity, theme)
    intensity_spec = VISUAL_INTENSITY_LEVELS[resolved_intensity]["description"]

    character_descriptions = []
    for a in config.agents[:6]:
        role_desc = "central lead commander" if a.role_type == "orchestrator" else "specialist operative"
        character_descriptions.append(
            f"'{a.name}' ({role_desc}, persona: {a.persona}, mission: {a.goal}, with legible callout label '{a.name.upper()}')"
        )
    chars_joined = "; ".join(character_descriptions)

    if preset is not None:
        return (
            f"A {resolved_intensity}-intensity {theme} illustration of an AI agent swarm team of {len(config.agents)} "
            f"collaborating characters set in {preset['setting']}. "
            f"Visual style & attire: {preset['attire_and_style']}. "
            f"Intensity & art direction ({resolved_intensity}): {intensity_spec} "
            f"The characters represent: {chars_joined}. "
            f"Topology & connections: {preset['connections']}. "
            f"8k resolution."
        )

    return (
        f"A {resolved_intensity}-intensity {theme} illustration of an AI agent swarm team of {len(config.agents)} "
        f"collaborating characters in a unified command environment. "
        f"Intensity & art direction ({resolved_intensity}): {intensity_spec} "
        f"The characters represent: {chars_joined}. "
        f"Holographic data streams connecting the orchestrator to the specialists, 8k resolution."
    )


def build_image_visualization_plan(
    config: SwarmConfig,
    *,
    theme: Optional[str] = None,
    intensity: Optional[str] = None,
    llm: Optional[Any] = None,
) -> Dict[str, str]:
    """Use the default model (with deterministic fallback) to pick/apply a theme + orthogonal intensity and craft an image prompt."""
    config, _ = sanitize_swarm_config(config)
    user_theme = (theme or "").strip()
    resolved_intensity = normalize_intensity(intensity, user_theme)
    intensity_spec = VISUAL_INTENSITY_LEVELS[resolved_intensity]["description"]
    mode = "user_specified" if user_theme else "model_auto_selected"

    agents_summary = "\n".join(
        f"- {a.name} ({a.role_type}): Persona='{a.persona}' | Goal='{a.goal}'"
        for a in config.agents
    )
    preset = _match_theme_preset(user_theme)
    preset_hint = (
        f"\nPreset Art Direction for '{preset['name']}': Setting: {preset['setting']}. "
        f"Attire & Style: {preset['attire_and_style']}. Connections: {preset['connections']}."
        if preset
        else ""
    )
    intensity_hint = (
        f"\nSelected Visual Intensity ('{resolved_intensity}'): {intensity_spec}"
    )

    if llm is not None:
        try:
            if user_theme:
                instructions = (
                    f"The user wants to visualize their AI agent swarm in the '{user_theme}' theme "
                    f"at '{resolved_intensity}' visual intensity. "
                    f"Keep `selected_theme` as '{user_theme}' and `selected_intensity` as '{resolved_intensity}', "
                    "explain briefly how this theme and intensity highlight the swarm in `theme_rationale`, "
                    "and craft a vivid text-to-image prompt in `image_prompt` that depicts each agent's persona "
                    "and goal collaborating together.\n\n"
                    f"{RICH_IMAGE_VISUALIZATION_GUIDELINES}{preset_hint}{intensity_hint}"
                )
            else:
                instructions = (
                    "The user did not specify a visual theme for their AI agent swarm visualization. "
                    "Analyze the agents' personas and goals below, pick the single most fitting and imaginative "
                    "visual theme from `CURATED_SIGNATURE_THEMES` (e.g., 'cyberpunk', 'sci-fi', 'magical forest', "
                    "'fantasy map', 'council of wizards', 'olympic gods', 'American gilded age modernism', "
                    "'noir detective', 'solarpunk', 'steampunk', 'ukiyo-e woodblock', 'isometric blueprint', or another "
                    f"custom theme) and render it at '{resolved_intensity}' intensity (`selected_intensity`), "
                    "explain why you chose it in `theme_rationale`, and craft a vivid text-to-image prompt in "
                    "`image_prompt` depicting the entire swarm and each agent's role.\n\n"
                    f"{RICH_IMAGE_VISUALIZATION_GUIDELINES}{intensity_hint}"
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
                    "selected_intensity": normalize_intensity(parsed.get("selected_intensity") or resolved_intensity),
                    "theme_selection_mode": mode,
                    "theme_rationale": str(parsed.get("theme_rationale") or "Selected by default model.").strip(),
                    "image_prompt": str(parsed["image_prompt"]).strip(),
                }
        except Exception as exc:
            logger.debug("LLM image prompt synthesis fell back to deterministic builder: %s", exc)

    if user_theme:
        chosen_theme = user_theme
        rationale = (
            f"User requested the '{user_theme}' visualization theme at '{resolved_intensity}' intensity."
        )
    else:
        chosen_theme, base_rationale = _heuristic_theme_for_swarm(config)
        rationale = f"{base_rationale} Rendered at '{resolved_intensity}' intensity."

    prompt = _build_fallback_image_prompt(config, chosen_theme, intensity=resolved_intensity)
    return {
        "selected_theme": chosen_theme,
        "selected_intensity": resolved_intensity,
        "theme_selection_mode": mode,
        "theme_rationale": rationale,
        "image_prompt": prompt,
    }


def generate_swarm_image(
    config: SwarmConfig,
    *,
    theme: Optional[str] = None,
    intensity: Optional[str] = None,
    aspect_ratio: str = "landscape",
    llm: Optional[Any] = None,
    dispatch_tool: Optional[Callable[[str, Dict[str, Any]], str]] = None,
) -> Dict[str, Any]:
    """Generate an image visualization of the agent swarm using the default model and `image_generate`."""
    plan = build_image_visualization_plan(config, theme=theme, intensity=intensity, llm=llm)
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
        "selected_intensity": plan["selected_intensity"],
        "theme_selection_mode": plan["theme_selection_mode"],
        "theme_rationale": plan["theme_rationale"],
        "aspect_ratio": valid_ratio,
        "image_prompt": plan["image_prompt"],
        "image_result": image_output,
        "copy_paste_ascii": copy_paste_ascii,
        "copy_paste_code_block": f"```text\n{copy_paste_ascii}\n```",
        "error": dispatch_error,
    }

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

    footer = "[Shared via Hermes MySwarm Plugin]"
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
    for line_idx, line in enumerate(raw_lines):
        color = _line_rgb_color(line)
        y0 = pad_top + line_idx * cell_h
        for col_idx, ch in enumerate(line):
            _draw_char_cell(ch, pad_x + col_idx * cell_w, y0, color)

    dest.write_bytes(_encode_png_rgb(img_w, img_h, buf))
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

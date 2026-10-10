"""Tool handlers and slash command dispatcher for the MySwarm Hermes plugin."""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import Any, List, Optional

try:
    from .backup_manager import (
        get_backup_status,
        import_shared_agents_file,
        revert_to_original_agents_file,
    )
    from .parser import format_abbreviated_list, load_swarm_config, resolve_agents_file
    from .sanitizer import export_sanitized_agents_file, load_sanitized_swarm_config
    from .visualizer import (
        generate_swarm_image,
        render_ascii_swarm,
        render_ascii_to_png_image,
        render_ascii_to_svg_image,
        render_copy_paste_ascii,
    )
except ImportError:
    from backup_manager import (
        get_backup_status,
        import_shared_agents_file,
        revert_to_original_agents_file,
    )
    from parser import format_abbreviated_list, load_swarm_config, resolve_agents_file
    from sanitizer import export_sanitized_agents_file, load_sanitized_swarm_config
    from visualizer import (
        generate_swarm_image,
        render_ascii_swarm,
        render_ascii_to_png_image,
        render_ascii_to_svg_image,
        render_copy_paste_ascii,
    )

logger = logging.getLogger(__name__)

# Active PluginContext bound during register(ctx)
_ACTIVE_CTX: Optional[Any] = None


def bind_context(ctx: Any) -> None:
    """Bind the Hermes PluginContext so tool and slash handlers can use ctx.llm and ctx.dispatch_tool."""
    global _ACTIVE_CTX
    _ACTIVE_CTX = ctx


def _get_llm(ctx: Optional[Any] = None) -> Optional[Any]:
    target = ctx or _ACTIVE_CTX
    if target is None:
        return None
    try:
        return getattr(target, "llm", None)
    except Exception:
        return None


def _get_dispatcher(ctx: Optional[Any] = None):
    target = ctx or _ACTIVE_CTX
    if target is None:
        return None
    dispatch = getattr(target, "dispatch_tool", None)
    return dispatch if callable(dispatch) else None


def _get_config_str(key: str, default: str = "", ctx: Optional[Any] = None) -> str:
    target = ctx or _ACTIVE_CTX
    if target is None:
        return default
    try:
        getter = getattr(target, "get_config", None)
        if callable(getter):
            val = getter(key, default=default)
            return str(val).strip() if val is not None else default
    except Exception:
        pass
    return default


def myswarm_list(args: dict, **kwargs: Any) -> str:
    """Handler for myswarm_list tool: output abbreviated list of agents, personas, and goals."""
    try:
        path = (args or {}).get("path")
        use_llm = bool((args or {}).get("use_llm", True))
        cfg = load_swarm_config(path, llm=_get_llm() if use_llm else None, use_llm_fallback=use_llm)
        formatted = format_abbreviated_list(cfg)
        backup = get_backup_status(path)
        return json.dumps(
            {
                "ok": True,
                "source_path": cfg.source_path,
                "title": cfg.title,
                "agent_count": len(cfg.agents),
                "agents": [a.to_dict() for a in cfg.agents],
                "formatted_list": formatted,
                "active_import": backup["active_import"],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


SHARING_HINT = (
    "Sharing Tip: You can share your ASCII code and/or your exported .md file (/myswarm export). "
    "The ASCII code is great for a quick visual preview and lightweight starter config (abbreviated 1-line "
    "personas/goals + routing), while the .md file is more comprehensive and preserves full agent instructions."
)


def myswarm_ascii(args: dict, **kwargs: Any) -> str:
    """Handler for myswarm_ascii tool: render ASCII SVG & PNG images and output a copy-paste ASCII code block."""
    try:
        path = (args or {}).get("path")
        style = str((args or {}).get("style") or "unicode").strip().lower()
        image_output_path = (args or {}).get("image_output_path")

        _resolved_file, workspace_dir = resolve_agents_file(path)
        cfg, san_result = load_sanitized_swarm_config(
            path,
            llm=_get_llm(),
            use_llm_fallback=True,
            use_llm_scrubber=True,
        )
        diagram = render_ascii_swarm(cfg, style=style, sanitize_pii=True)
        copy_paste = render_copy_paste_ascii(cfg, sanitize_pii=True)
        copy_paste_block = f"```text\n{copy_paste}\n```"

        base_img = Path(image_output_path).expanduser().resolve() if image_output_path else (workspace_dir / "myswarm-ascii.svg")
        svg_target = base_img.with_suffix(".svg")
        png_target = base_img.with_suffix(".png")
        img_title = f"MySwarm ASCII Topology — {cfg.title}"
        saved_svg_path = render_ascii_to_svg_image(
            diagram,
            svg_target,
            title=img_title,
        )
        saved_png_path = render_ascii_to_png_image(
            diagram,
            png_target,
            title=img_title,
        )

        return json.dumps(
            {
                "ok": True,
                "source_path": cfg.source_path,
                "agent_count": len(cfg.agents),
                "style": style,
                "pii_pruned": True,
                "total_redactions": san_result.total_redactions,
                "redaction_counts": san_result.redaction_counts,
                "llm_scrubbed": san_result.llm_scrubbed,
                "ascii_image_path": saved_svg_path,
                "ascii_svg_path": saved_svg_path,
                "ascii_png_path": saved_png_path,
                "ascii_diagram": diagram,
                "copy_paste_ascii": copy_paste,
                "copy_paste_code_block": copy_paste_block,
                "sharing_hint": SHARING_HINT,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def myswarm_visualize_image(args: dict, **kwargs: Any) -> str:
    """Handler for myswarm_visualize_image tool: generate a themed image of the agent setup (PII-pruned)."""
    try:
        path = (args or {}).get("path")
        theme = (args or {}).get("theme")
        if not theme:
            theme = _get_config_str("default_theme", "")
        aspect_ratio = str((args or {}).get("aspect_ratio") or "landscape").strip().lower()

        cfg, san_result = load_sanitized_swarm_config(
            path,
            llm=_get_llm(),
            use_llm_fallback=True,
            use_llm_scrubber=True,
        )
        result = generate_swarm_image(
            cfg,
            theme=theme or None,
            aspect_ratio=aspect_ratio,
            llm=_get_llm(),
            dispatch_tool=_get_dispatcher(),
        )
        result["pii_pruned"] = True
        result["total_redactions"] = san_result.total_redactions
        result["sharing_hint"] = SHARING_HINT
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def myswarm_export(args: dict, **kwargs: Any) -> str:
    """Handler for myswarm_export tool: sanitize PII from agents.md and export to a .md file."""
    try:
        output_path = (args or {}).get("output_path")
        source_path = (args or {}).get("source_path")
        use_llm_scrubber = bool((args or {}).get("use_llm_scrubber", True))
        default_filename = _get_config_str("default_export_filename", "myswarm-export.md") or "myswarm-export.md"

        res = export_sanitized_agents_file(
            output_path=output_path,
            source_path=source_path,
            default_filename=default_filename,
            llm=_get_llm() if use_llm_scrubber else None,
            use_llm_scrubber=use_llm_scrubber,
        )
        return json.dumps(
            {
                "ok": True,
                "output_path": res.output_path,
                "agent_count": res.agent_count,
                "total_redactions": res.total_redactions,
                "redaction_counts": res.redaction_counts,
                "llm_scrubbed": res.llm_scrubbed,
                "header": f"<!-- Exported via Hermes MySwarm Plugin | Agents: {res.agent_count} -->",
                "sharing_hint": SHARING_HINT,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def myswarm_import(args: dict, **kwargs: Any) -> str:
    """Handler for myswarm_import tool: display file contents, check for exploits/security risks (.md or ASCII), and import."""
    try:
        source_file = (args or {}).get("source_file")
        if not source_file:
            return json.dumps({"ok": False, "error": "Missing required parameter: 'source_file'"})
        workspace_dir = (args or {}).get("workspace_dir")
        preview_only = bool((args or {}).get("preview_only", False))
        allow_suspicious = bool((args or {}).get("allow_suspicious", False))
        res = import_shared_agents_file(
            source_file,
            workspace_dir=workspace_dir,
            llm=_get_llm(),
            preview_only=preview_only,
            allow_suspicious=allow_suspicious,
        )
        return json.dumps(res, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def myswarm_revert(args: dict, **kwargs: Any) -> str:
    """Handler for myswarm_revert tool: revert to the preserved original agents.md."""
    try:
        workspace_dir = (args or {}).get("workspace_dir")
        res = revert_to_original_agents_file(workspace_dir=workspace_dir)
        return json.dumps(res, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


SLASH_HELP = """\
/myswarm — Discover, visualize, export, and test community agents.md configs

Subcommands:
  /myswarm list [path]                  Abbreviated list of agents, personas, and goals
  /myswarm ascii [path]                 ASCII images (.svg & .png) + copy-paste ASCII symbols code block
  /myswarm image [theme]                Generate an image of your swarm (e.g. sci-fi, cyberpunk, or auto)
  /myswarm export [output.md]           Export sanitized agents.md with MySwarm Plugin header
  /myswarm import [--preview] <file>    Display file contents, run security/exploit check (.md or ASCII), & import
  /myswarm revert                       Revert back to your original agents.md
  /myswarm status                       Show active agents.md and backup/revert status
"""


def _format_import_screen_output(res: dict) -> str:
    """Format the pre-import file display, trust warning, security audit, and import status for the user's screen."""
    audit = res.get("security_audit") or {}
    lines = [
        res.get("trust_warning", ""),
        "",
        f"=== FILE CONTENTS TO BE IMPORTED ({res.get('imported_from')}) ===",
        "```text",
        (res.get("displayed_file_contents") or "").rstrip(),
        "```",
        "",
        "=== SECURITY & EXPLOIT AUDIT (Markdown & ASCII Inspector) ===",
        f"  Format Inspected : {audit.get('format_inspected', res.get('imported_format', 'unknown'))}",
        f"  Security Verdict : {str(audit.get('verdict', 'unknown')).upper()} (Risk Level: {audit.get('risk_level', 'none')})",
        f"  Audit Summary    : {audit.get('summary', '')}",
    ]
    for finding in audit.get("findings") or []:
        lines.append(
            f"  - [{finding.get('severity', 'medium').upper()}] {finding.get('category')}: "
            f"{finding.get('description')} (match: `{finding.get('match')}`)"
        )
    lines.append("")

    if res.get("action") == "preview":
        lines.extend(
            [
                f"[MySwarm Import Preview] Displayed {res.get('imported_from')} ({res.get('agent_count')} agents).",
                "  Original modified  : No (preview mode — run `/myswarm import <file>` after reviewing to activate).",
            ]
        )
    elif res.get("blocked_by_security_check"):
        lines.extend(
            [
                f"[MySwarm Import BLOCKED] {res.get('error')}",
                "  Original modified  : No (your active agents.md was kept untouched).",
            ]
        )
    else:
        lines.extend(
            [
                f"[MySwarm Import] Activated shared config: {res.get('imported_from')}",
                f"  Target file        : {res.get('target_file')} ({res.get('agent_count')} agents, format: {res.get('imported_format')})",
                "  Original preserved : Yes (run `/myswarm revert` anytime to restore your original agents.md)",
            ]
        )
    return "\n".join(lines)


def handle_slash_command(raw_args: str, ctx: Optional[Any] = None) -> str:
    """In-session `/myswarm` slash command handler."""
    active_ctx = ctx or _ACTIVE_CTX
    try:
        tokens: List[str] = shlex.split(raw_args or "")
    except ValueError:
        tokens = (raw_args or "").strip().split()

    if not tokens or tokens[0].lower() in {"help", "-h", "--help"}:
        return SLASH_HELP

    sub = tokens[0].lower()
    rest = tokens[1:]

    try:
        if sub == "list":
            path = rest[0] if rest else None
            cfg = load_swarm_config(path, llm=_get_llm(active_ctx), use_llm_fallback=True)
            return format_abbreviated_list(cfg)

        if sub == "ascii":
            style = "ascii" if "--ascii" in rest else "unicode"
            paths = [r for r in rest if not r.startswith("-")]
            path = paths[0] if paths else None
            _resolved_file, workspace_dir = resolve_agents_file(path)
            cfg, san_result = load_sanitized_swarm_config(
                path,
                llm=_get_llm(active_ctx),
                use_llm_fallback=True,
                use_llm_scrubber=True,
            )
            diagram = render_ascii_swarm(cfg, style=style, sanitize_pii=True)
            copy_paste = render_copy_paste_ascii(cfg, sanitize_pii=True)
            img_title = f"MySwarm ASCII Topology — {cfg.title}"
            svg_path = render_ascii_to_svg_image(
                diagram,
                workspace_dir / "myswarm-ascii.svg",
                title=img_title,
            )
            png_path = render_ascii_to_png_image(
                diagram,
                workspace_dir / "myswarm-ascii.png",
                title=img_title,
            )
            return (
                f"{diagram}\n\n"
                f"ASCII SVG Saved  : {svg_path}\n"
                f"ASCII PNG Saved  : {png_path}\n\n"
                f"Easy Copy-Paste ASCII Code:\n"
                f"```text\n{copy_paste}\n```\n\n"
                f"{SHARING_HINT}"
            )

        if sub == "image":
            theme = " ".join(rest).strip() if rest else (_get_config_str("default_theme", "", active_ctx) or None)
            cfg, _san = load_sanitized_swarm_config(
                None,
                llm=_get_llm(active_ctx),
                use_llm_fallback=True,
                use_llm_scrubber=True,
            )
            res = generate_swarm_image(
                cfg,
                theme=theme,
                llm=_get_llm(active_ctx),
                dispatch_tool=_get_dispatcher(active_ctx),
            )
            lines = [
                "[MySwarm Image Visualization]",
                f"  Theme     : {res['selected_theme']} ({res['theme_selection_mode']})",
                f"  Rationale : {res['theme_rationale']}",
                f"  Prompt    : {res['image_prompt']}",
            ]
            if res.get("ok") and res.get("image_result"):
                lines.append(f"  Image     : {json.dumps(res['image_result'], ensure_ascii=False)}")
            elif res.get("error"):
                lines.append(f"  Note      : Image generator returned: {res['error']}")
            return "\n".join(lines)

        if sub == "export":
            out_path = rest[0] if rest else None
            default_fn = _get_config_str("default_export_filename", "myswarm-export.md", active_ctx) or "myswarm-export.md"
            res = export_sanitized_agents_file(
                output_path=out_path,
                default_filename=default_fn,
                llm=_get_llm(active_ctx),
                use_llm_scrubber=True,
            )
            return (
                f"[MySwarm Export] Wrote comprehensive sanitized config to: {res.output_path}\n"
                f"  Agents exported : {res.agent_count}\n"
                f"  PII redactions  : {res.total_redactions} ({res.redaction_counts or 'none'})\n"
                f"  Header included : <!-- Exported via Hermes MySwarm Plugin | Agents: {res.agent_count} -->\n"
                f"  {SHARING_HINT}"
            )

        if sub == "import":
            preview_only = "--preview" in rest
            allow_suspicious = "--allow-suspicious" in rest
            file_args = [r for r in rest if not r.startswith("-")]
            if not file_args:
                return "Usage: /myswarm import [--preview] <path-to-shared-agents.md-or-ascii.txt>"
            res = import_shared_agents_file(
                file_args[0],
                llm=_get_llm(active_ctx),
                preview_only=preview_only,
                allow_suspicious=allow_suspicious,
            )
            return _format_import_screen_output(res)

        if sub == "revert":
            res = revert_to_original_agents_file()
            if res["original_existed"]:
                return (
                    f"[MySwarm Revert] Restored original configuration: {res['restored_file']} "
                    f"({res['agent_count']} agents)."
                )
            return "[MySwarm Revert] Removed imported configuration (no original agents.md existed prior to import)."

        if sub == "status":
            st = get_backup_status()
            return (
                f"[MySwarm Status]\n"
                f"  Workspace          : {st['workspace_dir']}\n"
                f"  Active agents file : {st['active_agents_file'] or '(none)'}\n"
                f"  Testing imported?  : {'Yes' if st['active_import'] else 'No'}\n"
                f"  Original backup?   : {'Preserved & ready to revert' if st['has_original_backup'] else 'None'}\n"
                f"  Last imported from : {st['imported_from'] or 'N/A'}"
            )

        return f"Unknown /myswarm subcommand: {sub}\n\n{SLASH_HELP}"
    except Exception as exc:
        return f"[MySwarm Error] {exc}"

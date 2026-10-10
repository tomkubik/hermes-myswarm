"""CLI subcommand tree (`hermes myswarm ...`) for the MySwarm plugin."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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


def setup_cli_argparse(subparser: argparse.ArgumentParser) -> None:
    """Configure the `hermes myswarm` subcommand parser."""
    subs = subparser.add_subparsers(dest="myswarm_subcommand")

    p_list = subs.add_parser("list", help="Output abbreviated list of agents, personas, and goals")
    p_list.add_argument("path", nargs="?", default=None, help="Optional path to agents.md or workspace directory")

    p_ascii = subs.add_parser(
        "ascii",
        help="Render ASCII visualization images (.svg and .png) AND a copy-paste ASCII symbols code block",
    )
    p_ascii.add_argument("path", nargs="?", default=None, help="Optional path to agents.md or workspace directory")
    p_ascii.add_argument("--style", choices=["unicode", "ascii"], default="unicode", help="Box drawing character set")
    p_ascii.add_argument(
        "--image-out",
        default=None,
        help="Base output path for the rendered ASCII images (.svg and .png, default: myswarm-ascii.svg / .png)",
    )

    p_image = subs.add_parser("image", help="Generate a themed image visualization of the agent swarm")
    p_image.add_argument("theme", nargs="?", default=None, help="Optional visual theme (e.g. sci-fi, cyberpunk, olympic gods)")
    p_image.add_argument(
        "--intensity",
        choices=["understated", "normal", "overstated"],
        default=None,
        help="Orthogonal visual intensity level (understated, normal, overstated)",
    )
    p_image.add_argument("--path", default=None, help="Optional path to agents.md or workspace directory")
    p_image.add_argument(
        "--aspect-ratio",
        choices=["landscape", "square", "portrait"],
        default="landscape",
        help="Image aspect ratio (default: landscape)",
    )

    p_export = subs.add_parser("export", help="Export sanitized agents.md to a shareable .md file")
    p_export.add_argument("output_path", nargs="?", default=None, help="Output .md file path (default: myswarm-export.md)")
    p_export.add_argument("--source", default=None, help="Optional source agents.md file or workspace directory")
    p_export.add_argument("--no-llm", action="store_true", help="Disable contextual LLM PII scrubbing pass")

    p_import = subs.add_parser(
        "import",
        help="Display file contents, run security/exploit check (.md or ASCII), and import while preserving original",
    )
    p_import.add_argument("source_file", help="Path to the shared .md or ASCII .txt agent configuration file")
    p_import.add_argument("--workspace", default=None, help="Target workspace directory (default: current directory)")
    p_import.add_argument(
        "--preview",
        action="store_true",
        help="Display the file contents and security audit on screen without overwriting agents.md yet",
    )
    p_import.add_argument(
        "--allow-suspicious",
        action="store_true",
        help="Override security check block if you have manually verified the file and trust its author",
    )

    p_revert = subs.add_parser("revert", help="Revert to the original agents.md preserved before import")
    p_revert.add_argument("--workspace", default=None, help="Target workspace directory (default: current directory)")

    p_status = subs.add_parser("status", help="Show active agents.md and backup/revert status")
    p_status.add_argument("--workspace", default=None, help="Target workspace directory (default: current directory)")

    subparser.set_defaults(func=handle_cli_command)


def handle_cli_command(args: Any) -> int:
    """Execute `hermes myswarm <subcommand>`."""
    try:
        from .handlers import SHARING_HINT, _format_import_screen_output, _get_dispatcher, _get_llm
    except ImportError:
        from handlers import SHARING_HINT, _format_import_screen_output, _get_dispatcher, _get_llm

    sub = getattr(args, "myswarm_subcommand", None)
    try:
        if sub == "list":
            cfg = load_swarm_config(getattr(args, "path", None), llm=_get_llm())
            print(format_abbreviated_list(cfg))
            return 0

        if sub == "ascii":
            raw_path = getattr(args, "path", None)
            _resolved_file, workspace_dir = resolve_agents_file(raw_path)
            cfg, _san_result = load_sanitized_swarm_config(raw_path, llm=_get_llm())
            diagram = render_ascii_swarm(cfg, style=getattr(args, "style", "unicode"), sanitize_pii=True)
            copy_paste = render_copy_paste_ascii(cfg, sanitize_pii=True)
            raw_img_out = getattr(args, "image_out", None)
            base_img = Path(raw_img_out).expanduser().resolve() if raw_img_out else (workspace_dir / "myswarm-ascii.svg")
            img_title = f"MySwarm ASCII Topology — {cfg.title}"
            saved_svg = render_ascii_to_svg_image(
                diagram,
                base_img.with_suffix(".svg"),
                title=img_title,
            )
            saved_png = render_ascii_to_png_image(
                diagram,
                base_img.with_suffix(".png"),
                title=img_title,
            )
            print(diagram)
            print(f"\nASCII SVG Saved  : {saved_svg}")
            print(f"ASCII PNG Saved  : {saved_png}")
            print("\nEasy Copy-Paste ASCII Code:")
            print(f"```text\n{copy_paste}\n```")
            print(f"\n{SHARING_HINT}")
            return 0

        if sub == "image":
            cfg, _san = load_sanitized_swarm_config(getattr(args, "path", None), llm=_get_llm())
            res = generate_swarm_image(
                cfg,
                theme=getattr(args, "theme", None),
                intensity=getattr(args, "intensity", None),
                aspect_ratio=getattr(args, "aspect_ratio", "landscape"),
                llm=_get_llm(),
                dispatch_tool=_get_dispatcher(),
            )
            print(f"Theme     : {res['selected_theme']} ({res['theme_selection_mode']})")
            print(f"Intensity : {res['selected_intensity']}")
            print(f"Rationale : {res['theme_rationale']}")
            print(f"Prompt    : {res['image_prompt']}")
            if res.get("image_result"):
                print(f"Image     : {json.dumps(res['image_result'], ensure_ascii=False)}")
            elif res.get("error"):
                print(f"Note      : {res['error']}")
            return 0

        if sub == "export":
            use_llm = not bool(getattr(args, "no_llm", False))
            res = export_sanitized_agents_file(
                output_path=getattr(args, "output_path", None),
                source_path=getattr(args, "source", None),
                llm=_get_llm() if use_llm else None,
                use_llm_scrubber=use_llm,
            )
            print(f"Exported comprehensive sanitized agents.md to: {res.output_path}")
            print(f"Agents exported : {res.agent_count}")
            print(f"PII redactions  : {res.total_redactions} ({res.redaction_counts or 'none'})")
            print(f"\n{SHARING_HINT}")
            return 0

        if sub == "import":
            res = import_shared_agents_file(
                getattr(args, "source_file"),
                workspace_dir=getattr(args, "workspace", None),
                llm=_get_llm(),
                preview_only=bool(getattr(args, "preview", False)),
                allow_suspicious=bool(getattr(args, "allow_suspicious", False)),
            )
            print(_format_import_screen_output(res))
            return 0 if res.get("ok") else 1

        if sub == "revert":
            res = revert_to_original_agents_file(workspace_dir=getattr(args, "workspace", None))
            if res["original_existed"]:
                print(f"Reverted to original configuration: {res['restored_file']} ({res['agent_count']} agents)")
            else:
                print("Removed imported configuration (no original agents.md existed prior to import).")
            return 0

        if sub == "status":
            st = get_backup_status(getattr(args, "workspace", None))
            print(json.dumps(st, indent=2))
            return 0

        print("Usage: hermes myswarm <list|ascii|image|export|import|revert|status>")
        return 1
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

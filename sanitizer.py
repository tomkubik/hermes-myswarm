"""Two-stage PII sanitizer and Markdown exporter for MySwarm."""

from __future__ import annotations

import getpass
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .parser import AgentSpec, SwarmConfig, parse_agents_markdown, resolve_agents_file
except ImportError:
    from parser import AgentSpec, SwarmConfig, parse_agents_markdown, resolve_agents_file

logger = logging.getLogger(__name__)

EXPORT_HEADER_PREFIX = "<!-- Exported via Hermes MySwarm Plugin"
_EXISTING_HEADER_RE = re.compile(r"^<!--\s*Exported via Hermes MySwarm Plugin[^>]*-->\s*\n?", re.IGNORECASE)

# Stage 1 deterministic PII regex patterns
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_SECRET_TOKEN_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_\-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
    r"|AIza[0-9A-Za-z\-_]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|glpat-[A-Za-z0-9\-_]{16,}"
    r")\b"
)

_BEARER_OR_KV_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|bearer|client[_-]?secret)"
    r"(\s*[:=]\s*|\s+)"
    r"(['\"]?[A-Za-z0-9_\-\.~+/]{12,}['\"]?)"
)

_URL_CREDENTIALS_RE = re.compile(r"(https?://)([^/\s:@]+:[^/\s@]+)@")

_UNIX_HOME_PATH_RE = re.compile(r"(?:/Users|/home)/([A-Za-z0-9._\-]+)(/[^\s`\"')>\]]*)?")
_WIN_HOME_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9._\-]+)(\\[^\s`\"')>\]]*)?", re.IGNORECASE)

_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)

_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{3}\)[\s.\-]?|\d{3}[\s.\-])\d{3}[\s.\-]\d{4}(?!\d)"
)

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Explicit personal metadata fields e.g. "Owner: John Smith", "User: Alice Doe", "Author: ..."
_EXPLICIT_PERSON_FIELD_RE = re.compile(
    r"^(\s*(?:[\-\*\•]\s*)?(?:\*\*|__)?(?:owner|author|user\s*name|real\s*name|full\s*name|contact|created\s*by|maintainer|employee|manager\s*name|slack\s*id|discord\s*id|telegram\s*id)(?:\*\*|__)?\s*[:\-–—]\s*)(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class SanitizationResult:
    """Output of the MySwarm PII sanitization pipeline."""

    sanitized_markdown: str
    agent_count: int
    redaction_counts: Dict[str, int] = field(default_factory=dict)
    total_redactions: int = 0
    llm_scrubbed: bool = False
    output_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_path": self.output_path,
            "agent_count": self.agent_count,
            "total_redactions": self.total_redactions,
            "redaction_counts": dict(self.redaction_counts),
            "llm_scrubbed": self.llm_scrubbed,
        }


def _current_os_usernames() -> List[str]:
    names = set()
    try:
        u = getpass.getuser().strip()
        if len(u) >= 3:
            names.add(u)
    except Exception:
        pass
    try:
        h = Path.home().name.strip()
        if len(h) >= 3:
            names.add(h)
    except Exception:
        pass
    # Exclude generic system words that might collide with regular English prose
    generic = {"user", "admin", "root", "ubuntu", "default", "runner", "home", "test", "guest", "agent"}
    return [n for n in names if n.lower() not in generic]


def _regex_scrub(content: str) -> Tuple[str, Dict[str, int]]:
    """Run deterministic Stage-1 PII scrubbing and return (scrubbed_text, counts_by_category)."""
    counts: Dict[str, int] = {}
    text = _EXISTING_HEADER_RE.sub("", content)

    def _inc(cat: str, n: int = 1) -> None:
        if n > 0:
            counts[cat] = counts.get(cat, 0) + n

    # 1. URL embedded credentials
    text, n = _URL_CREDENTIALS_RE.subn(r"\1[REDACTED_CREDENTIALS]@", text)
    _inc("url_credentials", n)

    # 2. Known API key / token prefixes
    text, n = _SECRET_TOKEN_RE.subn("[REDACTED_SECRET]", text)
    _inc("secrets_and_tokens", n)

    # 3. Key-value secrets / Bearer tokens
    def _replace_kv_secret(m: re.Match) -> str:
        val = m.group(3)
        if "[REDACTED" in val:
            return m.group(0)
        _inc("secrets_and_tokens", 1)
        return f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]"

    text = _BEARER_OR_KV_SECRET_RE.sub(_replace_kv_secret, text)

    # 4. Emails
    text, n = _EMAIL_RE.subn("[REDACTED_EMAIL]", text)
    _inc("emails", n)

    # 5. Local home paths (/Users/<user>/... -> ~/...)
    def _replace_unix_path(m: re.Match) -> str:
        _inc("user_paths", 1)
        rest = m.group(2) or ""
        return f"~{rest}"

    text = _UNIX_HOME_PATH_RE.sub(_replace_unix_path, text)

    def _replace_win_path(m: re.Match) -> str:
        _inc("user_paths", 1)
        rest = m.group(2) or ""
        return f"~{rest}"

    text = _WIN_HOME_PATH_RE.sub(_replace_win_path, text)

    # 6. Current OS username mentions
    for uname in _current_os_usernames():
        pat = re.compile(rf"\b{re.escape(uname)}\b", re.IGNORECASE)
        text, n = pat.subn("[REDACTED_USER]", text)
        _inc("os_username", n)

    # 7. SSNs & Phone numbers
    text, n = _SSN_RE.subn("[REDACTED_SSN]", text)
    _inc("ssn", n)

    text, n = _PHONE_RE.subn("[REDACTED_PHONE]", text)
    _inc("phone_numbers", n)

    # 8. IPv4 addresses
    text, n = _IPV4_RE.subn("[REDACTED_IP]", text)
    _inc("ip_addresses", n)

    # 9. Explicit personal identity fields (Owner/Author/Contact/Slack ID)
    def _replace_person_field(m: re.Match) -> str:
        val = m.group(2).strip()
        if val.startswith("[REDACTED"):
            return m.group(0)
        _inc("personal_identifiers", 1)
        return f"{m.group(1)}[REDACTED_PII]"

    text = _EXPLICIT_PERSON_FIELD_RE.sub(_replace_person_field, text)

    return text, counts


_LLM_SANITIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "sanitized_markdown": {
            "type": "string",
            "description": "The full Markdown document with any remaining contextual PII replaced by [REDACTED_NAME], [REDACTED_ORG], or [REDACTED_PII].",
        },
        "contextual_redactions_count": {
            "type": "integer",
            "description": "Number of additional contextual PII occurrences redacted.",
        },
    },
    "required": ["sanitized_markdown", "contextual_redactions_count"],
}


def sanitize_agents_markdown(
    content: str,
    *,
    llm: Optional[Any] = None,
    use_llm_scrubber: bool = True,
) -> SanitizationResult:
    """Clear PII from an agents.md string and prepend the MySwarm Plugin metadata header."""
    parsed_cfg = parse_agents_markdown(content, use_llm_fallback=False)
    agent_count = len(parsed_cfg.agents)

    stage1_text, counts = _regex_scrub(content)
    final_body = stage1_text
    llm_scrubbed = False

    if use_llm_scrubber and llm is not None and stage1_text.strip():
        try:
            res = llm.complete_structured(
                instructions=(
                    "You are a privacy and PII sanitizer for shareable AI agent configuration files (agents.md). "
                    "Inspect the Markdown below and replace any remaining Personally Identifiable Information "
                    "(real human names, private employer/company names, private repository URLs, internal Slack/Discord "
                    "channels, physical addresses, or personal identifiers) with `[REDACTED_NAME]`, `[REDACTED_ORG]`, "
                    "or `[REDACTED_PII]`. "
                    "CRITICAL: Preserve all AI agent names, personas, goals, tool names, and Markdown formatting verbatim. "
                    "Do NOT remove or summarize any agent sections."
                ),
                input=[{"type": "text", "text": stage1_text}],
                json_schema=_LLM_SANITIZE_SCHEMA,
                json_mode=True,
                schema_name="myswarm_pii_sanitize",
                purpose="myswarm_export_sanitize",
            )
            parsed = getattr(res, "parsed", None)
            if isinstance(parsed, dict):
                candidate = str(parsed.get("sanitized_markdown") or "").strip()
                extra_count = int(parsed.get("contextual_redactions_count") or 0)
                # Sanity check: ensure LLM didn't truncate the file
                if candidate and len(candidate) >= int(len(stage1_text.strip()) * 0.5):
                    final_body = _EXISTING_HEADER_RE.sub("", candidate)
                    llm_scrubbed = True
                    if extra_count > 0:
                        counts["contextual_pii_llm"] = extra_count
        except Exception as exc:
            logger.debug("Contextual LLM PII scrubbing skipped/failed: %s", exc)

    header = f"<!-- Exported via Hermes MySwarm Plugin | Agents: {agent_count} -->"
    formatted = f"{header}\n{final_body.lstrip()}"
    if not formatted.endswith("\n"):
        formatted += "\n"

    total = sum(counts.values())
    return SanitizationResult(
        sanitized_markdown=formatted,
        agent_count=agent_count,
        redaction_counts=counts,
        total_redactions=total,
        llm_scrubbed=llm_scrubbed,
    )


def export_sanitized_agents_file(
    output_path: Optional[str | Path] = None,
    *,
    source_path: Optional[str | Path] = None,
    default_filename: str = "myswarm-export.md",
    llm: Optional[Any] = None,
    use_llm_scrubber: bool = True,
) -> SanitizationResult:
    """Read the active agents.md, scrub PII, write to *output_path* (.md), and return the result."""
    src_file, workspace_dir = resolve_agents_file(source_path)
    if src_file is None or not src_file.is_file():
        raise FileNotFoundError(
            f"No agents.md (or AGENTS.md / AGENTS.override.md) found in {workspace_dir}"
        )

    if output_path:
        dest = Path(output_path).expanduser()
        if not dest.is_absolute():
            dest = (workspace_dir / dest).resolve()
        else:
            dest = dest.resolve()
    else:
        dest = (workspace_dir / default_filename).resolve()

    if dest.suffix.lower() != ".md":
        dest = dest.with_suffix(".md")

    # Never overwrite the live agents.md file during export
    if dest.resolve() == src_file.resolve():
        raise ValueError(
            f"Export destination ({dest}) cannot be the same file as the source agents.md ({src_file})."
        )

    raw_content = src_file.read_text(encoding="utf-8", errors="replace")
    result = sanitize_agents_markdown(raw_content, llm=llm, use_llm_scrubber=use_llm_scrubber)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(result.sanitized_markdown, encoding="utf-8")
    result.output_path = str(dest)
    return result


def sanitize_swarm_config(config: SwarmConfig) -> Tuple[SwarmConfig, Dict[str, int]]:
    """Run deterministic PII scrubbing across all fields of a parsed SwarmConfig."""
    combined_counts: Dict[str, int] = {}

    def _merge(counts: Dict[str, int]) -> None:
        for k, v in counts.items():
            combined_counts[k] = combined_counts.get(k, 0) + v

    clean_title, c_title = _regex_scrub(config.title)
    _merge(c_title)

    clean_raw, c_raw = _regex_scrub(config.raw_content)
    _merge(c_raw)

    clean_agents: List[AgentSpec] = []
    for agent in config.agents:
        c_name, cn = _regex_scrub(agent.name)
        c_persona, cp = _regex_scrub(agent.persona)
        c_goal, cg = _regex_scrub(agent.goal)
        _merge(cn)
        _merge(cp)
        _merge(cg)

        clean_delegates: List[str] = []
        for target in agent.delegates_to:
            ct, cd = _regex_scrub(target)
            _merge(cd)
            clean_delegates.append(ct.strip())

        clean_agents.append(
            AgentSpec(
                name=c_name.strip(),
                persona=c_persona.strip(),
                goal=c_goal.strip(),
                role_type=agent.role_type,
                delegates_to=clean_delegates,
            )
        )

    sanitized_cfg = SwarmConfig(
        source_path=config.source_path,
        title=clean_title.strip() or "Agent Swarm",
        agents=clean_agents,
        raw_content=clean_raw,
        parse_method=config.parse_method,
    )
    return sanitized_cfg, combined_counts


def load_sanitized_swarm_config(
    path_or_dir: Optional[str | Path] = None,
    *,
    llm: Optional[Any] = None,
    use_llm_fallback: bool = True,
    use_llm_scrubber: bool = True,
) -> Tuple[SwarmConfig, SanitizationResult]:
    """Load agents.md, run full 2-stage PII pruning (regex + optional LLM), and return (SwarmConfig, SanitizationResult)."""
    resolved_file, workspace_dir = resolve_agents_file(path_or_dir)
    if resolved_file is None or not resolved_file.is_file():
        raise FileNotFoundError(
            f"No agents.md (or AGENTS.md / AGENTS.override.md) found in {workspace_dir}"
        )

    raw_content = resolved_file.read_text(encoding="utf-8", errors="replace")
    san_result = sanitize_agents_markdown(
        raw_content,
        llm=llm,
        use_llm_scrubber=use_llm_scrubber,
    )
    cfg = parse_agents_markdown(
        san_result.sanitized_markdown,
        source_path=str(resolved_file),
        llm=llm,
        use_llm_fallback=use_llm_fallback,
    )
    cfg, extra_field_counts = sanitize_swarm_config(cfg)
    for k, v in extra_field_counts.items():
        if k not in san_result.redaction_counts:
            san_result.redaction_counts[k] = v
            san_result.total_redactions += v
    return cfg, san_result


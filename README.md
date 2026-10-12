# MySwarm — Hermes Plugin (`myswarm`)

**MySwarm** is a native plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent) that helps users discover, visualize, export (with best-effort PII pruning), and test/revert community `agents.md` swarm configurations with human approval.

> **Important Responsibility & Security Notice**:
> - **Best-Effort PII Pruning & User Responsibility**: MySwarm's PII scrubbing (deterministic regex patterns + optional contextual LLM redaction) operates strictly on a **best-effort basis** and cannot guarantee the removal of all sensitive, proprietary, or personally identifiable information. **Ultimately, you (the user) are solely responsible for reviewing and verifying any exported `.md` files, ASCII snippets, or images before sharing them.**
> - **Best-Effort Import Warnings & Human Approval**: MySwarm's import security inspection is a **best-effort heuristic and model-assisted warning**, not a guarantee against prompt injection or malicious agent instructions. Every `myswarm_import` (outside preview mode) and `myswarm_revert` tool call asks for **explicit human approval** via Hermes's `pre_tool_call` hook before overwriting your workspace `agents.md`. Only import configurations from sources you trust.

## Key Features

1. **Abbreviated Agent List (`myswarm_list` / `/myswarm list`)**
   Parses `agents.md` / `AGENTS.md` / `AGENTS.override.md` and outputs a concise table of agents, their personas, their goals, and orchestrator/specialist roles.
2. **ASCII Swarm Topology (`myswarm_ascii` / `/myswarm ascii`)**
   Runs best-effort PII scrubbing first, then out of the box renders **both** a vector SVG image (`myswarm-ascii.svg`) **and** a social-media-ready PNG image (`myswarm-ascii.png`) of your ASCII swarm diagram, a multi-line box-and-arrow topology diagram, **and** a ready-to-share **Easy Copy-Paste ASCII Code Block** made of pure 7-bit ASCII symbols (`+`, `-`, `|`, `===>`, role icons like `[\^/]`, `[#!#]`, `[{/}]`, `[?=?]`, stamped `[Shared via Hermes MySwarm Plugin]`).
   - *Sharing Tip*: Share the **ASCII code** for a quick visual preview and lightweight starter config (wrapped persona/goal summaries + routing), and/or share the exported **`.md` file** for the comprehensive, lossless agent instructions. Always review the output yourself before sharing.
3. **Rich AI-Generated Image Visualization (`myswarm_visualize_image` / `/myswarm image [--understated|--normal|--overstated] [theme]`)**
   Uses your active default model (`ctx.llm`) and Hermes's `image_generate` tool to create an art-directed illustration of your agent swarm across two **orthogonal dimensions**:
   - **Dimension 1: Theme / Art Style (`CURATED_SIGNATURE_THEMES`)**:
     - `cyberpunk` — megacity netrunner operations hub, cyberware, neural visors, fiber-optic data streams
     - `sci-fi` — orbital deep-space starship bridge, titanium-weave command suits, plasma-blue astrometric holo-tables
     - `magical forest` — bioluminescent ancient elder-tree sanctuary, carved runes, mossy workstations, ley-line streams
     - `fantasy map` — illustrated parchment cartography war-table, citadel bastions, compass roses, charted route lines
     - `council of wizards` — arcane spire rotunda, star-embroidered archmage robes, grimoires, spell-light threads
     - `olympic gods` — Mount Olympus marble pantheon, gold armor and filigree ornaments, pale white cloaks, fiery eyes, golden lightning streams
     - `American gilded age modernism` — Beaux-Arts & early Art Deco marble/brass syndicate rotunda, tailored Gilded Age attire, brass ticker-tape machines, Edison tungsten lighting
     - `noir detective` — 1940s rain-slicked detective bullpen, trench coats, Venetian blind shadows, crimson yarn evidence threads
     - `solarpunk` — sunlit botanical-glass arcology conservatory, organic-tech linen attire, solar-prism light streams
     - `steampunk` — Victorian brass-and-copper clockwork airship bridge, gearwork instruments, copper aether-conduits
     - `ukiyo-e woodblock` — Edo-period Japanese woodblock command pavilion, mineral-pigment robes, wave-and-wind scroll currents
     - `isometric blueprint` — architectural cyanotype & CAD technical schematic cutaway floor on a coordinate grid
   - **Dimension 2: Orthogonal Visual Intensity (`intensity`)**:
     - `understated` — subtle, restrained, minimalist, muted palette, soft ambient light, uncluttered poise
     - `normal` *(default)* — balanced cinematic concept art, natural dramatic lighting, clear proportions
     - `overstated` — exaggerated, maximalist, larger-than-life epic spectacle, hyper-saturated glow, lavish ornamentation
4. **Best-Effort PII-Scrubbed Markdown Export (`myswarm_export` / `/myswarm export [output.md]`)**
   Runs a best-effort two-stage PII scrubber (deterministic regex redaction for common emails, phone numbers, IPs, local `/Users/<name>` paths, API keys/tokens, and owner fields + optional contextual LLM redaction) and exports a `.md` file inside your current working directory (or `HERMES_HOME/plugin-data/myswarm/exports/`) prefixed with:
   ```markdown
   <!-- Exported via Hermes MySwarm Plugin | Agents: N -->
   ```
   *Note: Because automated PII pruning is best-effort, you are ultimately responsible for inspecting any exported file before sharing it publicly.*
5. **Human-Approved Config Import with Screen Display & Best-Effort Security Warning (`myswarm_import` / `/myswarm import [--preview] <shared.md|shared.txt>`)**
   - **Human Approval (`pre_tool_call` Hook)**: Every non-preview `myswarm_import` and `myswarm_revert` tool call prompts the user for explicit approval before writing to the workspace `agents.md` (and fails closed when unattended).
   - **On-Screen File Display**: Always displays the full contents of the file being imported (`displayed_file_contents`) on the user's screen so they can read it before/when importing (supports `--preview` / `preview_only=true` to inspect without modifying `agents.md`).
   - **Best-Effort Security Warning (Markdown & ASCII)**: Deterministic regex rules and an optional model pass provide a best-effort warning for common prompt-injection phrases, suspicious shell patterns, or credential exfiltration attempts—blocking flagged files by default in tool calls while preserving your original `agents.md` backup.
6. **One-Command Revert (`myswarm_revert` / `/myswarm revert`)**
   Asks for confirmation (when called as a tool) and restores your exact original `agents.md` configuration whenever you finish testing a shared setup.

---

## Usage

### In-Session Slash Commands
```text
/myswarm list
/myswarm ascii
/myswarm image
/myswarm image cyberpunk
/myswarm export ./my-sanitized-swarm.md
/myswarm import ./community-swarm.md
/myswarm status
/myswarm revert
```

### Terminal CLI Commands
```bash
hermes myswarm list
hermes myswarm ascii --style unicode
hermes myswarm image sci-fi
hermes myswarm export ./my-sanitized-swarm.md
hermes myswarm import ./community-swarm.md
hermes myswarm status
hermes myswarm revert
```

### Natural Language (LLM Tools)
- *"Show me an abbreviated list of my agents and their personas and goals."* → calls `myswarm_list`
- *"Draw an ASCII diagram of my agent setup."* → calls `myswarm_ascii`
- *"Create a cyberpunk image visualization of my agent setup."* (or *"Visualize my agent setup as an image"*) → calls `myswarm_visualize_image`
- *"Export my agents.md to a file with best-effort PII scrubbing."* → calls `myswarm_export`
- *"Import `shared-agents.md` so I can test it, and keep my old `agents.md`."* → calls `myswarm_import` (asks for approval)
- *"Revert back to my original `agents.md`."* → calls `myswarm_revert` (asks for approval)

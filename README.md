# MySwarm — Hermes Plugin (`myswarm`)

**MySwarm** is a native plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent) that helps users discover, visualize, sanitize/export, and safely test community `agents.md` swarm configurations.

## Key Features

1. **Abbreviated Agent List (`myswarm_list` / `/myswarm list`)**
   Parses `agents.md` / `AGENTS.md` / `AGENTS.override.md` and outputs a concise table of agents, their abbreviated personas, their goals, and orchestrator/specialist roles.
2. **ASCII Swarm Topology (`myswarm_ascii` / `/myswarm ascii`)**
   Runs best-effort PII scrubbing first, then out of the box renders **both** a vector SVG image (`myswarm-ascii.svg`) **and** a social-media-ready PNG image (`myswarm-ascii.png`) of your ASCII swarm diagram, a box-and-arrow topology diagram, **and** a ready-to-share **Easy Copy-Paste ASCII Code Block** made of pure 7-bit ASCII symbols (`+`, `-`, `|`, `===>`, role icons like `[\^/]`, `[#!#]`, `[{/}]`, `[?=?]`, stamped `[Shared via Hermes MySwarm Plugin]`).
   - *Sharing Tip*: Share the **ASCII code** for a quick visual preview and lightweight starter config (1-line personas/goals + routing), and/or share the exported **`.md` file** for the comprehensive, lossless agent instructions.
3. **Rich AI-Generated Image Visualization (`myswarm_visualize_image` / `/myswarm image [theme]`)**
   Uses your active default model (`ctx.llm`) and Hermes's `image_generate` tool to create an art-directed illustration of your agent swarm—portraying the central orchestrator, each specialist's persona/tools, legible agent name/goal callouts, and visual task delegation streams.
   - **Curated Signature Themes**:
     - `cyberpunk` — neon-drenched megacity netrunner operations hub, chrome cyberware, holographic HUDs & data streams
     - `sci-fi` — orbital deep-space starship bridge, titanium-weave command suits, plasma-blue astrometric holo-tables
     - `magical forest` — bioluminescent ancient elder-tree sanctuary, glowing runes, mossy workstations, ley-line streams
     - `fantasy map` — ornate living illustrated parchment cartography war-table, miniature citadel bastions, golden route lines
     - `council of wizards` — grand arcane spire rotunda, star-embroidered archmage robes, floating grimoires, spell-light threads
     - `olympic gods` — exaggerated Mount Olympus marble pantheon, lots of gleaming gold armor/ornaments, flowing pale white cloaks, blazing fiery eyes, golden lightning streams
     - `American gilded age modernism` — opulent Beaux-Arts & early Art Deco marble/brass syndicate rotunda, bespoke Gilded Age attire, brass ticker-tape machines, warm Edison tungsten glow
   - Or omit the theme and let your default model automatically pick the best visual theme based on your agents' personas and goals.
4. **PII-Cleared Markdown Export (`myswarm_export` / `/myswarm export [output.md]`)**
   Runs a two-stage PII scrubber (deterministic regex redaction for emails, phone numbers, IPs, local `/Users/<name>` paths, API keys/tokens, and owner fields + optional contextual LLM redaction) and exports a comprehensive `.md` file prefixed with:
   ```markdown
   <!-- Exported via Hermes MySwarm Plugin | Agents: N -->
   ```
5. **Safe Config Import with Screen Display & Security/Exploit Audit (`myswarm_import` / `/myswarm import [--preview] <shared.md|shared.txt>`)**
   - **Trust Warning**: Reminds users to only import configurations from authors they trust.
   - **On-Screen File Display**: Always displays the full contents of the file being imported (`displayed_file_contents`) on the user's screen so they can read it before/when importing (supports `--preview` / `preview_only=true` to inspect without modifying `agents.md`).
   - **Exploit & Security Risk Check (Markdown & ASCII)**: Both deterministic security rules and the Hermes Agent (`ctx.llm` + system prompt instructions) inspect every imported `.md` or Copy-Paste ASCII file for prompt injections, hidden instructions, destructive commands, remote code execution, and credential exfiltration—automatically blocking suspicious files by default while preserving your original `agents.md`.
6. **One-Command Revert (`myswarm_revert` / `/myswarm revert`)**
   Restores your exact original `agents.md` configuration whenever you finish testing a shared setup.

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
- *"Export my agents.md to a file cleared of PII."* → calls `myswarm_export`
- *"Import `shared-agents.md` so I can test it, and keep my old `agents.md`."* → calls `myswarm_import`
- *"Revert back to my original `agents.md`."* → calls `myswarm_revert`

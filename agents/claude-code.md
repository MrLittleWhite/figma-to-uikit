# Claude Code adapter

Read `../SKILL.md` first; this file is a referenced instruction adapter, not an automatically executed agent definition.

## Install

Copy this entire skill directory to `<project>/.claude/skills/figma-to-uikit/` for a project-local installation, or `~/.claude/skills/figma-to-uikit/` for a personal installation. Preserve scripts, schemas, templates and references. Do not copy only SKILL.md. Check the destination before copying; never overwrite an existing installation blindly.

In a new session, invoke `/figma-to-uikit` with a Figma URL/node selection or JSON path and the target UIKit project/output directory. If skill discovery differs in the installed version, explicitly ask Claude to read the installed SKILL.md and follow it.

## Workflow

1. Read target project instructions and UIKit conventions.
2. Discover available Figma MCP read/export capabilities and follow `../references/figma-acquisition.md`. No specific MCP provider is required and this skill does not install one.
3. Save an evidence-backed capture in the documented input format; do not assume MCP summaries are accepted raw input.
4. Use `python3 <skill-path>/scripts/figma_to_uikit.py --help`, then normalize, validate and generate into an explicit directory.
5. Read diagnostics, adapt generated baseline to existing code, build with the actual iOS scheme and compare simulator output when available.

The host assistant acquires/interprets evidence; Python only performs deterministic offline conversion. Do not call a model API from the converter. Do not alter global settings, permissions, or the Figma document as part of conversion.

# Install This Rule Pack Into a Project

## 1. Extract location

Extract this rule pack into the project root, next to `.git/`.

Example:

```text
project-root/
├── .git/
├── AGENTS.md
├── AI_DAILY_RULES.md
├── CODEX_START_HERE.md
├── docs/
├── .github/
├── .cursor/
├── skills/
├── frontend/
├── backend/
└── old-system/
```

Do not place these files inside `.git/`.



## 3. Read-only legacy reference

If an old system is used as reference material, place it under `old-system/` and keep it read-only.

Recommended `.gitignore` pattern:

```gitignore
old-system/*
!old-system/README.md
```

Analysis output should go under:

```text
docs/old-system-analysis/
```

## 4. Merge instead of blindly overwriting

If the project already has `.github/`, `.cursor/`, `docs/`, `frontend/`, or `backend/`, compare and merge the files manually. Do not blindly overwrite existing project work.

## 5. AI tools

External AI tools and skills are developer-local aids. They must not be installed through `npm install`, `postinstall`, CI, Docker, or application runtime scripts unless explicitly approved.

For optional AI tool setup, read:

```text
docs/tools/AI_TOOL_INSTALL_GUIDE.md
```

Hooks, plugins, API keys, OAuth tokens, and MCP tokens must be reviewed and trusted by the developer, not silently accepted by AI.


## GitHub CODEOWNERS

`.github/CODEOWNERS` is included as the code-owner review entry point. Add real GitHub users or teams after installing the rule pack, then enable code-owner review in branch protection. Do not leave fake owners in the file.

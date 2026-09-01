# Ponytail Compatibility Rules

## 1. Purpose

Ponytail is treated as a project-level AI rule-workflow guard for this repository.
It helps AI agents keep project rules active during development tasks.

These Ponytail compatibility rules are active by default as project rules.
They do not depend on an official Ponytail hook being installed on a developer machine.

## 2. Authority

Ponytail does not replace the project rule hierarchy.

Priority order:

```text
User latest instruction
> AGENTS.md
> AI_DAILY_RULES.md
> approved PRP or task plan
> planning files
> Ponytail or other external AI workflow tools
```

If Ponytail behavior conflicts with project rules, the AI must stop and ask.

## 3. Allowed use

Ponytail may be used to support:

```text
reading required project rules
keeping rule checks active during tasks
reminding AI to use PRP before complex work
reminding AI to maintain planning files for long tasks
preventing accidental edits outside allowed paths
preventing claims of completion without verification
```

## 4. Forbidden use

Ponytail must not be used to:

```text
modify old-system
connect to production systems
run production migrations
write or expose secrets
bypass PR review
bypass CI
deploy the project
add runtime dependencies
override AGENTS.md or AI_DAILY_RULES.md
```

## 5. Installation boundary

The project may document Ponytail-compatible behavior, but Ponytail must not be added as a production dependency.

Do not add Ponytail to:

```text
frontend/package.json
backend/pyproject.toml
Dockerfile
CI required steps
postinstall scripts
production servers
```

Local developer installation is separate from project runtime.
The project must remain usable even when Ponytail is not installed locally.

## 6. Completion report

If Ponytail or Ponytail-compatible rules are used, the AI completion report must mention:

```text
whether Ponytail rules were considered
which project rules were read
whether any conflict was detected
what verification was performed
```

# Ponytail Compatibility

Use this skill for any AI coding task that needs project-rule continuity or workflow guard behavior.

## Instructions

1. Read `AGENTS.md` and `AI_DAILY_RULES.md` first.
2. Read `docs/PONYTAIL_COMPATIBILITY_RULES.md`.
3. Identify the task type and the allowed edit paths.
4. Check whether the task needs a PRP, planning files, Context7, tests, or review.
5. Do not modify disallowed paths or production systems.
6. Do not treat Ponytail as a production dependency.
7. Stop and ask if Ponytail behavior conflicts with project rules or user instructions.

## Output requirement

Before implementation, state:

```text
Ponytail compatibility check: applied / not needed
Rules read:
Allowed paths:
Forbidden actions:
Verification plan:
```

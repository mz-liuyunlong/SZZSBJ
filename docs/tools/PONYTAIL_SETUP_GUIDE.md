# Ponytail Setup Guide

## Purpose

This guide documents how Ponytail is handled by the project rule pack.

Ponytail support is a rule-workflow compatibility layer. It is not a production dependency and is not required for the application to run.

## Project rule behavior

AI agents must follow `docs/PONYTAIL_COMPATIBILITY_RULES.md` whether or not the official Ponytail plugin is installed locally.

The rule pack provides the behavior baseline. Local Ponytail installation only improves automation for agents that support it.

## Installation boundary

Do not install Ponytail automatically through project setup.

Forbidden locations:

```text
frontend/package.json
backend/pyproject.toml
Dockerfile
GitHub Actions required jobs
postinstall scripts
production servers
```

Allowed location:

```text
developer local machine or AI tool configuration
```

## Required AI behavior

When an AI agent claims to use Ponytail or a Ponytail-like workflow, it must still read and follow:

```text
AGENTS.md
AI_DAILY_RULES.md
docs/tools/AI_SKILL_REGISTRY.md
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

Ponytail cannot approve code changes, bypass PR review, bypass CI, or override any project rule.

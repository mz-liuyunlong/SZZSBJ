# Docs-only Task Prompt

```text
Role: <single main role>
Worktree: <absolute path>
Branch: <branch>
Allowed files: <exact list>

Preflight pwd/branch/status/base; stop if dirty or mismatched.
Read project entry rules and all source documents before editing.

Modify only the listed docs. Do not change code, dependencies, CI, scripts, old-system, environment files or production configuration. Do not connect to a database/server, execute SQL, call real APIs, deploy or read secrets. Do not perform git add/commit/push/PR/merge.

Keep current facts, planned capabilities and approvals distinct. Preserve existing authorities; use links instead of copying conflicting rules. Run only existing safe documentation checks and report factual results.
```

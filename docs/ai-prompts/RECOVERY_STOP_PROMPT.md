# Recovery Stop Prompt

```text
STOP implementation immediately when directory, branch, base, worktree state, allowlist, PRP approval, tests, credentials/environment or production target is unexpected.

Do not switch, pull, stash, reset, restore, clean, merge, rebase, delete, rewrite, stage or upload to repair it.

Report:
- expected vs actual worktree/branch/base/status;
- unexpected files or failed checks;
- whether any write/external action already occurred;
- risk and smallest owner-controlled recovery options;
- information the owner must confirm.

Resume only after the owner explicitly resolves the mismatch and reissues scope.
```

# Dead Ends

Build site: context/plans/build-site.md

- 2026-10-26T13:46:03Z Worktree isolation: agent worktrees sometimes start on origin/master (f306cf3d) which lacks action-server/. Agents must branch from local master HEAD explicitly. Python packet worktree is on f306cf3d: cherry-pick its commits instead of merging.
- 2026-10-26T13:46:03Z Merging into master fails with "local changes would be overwritten" while the user's staged deletion of kairon-action/ is in the index. Stash (plain `git stash push`, no pathspec) before merging, `git stash pop --index` after. Never delete a packet branch before confirming the merge landed.
- 2026-10-26T13:46:03Z Pre-commit hook runs code-review-graph detect-changes (minutes). Use `--no-verify` for coordinator commits.
- 2026-10-26T14:07:45Z No MongoDB on this machine: the recorder (T-025) is validated with mongomock only; the 434-node recording run and every fixture-replay verification task need a real Mongo. Start one (docker or local) before T-053/T-057+.

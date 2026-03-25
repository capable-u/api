# Git Commit Message Instructions

For commit messages in this repository:

- Use Conventional Commits.
- Format: type(scope): summary
- Keep the header under 100 characters.
- Use English.
- Allowed types: feat, fix, refactor, perf, docs, ci, build, test, deps, chore
- Preferred scopes: search, upload, documents, api, ui, table, sidebar, release, changelog, workflows
- Summarize the final outcome of the work, not intermediate edits.
- Never write vague messages such as "update", "fix stuff", "changes", "final".

Examples:
- feat(search): add hybrid file search
- fix(upload): prevent duplicate upload requests
- refactor(api): simplify document service
- ci(release): add release please and commitlint setup
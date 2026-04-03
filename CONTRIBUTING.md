# API Contribution Guide

This guide explains how to write commit messages and set up `pre-commit` checks in this repository.

## 1) Pre-commit setup

Run from `api/`:

```bash
python3 -m pip install --upgrade pip pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

Run all checks manually:

```bash
pre-commit run --all-files --show-diff-on-failure
```

## 2) Ruff formatting behavior

This repository uses **Ruff** for both linting and formatting through `pre-commit`.

During `git commit` or `pre-commit run --all-files`, the `ruff-format` hook may automatically rewrite files.
If that happens, the commit/check will fail on purpose because the modified files must be reviewed and staged again.

Typical flow:

1. Run commit or `pre-commit`.
2. Ruff reformats some files.
3. Stage the updated files again (if needed):
   ```bash
   git add .
    ```
4.	Re-run the commit or checks.

This is expected behavior and does not mean the hook is broken.

You can also run Ruff manually before committing:
```bash
ruff format .
pre-commit run --all-files --show-diff-on-failure
```

## 3) Commit message rules

We use **Conventional Commits** with strict validation.

*You can also use [Auto-Generate commit message](.github/git-commit-instructions.md).*

Format:

```text
type(scope): summary
```

Rules:
- Use English.
- Keep header under 100 characters.
- Make summary specific and outcome-focused.
- Avoid vague messages like `update`, `fix stuff`, `changes`.

Allowed `type` values:
- `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `deps`, `chore`, `revert`

Examples:
- `feat(documents): add soft-delete restore endpoint`
- `fix(search): handle empty query safely`
- `ci(workflows): run pre-commit on pull requests`

## 4) PR title rule

PR title must follow the same Conventional Commit format and allowed types.

## 5) Before pushing

- Run `pre-commit run --all-files`.
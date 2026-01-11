Contributing

Thank you for contributing. This document explains the minimal workflow and checks we expect before opening a pull request.

Branching

Create a feature branch per change:

git checkout -b feat/short-description

Keep commits small and focused.

Local checks before commit

Run unit tests for changed area (fast, targeted):

PYTHONPATH=. python -m pytest -q tests/test_supabase_client.py

Run full test suite before pushing:

PYTHONPATH=. python -m pytest -q

Format and lint:

python -m black .
python -m flake8

Type checks (if applicable):

python -m mypy

Manual smoke test any interactive or integration behavior you changed.

Review staged changes and commit only related files:

git add -p
git diff --staged

Commit message style

Title: imperative, short (50 chars or less)

Body: explain why, not what; reference issue IDs if any

Example:

Add deterministic embedding stub and unit tests

- Add compute_embedding stub
- Implement SupabaseClient.upsert_note_with_embedding
- Add tests/test_supabase_client.py
Fixes: #123

Pull requests

Open a PR against main from your feature branch.

Ensure CI passes and include a short description of the change and testing performed.

Request at least one reviewer for non-trivial changes.

CI and branch protection

CI runs tests and linters on push and PRs.

Do not merge until CI passes and reviews are complete.

Adding tests

Add unit tests for new behavior and edge cases.

Keep tests deterministic and avoid network calls by using stubs or mocks.

🛠 Local development workflow

This project uses a Makefile to streamline formatting, linting, type checking, and testing. Once you’ve cloned the repo and set up your environment, you can use the following commands:

🔧 Formatting & Linting

make format — Format all Python files using black

make lint — Lint code using flake8 to catch style issues and simple bugs

make fix — Auto-fix formatting issues using black and isort

🧪 Testing & Type Checking

make test — Run all unit tests using pytest

make type — Run static type checks using mypy

✅ Full Pre-Commit Check

make check — Run all of the above in sequence: format, lint, type check, and tests

💡 Tip: Run make or make help to see available targets.

Contact

For questions about workflow or CI, open an issue or ping the repo maintainers.

COMMIT_CHECKLIST.md

# Commit Checklist

Use this checklist before committing and pushing.

- [ ] Branch created for this change
- [ ] Relevant unit tests run locally for changed modules
- [ ] Full test suite run locally
- [ ] Code formatted with black
- [ ] Linting passed (flake8)
- [ ] Type checks passed (mypy) if applicable
- [ ] Only related files staged (`git add -p`)
- [ ] Staged diff reviewed (`git diff --staged`)
- [ ] Commit message follows style guidelines
- [ ] PR opened with description and testing notes
- [ ] CI passing on PR before merge
# POC: Block PR merge unless code was reviewed via the VS Code extension's SSE flow

## Context
Goal is a required GitHub check run — "Appmod Extension Origin Check" — that passes only if the PR's current head commit was already analyzed via the backend's `/pr-reviewer/open` SSE endpoint (the flow the VS Code extension calls) before the PR was opened, and fails if the PR was opened without that pre-analysis (e.g. raised directly on github.com). Once this check exists and is marked "required" in GitHub branch protection, merging is blocked for any PR that didn't go through the extension flow first.

The user will implement these changes by hand — this is a spec, not a diff to apply.

## Signal being used
`handle_pull_request_event` in `App/pr_reviewer/github_app/webhook_handlers.py` already has the building block: when the SSE flow runs, `PRReport(metadata=payload).initialize_db()` (in `App/pr_reviewer/pipeline/core.py`, class `PRReport`, ~line 5104) writes a Mongo doc to `code_profile_db.pr_reports` with:
- `pr_metadata.repo_url` / `pr_metadata.head_branch` / `pr_metadata.base_branch`
- `commits.head` = the exact head SHA that was analyzed (fetched via `github_manager.get_pre_pr_files(...)` before the PR existed)
- `is_extension = True`
- `completed` = `True` once `insert_to_db` finishes

The existing code at `webhook_handlers.py:113-125` already queries this and compares `previous_report.commits.head == head_commit` — but only inside the `pr_search_url.split("/")[-1].isdigit()` branch, and only to decide whether to *reuse* the report for UX (skip re-running AI review), not to gate anything. We reuse the same query/comparison, but run it unconditionally and turn the result into a check-run conclusion.

This is SHA-bound (not just branch-name matching), so it can't be spoofed by opening a manually-created PR on a similarly-named branch — the attacker would need the exact commit content to have been reviewed via `/pr-reviewer/open` first.

## Changes

### 1. `App/pr_reviewer/enums.py` — `CheckRunConfig`
Add two static methods next to the existing `_APPMOD_QUALITY_CHECK_PASSED` / `_APPMOD_QUALITY_CHECK_FAILED` (~line 97-118), same dict shape so they plug straight into `create_check_run(**...)`:

```python
@staticmethod
def _ORIGIN_CHECK_PASSED():
    
    return {
        "name": "Appmod Extension Origin Check",
        "status": "completed",
        "conclusion": "success",
        "title": "PR Origin Verified ✅",
        "summary": "This PR's code was reviewed via the AppMod VS Code Extension before it was opened.",
        "text": "Origin check passed."
    }

@staticmethod
def _ORIGIN_CHECK_FAILED():
    return {
        "name": "Appmod Extension Origin Check",
        "status": "completed",
        "conclusion": "failure",
        "title": "PR Not Raised via Extension ❌",
        "summary": "This PR was not opened through the AppMod VS Code Extension. Please use the extension to raise PRs.",
        "text": "No matching extension-reviewed analysis was found for this exact commit."
    }
```

### 2. `App/pr_reviewer/github_app/webhook_handlers.py`

Add a small helper (near the top of the file, alongside `verify_webhook_signature`):

```python
def is_pr_origin_verified(payload, pr):
    origin_report = code_profile_db.pr_reports.find_one(
        {
            "pr_metadata.repo_url": payload['repository']['html_url'],
            "pr_metadata.head_branch": pr['head']['ref'],
            "pr_metadata.base_branch": pr['base']['ref'],
        },
        sort=[("created_at", -1)],
        projection={"is_extension": 1, "completed": 1, "commits": 1},
        hint=config.PREVIOUS_REPORT_INDEX_NAME,
    ) or {}

    current_head_sha = pr.get('head', {}).get('sha')
    return (
        bool(origin_report)
        and origin_report.get("is_extension", False)
        and origin_report.get("completed", False)
        and origin_report.get("commits", {}).get("head") == current_head_sha
    )
```

Call it and create the check run in two places, right after `github_manager = GitHubPRManager(...)` is constructed (reuse the same manager already created for the other check runs — do not build a second one):

- **`handle_pr_opened`** (~line 200-212): after the existing `github_manager.create_check_run(**CheckRunConfig.INITIAL_PR_APPMOD_QUALITY_CHECK.value, ...)` call, add:
  ```python
  origin_config = CheckRunConfig._ORIGIN_CHECK_PASSED() if is_pr_origin_verified(payload, pr) else CheckRunConfig._ORIGIN_CHECK_FAILED()
  github_manager.create_check_run(**origin_config, pat_token=token)
  ```
  This single call covers both code paths that lead into `handle_pr_opened` — the "reuse existing extension report" path (webhook_handlers.py:131-141) and the plain "opened/reopened" path (~155-158) — since both end up calling this function before returning.

- **`handle_pr_synchronize`** (~line 591-603): after the existing `INITIAL_PR_SYNC_APPMOD_QUALITY_CHECK` check-run creation, add the same two lines, re-evaluating against the new head SHA — so a PR that fails the origin check can flip to passing if the dev pushes a commit that *was* reviewed via `/pr-reviewer/open`, and a previously-passing PR flips to failing if new commits are pushed without going through the extension first.

Skip this for `handle_pr_closed` — not relevant once merged/closed.

### 3. Local test procedure (no new tooling needed, this is a run/verify recipe, not code)
1. Start the Flask app locally with the usual env vars (`MONGODB_CLIENT`, `MONGO_COLLECTION`, `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`, etc. — same ones already required to run this repo).
2. Since `create_check_run` always hits the real GitHub REST API (`App/pr_reviewer/utils/git_utils.py:620`), there's no mock mode — testing needs a real repo with your GitHub App installed.
3. Push a branch to that repo, then call `POST /api/pr_reviewer/pr-reviewer/open` locally with that branch's owner/repo/base/head/token info (same payload the extension sends) — this writes the `is_extension=True` Mongo doc keyed to that branch's current head SHA.
4. Because GitHub can't reach `localhost`, tunnel your local Flask port with `ngrok http <port>` (or smee.io) and temporarily point the GitHub App's webhook URL at `<tunnel>/api/pr_reviewer/pr-reviewer/webhook`.
5. Open the real PR on GitHub for that branch → confirm the "Appmod Extension Origin Check" run appears with conclusion `success`.
6. Control case: push a different branch and open a PR directly on GitHub *without* calling `/pr-reviewer/open` first → confirm the check appears with conclusion `failure`.

### 4. Branch protection (one-time GitHub UI step, not code)
Repo → Settings → Branches → protection rule on the target branch → enable "Require status checks to pass before merging" → add "Appmod Extension Origin Check" as required. (GitHub only lists a check as selectable after it has run at least once on the repo, so do step 3 first.)

## Optional: feature flag
`App/pr_reviewer/utils/misc_utils.py:7` already has `is_feature_enabled(db, feature_name, default=False)`, used elsewhere in this codebase. Consider wrapping the two `create_check_run` calls above in `if is_feature_enabled(code_profile_db, "block_merge_if_not_extension"): ...` so the POC can be toggled off without a deploy if it misfires on real PRs during testing.

## Verification
- Positive case: SSE flow run → PR opened on matching branch/commit → check run shows success → (once required) merge button enabled.
- Negative case: PR opened directly on GitHub with no prior SSE run → check run shows failure → merge button blocked once the check is marked required.
- Sync case: push new commits to an already-open, failing PR after running `/pr-reviewer/open` for the new head SHA → check flips to success on the `synchronize` event.

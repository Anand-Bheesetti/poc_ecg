# Plan: Auto-provision branch-protection ruleset for all org repos (existing + newly created)

## Goal (as requested)
1. When the GitHub App is installed at the **organization** level, the merge-block ruleset should automatically apply to **all repos** in that org.
2. If a **new repo is created** in that org **after** installation, the same ruleset should automatically apply to it too — no manual step.

This is a spec only. No code has been changed yet.

---

## What already exists today

`App/pr_reviewer/github_app/webhook_handlers.py:102-127` — `handle_installation_event`:

```python
def handle_installation_event(payload):
    """
    Auto-provision the org-wide origin-check ruleset when the App is installed on an org.
    """
    action = payload.get('action')
    if action != 'created':
        return jsonify({'message': f'Installation action {action} ignored'}), 200

    installation = payload.get('installation', {})
    installation_id = installation.get('id')
    account = installation.get('account', {})
    org = account.get('login')

    if account.get('type') != 'Organization':
        logger.info(f"Installation {installation_id} is on a user account ({org}), skipping ruleset provisioning")
        return jsonify({'message': 'User-account installation, ruleset provisioning skipped'}), 200

    github_app = GitHubApp()
    ruleset_payload = RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID)

    try:
        github_app.create_org_ruleset(installation_id, org, ruleset_payload)
    except Exception as e:
        logger.error(f"Failed to provision org ruleset for {org}: {e}", exc_info=True)

    return jsonify({'message': f'Installation event handled for {org}'}), 200
```

This is wired up only for the `installation` webhook event in `App/pr_reviewer/github_app/app.py:44-52`:

```python
if event_type == 'pull_request':
    return handle_pull_request_event(payload)
elif event_type == 'pull_request_review':
    return handle_pull_request_review_event(payload)
elif event_type == 'pull_request_review_comment':
    print("comming in pull_request_review_comment event")
    return handle_pull_request_review_comment_event(payload)
elif event_type == 'installation':
    return handle_installation_event(payload)
else:
    logger.info(f"Unhandled event type: {event_type}")
    return jsonify({'message': 'Event received'}), 200
```

The ruleset itself, `App/pr_reviewer/enums.py:382-414` — `RulesetConfig._ORIGIN_CHECK_ORG_RULESET`:

```python
class RulesetConfig:
    RULESET_NAME = "PRR Genius Extension Origin Check"

    @staticmethod
    def _ORIGIN_CHECK_ORG_RULESET(app_id):
        return {
            "name": RulesetConfig.RULESET_NAME,
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {"include": ["~ALL"], "exclude": []},
                "repository_name": {"include": ["*"], "exclude": []}
            },
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [
                            {
                                "context": "PRR Genius Extension Origin Check",
                                "integration_id": int(app_id)
                            }
                        ],
                        "strict_required_status_checks_policy": False
                    }
                }
            ]
        }
```

Key fact: `repository_name.include = ["*"]` is a **wildcard pattern**, evaluated dynamically by GitHub against every repo name in the org at the time a ref/PR is evaluated — it is not a static snapshot of repos taken when the ruleset was created. This means, in principle, requirement #1 and #2 are *already* satisfied by this one ruleset once it exists, for repos the App can see.

The actual gap is not the ruleset condition — it's that `handle_installation_event` is the **only** place that ever calls `create_org_ruleset`, and it only fires once, at install time. There's no code path that re-asserts or reacts when:
- a repo is later added to the App's access (relevant if the org chose "selected repositories" instead of "all repositories" at install time), or
- a new repo is created in the org.

---

## Cases and whether they're covered

| # | Scenario | Covered today? | Covered by this plan? |
|---|----------|-----------------|------------------------|
| A | App installed org-wide with **"All repositories"** access, at install time | ✅ Yes — `handle_installation_event` creates the wildcard ruleset once; it already matches every existing repo | ✅ (unchanged) |
| B | New repo created in an org where the App has **"All repositories"** access | ✅ Effectively yes, because the wildcard ruleset dynamically matches the new repo by name and GitHub auto-grants the App access to it. But there is **no explicit re-assertion** — if the ruleset was ever deleted/edited/lost after install, nothing notices | ✅ Adds an explicit, idempotent re-assert on `repository` (`created`) and `installation_repositories` (`added`) events, as a safety net + audit log entry per new repo |
| C | App installed org-wide with **"Selected repositories"** access, and an admin later **adds more repos** to that selection | ⚠️ Partially — the ruleset (if created) already matches those repos by name, but the App only gains the ability to *report* the required check on repos it has access to. Nothing today reacts to the access change | ✅ Adds `handle_installation_repositories_event` (`action == 'added'`) to log the newly accessible repos and re-assert the ruleset |
| D | New repo created in an org with **"Selected repositories"** access, and the repo is **not** added to the App's selection | ❌ Not covered — and **cannot** be covered by webhooks. GitHub will not deliver *any* event to an App for a repo it has no installation access to. The required-status-check rule would still nominally apply (wildcard match) but the App can never post the check, which would leave that repo's matching branches permanently blocked from merging (a required check that never runs blocks merge indefinitely) | ❌ Out of scope for a webhook-only solution. See "Not covered" section below for options |
| E | App installed on a **personal/user account** (not an org) | Explicitly skipped (`account.get('type') != 'Organization'`) | ❌ Unchanged — out of scope per your request, which was specifically "at org level" |
| F | Org ruleset is manually deleted or edited by an org admin after being created | ❌ Not covered — nothing re-creates it unless a new `installation`, `installation_repositories`, or `repository` event happens to fire afterward | ⚠️ Partially mitigated as a side effect (any subsequent repo-created/added event will re-assert it), but not proactively monitored |

---

## Code changes

### 1. `App/pr_reviewer/github_app/webhook_handlers.py`

Refactor the ruleset-provisioning logic out of `handle_installation_event` into a small reusable helper, then add two new handlers that call it. Replace lines 102-127:

```python
def _ensure_org_ruleset(installation_id, org):
    """
    Idempotently (re)provision the org-wide origin-check ruleset.
    create_org_ruleset treats a 422 (already exists) as a no-op, so this is safe to call
    repeatedly from multiple event handlers.
    """
    github_app = GitHubApp()
    ruleset_payload = RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID)

    try:
        github_app.create_org_ruleset(installation_id, org, ruleset_payload)
    except Exception as e:
        logger.error(f"Failed to provision org ruleset for {org}: {e}", exc_info=True)


def handle_installation_event(payload):
    """
    Auto-provision the org-wide origin-check ruleset when the App is installed on an org.

    The ruleset's repository_name condition is a wildcard ("*"), evaluated dynamically by
    GitHub against every repo in the org - including ones created later - so no further
    action is strictly required per-repo once this ruleset exists and the App has access.
    """
    action = payload.get('action')
    if action != 'created':
        return jsonify({'message': f'Installation action {action} ignored'}), 200

    installation = payload.get('installation', {})
    installation_id = installation.get('id')
    account = installation.get('account', {})
    org = account.get('login')

    if account.get('type') != 'Organization':
        logger.info(f"Installation {installation_id} is on a user account ({org}), skipping ruleset provisioning")
        return jsonify({'message': 'User-account installation, ruleset provisioning skipped'}), 200

    _ensure_org_ruleset(installation_id, org)

    return jsonify({'message': f'Installation event handled for {org}'}), 200


def handle_installation_repositories_event(payload):
    """
    Re-assert the org-wide ruleset whenever the App's repository access changes.

    Matters most when the installation is scoped to "selected repositories": the org-wide
    wildcard ruleset already matches every repo by name, but the required status check it
    enforces can only be satisfied on repos the App can actually post checks to. Repos
    listed here are the ones the App just gained access to.
    """
    action = payload.get('action')  # 'added' or 'removed'
    installation = payload.get('installation', {})
    installation_id = installation.get('id')
    account = installation.get('account', {})
    org = account.get('login')

    if account.get('type') != 'Organization':
        return jsonify({'message': 'User-account installation, ruleset provisioning skipped'}), 200

    if action == 'added':
        repos_added = [r.get('full_name') for r in payload.get('repositories_added', [])]
        logger.info(f"Repos added to installation {installation_id} for {org}: {repos_added}")
        _ensure_org_ruleset(installation_id, org)

    return jsonify({'message': f'Installation repositories event ({action}) handled for {org}'}), 200


def handle_repository_event(payload):
    """
    Re-assert the org-wide ruleset when a new repo is created in an org the App is installed on.

    The wildcard ruleset already applies to new repos automatically once the App can see them;
    this is a defensive re-assertion (e.g. in case the ruleset was previously deleted, or the
    original provisioning call failed) plus an audit-log entry per new repo.
    """
    action = payload.get('action')
    if action != 'created':
        return jsonify({'message': f'Repository action {action} ignored'}), 200

    repository = payload.get('repository', {})
    owner = repository.get('owner', {})
    org = owner.get('login')
    installation = payload.get('installation', {})
    installation_id = installation.get('id')

    if owner.get('type') != 'Organization' or not installation_id:
        logger.info(f"Repository {repository.get('full_name')} created outside an org installation, skipping")
        return jsonify({'message': 'Not an org installation, ruleset provisioning skipped'}), 200

    logger.info(f"New repository created in org {org}: {repository.get('full_name')}")
    _ensure_org_ruleset(installation_id, org)

    return jsonify({'message': f'Repository created event handled for {org}'}), 200
```

Notes:
- `handle_repository_event` only fires `_ensure_org_ruleset` for `action == 'created'`; other repository actions (`deleted`, `renamed`, `archived`, `transferred`, etc.) are ignored, matching current scope.
- `installation_id` on a `repository` event payload is present because these events are delivered through the GitHub App's webhook endpoint (every payload includes the `installation` object), not because we look it up separately.

### 2. `App/pr_reviewer/github_app/app.py`

Import the two new handlers (line 6-12) and route the two new event types (line 44-55):

```python
from pr_reviewer.github_app.webhook_handlers import (
    verify_webhook_signature,
    handle_pull_request_event,
    handle_pull_request_review_event,
    handle_pull_request_review_comment_event,
    handle_installation_event,
    handle_installation_repositories_event,
    handle_repository_event,
)
```

```python
    if event_type == 'pull_request':
        return handle_pull_request_event(payload)
    elif event_type == 'pull_request_review':
        return handle_pull_request_review_event(payload)
    elif event_type == 'pull_request_review_comment':
        print("comming in pull_request_review_comment event")
        return handle_pull_request_review_comment_event(payload)
    elif event_type == 'installation':
        return handle_installation_event(payload)
    elif event_type == 'installation_repositories':
        return handle_installation_repositories_event(payload)
    elif event_type == 'repository':
        return handle_repository_event(payload)
    else:
        logger.info(f"Unhandled event type: {event_type}")
        return jsonify({'message': 'Event received'}), 200
```

### 3. GitHub App settings (github.com — not a code change)

For GitHub to ever *send* the two new webhook events, the App's subscribed events must include:
- **Installation repositories** (fires `installation_repositories`)
- **Repository** (fires `repository`)

This is set under the GitHub App's settings → "Permissions & events" → "Subscribe to events". No permission scope changes are needed beyond what the App already has for org rulesets/checks. Without this step, the new handlers will simply never be invoked (harmless, but pointless) — this is the one manual step needed to activate the plan.

---

## What is explicitly NOT covered

- **Case D above**: a new repo created in an org where the App is installed with "selected repositories" access, and that repo is never added to the selection. GitHub does not deliver any webhook to an App for repos it has no installation access to, so this cannot be solved with event handlers alone. Options if this matters:
  - Recommend/require orgs to install the App with **"All repositories"** access (simplest, avoids the whole class of problem).
  - Add a periodic reconciliation job (e.g. a cron hitting `GET /orgs/{org}/installations` + `GET /installation/repositories` via the org's installation token) that diffs the App's visible repos against the ruleset and/or against `GET /orgs/{org}/repos`, and alerts (not auto-fixes, since it can't grant itself access) when repos exist outside the App's access. This is a bigger change and wasn't in scope of your request, flagging it here only for awareness.
- **Personal/user-account installs** — unchanged, intentionally out of scope since you asked specifically about org-level installs.
- **Ruleset drift** (case F) — only mitigated as a side effect of other events firing later; there's no active monitoring/alerting if a ruleset is deleted and no new repo/installation event happens to occur afterward.

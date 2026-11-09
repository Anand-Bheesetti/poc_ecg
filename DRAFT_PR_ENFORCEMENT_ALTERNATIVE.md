# Plan-Independent Alternative: Draft-PR Enforcement

## Why this exists

Required status checks — whether via **Repository/Organization Rulesets** or **classic branch protection** — are plan-gated by GitHub for private repos. Confirmed in testing: a manually-created ruleset succeeds on a private Free-plan repo, but attaching a **`required_status_checks`** rule to it returns:

```json
{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature.","status":"403"}
```

That gate is on the `required_status_checks` **rule type specifically**, not on rulesets as a container — the ruleset object itself can be created on a Free-plan private repo, but the one rule type this whole feature depends on cannot. That means for private repos on Free-plan personal accounts or Free-plan orgs, the required-check approach (branch protection rules, rulesets, per-repo/org automation via the GitHub App) **cannot produce a hard block, no matter how it's configured**.

## The mechanism that isn't plan-gated: Draft PRs

GitHub disables the "Merge pull request" button for a Draft PR — in the UI, and the merge REST endpoint itself refuses to merge a draft PR. This is true on every plan, public or private repos alike, no upgrade required.

Converting a PR to/from Draft is a **GraphQL mutation**, not REST, and only needs the `pull requests: write` permission the App already has for posting review comments — **no new permission grant required**, unlike the Rulesets automation approach.

## Implementation

### `App/pr_reviewer/github_app/auth.py` — GraphQL support

```python
def make_graphql_request(self, installation_token, query, variables=None):
    """Execute a GraphQL mutation/query using the installation token."""
    headers = {
        'Authorization': f'Bearer {installation_token}',
        'Content-Type': 'application/json'
    }
    return requests.post(
        'https://api.github.com/graphql',
        headers=headers,
        json={'query': query, 'variables': variables or {}},
        timeout=30
    )
```

### `App/pr_reviewer/enums.py` — the two mutations

```python
class DraftEnforcementConfig:
    CONVERT_TO_DRAFT_MUTATION = """
    mutation ConvertToDraft($pullRequestId: ID!) {
      convertPullRequestToDraft(input: {pullRequestId: $pullRequestId}) {
        pullRequest { id isDraft }
      }
    }
    """

    MARK_READY_MUTATION = """
    mutation MarkReady($pullRequestId: ID!) {
      markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) {
        pullRequest { id isDraft }
      }
    }
    """
```

`pullRequestId` is the PR's GraphQL node ID — already present in every `pull_request` webhook payload as `payload['pull_request']['node_id']`, no extra lookup needed.

### `App/pr_reviewer/github_app/webhook_handlers.py` — enforce it alongside the check run

```python
def enforce_draft_state(github_app, token, pr, origin_verified):
    """Fallback enforcement for plans where a required-status-check ruleset isn't available:
    force the PR into Draft (disables the Merge button) when origin isn't verified,
    and flip it back to Ready for review once it is.
    """
    node_id = pr.get('node_id')
    is_draft = pr.get('draft', False)

    if not origin_verified and not is_draft:
        mutation, target_state = DraftEnforcementConfig.CONVERT_TO_DRAFT_MUTATION, "draft"
    elif origin_verified and is_draft:
        mutation, target_state = DraftEnforcementConfig.MARK_READY_MUTATION, "ready_for_review"
    else:
        return  # already in the correct state

    response = github_app.make_graphql_request(token, mutation, {"pullRequestId": node_id})
    if response.status_code == 200 and not response.json().get("errors"):
        logger.info(f"PR node {node_id} moved to {target_state}")
    else:
        logger.error(f"Failed to move PR node {node_id} to {target_state}: {response.text}")
```

Call it right next to the existing check-run creation in both `handle_pr_opened` and `handle_pr_synchronize`:

```python
origin_verified = is_pr_origin_verified(payload, pr)
origin_config = CheckRunConfig._ORIGIN_CHECK_PASSED() if origin_verified else CheckRunConfig._ORIGIN_CHECK_FAILED()
github_manager.create_check_run(**origin_config, pat_token=token)
enforce_draft_state(github_app, token, pr, origin_verified)
```

### Closing the escape hatch: `ready_for_review`

"Mark ready for review" is a normal action any collaborator with write access can take — nothing stops them from clicking it to undo the auto-draft. To close that, react to it: add a handler for the `ready_for_review` action so if someone manually un-drafts a PR that still isn't origin-verified, it gets converted straight back to draft.

```python
# in handle_pull_request_event's action dispatch:
elif action == 'ready_for_review':
    pr = payload.get('pull_request', {})
    enforce_draft_state(github_app, token, pr, is_pr_origin_verified(payload, pr))
    return jsonify({'message': 'ready_for_review re-checked'}), 200
```

## Honest tradeoff vs. the required-check approach

This is genuinely a **softer** block than a required status check with an empty bypass list:

- A required check is enforced server-side by GitHub at merge time — there's no window where it can be bypassed, full stop (given no bypass actors configured).
- Draft-state enforcement is **reactive**: it only re-asserts itself when the `ready_for_review` webhook fires. Someone who un-drafts a PR and merges within the brief window before the webhook is received and processed could theoretically slip through. In practice this window is small (seconds), but it is not atomic the way a required check is.
- Converting a PR to Draft also has a minor UX side effect: reviewers may not get notified/requested the same way a normal "Open" PR does, since draft PRs are treated differently in GitHub's review-request flow.

## Recommendation

Use this as the mechanism for private repos on Free-plan accounts/orgs where the required-check ruleset approach is unavailable, and treat it as a **defense-in-depth layer** — on top of, not instead of — the required-check ruleset everywhere a paid plan makes that available (public repos, or private repos on GitHub Pro/Team/Enterprise).

A reasonable rollout logic: attempt the required-check ruleset first; if `create_repo_ruleset` comes back with the plan-upgrade 403, fall back to draft-based enforcement for that repo instead.

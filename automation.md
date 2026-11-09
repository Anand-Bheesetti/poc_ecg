# Per-Repo Branch Protection Automation — Detailed Code Changes

## What this solves

Today, `_provision_rulesets` builds **one** ruleset payload and applies it identically
to every repo the app is installed on. That breaks down for two reasons already
observed in testing:

- `ref_name.include: ["~ALL"]` made the rule apply to *every* branch, which blocked
  ordinary branch creation and direct pushes to feature/WIP branches, not just merges
  into a protected branch.
- Different repos use different branch names for their default/deployed branches
  (`main` vs `master`, `prod` vs `production` vs `deploy`, etc.) — a single hardcoded
  branch list can't represent all of them.

This change makes the protected-branch list **per-repo**, sourced from a new Mongo
collection (`repo_branch_config`), with a sane default for repos that don't have an
explicit entry, and adds an **admin API endpoint** so that list can be created,
extended, or corrected for any specific repo — and applied to GitHub immediately in
the same request, without waiting for another webhook to fire.

## Changes, in dependency order

1. `App/pr_reviewer/enums.py` — ruleset payload takes `ref_names` as a parameter, instead of a hardcoded value
2. `App/pr_reviewer/github_app/auth.py` — two additions: resolve an installation ID from just `owner/repo`, and make ruleset creation self-healing (update instead of skip if one already exists)
3. `App/pr_reviewer/github_app/webhook_handlers.py` — look up protected branches per repo from DB, with a default fallback, and use it when auto-provisioning on install/new-repo events
4. `App/config.py` — one new environment variable, the shared secret that authenticates the admin endpoint
5. `App/pr_reviewer/routes.py` — the admin endpoint itself: `POST /api/admin/repo-branch-config`

Each is explained in full below — what to change, exactly where, line by line why it's
written that way, and what breaks if you skip it.

---

## 1. `App/pr_reviewer/enums.py`

**File location:** `App/pr_reviewer/enums.py`, class `RulesetConfig`, currently around lines 382–414.

**Current code (what you have now):**
```python
class RulesetConfig:
    """
    Payload builder for the org-wide 'require extension origin check' ruleset.
    """

    RULESET_NAME = "PRR Genius Extension Origin Check"

    @staticmethod
    def _ORIGIN_CHECK_ORG_RULESET(app_id):
        return {
            "name": RulesetConfig.RULESET_NAME,
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {"include": ["~ALL"], "exclude": []}
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

**Replace it with:**
```python
class RulesetConfig:
    """
    Payload builder for the org-wide 'require extension origin check' ruleset.
    """

    RULESET_NAME = "PRR Genius Extension Origin Check"

    # Fallback branches to protect for repos with no entry in repo_branch_config
    # (i.e. newly onboarded repos that follow the standard naming convention).
    DEFAULT_PROTECTED_BRANCHES = ["main", "dev", "qa", "prod"]

    @staticmethod
    def _ORIGIN_CHECK_ORG_RULESET(app_id, ref_names):
        return {
            "name": RulesetConfig.RULESET_NAME,
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {"include": ref_names, "exclude": []}
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
                        "strict_required_status_checks_policy": False,
                        "do_not_enforce_on_create": True
                    }
                }
            ]
        }
```

**Line-by-line explanation of what changed:**

- `DEFAULT_PROTECTED_BRANCHES = ["main", "dev", "qa", "prod"]` — a new class-level
  constant. This is the list used for any repo that doesn't have an explicit document
  in `repo_branch_config`. It's read by `get_protected_branches_for_repo` in
  `webhook_handlers.py` (change 3 below), not used directly inside this function —
  it just needs to live somewhere shared, and `RulesetConfig` (the class that owns
  the ruleset shape) is the natural place for it.
- `_ORIGIN_CHECK_ORG_RULESET(app_id, ref_names)` — added a second required parameter,
  `ref_names`. Previously the branch list was hardcoded inline (`["~ALL"]`); now the
  caller passes in exactly which refs this specific repo should protect. This is
  the crux of "per-repo" — the same function now produces a different payload for
  every repo, driven entirely by what's passed in.
- `"ref_name": {"include": ref_names, "exclude": []}` — the only other change inside
  the payload body: `["~ALL"]` is replaced by whatever `ref_names` the caller supplied.
  Everything else in the payload (target, enforcement, bypass_actors, the rule type,
  the required check's context/integration_id) is untouched.
- `"do_not_enforce_on_create": True` — new parameter on the `required_status_checks`
  rule. Without it, GitHub evaluates the required check the instant a matching ref is
  *created*, not just when something merges into it — and since a brand-new branch has
  no check run yet, creation gets rejected outright ("Required status check ... is
  expected"). Setting this to `True` tells GitHub to skip enforcement at the moment of
  creation, and only start enforcing on subsequent pushes/merges into that ref.

**What this achieves:** the ruleset payload is no longer one-size-fits-all — the
caller now decides exactly which branches get protected per repo. Combined with
`do_not_enforce_on_create: True`, branch creation and pushes to any branch *not* in
`ref_names` (e.g. feature branches) are completely untouched by this rule, in every
repo, regardless of that repo's naming convention.

**What breaks if you skip this step:** every other change below depends on
`_ORIGIN_CHECK_ORG_RULESET` accepting `ref_names` — if you leave it as a single-arg
function, `webhook_handlers.py`'s and `routes.py`'s calls to it (which now always pass
two arguments) will raise `TypeError: _ORIGIN_CHECK_ORG_RULESET() takes 1 positional
argument but 2 were given`.

---

## 2. `App/pr_reviewer/github_app/auth.py`

**File location:** `App/pr_reviewer/github_app/auth.py`, class `GitHubApp`. Two separate
additions/changes in this file.

### 2a. New method: `get_installation_id_for_repo`

**Where to add it:** anywhere inside the `GitHubApp` class — logically it fits well
right before or after `create_repo_ruleset` (around line 165), since both are used
together by the admin endpoint.

**Why it's needed:** every existing call site that talks to GitHub as an installation
(`get_installation_token`, `create_repo_ruleset`, etc.) already has an `installation_id`
handy, because it came from a webhook payload (`payload['installation']['id']`). The
admin endpoint (change 5) is different — a human calls it with just `"owner/repo"`,
with no webhook payload in sight. So there needs to be a way to go from
`owner + repo` → `installation_id` on demand.

**Code to add:**
```python
def get_installation_id_for_repo(self, owner, repo):
    """
    Resolve the installation ID that covers a given repo, using app-level JWT auth.
    Needed when we want to (re)provision a ruleset outside of a webhook event,
    e.g. from an admin API call that only knows owner/repo.
    """
    jwt_token = self.generate_jwt()
    headers = {
        'Authorization': f'Bearer {jwt_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    url = f'https://api.github.com/repos/{owner}/{repo}/installation'
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()['id']
    raise Exception(f'Failed to resolve installation for {owner}/{repo}: {response.text}')
```

**How it works, in detail:**
- `self.generate_jwt()` — this is the existing method (already in the file, used by
  `get_installation_token`) that signs a short-lived JWT identifying the *app itself*
  (not a specific installation), using the app's private key. GitHub's
  `GET /repos/{owner}/{repo}/installation` endpoint specifically requires this
  app-level JWT auth, not an installation token — because its whole purpose is to
  tell you *which* installation covers a repo, so you can't already have that
  installation's token as a prerequisite.
- The request hits `https://api.github.com/repos/{owner}/{repo}/installation`, GitHub's
  documented endpoint for "get the installation for a repository." It requires the app
  to actually have access to that repo, otherwise it returns `404`.
- On success (`200`), the response body includes an `id` field — the installation ID —
  which is returned directly.
- On failure, an `Exception` is raised with the response body included, so the caller
  (the admin endpoint) can log exactly why resolution failed (most commonly: the app
  isn't installed on that repo yet, or the repo name is misspelled).

**What breaks if you skip this:** the admin endpoint in `routes.py` calls this method
directly (`github_app.get_installation_id_for_repo(owner, repo)`); without it, that
route will raise `AttributeError: 'GitHubApp' object has no attribute
'get_installation_id_for_repo'` on every request.

### 2b. Modify `create_repo_ruleset` to self-heal instead of skip

**Where:** the existing `create_repo_ruleset` method, currently around lines 165–186.

**Current code:**
```python
def create_repo_ruleset(self, installation_id, owner, repo, ruleset_payload):
    """
    Create the repo-level branch protection ruleset using the installation token.
    Returns a 422 if a ruleset with this name already exists on the repo —
    expected on webhook redelivery, not treated as an error here.
    """
    print("************ entered create repo ruleset ************")
    token = self.get_installation_token(installation_id)
    url = f"https://api.github.com/repos/{owner}/{repo}/rulesets"
    response = self.make_api_request(token, 'POST', url, ruleset_payload)

    if response.status_code in (200, 201):
        print("✅ Created ruleset successfully")
        logger.info(f"✅ Created ruleset '{ruleset_payload.get('name')}' for {owner}/{repo}")
    elif response.status_code == 422:
        print("⚠️ Ruleset already exists, skipping creation")
        logger.info(f"Ruleset '{ruleset_payload.get('name')}' already exists for {owner}/{repo}, skipping")
    else:
        print("❌ Failed to create ruleset:", response.status_code, response.text)
        logger.error(f"❌ Failed to create ruleset for {owner}/{repo}: {response.status_code} {response.text}")

    return response
```

**Why this needs to change:** the `elif response.status_code == 422` branch currently
just logs and returns — it never actually applies the new payload. That was fine when
the payload was identical for every repo (nothing to update). Now that the payload
is per-repo and can change over time (new branches added via the admin endpoint), a
`422` needs to mean "go fetch the existing ruleset and update it," not "give up."

**Replace the whole method with:**
```python
def create_repo_ruleset(self, installation_id, owner, repo, ruleset_payload):
    """
    Create (or update, if one already exists) the repo-level branch protection
    ruleset using the installation token. A 422 on create means a ruleset with
    this name already exists — instead of skipping, fetch its ID and PATCH it
    so DB config changes actually take effect on repos that were already provisioned.
    """
    print("************ entered create repo ruleset ************")
    token = self.get_installation_token(installation_id)
    url = f"https://api.github.com/repos/{owner}/{repo}/rulesets"
    response = self.make_api_request(token, 'POST', url, ruleset_payload)

    if response.status_code in (200, 201):
        print("✅ Created ruleset successfully")
        logger.info(f"✅ Created ruleset '{ruleset_payload.get('name')}' for {owner}/{repo}")

    elif response.status_code == 422:
        print("⚠️ Ruleset already exists, attempting update instead")
        list_response = self.make_api_request(token, 'GET', url)
        existing_ruleset = None
        if list_response.status_code == 200:
            existing_ruleset = next(
                (r for r in list_response.json() if r.get('name') == ruleset_payload.get('name')),
                None
            )

        if existing_ruleset:
            patch_url = f"{url}/{existing_ruleset['id']}"
            response = self.make_api_request(token, 'PATCH', patch_url, ruleset_payload)
            if response.status_code in (200, 201):
                print("✅ Updated existing ruleset successfully")
                logger.info(f"✅ Updated ruleset '{ruleset_payload.get('name')}' for {owner}/{repo}")
            else:
                print("❌ Failed to update ruleset:", response.status_code, response.text)
                logger.error(f"❌ Failed to update ruleset for {owner}/{repo}: {response.status_code} {response.text}")
        else:
            logger.error(f"Ruleset reported as existing but could not be located for {owner}/{repo}")

    else:
        print("❌ Failed to create ruleset:", response.status_code, response.text)
        logger.error(f"❌ Failed to create ruleset for {owner}/{repo}: {response.status_code} {response.text}")

    return response
```

**Step-by-step what this does differently:**
1. It still tries `POST .../rulesets` first, exactly as before — this is unchanged for
   the common "repo has no ruleset yet" case.
2. If GitHub responds `422` (meaning: a ruleset with this exact `name` already exists on
   this repo — GitHub enforces unique ruleset names per repo), instead of stopping, it
   issues a `GET` on the same `.../rulesets` URL, which returns the **list** of all
   rulesets on that repo.
3. It searches that list for one whose `name` matches `ruleset_payload.get('name')` —
   i.e. `"PRR Genius Extension Origin Check"` — using `next(..., None)`, which returns
   the first match or `None` if nothing matches.
4. If found, it builds the ruleset's individual URL (`.../rulesets/{id}`) and issues a
   `PATCH` request with the full new `ruleset_payload` — this is GitHub's documented way
   to update an existing ruleset's rules/conditions in place. This is what actually
   applies a changed branch list to a repo that was already provisioned.
5. If the `GET` list didn't turn up a matching ruleset (a rare inconsistency — GitHub
   said `422`/duplicate, but a follow-up list doesn't show it), it logs an error rather
   than silently doing nothing, so this situation is visible in logs instead of hidden.
6. The final `else` branch (any other status code, e.g. `403` for missing permissions,
   `5xx` for GitHub outages) is unchanged from before.

**What this achieves:** repos that already have the ruleset provisioned — whether
from before this change, or from an earlier/incorrect payload — get corrected the next
time `create_repo_ruleset` actually runs for them. Critically, this is what makes the
admin endpoint's "apply immediately" behavior possible: without this change, calling
`create_repo_ruleset` again for an already-provisioned repo would just hit the `422`
branch and do nothing, and the admin endpoint would silently fail to apply anything.

---

## 3. `App/pr_reviewer/github_app/webhook_handlers.py`

**File location:** `App/pr_reviewer/github_app/webhook_handlers.py`, near the existing
`_provision_rulesets` function, currently around lines 101–110.

### 3a. New function: `get_protected_branches_for_repo`

**Code to add** (place it directly above `_provision_rulesets`):
```python
def get_protected_branches_for_repo(repo_full_name):
    """
    Looks up which branches should require the origin check for this repo.
    Falls back to RulesetConfig.DEFAULT_PROTECTED_BRANCHES for repos that
    don't have an explicit entry (e.g. newly onboarded repos following the
    standard main/dev/qa/prod convention).
    """
    config_doc = code_profile_db.repo_branch_config.find_one(
        {"repo_full_name": repo_full_name}
    )
    branches = (config_doc or {}).get("protected_branches") or RulesetConfig.DEFAULT_PROTECTED_BRANCHES

    ref_names = ["~DEFAULT_BRANCH"] + list(branches)
    # de-duplicate while preserving order (in case "~DEFAULT_BRANCH" or a
    # duplicate branch name was also included in the stored list)
    seen = set()
    deduped = []
    for ref in ref_names:
        if ref not in seen:
            seen.add(ref)
            deduped.append(ref)
    return deduped
```

**Line-by-line:**
- `code_profile_db.repo_branch_config.find_one({"repo_full_name": repo_full_name})` —
  queries the new collection (no schema/migration required — MongoDB collections are
  created implicitly on first write) for a document matching this exact repo's full
  name, e.g. `"Techolution/some-repo"`. Returns `None` if nothing is found, which is the
  expected/normal case for any repo that's never been explicitly configured.
- `(config_doc or {}).get("protected_branches") or RulesetConfig.DEFAULT_PROTECTED_BRANCHES` —
  two fallbacks chained: `config_doc or {}` guards against `config_doc` being `None`
  (so `.get(...)` doesn't raise `AttributeError`); then `or RulesetConfig.DEFAULT_PROTECTED_BRANCHES`
  covers both "no document at all" and "document exists but has an empty/missing
  `protected_branches` field."
- `ref_names = ["~DEFAULT_BRANCH"] + list(branches)` — `~DEFAULT_BRANCH` is a special
  value GitHub's ruleset API recognizes, meaning "whatever this repo's actual default
  branch is" (resolved automatically by GitHub, no matter if it's `main`, `master`,
  or anything else). It's always included, unconditionally, so the default branch is
  never accidentally left unprotected even if it's misspelled or missing from a manual
  `protected_branches` list.
- The dedup loop (`seen`/`deduped`) exists because someone could accidentally include
  `"~DEFAULT_BRANCH"` again inside their own `protected_branches` list, or list the same
  branch twice — GitHub's API isn't guaranteed to reject duplicate entries gracefully,
  so this normalizes the list before it's sent.

### 3b. Modify `_provision_rulesets` to build the payload per repo

**Current code:**
```python
def _provision_rulesets(github_app, installation_id, repos):
    print("Provisioning rulesets for repos...")
    ruleset_payload = RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID)
    for repo in repos:
        owner, name = repo['full_name'].split('/', 1)
        try:
            github_app.create_repo_ruleset(installation_id, owner, name, ruleset_payload)
        except Exception as e:
            logger.error(f"Failed to provision ruleset for {repo['full_name']}: {e}", exc_info=True)
```

**Replace with:**
```python
def _provision_rulesets(github_app, installation_id, repos):
    print("Provisioning rulesets for repos...")
    for repo in repos:
        owner, name = repo['full_name'].split('/', 1)
        try:
            ref_names = get_protected_branches_for_repo(repo['full_name'])
            ruleset_payload = RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID, ref_names)
            github_app.create_repo_ruleset(installation_id, owner, name, ruleset_payload)
        except Exception as e:
            logger.error(f"Failed to provision ruleset for {repo['full_name']}: {e}", exc_info=True)
```

**What changed and why:** previously, `ruleset_payload` was computed **once**, before
the loop, and the exact same payload (same hardcoded branch list) was reused for every
repo in `repos`. Now, `ref_names` and `ruleset_payload` are computed **inside** the loop,
once per repo, using that specific repo's `full_name` to look up its own protected
branches. This is the actual mechanism that makes "different repos, different branch
names" work — the loop body is otherwise unchanged (still calls
`github_app.create_repo_ruleset(...)`, still catches and logs exceptions per-repo so one
bad repo doesn't stop the rest).

**What breaks if you skip this:** without this change, even after adding
`get_protected_branches_for_repo` and updating `_ORIGIN_CHECK_ORG_RULESET`'s signature,
`_provision_rulesets` would still call `_ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID)`
with only one argument — a `TypeError` at runtime, since the function now requires
`ref_names`.

**No new imports needed** — `RulesetConfig` and `GitHubAppConfig` are already imported
at the top of this file; `code_profile_db` is already imported (`from models import
code_profile_db`).

---

## 4. `App/config.py`

**File location:** `App/config.py`, alongside the other shared-secret variables (near
`APPSEC_SHARED_SECRET`, currently around line 224).

**Add:**
```python
ADMIN_API_SECRET = os.environ.get("ADMIN_API_SECRET", "")
```

**Why this is needed, in detail:** the admin endpoint (change 5) lets a caller rewrite
which branches on any repo require this origin check before merging — that's a
security-relevant capability (it can weaken or strengthen branch protection for any
repo the app has access to), so it must not be reachable by an unauthenticated caller.
This introduces a single shared secret, read from an environment variable at startup
(consistent with how `APPSEC_SHARED_SECRET` and other secrets are already handled in
this file — none of them are hardcoded, all sourced from `os.environ`).

**Deployment note:** this needs an actual value set in every environment
(`config_local.env` for local dev, and whatever secret-management mechanism is used for
staging/prod) before the endpoint can be called successfully — if the variable is unset,
`os.environ.get("ADMIN_API_SECRET", "")` defaults to an empty string, and (as built in
change 5) the endpoint is designed to reject **all** requests when the secret is empty,
rather than accidentally allowing an empty-string match.

---

## 5. `App/pr_reviewer/routes.py`

**File location:** `App/pr_reviewer/routes.py`. This is a brand-new route, added
alongside the existing `pr_reviewer_bp.route(...)` definitions (the blueprint is defined
at the top of the file, line 34: `pr_reviewer_bp = Blueprint('pr_reviewer', __name__,
url_prefix='/api/pr_reviewer')`).

### 5a. Imports to add at the top of the file

```python
import hmac
from pr_reviewer.enums import RulesetConfig
from pr_reviewer.github_app.auth import GitHubApp
from pr_reviewer.github_app.webhook_handlers import get_protected_branches_for_repo
```

- `hmac` — used for a constant-time string comparison (`hmac.compare_digest`) when
  checking the caller's secret against `config.ADMIN_API_SECRET`. This matters because a
  naive `==` comparison on strings can leak timing information about how many leading
  characters matched, which is (in theory) exploitable to guess a secret byte-by-byte.
  `hmac.compare_digest` runs in constant time regardless of where the mismatch occurs.
  This mirrors the same reasoning already used for the existing webhook signature check
  (`hmac.compare_digest` is already used in `verify_webhook_signature` in
  `webhook_handlers.py`), so this keeps the same security posture consistent across the
  codebase.
- `RulesetConfig`, `GitHubApp`, `get_protected_branches_for_repo` — needed to rebuild the
  payload and call GitHub the same way `_provision_rulesets` does, but from this route
  instead of from a webhook handler.
- `datetime` is **not** newly needed — `routes.py` already has `from datetime import
  datetime, timezone` at the top (line 1), so `datetime.utcnow()` is available already.
- `config`, `request`, `jsonify`, `code_profile_db`, `logger`, `cross_origin` — all
  already imported at the top of this file; nothing further to add for those.

### 5b. The route itself

**Add this function** anywhere among the other `@pr_reviewer_bp.route(...)` definitions:

```python
@pr_reviewer_bp.route('/admin/repo-branch-config', methods=['POST'])
@cross_origin(supports_credentials=True)
def upsert_repo_branch_config():
    """
    Admin endpoint to set/update which branches require the PRR origin check
    before merge, for a specific repo. Immediately re-provisions the ruleset
    on GitHub so the change takes effect without waiting for another webhook.
    """
    provided_secret = request.headers.get('X-Admin-Api-Key', '')
    if not config.ADMIN_API_SECRET or not hmac.compare_digest(provided_secret, config.ADMIN_API_SECRET):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    repo_full_name = data.get('repo_full_name')  # e.g. "Techolution/Appmod-Backend"
    protected_branches = data.get('protected_branches')  # e.g. ["staging", "production"]

    if not repo_full_name or '/' not in repo_full_name:
        return jsonify({'error': 'repo_full_name must be provided as "owner/repo"'}), 400
    if not isinstance(protected_branches, list) or not protected_branches:
        return jsonify({'error': 'protected_branches must be a non-empty list'}), 400

    code_profile_db.repo_branch_config.update_one(
        {"repo_full_name": repo_full_name},
        {"$set": {
            "repo_full_name": repo_full_name,
            "protected_branches": protected_branches,
            "updated_at": datetime.utcnow()
        }},
        upsert=True
    )

    owner, repo = repo_full_name.split('/', 1)
    github_app = GitHubApp()
    try:
        installation_id = github_app.get_installation_id_for_repo(owner, repo)
        ref_names = get_protected_branches_for_repo(repo_full_name)
        ruleset_payload = RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID, ref_names)
        github_app.create_repo_ruleset(installation_id, owner, repo, ruleset_payload)
    except Exception as e:
        logger.error(f"Saved config but failed to re-provision ruleset for {repo_full_name}: {e}", exc_info=True)
        return jsonify({
            'message': f'Saved protected branches for {repo_full_name}, but failed to apply on GitHub — will retry on next webhook event.',
            'error': str(e)
        }), 207

    return jsonify({'message': f'Updated and applied protected branches for {repo_full_name}: {ref_names}'}), 200
```

**Very detailed walkthrough, section by section:**

**Route declaration:**
- `@pr_reviewer_bp.route('/admin/repo-branch-config', methods=['POST'])` — registers this
  function at `POST /api/admin/repo-branch-config` (the `/api/pr_reviewer`
  prefix comes from the blueprint's `url_prefix`). `POST`-only because this endpoint
  mutates state (both the DB and GitHub) — it's not a read/query endpoint.
- `@cross_origin(supports_credentials=True)` — matches the pattern already used on every
  other route in this file (e.g. the webhook route, `/pr-reviewer/open`, etc.), so CORS
  handling stays consistent.

**Authentication check:**
```python
provided_secret = request.headers.get('X-Admin-Api-Key', '')
if not config.ADMIN_API_SECRET or not hmac.compare_digest(provided_secret, config.ADMIN_API_SECRET):
    return jsonify({'error': 'Unauthorized'}), 401
```
- Reads a custom header, `X-Admin-Api-Key`, from the incoming request. `.get(..., '')`
  defaults to an empty string if the header is missing entirely, so there's no `None`
  passed into the comparison.
- The condition has two parts joined by `or`, both of which must be false (i.e., both
  checks must "pass") for the request to proceed:
  - `not config.ADMIN_API_SECRET` — true (meaning: reject) if the secret was never
    configured in this environment. This makes the endpoint **fail closed**: if you
    forget to set `ADMIN_API_SECRET`, the endpoint refuses everyone, rather than
    accidentally matching an empty-string header against an empty-string config value.
  - `not hmac.compare_digest(provided_secret, config.ADMIN_API_SECRET)` — true (meaning:
    reject) if the header's value doesn't match the configured secret, checked in
    constant time.
- On failure: `401 Unauthorized` with a generic error message — deliberately vague (just
  `"Unauthorized"`, not "wrong secret" or "missing header") so it doesn't help an
  attacker distinguish between "no header sent" and "wrong value sent."

**Input parsing and validation:**
```python
data = request.json or {}
repo_full_name = data.get('repo_full_name')
protected_branches = data.get('protected_branches')

if not repo_full_name or '/' not in repo_full_name:
    return jsonify({'error': 'repo_full_name must be provided as "owner/repo"'}), 400
if not isinstance(protected_branches, list) or not protected_branches:
    return jsonify({'error': 'protected_branches must be a non-empty list'}), 400
```
- `request.json or {}` — guards against a request with no JSON body at all (Flask's
  `.json` would otherwise be `None`), so `.get(...)` calls below don't raise.
- `repo_full_name` is expected in `"owner/repo"` form (matching the format
  GitHub itself uses for `repo['full_name']` elsewhere in this codebase, e.g. in
  `_provision_rulesets`). The check `'/' not in repo_full_name` is a minimal sanity
  check — it doesn't fully validate the value is a real repo, but it catches the most
  common mistake (passing just `"repo"` without the owner).
- `protected_branches` must be a **non-empty list** — `isinstance(..., list)` rejects a
  string or dict accidentally sent instead of an array; `not protected_branches` (on a
  list) is `True` for an empty list `[]`, which is rejected too, since an empty list
  would mean "protect nothing but still include `~DEFAULT_BRANCH`" — arguably valid, but
  disallowed here to force the caller to be explicit rather than accidentally submitting
  an empty payload.
- Both validation failures return `400 Bad Request` with a message describing exactly
  what's wrong — these are client-input errors, distinct from the `401` above and the
  `207`/`500`-style failures below.

**Persisting to MongoDB:**
```python
code_profile_db.repo_branch_config.update_one(
    {"repo_full_name": repo_full_name},
    {"$set": {
        "repo_full_name": repo_full_name,
        "protected_branches": protected_branches,
        "updated_at": datetime.utcnow()
    }},
    upsert=True
)
```
- `update_one` with a filter of `{"repo_full_name": repo_full_name}` — finds the existing
  document for this repo, if any.
- `$set` — **overwrites** the `protected_branches` field with exactly what was sent (this
  is the "full replace, not merge" behavior flagged as edge case #4 further down — if
  you're adding branches to an existing list, you must include the full list, not just
  the new entries).
- `upsert=True` — if no document exists yet for this repo, one is created. This means
  the very first call for a given repo both creates its config *and* applies it — no
  separate "create" vs. "update" endpoint needed.
- `updated_at` — a timestamp for auditing/debugging (e.g. "when was this repo's config
  last touched"), not read by any other code path.

**Immediately applying the change to GitHub:**
```python
owner, repo = repo_full_name.split('/', 1)
github_app = GitHubApp()
try:
    installation_id = github_app.get_installation_id_for_repo(owner, repo)
    ref_names = get_protected_branches_for_repo(repo_full_name)
    ruleset_payload = RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID, ref_names)
    github_app.create_repo_ruleset(installation_id, owner, repo, ruleset_payload)
except Exception as e:
    logger.error(f"Saved config but failed to re-provision ruleset for {repo_full_name}: {e}", exc_info=True)
    return jsonify({
        'message': f'Saved protected branches for {repo_full_name}, but failed to apply on GitHub — will retry on next webhook event.',
        'error': str(e)
    }), 207

return jsonify({'message': f'Updated and applied protected branches for {repo_full_name}: {ref_names}'}), 200
```
- `owner, repo = repo_full_name.split('/', 1)` — splits `"owner/repo"` into its two
  parts; `maxsplit=1` ensures a repo name that itself happens to contain a `/`
  (uncommon, but technically possible in some Git hosting setups) doesn't break the
  split.
- `GitHubApp()` — instantiated fresh here, exactly like every webhook handler does
  (`github_app = GitHubApp()`), reading app ID/private key from `GitHubAppConfig`
  internally — no new instantiation pattern introduced.
- `github_app.get_installation_id_for_repo(owner, repo)` — this is change 2a: resolves
  which installation covers this specific repo, since (unlike a webhook handler) this
  route has no installation ID handed to it.
- `get_protected_branches_for_repo(repo_full_name)` — re-reads from Mongo (the document
  that was *just* written above) rather than reusing the in-memory `protected_branches`
  variable directly. This is intentional: it exercises the exact same code path that
  `_provision_rulesets` uses on every webhook-driven provisioning, so the admin endpoint
  and the webhook flow can never drift into producing different payloads for the same
  stored config — there's exactly one function that turns "repo name" into "ref_names,"
  and every caller goes through it.
- `RulesetConfig._ORIGIN_CHECK_ORG_RULESET(GitHubAppConfig.GITHUB_APP_ID, ref_names)` —
  builds the payload, identical in shape to what `_provision_rulesets` builds.
- `github_app.create_repo_ruleset(installation_id, owner, repo, ruleset_payload)` — this
  is where change 2b (the self-healing `PATCH`) actually gets exercised: for a repo
  that's already provisioned, this call will hit the `422` branch internally and
  `PATCH` the existing ruleset with the new branch list, rather than doing nothing.
- **Error handling — why `207`:** if anything in this block throws (repo not
  accessible to the app, GitHub API error, network failure), the DB write **already
  succeeded** — so this isn't a total failure, it's a partial one: state saved, GitHub
  not yet in sync. `207 Multi-Status` is the conventional HTTP code for "some parts of
  this request succeeded, some didn't" (vs. `500`, which would incorrectly imply nothing
  happened, or `200`, which would incorrectly imply everything succeeded). The response
  body explicitly tells the caller what happened and that a future webhook (next install
  event, or manual redelivery) will retry it.
- **Success response (`200`):** includes the exact `ref_names` that were applied, so the
  caller can immediately verify (e.g. in a script) that the branches they expected are
  the ones that got sent to GitHub — including the automatically-added `~DEFAULT_BRANCH`.

### 5c. One more import needed for the `207` branch and general use

`GitHubAppConfig` is referenced in the route (`GitHubAppConfig.GITHUB_APP_ID`) — check
whether it's already imported at the top of `routes.py`. It is: line 14,
`from pr_reviewer.config.github_config import GitHubAppConfig` — no action needed.

---

## New DB collection

`code_profile_db.repo_branch_config`

```json
{
  "repo_full_name": "Techolution/some-repo",
  "protected_branches": ["staging", "production"],
  "updated_at": "2026-07-22T10:00:00Z"
}
```

No migration needed — MongoDB creates the collection on first write, and
`find_one` returning `None` for repos without a document is exactly the "use the
default" case handled by `get_protected_branches_for_repo`.

## Calling the admin endpoint

```bash
curl -X POST https://<host>/api/admin/repo-branch-config \
  -H "X-Admin-Api-Key: <ADMIN_API_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"repo_full_name": "Techolution/some-repo", "protected_branches": ["staging", "production"]}'
```

**Expected responses:**
| Status | Meaning |
|---|---|
| `200` | DB updated and ruleset applied on GitHub successfully. Body includes the exact `ref_names` sent to GitHub. |
| `400` | Malformed input — missing/invalid `repo_full_name` or `protected_branches`. Nothing was written. |
| `401` | Missing/incorrect `X-Admin-Api-Key` header, or `ADMIN_API_SECRET` isn't configured in this environment at all. |
| `207` | DB was updated, but applying it to GitHub failed (e.g. app not installed on that repo, GitHub API error) — will self-correct on the next webhook redelivery, or you can retry the same call. |

**To add branches to a repo that already has a config** (rather than replacing it),
call this with the **full desired list**, not just the new branches — e.g. if
`Techolution/some-repo` already protects `["staging", "production"]` and you want to
add `"hotfix"`, send `["staging", "production", "hotfix"]`, not just `["hotfix"]`. See
edge case #4 below.

---

## When does a repo actually get (or lose) the rule, and on which branches?

### Trigger → what happens

| Trigger | What happens to the repo | Branches protected |
|---|---|---|
| App installed fresh (`installation`, `action: created`) — single, selected, or all-repos | Ruleset created on **every** repo the installation can access (via `list_installation_repositories`) | `~DEFAULT_BRANCH` + that repo's `repo_branch_config` entry, or `main/dev/qa/prod` if no entry exists yet |
| Repo added to an existing install, or a new repo auto-included under "All repositories" (`installation_repositories`, `action: added`) | Ruleset created on just the newly added repo(s) | Same resolution as above |
| Admin calls `POST /admin/repo-branch-config` for a repo | DB record upserted, then the ruleset is immediately re-applied (created if missing, `PATCH`ed if it already exists) | Exactly the list passed in the request (+ `~DEFAULT_BRANCH`), replacing whatever was protected before |
| Webhook redelivery of `installation`/`installation_repositories` | Ruleset re-applied per repo — `PATCH`ed if it already exists (via the self-healing change in `auth.py`), so it self-corrects to the current DB/default state rather than being skipped | Same resolution as above |
| Repo removed from the installation, or app uninstalled | **Nothing.** GitHub revokes the app's access; no code path deletes the ruleset or the `repo_branch_config` document — it's simply orphaned until/unless the repo is reinstalled | N/A |
| Repo renamed (`repository`, `action: renamed`) | **Not handled.** This event isn't subscribed to, so `repo_branch_config`'s `repo_full_name` key becomes stale | Falls back to `DEFAULT_PROTECTED_BRANCHES` on the next provisioning pass, silently losing the custom list |

### Per-branch behavior once a repo is provisioned

| Branch | Create | Direct `git push` (no PR) | PR opened/synced targeting this branch | PR merge |
|---|---|---|---|---|
| A branch in the resolved `ref_names` (e.g. `main`, `dev`, `qa`, `prod`, or the repo's actual default branch, or a custom entry like `staging`) | Allowed — exempted by `do_not_enforce_on_create` | **Blocked** unless the pushed commit already carries a passing origin check (effectively never true for a bare push with no PR) — see edge case #1 below | Origin check run posted (`success`/`failure`) via `is_pr_origin_verified` | Blocked until the check is `success` |
| Any other branch (feature/personal/WIP branches, anything not explicitly listed) | Unaffected — rule doesn't match this ref at all | Unaffected | Origin check run is still posted (check-run creation isn't conditioned on the ruleset), but it has no enforcement power here since this ref isn't in `ref_names` | Not applicable — this branch is a PR *source*, not a merge target; merging **into** a protected branch is still gated regardless of which branch the PR came from |

---

## Edge cases to know about

1. **Direct pushes to protected branches are blocked too, not just PR merges.** `required_status_checks` enforces on any ref update matching `ref_name`, not only PR merges. Since the origin check-run is only ever created reactively from a `pull_request` webhook event, a bare `git push origin main` (no PR involved) has no check run to satisfy and will be rejected. If your teams ever push directly to `main`/`dev`/`qa`/`prod` outside of a PR, this will now block that — likely desirable (forces PR-only workflow on those branches), but worth confirming it's intended.

2. **PRs already open at the moment a repo gets provisioned become unmergeable until they receive a new event.** The origin check run only gets created on `opened`/`reopened`/`synchronize`. A PR that was already open before install/provisioning won't have a check run yet, so it shows the check as permanently "Expected" (blocking merge) until someone pushes a new commit or closes/reopens it.

3. **Updating `protected_branches` via the admin endpoint is a full replace, not a merge.** `get_protected_branches_for_repo` uses the DB list *instead of* the defaults, not in addition to them, and the endpoint's `$set` overwrites the whole array. If a repo already has a custom entry (say `["staging", "production"]`) and someone calls the endpoint to *add* `"hotfix"` but only sends `["hotfix"]`, the result replaces the list entirely — `staging` and `production` lose protection. Always send the full desired list, not just the delta.

4. **Branch names are case-sensitive and must match exactly.** Sending `"Main"` in `protected_branches` will not match an actual branch named `main`. There's no normalization in the admin endpoint today.

5. **Protecting a branch that doesn't exist yet is harmless.** The ruleset is declarative — GitHub just won't have anything to enforce until a branch with that name is created. Once created, `do_not_enforce_on_create` still exempts the creation moment itself; enforcement starts on the first push/merge after that.

6. **Repo/app removal doesn't clean up `repo_branch_config`.** If a repo is removed from the installation (or the app is uninstalled) and later reinstalled, its old `repo_branch_config` document is still there and gets picked up again automatically — usually desirable, but means stale config for a repo that changed ownership or was repurposed could resurface unexpectedly.

7. **Repo renames silently fall back to defaults.** Since `repository` `renamed` events aren't handled, a renamed repo's custom branch list becomes unreachable (keyed under the old `owner/repo` string) and the next provisioning pass uses `DEFAULT_PROTECTED_BRANCHES` instead, without any error or warning. The admin endpoint would need to be called again with the new repo name after a rename.

8. **`get_installation_id_for_repo` will fail if the app isn't actually installed on that repo yet.** Calling the admin endpoint for a repo the GitHub App has no access to returns a `403`/`404` from GitHub's `/repos/{owner}/{repo}/installation` endpoint — the DB record still gets saved (the endpoint returns `207`), but the ruleset won't be applied until the app is actually installed there, at which point the *next* fresh-install or `installation_repositories` event will pick up the already-saved config automatically.

9. **Missing `ADMIN_API_SECRET` locks the admin endpoint entirely (fails closed, not open).** If the env var isn't set, `config.ADMIN_API_SECRET` is `""`, and the check `if not config.ADMIN_API_SECRET or ...` rejects every request with `401` — intentional (no secret configured means no one should be able to call it), but worth remembering if the endpoint mysteriously always 401s in a fresh environment; check that `ADMIN_API_SECRET` is actually set before assuming something else is wrong.

---

## Edge case coverage — what this design fixes vs. what's still open

| # | Edge case | Status | Notes |
|---|---|---|---|
| 1 | Branch **creation** blocked by the required check | ✅ Covered | `do_not_enforce_on_create: True` in `enums.py` |
| 2 | Different repos have different default/deployed branch names | ✅ Covered | `~DEFAULT_BRANCH` always included; per-repo overrides via `repo_branch_config` |
| 3 | Feature/WIP branch push & creation blocked repo-wide (`~ALL` root cause) | ✅ Covered | `ref_name.include` is now an explicit list (`~DEFAULT_BRANCH` + configured branches), never `~ALL` |
| 4 | Adding new protected branches later, without a code deploy | ✅ Covered | Admin endpoint (`POST /admin/repo-branch-config`) |
| 5 | Config changes not applying to repos already provisioned | ✅ Covered | `create_repo_ruleset` self-heals: `422` → look up existing ruleset → `PATCH` |
| 6 | Admin endpoint reachable without authorization | ✅ Covered | `X-Admin-Api-Key` header checked via `hmac.compare_digest` against `ADMIN_API_SECRET`; fails closed if unset |
| 7 | Direct `git push` (no PR) straight to a protected branch | ⚠️ Not fixed — by design | `required_status_checks` enforces on any ref update, not just merges. A bare push to `main`/`dev`/`qa`/`prod` with no prior check run gets rejected. This is inherent to the rule type, not something the payload can selectively disable; confirm this is acceptable (effectively forces PR-only workflow on protected branches) |
| 8 | PRs already open at the moment a repo is (re)provisioned | ❌ Not covered | No backfill logic exists — an already-open PR's check stays "Expected" until a new `synchronize`/`reopened` event fires. Would need `_provision_rulesets` (or the admin endpoint) to also list and backfill checks on currently-open PRs |
| 9 | `repo_branch_config` update is a full replace, not additive | ❌ Not covered | Both the manual Mongo path and the admin endpoint overwrite `protected_branches` entirely; there's no "append" mode. Caller must always resend the full list |
| 10 | Branch name case-sensitivity / typos | ❌ Not covered | No normalization or validation against the repo's actual branch list — `"Main"` silently won't match `main` |
| 11 | Protecting a branch name that doesn't exist yet | ✅ Not a problem | Harmless — ruleset is declarative, simply has nothing to enforce until that branch exists |
| 12 | Repo removed from install / app uninstalled | ❌ Not covered | `repo_branch_config` document is orphaned, not cleaned up; resurfaces automatically if the repo is reinstalled later |
| 13 | Repo renamed (`repository` `renamed` event) | ❌ Not covered | Event isn't subscribed to; `repo_full_name` key goes stale, falls back to `DEFAULT_PROTECTED_BRANCHES` silently. Admin endpoint would need to be called again with the new name |
| 14 | No way to view current config without querying Mongo/GitHub directly | ❌ Not covered | Only a write path (`POST`) exists; no `GET /admin/repo-branch-config/{repo}` to inspect what's currently stored/applied |
| 15 | No way to remove/reset a repo back to defaults | ❌ Not covered | No `DELETE` endpoint; reverting to defaults today requires manually deleting the Mongo document, then re-triggering provisioning |
| 16 | Concurrent admin calls for the same repo (race condition) | ❌ Not covered | Two near-simultaneous `POST`s for the same repo could interleave their Mongo `update_one` and GitHub `PATCH` calls; no locking. Low risk in practice (this is an admin-only, low-frequency endpoint) but not explicitly guarded |
| 17 | No audit trail of *who* changed a repo's protected branches | ❌ Not covered | Only `updated_at` is stored — no caller identity/user attribution recorded |
| 18 | No emergency bypass for the required check | ❌ Not covered | `bypass_actors: []` — not even org/repo admins can merge past a failing check. Intentional per earlier discussion, but flagged again since it has no escape hatch |
| 19 | Fork-based PRs may fail the origin check even when genuinely reviewed | ❌ Not covered | Pre-existing gap in `is_pr_origin_verified` (looks up `pr_reports` by the **base** repo's URL, not the fork's) — unrelated to this specific per-repo/admin-API change, carried over from the original origin-check feature |

---

## Testing the admin endpoint locally

### 1. Set `ADMIN_API_SECRET`

Add to `App/config_local.env` (or your environment's equivalent):

```
ADMIN_API_SECRET=b3f1c9e8a2d74f0b9c6e5a1d8f47b2c0e9a3d6f1b8c4e7a2d5f9b6c1e8a4d7f2
```

This is an **example value only** — don't reuse this literal string anywhere real.
Generate an actual random secret with either of:

```bash
openssl rand -hex 32
# or
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Call the endpoint

Assuming the app is running locally on port `5002` (per `app.run(host="0.0.0.0", port=5002, ...)` in `App/app.py`):

```bash
curl -X POST http://localhost:5002/api/admin/repo-branch-config \
  -H "X-Admin-Api-Key: b3f1c9e8a2d74f0b9c6e5a1d8f47b2c0e9a3d6f1b8c4e7a2d5f9b6c1e8a4d7f2" \
  -H "Content-Type: application/json" \
  -d '{
        "repo_full_name": "Techolution/some-repo",
        "protected_branches": ["main", "dev", "qa", "prod"]
      }'
```

Expected on success:
```json
{"message": "Updated and applied protected branches for Techolution/some-repo: ['~DEFAULT_BRANCH', 'main', 'dev', 'qa', 'prod']"}
```
(HTTP `200`)

### 3. Quick negative tests worth running

```bash
# Wrong/missing secret -> expect 401
curl -X POST http://localhost:5002/api/admin/repo-branch-config \
  -H "X-Admin-Api-Key: wrong-secret" \
  -H "Content-Type: application/json" \
  -d '{"repo_full_name": "Techolution/some-repo", "protected_branches": ["main"]}'

# Missing protected_branches -> expect 400
curl -X POST http://localhost:5002/api/admin/repo-branch-config \
  -H "X-Admin-Api-Key: b3f1c9e8a2d74f0b9c6e5a1d8f47b2c0e9a3d6f1b8c4e7a2d5f9b6c1e8a4d7f2" \
  -H "Content-Type: application/json" \
  -d '{"repo_full_name": "Techolution/some-repo"}'

# Repo the app isn't installed on -> expect 207 (saved to DB, GitHub apply failed)
curl -X POST http://localhost:5002/api/admin/repo-branch-config \
  -H "X-Admin-Api-Key: b3f1c9e8a2d74f0b9c6e5a1d8f47b2c0e9a3d6f1b8c4e7a2d5f9b6c1e8a4d7f2" \
  -H "Content-Type: application/json" \
  -d '{"repo_full_name": "SomeOtherOrg/not-installed-repo", "protected_branches": ["main"]}'
```

### 4. Verify on GitHub

After a `200` response, check the repo on GitHub: Settings → Rules → Rulesets →
`PRR Genius Extension Origin Check` → confirm the "Enforcement status" is active and
the branch/ref targeting matches the `protected_branches` list you sent.

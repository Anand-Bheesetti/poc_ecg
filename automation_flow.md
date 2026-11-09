# Per-Repo Branch Protection Automation — Flow Charts

Companion to [`automation.md`](./automation.md), which has the full code changes and
explanations. This file is the visual reference — how the pieces connect and in what
order things fire, across all three entry points into the system:

1. GitHub webhooks (`installation`, `installation_repositories`, `pull_request`)
2. The admin API (`POST /admin/repo-branch-config`)
3. GitHub's own ruleset enforcement, once a repo is provisioned

---

## 1. System overview — all entry points

```mermaid
flowchart TD
    subgraph Entry["Entry points"]
        A1["GitHub: App installed\n(installation, action=created)"]
        A2["GitHub: repo added to install\n(installation_repositories, action=added)"]
        A3["Admin: POST /admin/repo-branch-config"]
        A4["GitHub: PR opened / reopened / synchronize\n(pull_request)"]
    end

    A1 --> B1[handle_installation_event]
    A2 --> B2[handle_installation_repositories_event]
    A3 --> B3[upsert_repo_branch_config route]
    A4 --> B4["handle_pr_opened / handle_pr_synchronize"]

    B1 --> C[_provision_rulesets]
    B2 --> C
    C --> D[get_protected_branches_for_repo]
    B3 --> E[(repo_branch_config upsert)]
    E --> D

    D --> F["RulesetConfig._ORIGIN_CHECK_ORG_RULESET(app_id, ref_names)"]
    F --> G[GitHubApp.create_repo_ruleset]
    G --> H[("GitHub: Repository Ruleset\nrequired_status_checks on ref_names")]

    B4 --> I[is_pr_origin_verified]
    I --> J["GitHubPRManager.create_check_run\n('PRR Genius Extension Origin Check')"]
    J --> K[("GitHub: Check Run\nsuccess / failure")]

    H -.enforces against.-> K
    K -.gates.-> L{{"Merge button"}}
    H -.gates.-> L
```

**How to read this:** the top row is every way this system gets triggered. Everything
on the left (`A1`, `A2`, `A3`) ends up building and applying a **ruleset** — the thing
that decides *which branches* require the check. Everything on the right (`A4`) decides
*whether the check passes* for a specific PR. GitHub combines both at merge time: the
ruleset says "this branch needs a passing `PRR Genius Extension Origin Check`," and the
check run says whether this PR's head commit has one.

---

## 2. Provisioning a ruleset — fresh install / new repo added

```mermaid
flowchart TD
    Start(["installation webhook\naction: created"]) --> ListRepos["list_installation_repositories(installation_id)\nGET /installation/repositories (paginated)"]
    Start2(["installation_repositories webhook\naction: added"]) --> UseAdded["repos = payload.repositories_added"]

    ListRepos --> Loop
    UseAdded --> Loop

    Loop{{"For each repo\nin repos"}} --> Split["owner, name = repo.full_name.split('/')"]
    Split --> GetBranches[get_protected_branches_for_repo]

    subgraph GetBranches_detail["get_protected_branches_for_repo(repo_full_name)"]
        direction TB
        Q1["Query repo_branch_config\nfind_one({repo_full_name})"]
        Q1 --> Q2{{"Document found\nAND protected_branches\nnon-empty?"}}
        Q2 -- Yes --> Q3["branches = doc.protected_branches"]
        Q2 -- No --> Q4["branches = DEFAULT_PROTECTED_BRANCHES\n(main, dev, qa, prod)"]
        Q3 --> Q5["ref_names = ['~DEFAULT_BRANCH'] + branches"]
        Q4 --> Q5
        Q5 --> Q6["De-duplicate, preserve order"]
    end

    Q6 --> BuildPayload["RulesetConfig._ORIGIN_CHECK_ORG_RULESET(app_id, ref_names)"]
    BuildPayload --> Create["GitHubApp.create_repo_ruleset\n(installation_id, owner, name, payload)"]
    Create --> NextRepo{{"More repos\nremaining?"}}
    NextRepo -- Yes --> Loop
    NextRepo -- No --> Done(["Done — logged per-repo\nsuccess/failure"])

    Create -.on exception.-> LogErr["logger.error(...)\ncontinue to next repo\n(one bad repo doesn't stop the batch)"]
    LogErr --> NextRepo
```

---

## 3. `create_repo_ruleset` — the self-healing create-or-update logic

```mermaid
flowchart TD
    Start(["create_repo_ruleset(installation_id, owner, repo, payload)"]) --> Token["get_installation_token(installation_id)"]
    Token --> Post["POST /repos/{owner}/{repo}/rulesets"]
    Post --> Status{{"Response status?"}}

    Status -- "200 / 201" --> Created["✅ Ruleset created\n(first time provisioning this repo)"]

    Status -- "422\n(name already exists)" --> ListExisting["GET /repos/{owner}/{repo}/rulesets\n(list all rulesets on repo)"]
    ListExisting --> Find{{"Find ruleset where\nname == 'PRR Genius Extension\nOrigin Check'"}}
    Find -- Found --> Patch["PATCH /repos/{owner}/{repo}/rulesets/{id}\nwith new payload"]
    Patch --> PatchStatus{{"Patch\nsucceeded?"}}
    PatchStatus -- Yes --> Updated["✅ Ruleset updated in place\n(branch list corrected to\ncurrent DB/default state)"]
    PatchStatus -- No --> LogPatchErr["❌ logger.error\n(update failed)"]
    Find -- Not found --> LogInconsistent["❌ logger.error\n(reported as existing but\ncould not be located)"]

    Status -- "Other (403, 5xx, ...)" --> LogOtherErr["❌ logger.error\n(create failed — commonly:\nmissing Administration permission)"]

    Created --> Return(["return response"])
    Updated --> Return
    LogPatchErr --> Return
    LogInconsistent --> Return
    LogOtherErr --> Return
```

---

## 4. Admin API request — `POST /admin/repo-branch-config`

```mermaid
flowchart TD
    Start(["POST /api/admin/repo-branch-config\nheader: X-Admin-Api-Key\nbody: {repo_full_name, protected_branches}"]) --> Auth{{"ADMIN_API_SECRET set\nAND header matches\n(hmac.compare_digest)?"}}
    Auth -- No --> R401(["401 Unauthorized"])
    Auth -- Yes --> Validate{{"repo_full_name has '/'\nAND protected_branches is\nnon-empty list?"}}
    Validate -- No --> R400(["400 Bad Request"])
    Validate -- Yes --> Upsert["Mongo: repo_branch_config.update_one\n($set full protected_branches array,\nupsert=True)"]

    Upsert --> Resolve["GitHubApp.get_installation_id_for_repo(owner, repo)\nGET /repos/{owner}/{repo}/installation\n(app-level JWT auth)"]
    Resolve --> Try{{"Resolved OK?"}}
    Try -- No / raises --> R207(["207 Multi-Status\nDB saved, GitHub not yet updated\n(will self-correct on next\nwebhook redelivery)"])
    Try -- Yes --> Rebuild["get_protected_branches_for_repo(repo_full_name)\n(re-reads what was just written)"]
    Rebuild --> BuildPayload["RulesetConfig._ORIGIN_CHECK_ORG_RULESET(app_id, ref_names)"]
    BuildPayload --> Apply["GitHubApp.create_repo_ruleset(...)\n(create-or-update, see diagram 3)"]
    Apply --> ApplyOk{{"Applied without\nexception?"}}
    ApplyOk -- No --> R207
    ApplyOk -- Yes --> R200(["200 OK\nbody includes the exact\nref_names that were applied"])
```

---

## 5. PR lifecycle — origin check + merge gating (end-to-end sequence)

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant Ext as PRR Genius\nVS Code Extension
    participant DB as MongoDB\n(pr_reports)
    participant GH as GitHub
    participant App as This App\n(webhook_handlers.py)

    Dev->>Ext: Run review on local branch
    Ext->>DB: Write pr_reports doc\n(is_extension=True, completed=True,\ncommits.head=<sha>)

    Dev->>GH: Open PR (or push new commits)
    GH->>App: webhook: pull_request\n(opened / reopened / synchronize)

    App->>DB: is_pr_origin_verified(payload, pr)\nquery pr_reports by repo_url + head_branch + base_branch
    DB-->>App: latest matching report (or none)

    alt report exists AND is_extension AND completed AND commits.head == PR's current head sha
        App->>GH: create_check_run\n(name="PRR Genius Extension Origin Check", conclusion=success)
    else no match / stale commit / not from extension
        App->>GH: create_check_run\n(name="PRR Genius Extension Origin Check", conclusion=failure)
    end

    Note over GH: Repository ruleset requires this exact\ncheck (by name + integration_id) to pass\non any ref in ref_names (main/dev/qa/prod/etc.)

    Dev->>GH: Click "Merge"
    GH->>GH: Evaluate ruleset:\nis base branch in ref_names?\nAND is required check success?

    alt base branch protected AND check = success
        GH-->>Dev: Merge allowed
    else base branch protected AND check = failure/pending
        GH-->>Dev: Merge blocked\n("Required status check\nis expected/failing")
    else base branch NOT in ref_names
        GH-->>Dev: Merge allowed\n(ruleset doesn't apply to this branch at all)
    end
```

---

## 6. Where each diagram maps back to `automation.md`

| Diagram | Corresponds to section in `automation.md` |
|---|---|
| 1. System overview | Whole document, high level |
| 2. Provisioning flow | §1 (`enums.py`), §3 (`webhook_handlers.py`) |
| 3. Self-healing create/update | §2b (`auth.py` — `create_repo_ruleset`) |
| 4. Admin API flow | §2a (`auth.py` — `get_installation_id_for_repo`), §5 (`routes.py`) |
| 5. PR sequence | Pre-existing origin-check feature (`is_pr_origin_verified`, `create_check_run`) that this automation gates via the ruleset |

Edge cases and what's still uncovered are listed in `automation.md`'s
**"Edge case coverage"** table — this file only shows the happy-path flow through each
piece, not the failure/gap scenarios.

# Commit Secret Exposure Scan — new pipeline in the PR "opened" SSE flow

## Context
The PR reviewer runs FA, DevOps, TQA and Coding Standards, but nothing checks whether a commit on the head branch leaked a credential. A secret that was committed and later removed still sits in git history. This change adds a pipeline that:
- scans every commit between base and head,
- groups the file diffs into AI calls that stay under a configurable token threshold, without ever splitting a file,
- asks the AI for findings (commit sha, file name, key name, start and end line),
- stores the result on the PR report document, the same way DevOps and CSA results are stored,
- streams the result in the opened SSE flow.

**Built from scratch.** This plan does not use or depend on any uncommitted local work. The untracked files `App/pr_reviewer/commit_scan/` and `App/pr_reviewer/prompts/extension/commit_secret_scan_prompts.py` are **left untouched**. New code goes in new paths, so nothing collides with them. The only code reused is code that is already committed (listed under "Reused committed code").

**Decisions made:**
| Topic | Decision |
|---|---|
| Single file diff larger than the threshold | Sent **alone** in its own AI call and flagged `oversized`. It is never split. |
| Where the threshold comes from | Env `SECRET_SCAN_TOKEN_THRESHOLD` (default 60000). Payload field `secret_scan_token_threshold` overrides it per request. |
| Which flow runs it | **Opened** SSE flow only (`handle_pr_opened_sse`). |
| What is stored about the secret | `key_name`, a masked value, and a sha256 fingerprint. The raw secret is never stored or streamed. |
| Effect on PR status | **Report only.** It does not change the `completed` status or the Passed/Failed judgement. |

---

## New package: `App/pr_reviewer/secret_scan/`
| File | Responsibility |
|---|---|
| `__init__.py` | Exports `run_secret_scan` |
| `config.py` | Env-backed settings, listed below |
| `models.py` | Dataclasses `FileDiff`, `CommitDiff`, `ScanBlock`, `ScanBatch` |
| `fetcher.py` | Steps 1–2: fetch commits and per-commit file diffs from GitHub |
| `filters.py` | Step 3: drop binary, lock and other noise files |
| `batcher.py` | Step 4: the token-threshold batching pipeline |
| `scanner.py` | Steps 5–6 and orchestration: build prompts, call the LLM, validate findings, assemble the result dict |

**Settings in `config.py`:**
| Env var | Default | Meaning |
|---|---|---|
| `SECRET_SCAN_TOKEN_THRESHOLD` | 60000 | Token threshold per AI call |
| `SECRET_SCAN_MAX_COMMITS` | 500 | Most commits scanned per PR |
| `SECRET_SCAN_MAX_BLOCKS_PER_BATCH` | 15 | Most commit blocks in one AI call |
| `SECRET_SCAN_GITHUB_WORKERS` | 5 | Parallel GitHub calls |
| `SECRET_SCAN_LLM_WORKERS` | 4 | Parallel LLM calls |
| `SECRET_SCAN_LLM_ATTEMPTS` | 2 | Attempts per AI call |

**New prompts file:** `App/pr_reviewer/prompts/extension/secret_scan_prompts.py` (Step 5).

## Step 1 — Fetch the commits between base and head (`fetcher.py`)
Class `CommitFetcher(token, owner, repo, is_forked_repo=False, fork_owner="", fork_repo="")` makes every request through the committed `GitHubApp().make_api_request(token, "GET", url)` ([auth.py:47](App/pr_reviewer/github_app/auth.py#L47)), which already retries.

`list_commits(base, head)`:
- **Compare URL:** use the same URL rules as `get_pre_pr_files` ([git_utils.py:147-153](App/pr_reviewer/utils/git_utils.py#L147-L153)):
  - Same repo: `/repos/{owner}/{repo}/compare/{base}...{head}`
  - Fork: `/repos/{fork_owner}/{fork_repo}/compare/{fork_owner}:{base}...{owner}:{head}`
  - URL-encode both branch names, keeping `/` unescaped.
- **Paging:** request with `per_page=100&page=n` and stop when the response has no commits, when `total_commits` is reached, or at `SECRET_SCAN_MAX_COMMITS`.
- **Order:** the API returns commits oldest first. Keep that order, because it drives the order of the prompt.
- **Errors:** a non-200 response raises `GitHubAPIError(status_code)`.

## Step 2 — Fetch the file diffs of each commit (`fetcher.py`)
- **Merge commits:** first drop commits with more than one parent and record them as `skipped_commits: [{commit_sha, reason: "merge_commit"}]`. A merge commit's diff repeats changes that are already in its parent commits.
- **Per-commit files:** `get_commit_files(sha)` calls `GET /repos/{owner}/{repo}/commits/{sha}?per_page=100&page=n` and follows pages until a page has fewer than 100 files. Use the head repo here, because the head commits live there.
- **Parallelism:** run the fetches in a `ThreadPoolExecutor(SECRET_SCAN_GITHUB_WORKERS)`.
- **Building the model:** each commit becomes `CommitDiff(sha, message, author, authored_at, html_url, files, skipped_files)`.

**Diff rendering:** `render_patch(patch)` lives in `fetcher.py` and turns GitHub's unified-diff `patch` into numbered lines of the new file.
- Parse each hunk header `@@ -a,b +c,d @@` and start counting new-file lines at `c`.
- A `+` line becomes `f"{n:>6} + {text}"`, is added to `added_lines[n] = text`, and increments `n`.
- A context line becomes `f"{n:>6}   {text}"` and increments `n`.
- A `-` line is dropped, because a secret on a removed line wasn't introduced by this commit.
- `\ No newline at end of file` is ignored.
- A hunk with no `+` lines is dropped.
- Hunks are separated by a line containing `...`.
- The result is `FileDiff(path, status, rendered_lines, added_lines, additions, deletions, tokens)`.

## Step 3 — Remove binary, lock and other noise files (`filters.py`)
`skip_reason(file_info) -> str | None`. Every skipped file is recorded in its commit's `skipped_files: [{file_path, reason}]`, so gaps in coverage stay visible.

| Reason | When it applies |
|---|---|
| `removed` | The file's status is `removed` |
| `lock_file` | The base name is in the lock-file set below, or ends with `.lock` |
| `binary` | The extension is in the binary set below |
| `vendor` | A path segment is `node_modules`, `vendor`, `third_party`, `.venv`, `venv`, `site-packages`, `bower_components`, `__pycache__` or `.yarn` |
| `minified` | The name ends with `.min.js`, `.min.css` or `.map` |
| `no_patch` | GitHub sent no `patch`. This happens for binaries, very large diffs and pure renames. |
| `no_added_lines` | Applied after rendering: the diff has no `+` lines |

- **Lock files:** package-lock.json, npm-shrinkwrap.json, yarn.lock, pnpm-lock.yaml, poetry.lock, Pipfile.lock, uv.lock, pdm.lock, Gemfile.lock, composer.lock, Cargo.lock, go.sum, Podfile.lock, packages.lock.json, flake.lock, pubspec.lock, gradle.lockfile.
- **Binary extensions:** images, audio, video, fonts, archives, office documents, PDFs, compiled objects and libraries, `.pyc`, `.class`, `.wasm`, databases, and ML weights.

## Step 4 — The token-threshold batching pipeline (`batcher.py`)
**Counting tokens:**
- `count_tokens(text)` uses tiktoken `cl100k_base` with `disallowed_special=()`, which matches `num_tokens_from_string` in [al_suggestions/helpers.py:2582](App/coding_standards/al_suggestions/helpers.py#L2582).
- The encoder is loaded lazily and cached.
- If tiktoken can't be imported, it falls back to `len(text)//4 + 1`. tiktoken is already in `App/requirements.txt`.

**Budget:**
- `threshold = payload override or SECRET_SCAN_TOKEN_THRESHOLD`
- `budget = max(threshold - count_tokens(system_prompt) - count_tokens(user_prompt_template), 2000)`

**Rendered text:**
- A file renders as `<file path="..." status="...">\n<lines>\n</file>`. Its `tokens` are measured once, on that text.
- A commit renders as `<commit sha="..."[ part="i/n"]>\nMessage: <subject>\n<file blocks>\n</commit>`. `header_tokens` is the token count of that wrapper without any files.

**4a. Commit → blocks: `commit_to_blocks(commit, budget) -> list[ScanBlock]`**
1. **The whole commit fits:** if `header + Σ file.tokens <= budget`, the whole commit becomes **one block**.
2. **The commit is too big:** split it **at file boundaries only**.
   - Sort the files from largest to smallest.
   - Place each file in the first part where `part.tokens + file.tokens <= budget - header`; open a new part if none fits.
   - A file whose `file.tokens > budget - header` gets a part of its own with `oversized=True`. **A file is never split.**
3. **Output:** each part becomes `ScanBlock(sha, part=i, total_parts=n, files, tokens, oversized)`.
   - Files inside a part keep their original commit order.
   - The block is rendered with its commit header, and `tokens` is re-measured on the final text.

**4b. Blocks → batches: `build_batches(commits, budget) -> list[ScanBatch]`**
1. Collect the blocks of every commit.
2. Pack them with first-fit decreasing by tokens. A block goes into the first batch where `batch.tokens + block.tokens <= budget` and `len(batch.blocks) < SECRET_SCAN_MAX_BLOCKS_PER_BATCH`; otherwise it opens a new batch.
3. An `oversized` block always gets a batch of its own, and that batch is marked `oversized=True`.
4. Inside each batch, sort the blocks by commit order and then by part number, so the prompt reads chronologically.
5. Number the batches `batch-1…n`.

**What this produces:**
- Small commits are combined into one call.
- Several file diffs from the same commit are combined.
- A large commit is spread across calls at file boundaries, and its parts can share a call with other commits.

**Invariants:**
- Every scanned file appears in exactly one batch.
- No file is ever split.
- Every batch that isn't `oversized` has `tokens <= budget`.

## Step 5 — Prompts (`prompts/extension/secret_scan_prompts.py`)
**`secret_scan_system_prompt`.** Role: a senior application security engineer auditing git commits for leaked secrets. It explains:
- **Input format:**
  - one or many `<commit sha>` blocks;
  - a large commit can arrive as several blocks with the same sha (`part="i/n"`), and these are parts of one commit;
  - each `<commit>` holds `<file path>` blocks;
  - every line starts with its new-file line number and a marker: `+` means added, a space means context.
- **What to report:** only real credentials on **`+` lines**. Covers:
  - cloud keys: AWS, GCP service account, Azure;
  - API keys and tokens: OpenAI, Anthropic, Stripe secret keys, Slack, GitHub and GitLab, Twilio, SendGrid, Google;
  - private keys: PEM and SSH;
  - JWT signing secrets;
  - passwords in connection strings or URLs;
  - OAuth client secrets, webhook secrets, hard-coded bearer tokens, session secrets.
- **What not to report:**
  - context lines;
  - placeholders and dummies ("your-api-key", `<API_KEY>`, "changeme", "xxx", empty strings);
  - environment or secret-manager lookups (`os.getenv`, `process.env`, `${VAR}`, `{{ secrets.X }}`, Vault);
  - key names with no value;
  - public identifiers (publishable `pk_` keys, Firebase web `apiKey`, OAuth client IDs on their own, UUIDs, hashes, SHAs);
  - known fake values in tests.
  - When unsure, don't report: precision matters more than recall.
- **Line numbers:** copy `start_line` and `end_line` from the line-number prefixes and never count lines yourself. A multi-line secret spans its first to last line.
- **Output:** only a ```json fenced object:
  ```json
  {"findings": [{
    "title": "AWS secret key hard-coded in settings.py",
    "commit_sha": "<full sha from the <commit sha> attribute>",
    "file_name": "<path from the <file path> attribute>",
    "key_name": "<variable / config key / header that holds the secret, copied from the diff, e.g. AWS_SECRET_ACCESS_KEY; if unnamed, the credential type e.g. 'PEM private key'>",
    "secret_type": "aws_key|gcp_service_account|azure_key|api_key|token|password|private_key|connection_string|other",
    "exposed_value": "<exact value only, not the whole line>",
    "start_line": 12,
    "end_line": 12
  }]}
  ```
- **Finding rules:**
  - Report one finding per occurrence. If the same secret appears in two commits, that is two findings.
  - When nothing is found, return `{"findings": []}`.

**`secret_scan_user_prompt`:**
```
Scan the following {block_count} commit block(s) from repository "{repository}" for exposed secrets in ADDED lines.

{commit_blocks}

Return only the JSON object described in your instructions.
```

## Step 6 — LLM call and validation (`scanner.py`)
**`scan_batch(batch, repository, commits_by_sha, user)`:**
- Formats the user prompt with the batch's rendered blocks.
- Calls the committed `techo_llm_call(user_prompt, system_prompt, flag=True, user_name=…, user_id=…, user_email=…)` ([helper.py:2321](App/pr_reviewer/pipeline/helper.py#L2321)).
- Tries up to `SECRET_SCAN_LLM_ATTEMPTS` times.
- Parses the response with the committed `Predict.extract_json_block` ([predict.py:620](App/predict.py#L620)), then `json.loads`, falling back to `robust_json_parser` ([helper.py:1397](App/pr_reviewer/pipeline/helper.py#L1397)).
- Accepts either `{"findings": [...]}` or a bare list.
- Batches run in a `ThreadPoolExecutor(SECRET_SCAN_LLM_WORKERS)`.
- Returns a per-batch record: `batch_id`, `commit_shas`, `blocks [{commit_sha, part, total_parts, files, tokens}]`, `tokens`, `oversized`, `status`, `attempts`, `raw_findings_count`, `findings_count`, `error`.

**`validate_findings(raw, batch, commits_by_sha)`** removes hallucinated findings. It drops a finding when:
- **sha:** `commit_sha` doesn't match a sha in this batch. A prefix of 7 or more characters is accepted, and a batch with a single commit uses that commit.
- **file:** `(sha, file_name)` was not sent in this batch.
- **lines:** `start_line` or `end_line` are not integers, or none of the lines in the range are added lines. Swapped `start_line` / `end_line` are corrected rather than dropped.
- **value:** the first line of `exposed_value`, after trimming quotes, does not appear in the added lines of that range.
- **duplicate:** a finding with the same `(sha, file, start, end, fingerprint)` was already kept.

Each kept finding has:
- `finding_id` (a uuid4), `title`, `commit_sha`, `commit_url` (the commit's `html_url`), `file_name`, `key_name`, `secret_type`
- `masked_value`: the first 4 characters, then `*`s, then the last 4. A value of 8 characters or fewer is fully masked.
- `secret_fingerprint`: sha256 of the value.
- `start_line`, `end_line`, `batch_id`

**`run_secret_scan(owner, repo, base, head, token, is_forked_repo, fork_owner, fork_repo, token_threshold=None, user=None) -> dict`:**
- It is pure: it does **no DB writes**.
- It runs Steps 1–6 and returns:
```
status: completed | partial | failed      (based on how many batches failed)
token_threshold, budget, base_branch, head_branch, scanned_at (UTC ISO)
summary: {total_commits, commits_scanned, commits_skipped, files_scanned, files_skipped,
          tokens_scanned, llm_batches, oversized_batches, failed_batches,
          total_findings, commits_with_findings}
findings: [...]
commits: [{commit_sha, message, author, authored_at, html_url, tokens,
           files_scanned, files_skipped, batch_ids}]
skipped_commits: [...]
batches: [per-batch records]
```

## Step 7 — Store in `pr_reports`, the same way as DevOps and CSA
**File:** [core.py](App/pr_reviewer/pipeline/core.py).

**Report object:** in `PRReport.__init__` (around line 6032), add `self.commit_secret_scan = {}`.

**New method:** add `PRReviewPipeline.start_commit_secret_scan_pipeline(self)` next to `start_devops_analysis_pipeline` (around line 2265).
- If `self.flow_manager.get_status(self.pull_request_url) == "closed"`, return `("success", 200)` straight away. This is the same guard the DevOps pipeline uses.
- Otherwise, read its inputs from `self.payload`:
  - `pull_request.owner`, `pull_request.repo_name`
  - `base_branch`, `head_branch`, `token`
  - `pull_request.is_forked_repo` / `forked_repo_owner` / `forked_repo_name`
  - `secret_scan_token_threshold`
  - plus `self.user_name/id/email`
- Call `run_secret_scan(...)`.
- Set `self.pr_report.commit_secret_scan = result` and store it with the same call DevOps and CS use:
  ```python
  self.pr_report.insert_assessment_to_db(self.document_id, {"commit_secret_scan": result})
  ```
  That method ([core.py:6289](App/pr_reviewer/pipeline/core.py#L6289)) sanitises the data and `$set`s it onto the `pr_reports` document.
- **Return:** `("success", 200)`.
- **On any exception:**
  - log the traceback;
  - set `commit_secret_scan = {"status": "failed", "error": str(e)}`;
  - store that;
  - return `("failed", 500)`.
- It never raises, so the other pipelines are never affected.

## Step 8 — Trigger in the opened SSE flow
**File:** [webhook_handlers.py](App/pr_reviewer/github_app/webhook_handlers.py), function `handle_pr_opened_sse`.

1. **Start it in parallel.** Next to the other parallel submits (`met_req_future`, `devops_future`, `tqa_future`, around line 1440):
   ```python
   secret_scan_future = executor.submit(pipeline.start_commit_secret_scan_pipeline)
   ```
   Then yield:
   - `pipeline_start {pipeline: "commit_secret_scan"}`
   - `watch_me_work` with id 5, "Secret Exposure Scan", status `pending`, and one subStep 5.1 "Commit-wise Secret Scan" described as "Scanning every commit between base and head for exposed credentials..."
2. **Collect the result.** After the Coding Standards `watch_me_work` completion has been yielded (around line 2042) and **before** the `completed` event:
   - call `secret_message, secret_status = secret_scan_future.result()`;
   - yield `pipeline_result {pipeline: "commit_secret_scan", message, status}`;
   - yield `commit_secret_scan {pipeline: "commit_secret_scan_results", message: "Commit secret exposure findings", result: {status, summary, findings}}`;
   - yield `watch_me_work` id 5 with status `completed`. Its subStep 5.1 description is `json.dumps(findings, indent=4, default=str)`.
3. **Leave the gate alone.** Don't add it to `pipelines_ok`, and don't change the judgement (report only).

`payload["token"]` is already set by `update_payload_for_extension_open_flow`. It is the same token `get_pre_pr_files` uses.

---

## Files
| File | Change |
|---|---|
| `App/pr_reviewer/secret_scan/` | **New.** `__init__`, `config`, `models`, `fetcher`, `filters`, `batcher`, `scanner` |
| `App/pr_reviewer/prompts/extension/secret_scan_prompts.py` | **New.** System and user prompt |
| `App/pr_reviewer/pipeline/core.py` | `PRReport.commit_secret_scan`; `PRReviewPipeline.start_commit_secret_scan_pipeline` |
| `App/pr_reviewer/github_app/webhook_handlers.py` | Submit the future and yield the SSE events in `handle_pr_opened_sse` |

The untracked local files (`commit_scan/`, `commit_secret_scan_prompts.py`, and the others) are not read, imported, modified or deleted.

## Reused committed code
| Code | Used for |
|---|---|
| `GitHubApp.make_api_request` ([auth.py:47](App/pr_reviewer/github_app/auth.py#L47)) | GitHub calls |
| The compare-URL pattern in `get_pre_pr_files` ([git_utils.py:147](App/pr_reviewer/utils/git_utils.py#L147)) | Building compare URLs, including forks |
| `techo_llm_call` and `robust_json_parser` ([helper.py](App/pr_reviewer/pipeline/helper.py)) | The LLM call and JSON parsing |
| `Predict.extract_json_block` ([predict.py:620](App/predict.py#L620)) | Pulling the JSON block out of the response |
| `PRReport.insert_assessment_to_db` ([core.py:6289](App/pr_reviewer/pipeline/core.py#L6289)) | Storing the result |
| tiktoken `cl100k_base`, same as [al_suggestions/helpers.py:2582](App/coding_standards/al_suggestions/helpers.py#L2582) | Token counting |

## Verification
1. **Batcher unit check.** Run a scratch script in the session scratchpad. Build fake `CommitDiff` and `FileDiff` objects with fixed token counts and use budget 1000. Check that:
   - three small commits of 200 tokens each end up in **one** batch;
   - a commit with files of 600, 500 and 300 tokens is split at file boundaries into parts of at most the budget, labelled `1/2` and `2/2`;
   - a 1500-token file ends up alone in an `oversized` batch;
   - every file appears exactly once, and no file's text is cut.
2. **Render and filter check.** Run `render_patch` on a sample patch with two hunks and confirm the line numbers and `added_lines`. Run `skip_reason` on `package-lock.json`, `logo.png`, `vendor/x.js` and a removed file.
3. **Validation check.** Feed mocked LLM output to `validate_findings` with these cases:
   - a wrong sha;
   - a file that wasn't sent;
   - a line that isn't an added line;
   - a value that isn't on its lines;
   - one valid finding.

   Only the valid finding should survive, with `key_name` and a masked value.
4. **Compile check.** Run `python -m py_compile` on all new and modified files.
5. **End-to-end.** Run the app, then POST `/api/pr_reviewer/pr-reviewer/open` with action `opened` against a test branch that has a planted, realistic-looking random key. Pass `secret_scan_token_threshold` around 3000 so several batches are formed. Confirm that:
   - the SSE stream emits `commit_secret_scan` with the right sha, file, key_name and lines, and a masked value;
   - `pr_reports.<document_id>.commit_secret_scan` holds the same data with `summary.llm_batches > 1`;
   - the other pipelines and the `completed` status are unchanged.

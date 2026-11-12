"""
pr_batching.py

Trigger `recommend_pr_batches(...)` when the changed-file count between two
branches exceeds your threshold. Returns a list of BatchGroup, each kept
under the threshold, together covering every changed file exactly once.

Pipeline: fetch diff -> relatedness signals (tree-sitter imports, directory,
naming pairs, co-change history) -> graph clustering -> LLM refinement
(pluggable) -> hard validation (coverage + threshold), with a deterministic
fallback if the LLM step can't be made to pass validation.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from pr_reviewer.utils.tree_sitter_utils import DependencyExtractor


# ---------- Data structures ----------

@dataclass
class FileChange:
    filename: str
    status: str  # added, modified, removed, renamed
    changes: int


@dataclass
class BatchGroup:
    group_id: str
    files: list[str]
    reasoning: str = ""
    suggested_pr_title: str = ""
    depends_on: list[str] = field(default_factory=list)  # group_ids this must merge after


# ---------- Step 1: fetch diff ----------

def fetch_changed_files(access_token: str, repo_url: str, base_branch: str, head_branch: str) -> list[FileChange]:
    """Fetch changed files between base and head using GitHub's compare API."""
    owner_repo = _parse_owner_repo(repo_url)
    url = f"https://api.github.com/repos/{owner_repo}/compare/{base_branch}...{head_branch}"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [
        FileChange(filename=f["filename"], status=f["status"], changes=f.get("changes", 0))
        for f in data.get("files", [])
    ]


def _parse_owner_repo(repo_url: str) -> str:
    match = re.search(r"github\.com[:/](?P<owner_repo>[\w.-]+/[\w.-]+?)(\.git)?$", repo_url.strip())
    if not match:
        raise ValueError(f"Could not parse owner/repo from {repo_url}")
    return match.group("owner_repo")


# ---------- Step 2: relatedness signals ----------

# Maps file extensions to the language names DependencyExtractor understands.
# This is a superset of the old tree_sitter_languages-based mapping.
EXTENSION_LANGUAGE = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".h": "cpp", ".hpp": "cpp",
    ".c": "c",
    ".php": "php",
}

# One shared extractor instance; it loads whichever tree-sitter language
# grammars are installed once, at import time.
_dependency_extractor = DependencyExtractor()


def extract_imports(repo_dir: str, filename: str) -> list[dict]:
    """Extract detailed import dicts for a file via DependencyExtractor, if a grammar is available.

    Each dict has the shape produced by DependencyExtractor.extract_detailed_dependencies:
    {'module', 'imports', 'statement', 'alias', 'type', 'category'}.
    """
    language = EXTENSION_LANGUAGE.get(os.path.splitext(filename)[1])
    if language is None or language not in _dependency_extractor.languages:
        return []

    file_path = os.path.join(repo_dir, filename)
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            code = fh.read()
        return _dependency_extractor.extract_detailed_dependencies(code, language)
    except Exception:
        return []


def _module_candidate_paths(source_file: str, module: str, language: str) -> list[str]:
    """Turn an import's module string into candidate '/'-joined, extension-less
    path suffixes that might correspond to another changed file.

    This is a heuristic, not a real module resolver: it's meant to catch the
    common cases (relative JS/TS imports, straightforward Python dotted
    imports, Java-style package.Class imports) well enough to score
    relatedness, not to be a build-system-accurate resolution.
    """
    source_dir = os.path.dirname(source_file)

    if language in ("javascript", "typescript", "tsx"):
        if module.startswith("."):
            resolved = os.path.normpath(os.path.join(source_dir, module))
            return [resolved.replace(os.sep, "/").lstrip("/")]
        # bare/scoped/subpath imports (npm packages, path aliases) aren't
        # resolvable to a local file without a bundler config, so skip them.
        return []

    if language == "python":
        segments = [s for s in module.split(".") if s]
        if not segments:
            return []
        as_root = "/".join(segments)
        candidates = {as_root}
        if source_dir:
            candidates.add("/".join([*source_dir.split(os.sep), *segments]))
        return list(candidates)

    if language == "java":
        segments = [s for s in module.split(".") if s]
        return ["/".join(segments)] if segments else []

    if language == "go":
        # Go import paths are package paths (often "example.com/mod/pkg"),
        # not file paths; matching is done on the path's tail below.
        return [module.strip("/")]

    if language in ("cpp", "c"):
        return [module.strip("/")]

    if language == "rust":
        return [module.replace("::", "/")]

    if language == "php":
        return [module.replace("\\", "/")]

    if language == "ruby":
        return [module]

    return [module]


def _find_matching_changed_files(candidates: list[str], changed_filenames: list[str], exclude: str) -> set[str]:
    """Match candidate path suffixes against the set of changed files."""
    matches: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip("/")
        if not candidate:
            continue
        candidate_last = candidate.split("/")[-1]

        for fn in changed_filenames:
            if fn == exclude:
                continue
            fn_normalized = fn.replace(os.sep, "/")
            fn_no_ext = os.path.splitext(fn_normalized)[0]
            fn_stem = os.path.splitext(os.path.basename(fn))[0]

            if (
                fn_normalized == candidate
                or fn_no_ext == candidate
                or fn_normalized.endswith("/" + candidate)
                or fn_no_ext.endswith("/" + candidate)
                or fn_no_ext.endswith("/" + candidate + "/index")
                or fn_stem == candidate_last
            ):
                matches.add(fn)

    return matches


def resolve_imports_to_changed_files(
    source_file: str,
    imports: list[dict],
    language: str,
    changed_filenames: list[str],
) -> set[str]:
    """Map a file's parsed imports back to the other changed files they likely refer to."""
    resolved: set[str] = set()
    for dep in imports:
        module = dep.get("module")
        if not module:
            continue
        candidates = _module_candidate_paths(source_file, module, language)
        resolved |= _find_matching_changed_files(candidates, changed_filenames, exclude=source_file)
    return resolved


def get_co_change_pairs(repo_dir: str, base_branch: str, head_branch: str) -> dict[tuple[str, str], int]:
    """Count how often pairs of files were committed together historically."""
    try:
        log_output = subprocess.run(
            ["git", "-C", repo_dir, "log", "--name-only", "--pretty=format:__COMMIT__",
             f"{base_branch}..{head_branch}"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except Exception:
        return {}

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    commit_files: list[str] = []
    for line in log_output.splitlines() + ["__COMMIT__"]:
        if line == "__COMMIT__":
            for i in range(len(commit_files)):
                for j in range(i + 1, len(commit_files)):
                    pair_counts[tuple(sorted((commit_files[i], commit_files[j])))] += 1
            commit_files = []
        elif line.strip():
            commit_files.append(line.strip())
    return pair_counts


def naming_pair_score(file_a: str, file_b: str) -> float:
    """Heuristic score for test/source naming pairs, e.g. foo.py <-> test_foo.py."""
    base_a = os.path.splitext(os.path.basename(file_a))[0]
    base_b = os.path.splitext(os.path.basename(file_b))[0]
    stripped_a = re.sub(r"^test_|_test$|\.test$|\.spec$", "", base_a)
    stripped_b = re.sub(r"^test_|_test$|\.test$|\.spec$", "", base_b)
    return 1.0 if stripped_a and stripped_a == stripped_b else 0.0


# ---------- Step 3: build relatedness graph & cluster ----------

class UnionFind:
    def __init__(self, items: list[str]):
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: str, b: str):
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[root_a] = root_b


def build_relatedness_graph(
    files: list[FileChange],
    repo_dir: str,
    base_branch: str,
    head_branch: str,
    similarity_cutoff: float = 0.3,
) -> dict[tuple[str, str], float]:
    """Weighted edge score between every pair of changed files."""
    filenames = [f.filename for f in files]
    co_change = get_co_change_pairs(repo_dir, base_branch, head_branch)

    # Parse imports once per file, then resolve each file's imports against
    # the rest of the changed set so we score real import edges rather than
    # loose substring matches.
    resolved_imports_by_file: dict[str, set[str]] = {}
    for fn in filenames:
        language = EXTENSION_LANGUAGE.get(os.path.splitext(fn)[1])
        deps = extract_imports(repo_dir, fn)
        resolved_imports_by_file[fn] = (
            resolve_imports_to_changed_files(fn, deps, language, filenames) if language else set()
        )

    edges: dict[tuple[str, str], float] = {}
    for i in range(len(filenames)):
        for j in range(i + 1, len(filenames)):
            a, b = filenames[i], filenames[j]
            score = 0.0

            if os.path.dirname(a) == os.path.dirname(b) and os.path.dirname(a):
                score += 0.3

            score += 0.4 * naming_pair_score(a, b)

            pair_key = tuple(sorted((a, b)))
            if co_change.get(pair_key, 0) > 0:
                score += min(0.4, 0.1 * co_change[pair_key])

            if b in resolved_imports_by_file.get(a, set()):
                score += 0.6
            if a in resolved_imports_by_file.get(b, set()):
                score += 0.6

            if score >= similarity_cutoff:
                edges[(a, b)] = score

    return edges


def cluster_files(files: list[FileChange], edges: dict[tuple[str, str], float]) -> list[list[str]]:
    filenames = [f.filename for f in files]
    uf = UnionFind(filenames)
    for (a, b) in edges:
        uf.union(a, b)

    clusters: dict[str, list[str]] = defaultdict(list)
    for fn in filenames:
        clusters[uf.find(fn)].append(fn)
    return list(clusters.values())


def split_oversized_cluster(cluster: list[str], threshold: int) -> list[list[str]]:
    """Deterministic fallback split: chunk an oversized cluster by directory, then by size."""
    if len(cluster) <= threshold:
        return [cluster]

    by_dir: dict[str, list[str]] = defaultdict(list)
    for fn in cluster:
        by_dir[os.path.dirname(fn)].append(fn)

    chunks: list[list[str]] = []
    current: list[str] = []
    for _, group_files in sorted(by_dir.items()):
        for fn in group_files:
            current.append(fn)
            if len(current) >= threshold:
                chunks.append(current)
                current = []
    if current:
        chunks.append(current)
    return chunks


# ---------- Step 4: LLM refinement (pluggable) ----------

# A real refine_fn should call your CATechoLLMClient with the clusters + threshold,
# get back a structured JSON group proposal (validated, retried on schema failure
# the way CATechoLLMClient already does), and return BatchGroup objects. On a
# validation retry, `prior_problems` tells it what to fix (e.g. "3 files unassigned",
# "group pr-1 has 14 files, threshold is 10").
LLMRefineFn = Callable[[list[list[str]], int, Optional[list[str]]], list[BatchGroup]]


def default_llm_refine(clusters: list[list[str]], threshold: int, prior_problems: Optional[list[str]] = None) -> list[BatchGroup]:
    """No-LLM fallback: numbers the deterministic clusters, splitting any that are oversized.
    Threshold is a hard cap, so a split that breaks an import edge is tagged via depends_on."""
    groups: list[BatchGroup] = []
    for idx, cluster in enumerate(clusters):
        chunks = split_oversized_cluster(cluster, threshold)
        chunk_ids = [f"pr-{idx}-{sub_idx}" if len(chunks) > 1 else f"pr-{idx}" for sub_idx in range(len(chunks))]
        for sub_idx, (chunk, group_id) in enumerate(zip(chunks, chunk_ids)):
            groups.append(BatchGroup(
                group_id=group_id,
                files=chunk,
                reasoning="Grouped by directory/import/co-change proximity",
                suggested_pr_title=f"Update {os.path.dirname(chunk[0]) or 'root'}",
                depends_on=[chunk_ids[sub_idx - 1]] if sub_idx > 0 else [],
            ))
    return groups


# ---------- Step 5: validate ----------

def validate_groups(groups: list[BatchGroup], all_files: list[str], threshold: int) -> list[str]:
    """Returns a list of problems; empty list means the batching is valid."""
    problems: list[str] = []
    assigned = [fn for g in groups for fn in g.files]
    missing = set(all_files) - set(assigned)
    duplicated = {fn for fn in assigned if assigned.count(fn) > 1}

    if missing:
        problems.append(f"Unassigned files: {sorted(missing)}")
    if duplicated:
        problems.append(f"Files assigned to multiple groups: {sorted(duplicated)}")
    for g in groups:
        if len(g.files) > threshold:
            problems.append(f"Group {g.group_id} has {len(g.files)} files, exceeds threshold of {threshold}")

    return problems


# ---------- Entry point ----------

def recommend_pr_batches(
    access_token: str,
    repo_url: str,
    base_branch: str,
    head_branch: str,
    threshold: int,
    repo_dir: Optional[str] = None,
    llm_refine_fn: LLMRefineFn = default_llm_refine,
    max_retries: int = 2,
) -> list[BatchGroup]:
    """
    Call this when the changed-file count between base_branch and head_branch
    exceeds `threshold`. Returns BatchGroup objects, each under the threshold,
    covering every changed file exactly once.

    repo_dir: local clone with both branches available, used for import parsing
    and co-change history. If omitted, a shallow clone is made to a temp dir
    and removed afterward.
    """
    changed_files = fetch_changed_files(access_token, repo_url, base_branch, head_branch)
    if len(changed_files) <= threshold:
        return [BatchGroup(group_id="pr-0", files=[f.filename for f in changed_files])]

    owns_temp_dir = repo_dir is None
    if owns_temp_dir:
        repo_dir = _shallow_clone(access_token, repo_url, base_branch, head_branch)

    try:
        edges = build_relatedness_graph(changed_files, repo_dir, base_branch, head_branch)
        clusters = cluster_files(changed_files, edges)
        all_filenames = [f.filename for f in changed_files]

        groups = llm_refine_fn(clusters, threshold, None)
        problems = validate_groups(groups, all_filenames, threshold)

        attempt = 0
        while problems and attempt < max_retries:
            groups = llm_refine_fn(clusters, threshold, problems)
            problems = validate_groups(groups, all_filenames, threshold)
            attempt += 1

        if problems:
            # deterministic fallback guarantees a valid, if less elegant, batching
            groups = default_llm_refine(clusters, threshold)

        return groups
    finally:
        if owns_temp_dir:
            shutil.rmtree(repo_dir, ignore_errors=True)


def _shallow_clone(access_token: str, repo_url: str, base_branch: str, head_branch: str) -> str:
    owner_repo = _parse_owner_repo(repo_url)
    clone_url = f"https://x-access-token:{access_token}@github.com/{owner_repo}.git"
    tmp_dir = tempfile.mkdtemp(prefix="pr_batching_")
    subprocess.run(["git", "clone", "--no-checkout", clone_url, tmp_dir], check=True, capture_output=True)
    subprocess.run(["git", "-C", tmp_dir, "fetch", "origin", base_branch, head_branch], check=True, capture_output=True)
    subprocess.run(["git", "-C", tmp_dir, "checkout", head_branch], check=True, capture_output=True)
    return tmp_dir



groups = recommend_pr_batches(
    access_token="YOUR_GITHUB_ACCESS_TOKEN",
    repo_url="https://github.com/Techolution/Appmod-Backend.git",
    base_branch="main",
    head_branch="dev",
    threshold=8
)

print(groups)


"""
Computes per-file input/output token counts from a debug_outputs_* folder.

Input tokens  = tokens(system_prompt) + tokens(user_prompt)
Output tokens = tokens(raw_ai_response)

Token counts come from the real Vertex AI count_tokens API for
gemini-3-flash-preview (the model this project's pipeline actually uses,
see App/pr_reviewer/enums.py). This requires:
  - LLM_PROJECT_ID set (loaded from App/config_local.env if not already set)
  - GOOGLE_APPLICATION_CREDENTIALS pointing at a valid service account key
    (defaults to App/credentials.json if present and unset)

Usage:
    python token_usage_report.py /path/to/debug_outputs_<id> [--csv out.csv]
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

MODEL_NAME = "gemini-3-flash-preview"
APP_DIR = Path(__file__).resolve().parent

SYSTEM_PREFIX = "system_prompt_"
USER_PREFIX = "user_prompt_"
RESPONSE_PREFIX = "raw_ai_response_"

_CLIENT = None


def get_client() -> genai.Client:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    load_dotenv(APP_DIR / "config_local.env")

    default_creds = APP_DIR / "credentials.json"
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and default_creds.is_file():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(default_creds)

    project_id = os.environ.get("LLM_PROJECT_ID")
    if not project_id:
        sys.exit("LLM_PROJECT_ID is not set (checked env and App/config_local.env)")

    _CLIENT = genai.Client(vertexai=True, project="lumbar-poc", location="global")
    return _CLIENT


def read_text(path: Path) -> str:
    """Read a debug file's real text content.

    These files are written as a JSON-encoded string (e.g. json.dumps(text)),
    so decode with json.loads and fall back to the raw bytes if that fails.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, str):
            return decoded
        return json.dumps(decoded)
    except json.JSONDecodeError:
        return raw


def count_tokens(text: str, retries: int = 3) -> int:
    if not text:
        return 0

    client = get_client()
    for attempt in range(retries):
        try:
            resp = client.models.count_tokens(model=MODEL_NAME, contents=text)
            return resp.total_tokens or 0
        except genai_errors.ClientError:
            raise
        except genai_errors.ServerError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def suffix_after(prefix: str, filename: str) -> str:
    return filename[len(prefix):] if filename.startswith(prefix) else None


def collect_rows(base: Path):
    prompts_dir = base / "prompts"
    responses_dir = base / "ai_responses"

    if not prompts_dir.is_dir() or not responses_dir.is_dir():
        sys.exit(f"Expected 'prompts' and 'ai_responses' subfolders under {base}")

    rows = []
    unmatched = []

    for category_dir in sorted(p for p in prompts_dir.iterdir() if p.is_dir()):
        category = category_dir.name
        response_category_dir = responses_dir / category

        system_by_suffix = {}
        user_by_suffix = {}
        for f in category_dir.iterdir():
            if not f.is_file():
                continue
            suf = suffix_after(SYSTEM_PREFIX, f.name)
            if suf is not None:
                system_by_suffix[suf] = f
                continue
            suf = suffix_after(USER_PREFIX, f.name)
            if suf is not None:
                user_by_suffix[suf] = f

        response_by_suffix = {}
        matched_response_files = set()
        if response_category_dir.is_dir():
            for f in response_category_dir.iterdir():
                if not f.is_file():
                    continue
                suf = suffix_after(RESPONSE_PREFIX, f.name)
                if suf is not None:
                    response_by_suffix[suf] = f

        all_suffixes = sorted(set(system_by_suffix) | set(user_by_suffix))
        for suf in all_suffixes:
            system_file = system_by_suffix.get(suf)
            user_file = user_by_suffix.get(suf)
            response_file = response_by_suffix.get(suf)

            system_tokens = count_tokens(read_text(system_file)) if system_file else 0
            user_tokens = count_tokens(read_text(user_file)) if user_file else 0
            output_tokens = count_tokens(read_text(response_file)) if response_file else 0

            if response_file is not None:
                matched_response_files.add(response_file.name)

            rows.append({
                "category": category,
                "request_id": suf.rsplit(".txt", 1)[0],
                "system_prompt_tokens": system_tokens,
                "user_prompt_tokens": user_tokens,
                "input_tokens": system_tokens + user_tokens,
                "output_tokens": output_tokens,
                "missing_system_prompt": system_file is None,
                "missing_user_prompt": user_file is None,
                "missing_ai_response": response_file is None,
            })

        # Response files with no matching prompt pair (e.g. fallback responses).
        if response_category_dir.is_dir():
            for f in response_category_dir.iterdir():
                if f.is_file() and f.name not in matched_response_files:
                    unmatched.append({
                        "category": category,
                        "file": f.name,
                        "output_tokens": count_tokens(read_text(f)),
                    })

    return rows, unmatched


def print_report(rows, unmatched):
    header = f"{'category':<35}{'request_id':<28}{'input_tokens':>13}{'output_tokens':>14}"
    print(header)
    print("-" * len(header))

    totals_by_category = {}
    grand_input = grand_output = 0

    for row in rows:
        flags = []
        if row["missing_system_prompt"]:
            flags.append("no-system-prompt")
        if row["missing_user_prompt"]:
            flags.append("no-user-prompt")
        if row["missing_ai_response"]:
            flags.append("no-ai-response")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""

        print(f"{row['category']:<35}{row['request_id']:<28}"
              f"{row['input_tokens']:>13}{row['output_tokens']:>14}{flag_str}")

        cat_totals = totals_by_category.setdefault(row["category"], [0, 0])
        cat_totals[0] += row["input_tokens"]
        cat_totals[1] += row["output_tokens"]
        grand_input += row["input_tokens"]
        grand_output += row["output_tokens"]

    if unmatched:
        print("\nResponse files with no matching prompt pair:")
        for u in unmatched:
            print(f"  {u['category']:<35}{u['file']:<40}{u['output_tokens']:>10} output tokens")
            grand_output += u["output_tokens"]

    print("\nTotals by category")
    print("-" * len(header))
    for category, (inp, out) in sorted(totals_by_category.items()):
        print(f"{category:<35}{'':<28}{inp:>13}{out:>14}")

    print("-" * len(header))
    print(f"{'GRAND TOTAL':<35}{'':<28}{grand_input:>13}{grand_output:>14}")


def write_csv(rows, unmatched, csv_path: Path):
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category", "request_id", "system_prompt_tokens", "user_prompt_tokens",
            "input_tokens", "output_tokens", "missing_system_prompt",
            "missing_user_prompt", "missing_ai_response",
        ])
        for row in rows:
            writer.writerow([
                row["category"], row["request_id"], row["system_prompt_tokens"],
                row["user_prompt_tokens"], row["input_tokens"], row["output_tokens"],
                row["missing_system_prompt"], row["missing_user_prompt"],
                row["missing_ai_response"],
            ])
        for u in unmatched:
            writer.writerow([u["category"], u["file"], "", "", "", u["output_tokens"], "", "", "unmatched_response"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_dir", type=Path, help="Path to the debug_outputs_<id> folder")
    parser.add_argument("--csv", type=Path, default=None, help="Optional path to write a CSV report")
    args = parser.parse_args()

    rows, unmatched = collect_rows(args.base_dir)
    print_report(rows, unmatched)

    if args.csv:
        write_csv(rows, unmatched, args.csv)
        print(f"\nCSV written to {args.csv}")


if __name__ == "__main__":
    main()

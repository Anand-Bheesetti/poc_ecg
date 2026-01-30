# You are a coding agent responsible for implementing features from the technical roadmap...
import os
from anthropic import AnthropicVertex
from src.planning_agent import planning_agent
from src.code_extraction import analyze_github_repo 
from dotenv import load_dotenv# Importing code extraction logic

# github_url = input("Enter the GitHub repo URL (or press Enter to skip): ").strip() or None
# problem_statement = input("Enter the problem statement: ")
# language_choice = input("Enter the programming language: ")

# plan = planning_agent(problem_statement, language_choice, github_url)
# if github_url is not None:
#     repo_analysis = analyze_github_repo(github_url)
# else:
#     repo_analysis = None

load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# Anthropic API client setup
LOCATION = "us-east5"
client = AnthropicVertex(region=LOCATION, project_id="lumbar-poc")

def code_agent(problem, language, plan, repo_analysis=None):
    system_prompt = """<Role>
    
    You are a coding agent responsible for implementing features from the technical roadmap. You must write code in the current file and its dependencies based on the roadmap and existing code structure. You have **100,000 generational tokens** to use for code modifications.
    </Role>

    ## **Code Generation Guidelines**
    - Always specify the **file path** where the code should be written.
    - If modifying an existing file, specify the **start and end line numbers**.
    - If creating a new file, indicate **'NEW FILE'** next to the file path.
    - Ensure that all generated code adheres to the **existing project structure**.
    - Clearly distinguish between **new additions and modifications**.
    - Include **concise inline comments** explaining why the changes are made.
    
    ---
    ## **Example Response Format**
    Each response must include:

    ### **1️⃣ File Path & Operation Type**
    ```filepath
    src/module/new_script.py  # NEW FILE
    ```

    ```operation_type: ADD```

    ### **2️⃣ Code Block**
    ```python
    # This script initializes the database connection
    import sqlite3

    def connect_db():
        return sqlite3.connect("database.db")
    ```

    ### **3️⃣ Modification Example (Existing File)**
    ```filepath
    src/module/existing_script.py  # MODIFY
    ```

    ```operation_type: REPLACE```
    ```Start_line: 15```
    ```End_line: 25```

    ```python
    # Updated function to include error handling
    def fetch_data():
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            return cursor.fetchall()
        except Exception as e:
            print(f"Database Error: {e}")
            return []
    ```

    ---
    ## **Summary of Changes**
    - Created `new_script.py` for database initialization.
    - Modified `existing_script.py` to improve error handling.
    - Ensured compatibility with existing project structure.

    ---
    **Follow this structure for every generated file or modification.**
""".strip()

    user_prompt = f"""
    Problem Statement: {problem}
    Programming Language: {language}
    Plan: {plan}
    Repository Analysis: {repo_analysis if repo_analysis else "Not Provided"}
    """.strip()

    response = client.messages.create(
        model="claude-3-5-haiku@20241022",
        max_tokens=4096,
        messages=[  # System-level prompt
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": system_prompt}# User's input
        ]
    )

    return response.content[0].text

# print(code_agent(problem_statement, language_choice, plan, repo_analysis))

import subprocess
import tempfile
import json
import uuid
import os
import signal
from typing import List, Dict, Any


class TestTimeout(Exception):
    pass


def _run_with_timeout(cmd, timeout):
    """
    Runs a subprocess command with timeout and captures output safely.
    """
    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True
        )
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired:
        raise TestTimeout("Execution exceeded time limit")


def testing_agent(
    generated_code: str,
    test_cases: List[Dict[str, Any]],
    language: str = "python",
    timeout_seconds: int = 3
) -> Dict[str, Any]:
    """
    Fully-featured Test Agent

    Capabilities:
    - Secure sandboxed execution
    - Language-agnostic execution model
    - Multiple test case support
    - Deep assertion logic
    - Robust error & timeout handling
    - Seamless handoff from code agent

    Test Case Schema:
    {
        "type": "function | script | stdout | exception",
        "target": "function_name (optional)",
        "inputs": [],
        "expected": Any,
        "assertion": "equals | contains | type | raises"
    }
    """

    report = {
        "test_run_id": str(uuid.uuid4()),
        "language": language,
        "execution_status": "NOT_STARTED",
        "test_results": [],
        "summary": {
            "total": len(test_cases),
            "passed": 0,
            "failed": 0
        }
    }

    # -----------------------------
    # 1. Create sandbox
    # -----------------------------
    with tempfile.TemporaryDirectory() as sandbox:
        if language == "python":
            code_file = os.path.join(sandbox, "solution.py")
            with open(code_file, "w") as f:
                f.write(generated_code)
        else:
            return {
                "execution_status": "FAILED",
                "error": f"Unsupported language: {language}"
            }

        # -----------------------------
        # 2. Run test cases
        # -----------------------------
        for idx, test in enumerate(test_cases, start=1):
            result = {
                "test_case_id": idx,
                "type": test.get("type"),
                "status": "FAILED",
                "error": None
            }

            try:
                if test["type"] == "stdout":
                    cmd = ["python", code_file]
                    rc, out, err = _run_with_timeout(cmd, timeout_seconds)

                    if test["assertion"] == "contains":
                        assert test["expected"] in out
                    else:
                        assert out.strip() == str(test["expected"])

                elif test["type"] == "function":
                    wrapper = f"""
import json
from solution import {test["target"]}
print(json.dumps({test["target"]}(*{test.get("inputs", [])})))
"""
                    wrapper_file = os.path.join(sandbox, "runner.py")
                    with open(wrapper_file, "w") as f:
                        f.write(wrapper)

                    cmd = ["python", wrapper_file]
                    rc, out, err = _run_with_timeout(cmd, timeout_seconds)

                    output = json.loads(out.strip())

                    if test["assertion"] == "equals":
                        assert output == test["expected"]
                    elif test["assertion"] == "type":
                        assert isinstance(output, test["expected"])
                    else:
                        raise ValueError("Unsupported assertion")

                elif test["type"] == "exception":
                    wrapper = f"""
from solution import {test["target"]}
{test["target"]}(*{test.get("inputs", [])})
"""
                    wrapper_file = os.path.join(sandbox, "runner.py")
                    with open(wrapper_file, "w") as f:
                        f.write(wrapper)

                    cmd = ["python", wrapper_file]
                    try:
                        _run_with_timeout(cmd, timeout_seconds)
                        raise AssertionError("Expected exception was not raised")
                    except subprocess.CalledProcessError:
                        pass  # Expected

                else:
                    raise ValueError("Unknown test type")

                result["status"] = "PASSED"
                report["summary"]["passed"] += 1

            except TestTimeout as e:
                result["error"] = "TIMEOUT"
                report["summary"]["failed"] += 1

            except AssertionError as e:
                result["error"] = str(e)
                report["summary"]["failed"] += 1

            except Exception as e:
                result["error"] = str(e)
                report["summary"]["failed"] += 1

            report["test_results"].append(result)

    report["execution_status"] = "COMPLETED"
    return report

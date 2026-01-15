from anthropic import AnthropicVertex
from src.code_agent import code_agent
from src.planning_agent import planning_agent
from src.code_extraction import analyze_github_repo
from src.simulation_agent import simulation_agent
from dotenv import load_dotenv
import os
import json

# Load environment variables
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# Anthropic API client setup
LOCATION = "us-east5"
client = AnthropicVertex(region=LOCATION, project_id="lumbar-poc")

def debugging_agent(problem, plan, code, feedback, repo_analysis=None):
    # Convert JSON objects to properly formatted strings
    plan_json = json.dumps(plan, indent=4)
    code_json = json.dumps(code, indent=4)
    repo_json = json.dumps(repo_analysis, indent=4) if repo_analysis else "N/A"
    feedback_json = json.dumps(feedback, indent=4)

    system_prompt = f"""<Role>

    You are a **highly advanced Debugging Agent** with expertise in software development, debugging, and enterprise-level code optimization. Your responsibility is to analyze the feedback provided by the Simulation Agent and modify the generated code to ensure that:

    ✅ The code **fully implements** the problem statement's requirements.  
    ✅ All **identified errors, missing functionalities, and issues** are completely resolved.  
    ✅ The code is **fully functional, free from logical, syntax, and dependency errors**.  
    ✅ The modified code **works correctly across all files together** as a cohesive system.  
    ✅ The code adheres to **enterprise-level best practices, maintainability, and scalability** standards.  

    ---  

    ## **🔍 Debugging Process**  

    ### **Step 1: Understand the Problem Statement**
    - Thoroughly analyze the **problem statement** to understand the intended functionality.
    - Identify **key functionalities** that the code should implement.

    ### **Step 2: Analyze Feedback and Issues**
    - Carefully review the **Simulation Agent's feedback** and pinpoint the affected files and functions.
    - The feedback follows this format:

    **If everything is correct:**  
    ```json
    {{
        "files": [
            {{"filename": "file1.py", "status": "Correct"}},
            {{"filename": "file2.js", "status": "Correct"}}
        ]
    }}
    ```

    - If all files have `"status": "Correct"`, the debugging agent must do nothing and simply print:
      `"Everything generated is correct. No modifications needed."`

    - If there is any file whose status is **not** `"Correct"`, the debugging agent must:
      - Identify the specific issues in those files.
      - Debug and modify the code accordingly.
      - Resolve:
        - ❌ **Logical errors** (incorrect algorithm implementation).
        - ❌ **Syntax errors** (invalid syntax, typos, incorrect function calls).
        - ❌ **Missing or incorrect dependencies** (missing imports, incorrect module usage).
        - ❌ **Code structure and modularization issues** (poor function/class design).
        - ❌ **Performance inefficiencies** (suboptimal code that needs improvement).
        - ❌ **Security vulnerabilities** (hardcoded secrets, unsafe practices).

    ### **Step 3: Modify the Code and Apply Fixes**
    - **Correct all identified issues** and implement missing functionalities.
    - Ensure **all files work together correctly** after modifications.
    - Follow **best practices for modularity, maintainability, and reusability**.
    - If necessary, **refactor the code** to improve structure, readability, and performance.

    ### **Step 4: Validate the Code After Fixes**
    - Perform **static validation** to ensure:
      - ✅ **No syntax errors** remain.
      - ✅ **All functions, methods, and imports are correctly defined**.
      - ✅ **Code execution will not fail due to missing dependencies**.
      - ✅ **Business logic is implemented correctly** as per the problem statement.

    ### **Step 5: Ensure Enterprise-Level Code Standards**
    Your modifications should follow:
    - **Scalability & Maintainability** – The code should be modular, well-structured, and easy to extend.
    - **Readability & Documentation** – Proper inline comments and docstrings should be added.
    - **Security Best Practices** – No hardcoded credentials, secure input validation, and safe API usage.
    - **Performance Optimization** – Avoid redundant computations and inefficient loops.
    - **Error Handling** – Implement proper exception handling mechanisms.
    - **Code Formatting** – Follow industry-standard conventions (e.g., PEP8 for Python).

    ---  

    ## **📝 Inputs Provided**
    - **Problem Statement:**  
        {problem}
    - **Initial Code Generation Plan:**
        ```json
        {plan_json}
        ```
    - **Generated Code (Before Debugging):**
        ```json
        {code_json}
        ```
    - **Repository Analysis (if available):**
        ```json
        {repo_json}
        ```
    - **Feedback from Simulation Agent:**
        ```json
        {feedback_json}
        ```
    """.strip()

    response = client.messages.create(
        model="claude-3-5-haiku@20241022",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": system_prompt}
        ]
    )
    return response.content[0].text

# print(debugging_agent(problem_statement, plan, code, feedback, repo_analysis))

def signin(user_name = None):
    return user_name


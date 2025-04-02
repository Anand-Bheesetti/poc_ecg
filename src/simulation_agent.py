from anthropic import AnthropicVertex
import os
from dotenv import load_dotenv
import json
from src.code_agent import code_agent
from src.planning_agent import planning_agent
from src.code_extraction import analyze_github_repo

load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# Anthropic API client setup
LOCATION = "us-east5"
client = AnthropicVertex(region=LOCATION, project_id="lumbar-poc")

# github_url = input("Enter the GitHub repo URL (or press Enter to skip): ").strip() or None
# problem_statement = input("Enter the problem statement: ")
# language_choice = input("Enter the programming language: ")

# Generate Plan & Repository Analysis
# plan = planning_agent(problem_statement, language_choice, github_url)
# repo_analysis = analyze_github_repo(github_url) if github_url else None

# code=code_agent(problem_statement, language_choice, plan, repo_analysis)
# extracted_code=process_agent_output(code)



import json

def simulation_agent(problem, language, extracted_code):
    system_prompt = f"""<Role>

    You are a **simulation agent** responsible for validating whether the generated code correctly solves a given problem statement. You do not execute the code directly but instead **simulate its behavior** through static analysis, dependency verification, and logical validation.

    Your primary objectives:
    1. **Analyze the Problem Statement**: Understand the problem the code is supposed to solve.
    2. **Verify Code Functionality**: Ensure each generated file correctly implements the required logic.
    3. **Check Dependencies**: Validate interdependencies between files, function calls, and module imports.
    4. **Generate and Validate Test Cases**: If applicable, create meaningful test cases for basic input-output validation.
    5. **Simulate Code Execution**: Perform a dry-run of the code logic and compare expected vs. simulated output.
    6. **Provide Feedback**: Identify missing functionalities, incorrect implementations, and suggest necessary changes.

    </Role>

    ---

    ## **Simulation Process**

    ### **📝 1. Read Inputs**
    - **Problem Statement:**  
    {problem}
    - **Generated Code (Multiple Files):**  
    ```json
    {json.dumps(extracted_code, indent=4)}
    ```

    ### **🔍 2. Static Code Analysis**
    - Extract all functions, classes, and expected behavior.
    - Identify missing logic, syntax errors, and improper function definitions.
    - Ensure each file contributes meaningfully to solving the problem.

    ### **🔗 3. Dependency Validation**
    - Check that all **imports and function calls** are properly defined.
    - Detect **missing functions, undefined references, or circular dependencies**.

    ### **🧪 4. Test Case Generation (If Applicable)**
    - If the problem is computational (e.g., "Check if a number is prime"), generate test cases.
    - Example:
    - **Problem Statement:** "Check if a number is prime."
    - **Generated Test Cases:**
      ```json
      {{
        "inputs": [2, 3, 4, 5, 16, 17],
        "expected_outputs": [true, true, false, true, false, true]
      }}
      ```
    - Create **edge cases** (e.g., large numbers, negative values, zero, etc.).

    ### **🛠 5. Dry-Run Code Simulation**
    - Identify the **main function or entry point** in the generated code.
    - Simulate how **input data flows** through different files.
    - Predict **expected output** based on logical evaluation.
    - Compare simulated vs. expected results.

    ### **❌ 6. Identify Issues & Provide Actionable Feedback**
    - If the solution **is correct**, confirm the implementation.
      If the solution **is correct**, return the list of all file names with a `"status": "Correct"` message.
    - If **errors are found**:
      - Specify **which file** has issues.
      - Describe **what functionality is missing or incorrect**.
      - Suggest **specific fixes** to correct the errors.

    ## **Output Format**
    **If everything is correct:**
    ```json
    {{
      "files": [
        {{"filename": "file1.py", "status": "Correct"}},
        {{"filename": "file2.js", "status": "Correct"}}
      ]
    }}
    ```

    **If errors are found:**
    ```json
    [
      {{
        "filename": "src/module/example.py",
        "status": "Needs Review",
        "functions": ["function_name_1", "function_name_2"],
        "classes": ["ClassName"],
        "dependencies": {{
          "missing_imports": ["module_name"],
          "undefined_references": ["function_name"],
          "circular_dependencies": ["file1.py -> file2.py -> file1.py"]
        }},
        "issues": ["Description of issues found"],
        "suggestions": ["Possible improvements"]
      }}
    ]
    ```
    """.strip()

    response = client.messages.create(
        model="claude-3-5-haiku@20241022",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": system_prompt}
            
        ]
    )
    if not response.content:
        return "⚠️ No response received from the API. Check API call format and authentication."

    return response.content[0].text



# print(simulation_agent(problem_statement,language_choice,code))


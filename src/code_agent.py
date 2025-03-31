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

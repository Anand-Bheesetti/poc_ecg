import os
from anthropic import AnthropicVertex
from dotenv import load_dotenv
from src.code_extraction import analyze_github_repo  # Importing code extraction logic

# Load environment variables
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# Anthropic API client setup
LOCATION = "us-east5"
client = AnthropicVertex(region=LOCATION, project_id="lumbar-poc")


def planning_agent(problem, language, github_url=None):
    """
    Generates a detailed plan based on the problem statement.
    - If a GitHub repository URL is provided, it extracts and analyzes the existing code.
    - If no GitHub URL is given, it generates a plan from scratch.

    Args:
        problem (str): The problem statement.
        language (str): The programming language.
        github_url (str, optional): The GitHub repository URL (if an existing codebase is provided).

    Returns:
        str: The generated planning details.
    """
    
    if github_url:
        print("📥 Extracting and analyzing the existing GitHub repository...")
        repo_analysis = analyze_github_repo(github_url)  # Extract and analyze the repo
        
        # Generate plan based on extracted analysis
        system_prompt = f"""<role>
You are a highly intelligent AI assistant responsible for analyzing and modifying an existing codebase. Your objective is to identify relevant files, determine necessary changes, and generate a structured hierarchical plan for efficient code modification.
</role>
<task>
Analyze the given feature request, dependency mapping, and relevant files/entities. Generate a structured, top-down hierarchical task breakdown that details the precise steps required for code implementation. Ensure dependencies are correctly managed by organizing tasks in a logical sequence while maintaining a modular, reusable, and testable approach.
</task>
<problem_statement>
{problem}
</problem_statement>
<existing_codebase_analysis>
Below is the analysis of the existing repository. Identify the relevant files that require modification:
{repo_analysis}
</existing_codebase_analysis>
<instructions>
1. Feature Breakdown: Extract high-level tasks required to implement the feature.
2. Code-Centric Hierarchical Decomposition: Break each task into smaller sub-tasks down to an atomic, implementable unit.
3. Dependency Mapping: Organize tasks in a logical sequence ensuring:
   - If a task depends on another task, it must appear after the required dependency.
   - Identify impacts on existing files and adjust execution order accordingly.
4. Implementation-Level Sub-Tasks: Define concrete, code-level sub-tasks including:
   - Data Structures & Models – Define necessary schemas or models.
   - Data Exchange & Transformation – Implement serialization and transformation mechanisms.
   - Core Logic & Processing – Develop business logic, workflows, and algorithms.
   - Interface & Integration Points – Implement APIs, services, and event-driven handlers.
   - Validation & Error Handling – Implement validation mechanisms, logging, and error handling.
   - Testing & Verification – Ensure correctness through unit and integration tests.
5. Strict Modularity & Isolation: Tasks should be independent where possible, enabling isolated development and testing.
6. Explicit Descriptions: Each task and sub-task must include:
   - Title (concise and descriptive).
   - Description (purpose, expected outcome, and a high-level explanation of code changes).
   - Dependencies (files, database entities, or code components it relies on).
   - Code (function/class skeletons with appropriate structure but no actual implementation).
7. Output Format: Provide the plan as a JSON adjacency list, structured as follows:
   - "nodes": List of tasks with id, title, description, dependencies, and code.
   - "adjacency_list": A 2D array mapping parent-child relationships.
   - "dependencies": Explicit mapping of file/entity dependencies.
8. Strict Execution Order: The hierarchy should follow a top-to-bottom execution order:
   - The root node represents the main feature.
   - High-level tasks branch from the root.
   - Sub-tasks connect to immediate parent tasks.
   - Dependencies dictate execution sequencing.
9. No Assumptions: Do not introduce external assumptions beyond the provided project details and dependencies.
</instructions>
<expected_output>
1. Identify which files need to be modified.
2. Describe what changes should be made to those files.
3. Explain the most efficient way to implement these changes.
4. Provide a high-level step-by-step plan for modifications.
5. Specify any new dependencies and explicitly include a task for updating `requirements.txt`.
</expected_output>
Strict Instructions:
- Do not generate actual code.
- Focus only on analysis and structured planning.
</system_prompt>
"""

    else:
        print("📝 No GitHub repository provided. Creating a plan from scratch...")
        
        system_prompt=f"""You are a programmer tasked with generating appropriate plan to solve a given problem
using the {language} programming language.
## Problem
{problem}
**Expected Output:**
Your response must be structured as follows:
### Problem Understanding
- Think about the original problem. Develop an initial
 understanding about the problem.
 ### Recall Example Problem
Recall a relevant and distinct problems (different from problem
mentioned above) and
- Describe it
- Generate {language} code step by step to solve that problem
- Discuss the algorithm to solve this problem
- Finally generate a planning to solve that problem.
### Algorithm to solve the original problem
- Write down the algorithm that is well suited for the original
 problem
- Give some tutorials to about the algorithm for example:
 - How to approach this type of algorithm
 - Important things to consider.
 ### Plan
- Write down a detailed, step-by-step plan to solve the
 **original problem**.
 **Important Instruction:**
- Strictly follow the instructions.
- Do not generate code.

"""

    # Call Anthropic Claude to generate the plan
    response = client.messages.create(
        model="claude-3-5-haiku@20241022",
        max_tokens=2000,
        messages=[{"role": "user", "content": system_prompt}]
    )

    return response.content[0].text



# github_url = input("Enter the GitHub repo URL (or press Enter to skip): ").strip() or None
# problem_statement = input("Enter the problem statement: ")
# language_choice = input("Enter the programming language: ")

# plan = planning_agent(problem_statement, language_choice, github_url)
# print("\n📝 Generated Plan:\n", plan)

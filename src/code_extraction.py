import os
import tempfile
import git
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_c_sharp as tscsharp

# Load the Python and C# language modules for Tree-sitter
PY_LANGUAGE = Language(tspython.language())
CS_LANGUAGE = Language(tscsharp.language())

def extract_code_from_repo(repo_url):
    # Create a temporary directory to clone the repository
    temp_dir = tempfile.mkdtemp()

    try:
        # Clone the repository
        repo = git.Repo.clone_from(repo_url, temp_dir)

        # Dictionary to store file contents
        code_files = {}

        # Walk through the repository files
        for root, _, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)

                # Read the file content
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        code_files[file_path.replace(temp_dir, '')] = f.read()
                except Exception as e:
                    print(f"Skipping {file}: {e}")

        return code_files

    finally:
        # Cleanup: remove the cloned repo
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

def analyze_code_from_string(code: str, language: str):
    if language == "python":
        parser = Parser(PY_LANGUAGE)
    elif language == "csharp":
        parser = Parser(CS_LANGUAGE)
    else:
        return {}

    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    imports = []
    functions = []
    classes = []
    variables = []

    def traverse(node):
        if node.type in ["import_statement", "import_from_statement", "using_directive"]:
            imports.append(code[node.start_byte:node.end_byte].strip())
        elif node.type in ["function_definition", "method_declaration"]:
            name_node = node.child_by_field_name('name')
            params_node = node.child_by_field_name('parameters')

            if name_node:
                func_name = code[name_node.start_byte:name_node.end_byte].strip()
                parameters = []

                # Extract parameters if available
                if params_node:
                    for param in params_node.children:
                        if param.type == "identifier" or param.type == "parameter":
                            parameters.append(code[param.start_byte:param.end_byte].strip())

                functions.append({
                    "name": func_name,
                    "parameters": parameters
                })
        elif node.type in ["class_definition", "class_declaration"]:
            name_node = node.child_by_field_name('name')
            if name_node:
                classes.append(code[name_node.start_byte:name_node.end_byte].strip())
        # elif node.type in ["assignment", "augmented_assignment", "variable_declaration"]:
        #     variables.append(code[node.start_byte:node.end_byte].strip())
        elif node.type in ["assignment", "augmented_assignment", "variable_declaration"]:
    # Extract variable names from children nodes
            for child in node.children:
                if child.type == "identifier":  # Ensures only variable names are captured
                    variables.append(code[child.start_byte:child.end_byte].strip())



        for child in node.children:
            traverse(child)

    traverse(root_node)

    return {
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "variables": variables
    }

def analyze_github_repo(repo_url):
    code_data = extract_code_from_repo(repo_url)
    analysis_results = {}

    for file, code in code_data.items():
        if file.endswith(".py"):
            analysis_results[file] = analyze_code_from_string(code, "python")
        elif file.endswith(".cs"):
            analysis_results[file] = analyze_code_from_string(code, "csharp")

    return analysis_results

# Input and Execution
# repo_url = input("Enter the GitHub repo URL: ")  # Replace with the actual repo URL
# analysis = analyze_github_repo(repo_url)

# # Print the results
# for file, result in analysis.items():
#     print(f"File: {file}\nAnalysis: {result}\n")

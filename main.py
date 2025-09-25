from flask import Flask,request,jsonify
from src.planning_agent import planning_agent
from src.code_extraction import analyze_github_repo
from src.code_agent import code_agent
from src.simulation_agent import simulation_agent
from src.debugging_agent import debugging_agent

app=Flask(__name__)


# Application secret key
SECRET_KEY = os.getenv("APP_SECRET_KEY", "default_secret")

# Database URL for connecting
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")

# Timeout for DB connections
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "30"))

# Debug mode flag
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
@app.route("/")
def home():
    return "The ECG POC is running fine>>>"

@app.route("/generate",methods=["GET","POST"])
def generate():
    data=request.get_json()
    problem = data.get("problem")
    language = data.get("language")
    github_url = data.get("github_url", "")

    if not problem or not language:
        return jsonify({"error": "Missing required fields: 'problem' and 'language'"}), 400

    

    # Analyze GitHub repo (if provided)
    repo_analysis = analyze_github_repo(github_url) if github_url else None

    # Step 1: Generate a Plan
    
    plan = planning_agent(problem, language, github_url)

    # Step 2: Generate Code
    
    code = code_agent(problem, language, plan, repo_analysis)

    # Step 3: Run Simulation to Test Code
    
    feedback = simulation_agent(problem, language, code)

    # Step 4: Debugging based on Feedback
    
    debugging_results = debugging_agent(problem, plan, code, feedback, repo_analysis)

    # Return the response
    return jsonify({
        "plan": plan,
        "generated_code": code,
        "simulation_results": feedback,
        "debugging_results": debugging_results
    }), 200

import os
import sys

# New environment variables used
API_KEY = os.getenv("NEW_API_KEY")   # Should be checked for missing value
DB_URL = os.getenv("NEW_DATABASE_URL")  # Another new env var

def fun1(a,b):   # Violation: bad function name + single-char params
    c=a+b  # Violation: missing spaces around operators
    if c>10:print("greater") # Violation: inline statement, no proper formatting
    return c

def check_api():
    if API_KEY == None:   # Violation: should use "is None"
        print("No API Key provided!")  
    else:
        print("API Key length is", len(API_KEY))

class myclass:  # Violation: class name not in PascalCase
    def __init__(self,x):
        self.x=x  # Violation: no spaces around assignment
    def prnt(self):print(self.x)  # Violation: bad method name, inline print

# Logic violation: using == for assignment inside loop (typo bug)
for i in range(5):
    val==i*2   # Violation: accidental comparison instead of assignment

check_api()
obj=myclass(42)
obj.prnt()




if __name__=="__main__":

    app.run(debug=True)


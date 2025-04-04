from flask import Flask,request,jsonify
from src.planning_agent import planning_agent
from src.code_extraction import analyze_github_repo
from src.code_agent import code_agent
from src.simulation_agent import simulation_agent
from src.debugging_agent import debugging_agent

app=Flask(__name__)



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



if __name__=="__main__":
    app.run(debug=True)
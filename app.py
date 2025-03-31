
import streamlit as st
from src.planning_agent import planning_agent
from src.code_agent import code_agent
from src.code_extraction import analyze_github_repo

st.title("POC For ECG")

# User Inputs
problem = st.text_input("Enter the problem statement")
language = st.selectbox("Select the language", ["Python", "C#"])
github_url = st.text_input("Enter the GitHub repo URL (or press Enter to skip)")

repo_analysis = None

# Generate Plan
if st.button("Generate Plan"):
    if not problem:
        st.error("Please enter a problem statement.")
    else:
        with st.spinner("Generating Plan..."):
            plan = planning_agent(problem, language, github_url)
        st.write("### Generated Plan:")
        st.code(plan, language="markdown")

# Generate Code
if st.button("Generate Code"):
    if not problem:
        st.error("Please enter a problem statement.")
    else:
        with st.spinner("Analyzing GitHub Repository..."):
            repo_analysis = analyze_github_repo(github_url) if github_url else None

        with st.spinner("Generating Code..."):
            plan = planning_agent(problem, language, github_url)  # Reuse generated plan
            code = code_agent(problem, language, plan, repo_analysis)

        st.write("### Generated Code:")
        st.text_area("Generated Code", code, height=1000) # Auto-highlight syntax

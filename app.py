

import streamlit as st
from src.planning_agent import planning_agent
from src.code_extraction import analyze_github_repo
from src.code_agent import code_agent
from src.simulation_agent import simulation_agent
from src.debugging_agent import debugging_agent
import json
import os
from dotenv import load_dotenv

st.title("POC For ECG")
problem=st.text_input("Enter the problem statement")
language=st.selectbox("Select the language", ["Python", "C#"])
github_url=st.text_input("Enter the GitHub repo URL (or press Enter to skip)")
repo_analysis=None
if st.button("Generate"):

    repo_analysis = analyze_github_repo(github_url) if github_url else None
    st.header("Plan")
    with st.spinner("Generating Plan...."):
        plan=planning_agent(problem,language,github_url)
        st.text_area("generated plan",plan,height=5000)
        
    st.header("code")
    with st.spinner("Generating code...."):
        code=code_agent(problem,language,plan,repo_analysis)
        st.text_area("Generated code",code,height=5000)
        
    st.header("simulation")
    with st.spinner("Testing the code generated through simulation...."):
        feedback=simulation_agent(problem,language,code)
        st.text_area("test simulation results",feedback,height=5000)
        
    st.header("Debugging")
    with st.spinner("Debugging...."):
        debugging_results=debugging_agent(problem,plan,code,feedback,repo_analysis)
        st.text_area("debugging Results",debugging_results,height=5000)

    
        
    
    
        
    
    



    




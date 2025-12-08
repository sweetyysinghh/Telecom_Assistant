import streamlit as st
import sys
import os

# Add the project root to sys.path to allow absolute imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from telecom_assistant.ui.streamlit_app import render_login, render_admin_dashboard, render_customer_dashboard

# Page Config
st.set_page_config(
    page_title="Telecom Assistant",
    page_icon="📡",
    layout="wide"
)

def main():
    # Initialize Session State
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    
    if "role" not in st.session_state:
        st.session_state["role"] = None

    # Navigation Logic
    if not st.session_state["logged_in"]:
        render_login()
    else:
        if st.session_state["role"] == "admin":
            render_admin_dashboard()
        elif st.session_state["role"] == "customer":
            render_customer_dashboard()

if __name__ == "__main__":
    main()

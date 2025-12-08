import streamlit as st
import os
import sqlite3
import sys

# Add project root to sys.path so we can import from telecom_assistant
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

from telecom_assistant.config.config import Config
from telecom_assistant.utils.document_loader import load_documents
from telecom_assistant.orchestration.graph import run_orchestrator

# ================== AUTH CONFIG ==================

# Common password for ALL users
SHARED_PASSWORD = "user"


def _inject_styles():
    """Inject custom CSS for improved visuals."""
    st.markdown(
        """
        <style>
        /* Page background and container */
        .stApp {
            background: linear-gradient(180deg, #f6fbff 0%, #ffffff 60%);
            color: #0f172a;
            font-family: 'Segoe UI', Roboto, Arial, sans-serif;
        }
        /* Card-like boxes */
        .card {
            background: #ffffff;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 4px 20px rgba(16,24,40,0.06);
        }
        .brand {
            color: #0ea5e9;
            font-weight: 700;
        }
        .muted {
            color: #64748b;
            font-size: 0.95em;
        }
        .doc-list {
            list-style: none;
            padding-left: 0;
        }
        .doc-item {
            padding: 8px 0;
            border-bottom: 1px solid #eef2ff;
        }
        .feature {
            text-align: center;
            padding: 12px;
        }
        .feature .emoji {
            font-size: 26px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_user_by_customer_id(customer_id: str):
    """
    Look up a user by customer_id in the database.

    Expects a `customers` table with column: customer_id.
    Returns:
      - dict: {"customer_id": ..., "role": ...} if found
      - None if not found or on error.
    """
    db_path = getattr(Config, "DB_PATH", "data/telecom.db")

    if not os.path.exists(db_path):
        st.error(f"Database not found at: {db_path}. Please create the 'customers' table.")
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # ✅ Only check for existence of customer_id now
        cursor.execute("SELECT customer_id FROM customers WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
    except sqlite3.OperationalError as e:
        st.error(f"Database error while looking up customer: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if row:
        # ✅ Infer role directly based on customer_id
        role = "admin" if customer_id.lower() == "admin" else "customer"
        return {"customer_id": row[0], "role": role}

    return None


# ================== UI RENDER FUNCTIONS ==================


def render_login():
    """Renders the login page with an attractive layout."""
    _inject_styles()

    # Header
    header_col1, header_col2 = st.columns([2, 3])
    with header_col1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='brand'>📡 Telecom Assistant</div>", unsafe_allow_html=True)
        st.markdown("<div class='muted'>AI-powered support for Billing, Network & Service Plans</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with header_col2:
        st.image(os.path.join(os.path.dirname(__file__), "../data/logo.png"), width=120) if os.path.exists(os.path.join(os.path.dirname(__file__), "../data/logo.png")) else st.write("")

    st.markdown("---")

    # Main layout: left - benefits, right - login form
    left, right = st.columns([2, 1])

    with left:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Why use Telecom Assistant?")
        st.markdown("""
        - Fast resolution for billing queries
        - Instant network troubleshooting guides
        - Personalized service plan recommendations
        """)

        feats = st.columns(3)
        with feats[0]:
            st.markdown("<div class='feature'><div class='emoji'>⚡</div><b>Fast</b><div class='muted'>Get answers instantly</div></div>", unsafe_allow_html=True)
        with feats[1]:
            st.markdown("<div class='feature'><div class='emoji'>🔒</div><b>Secure</b><div class='muted'>Your data stays local</div></div>", unsafe_allow_html=True)
        with feats[2]:
            st.markdown("<div class='feature'><div class='emoji'>🤝</div><b>Human-like</b><div class='muted'>Helpful conversation flow</div></div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Sign in")

        # Use immediate inputs + button to avoid double-click behavior
        customer_id = st.text_input("Customer ID", placeholder="e.g. CUST001", key="login_customer_id")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Sign in"):
            if not customer_id or not password:
                st.error("Please enter both Customer ID and password.")
            else:
                # 1️⃣ Shared password check
                if password != SHARED_PASSWORD:
                    st.error("Invalid password.")
                else:
                    # 2️⃣ Check if Customer ID exists
                    user = get_user_by_customer_id(customer_id)
                    if user is None:
                        st.error("Customer ID not found in the database.")
                    else:
                        # 3️⃣ Set session state
                        st.session_state["logged_in"] = True
                        st.session_state["role"] = user["role"]
                        st.session_state["customer_id"] = user["customer_id"]

                        if user["role"] == "admin":
                            st.success(f"Logged in as Admin ({user['customer_id']})")
                        else:
                            st.success(f"Logged in as Customer ({user['customer_id']})")

                        # Immediately update session state and return so Streamlit re-runs
                        return

        st.markdown("</div>", unsafe_allow_html=True)


def render_admin_dashboard():
    """Renders the Admin Dashboard for document management."""
    _inject_styles()

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.header("Admin Dashboard — Knowledge Base")
    st.write("Upload technical docs to keep the assistant up to date.")

    with st.expander("Upload & Index Documents", expanded=True):
        uploaded_files = st.file_uploader(
            "Choose files", 
            accept_multiple_files=True,
            type=["pdf", "md", "txt"]
        )

        if st.button("Process Documents"):
            if uploaded_files:
                docs_dir = os.path.join(Config.DATA_DIR, "documents")
                os.makedirs(docs_dir, exist_ok=True)

                progress_bar = st.progress(0)
                status_text = st.empty()

                for i, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"Processing {uploaded_file.name}...")
                    file_path = os.path.join(docs_dir, uploaded_file.name)

                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    progress_bar.progress((i + 1) / len(uploaded_files))

                status_text.text("Updating Knowledge Base (Indexing)...")

                try:
                    load_documents()
                    st.success(f"Successfully processed {len(uploaded_files)} documents and updated the Knowledge Base!")
                except Exception as e:
                    st.error(f"Error updating knowledge base: {e}")
            else:
                st.warning("Please upload at least one file.")

    st.markdown("</div>", unsafe_allow_html=True)

    # Show current documents
    st.markdown("<div class='card' style='margin-top:16px;'>", unsafe_allow_html=True)
    st.subheader("Current Documents")
    docs_dir = os.path.join(Config.DATA_DIR, "documents")
    if os.path.exists(docs_dir):
        files = sorted(os.listdir(docs_dir))
        if files:
            for fname in files:
                path = os.path.join(docs_dir, fname)
                size = os.path.getsize(path)
                st.markdown(f"<div class='doc-item'><b>{fname}</b> <span class='muted'>— {size} bytes</span></div>", unsafe_allow_html=True)
        else:
            st.info("No documents uploaded yet.")
    else:
        st.info("No documents directory found. Upload documents to create it.")

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Logout"):
        st.session_state["logged_in"] = False
        return


def render_customer_dashboard():
    """Renders the Customer Dashboard for chat with a polished UI."""
    _inject_styles()

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.header("Telecom Customer Support")

    # Quick action cards
    qa1, qa2, qa3 = st.columns(3)
    with qa1:
        if st.button("📜 Billing" ):
            st.session_state.setdefault("messages", []).append({"role": "assistant", "content": "I can help with billing. Tell me your bill number or issue."})
    with qa2:
        if st.button("📶 Network" ):
            st.session_state.setdefault("messages", []).append({"role": "assistant", "content": "Describe your network issue and I'll run diagnostics."})
    with qa3:
        if st.button("🛎️ Plans" ):
            st.session_state.setdefault("messages", []).append({"role": "assistant", "content": "I can recommend service plans based on your usage — tell me your monthly data usage."})

    st.markdown("</div>", unsafe_allow_html=True)

    # Sidebar with customer details
    with st.sidebar:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.header("Customer Details")
        customer_id = st.text_input(
            "Customer ID", 
            value=st.session_state.get("customer_id", "CUST001")
        )
        st.session_state["customer_id"] = customer_id

        if st.button("Clear Chat History"):
            st.session_state["messages"] = []
            return

        if st.button("Logout"):
            st.session_state["logged_in"] = False
            return
        st.markdown("</div>", unsafe_allow_html=True)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
        st.session_state["messages"].append({
            "role": "assistant", 
            "content": "Hello! I'm your Telecom Assistant. How can I help you today with your billing, network, or service plans?"
        })

    # Show messages inside a styled container
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"]) 

    # Chat input
    if prompt := st.chat_input("Type your query here..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = run_orchestrator(prompt, customer_id)
                    st.markdown(response)
                    st.session_state["messages"].append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"An error occurred: {e}")


def main():
    st.set_page_config(page_title="Telecom Assistant", page_icon="📡", layout="wide")

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        render_login()
    else:
        role = st.session_state.get("role", "customer")
        if role == "admin":
            render_admin_dashboard()
        else:
            render_customer_dashboard()


if __name__ == "__main__":
    main()

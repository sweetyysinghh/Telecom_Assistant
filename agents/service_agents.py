from langgraph.prebuilt import create_react_agent
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langchain_experimental.tools import PythonREPLTool
from telecom_assistant.utils.database import get_database
from telecom_assistant.utils.document_loader import load_documents
from telecom_assistant.config.config import Config
import os
import sqlite3
from typing import Optional, Dict

# Set API Key
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

# Define a prompt template for service recommendations
SERVICE_RECOMMENDATION_TEMPLATE = """You are a telecom service advisor who helps customers find the best plan for their needs.
When recommending plans, consider:
1. The customer's usage patterns (data, voice, SMS)
2. Number of people/devices that will use the plan
3. Special requirements (international calling, streaming, etc.)
4. Budget constraints

Always explain WHY a particular plan is a good fit for their needs.
"""

def estimate_data_usage(activities: str) -> str:
    """
    Estimate monthly data usage based on activities.
    Example input: "streaming 2 hours of video daily, browsing 3 hours, video calls 1 hour weekly"
    """
    # Simple heuristic estimation
    total_gb = 0.0
    activities = activities.lower()
    
    if "streaming" in activities:
        # Assume HD streaming ~3GB/hr
        total_gb += 3.0 * 30 * 2 # Mock: 2 hours daily
    if "browsing" in activities:
        # Assume 0.1GB/hr
        total_gb += 0.1 * 30 * 3 # Mock: 3 hours daily
    if "video call" in activities:
        # Assume 1GB/hr
        total_gb += 1.0 * 4 * 1 # Mock: 1 hour weekly
        
    # If no specific keywords found, return a generic estimate or ask for more info
    if total_gb == 0:
        return "Could not estimate usage from description. Please specify hours for streaming, browsing, etc."
        
    return f"Estimated monthly data usage: {total_gb} GB"

def search_service_docs(query: str) -> str:
    """Search service plan documentation for qualitative details (benefits, terms)."""
    try:
        index = load_documents()
        if not index:
            return "Error: Document index not available."
        query_engine = index.as_query_engine()
        response = query_engine.query(query)
        return str(response)
    except Exception as e:
        return f"Error searching docs: {str(e)}"

# New helper: fetch customer and plan info from the DB
def fetch_customer_info(customer_id: str) -> Optional[Dict]:
    """Try to fetch structured customer + current plan info. Returns None if not found or on error."""
    # Prefer structured sqlite fetch for a reliable dict result
    try:
        conn = sqlite3.connect(getattr(Config, 'DATABASE_PATH', getattr(Config, 'DB_PATH', 'data/telecom.db')))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.customer_id, c.name, c.email, c.phone_number, c.service_plan_id,
                   sp.name AS plan_name, sp.monthly_cost, sp.data_limit_gb
            FROM customers c
            LEFT JOIN service_plans sp ON c.service_plan_id = sp.plan_id
            WHERE c.customer_id = ?
            """,
            (customer_id,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "customer_id": row[0],
            "name": row[1],
            "email": row[2],
            "phone_number": row[3],
            "service_plan_id": row[4],
            "plan_name": row[5],
            "monthly_cost": row[6],
            "data_limit_gb": row[7]
        }
    except Exception:
        # If sqlite fetch fails, attempt to use the SQLDatabase wrapper as a fallback
        try:
            db = get_database()
            query = f"SELECT customer_id, name, email, phone_number, service_plan_id FROM customers WHERE customer_id = '{customer_id}'"
            raw = db.run(query)
            # raw is often a textual representation; return it as a minimal dict
            return {"raw": str(raw)}
        except Exception:
            return None


def build_customer_context(customer_info: Dict) -> str:
    """Build a short plain-text context block from the customer_info dict to include for the agent."""
    if not customer_info:
        return ""
    if "raw" in customer_info:
        return f"Customer DB info (raw): {customer_info['raw']}\n"

    parts = [f"Customer ID: {customer_info.get('customer_id')}"]
    if customer_info.get('name'):
        parts.append(f"Name: {customer_info.get('name')}")
    if customer_info.get('plan_name'):
        parts.append(f"Current Plan: {customer_info.get('plan_name')} (ID: {customer_info.get('service_plan_id')})")
    if customer_info.get('monthly_cost') is not None:
        parts.append(f"Monthly cost: {customer_info.get('monthly_cost')}")
    if customer_info.get('data_limit_gb') is not None:
        parts.append(f"Data limit (GB): {customer_info.get('data_limit_gb')}")

    return "Customer info: " + "; ".join(parts) + "\n"

def create_service_agent():
    """Create and return a LangGraph agent for service recommendations"""
    
    # Create LLM
    llm = ChatOpenAI(model=Config.OPENAI_MODEL_NAME, temperature=0.2)
    
    # Create Tools
    db = get_database()
    sql_tool = QuerySQLDataBaseTool(db=db)
    python_tool = PythonREPLTool()
    
    usage_tool = Tool(
        name="estimate_data_usage",
        func=estimate_data_usage,
        description="Estimate monthly data usage based on activity descriptions."
    )
    
    vector_tool = Tool(
        name="search_service_docs",
        func=search_service_docs,
        description="Search for qualitative plan details, benefits, and terms in the documentation."
    )
    
    tools = [sql_tool, python_tool, usage_tool, vector_tool]
    
    # Create Agent using LangGraph prebuilt
    # messages_modifier acts as the system message
    agent_executor = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SERVICE_RECOMMENDATION_TEMPLATE
    )
    
    return agent_executor

# Modified: accept optional customer_id and include DB-derived context when available
def process_recommendation_query(query: str, customer_id: Optional[str] = None):
    """Process a service recommendation query using the LangGraph agent.

    If customer_id is provided, basic customer and current-plan details are fetched from the DB
    and prepended to the user's query so the agent can give a personalized answer.
    """
    agent_executor = create_service_agent()

    # Build context from DB when customer_id provided
    customer_context = ""
    if customer_id:
        info = fetch_customer_info(customer_id)
        if info:
            customer_context = build_customer_context(info)
        else:
            customer_context = f"Note: no customer data found for id={customer_id}.\n"

    full_prompt = customer_context + "User question: " + query

    try:
        # LangGraph invoke takes {"messages": [...]}
        response = agent_executor.invoke({"messages": [("user", full_prompt)]})
        # The last message in the state is the AI's final response
        # Handle different return shapes gracefully
        msgs = response.get("messages") if isinstance(response, dict) else None
        if msgs:
            return msgs[-1].content
        # fallback: stringified response
        return str(response)
    except Exception as e:
        return f"Error processing recommendation: {e}"

if __name__ == "__main__":
    # Test run
    print("Starting Service Agent Test...")
    print(process_recommendation_query("What is the best plan for a family of 4 with high data usage?", customer_id="CUST001"))

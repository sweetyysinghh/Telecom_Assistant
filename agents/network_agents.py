import autogen
from telecom_assistant.config.config import Config
from telecom_assistant.utils.database import get_database
from telecom_assistant.utils.document_loader import load_documents
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
import os

# Set API Key
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

def create_network_agents():
    """Create and return an AutoGen group chat for network troubleshooting"""
    
    # Configuration for agents
    config_list = [{
        "model": Config.OPENAI_MODEL_NAME,
        "api_key": Config.OPENAI_API_KEY,
    }]
    
    llm_config = {
        "config_list": config_list,
        "temperature": 0.2,
        "timeout": 120,
    }

    # --- Tools Setup ---
    
    # 1. Network Status Tool
    def check_network_status(location: str) -> str:
        """Check for network outages or incidents in a specific location using the DB.

        Safe: if the DB schema doesn't match or query fails, return a friendly message
        rather than raising an exception so the orchestrator can present a helpful reply.
        """
        try:
            db = get_database()
            if not location:
                return "No specific location provided to check for outages."
            pattern = f"%{location}%"
            with db._engine.connect() as conn:
                rows = conn.execute(text("SELECT area, status, updated_at, details FROM network_status WHERE area LIKE :p"), {"p": pattern}).fetchall()
                if not rows:
                    return f"No reported network incidents found in '{location}'."
                parts = []
                for r in rows:
                    area = r[0]
                    status = r[1]
                    updated = r[2] if len(r) > 2 else ""
                    details = r[3] if len(r) > 3 else ""
                    parts.append(f"Area: {area} — Status: {status}. {details} (updated: {updated})")
                return "\n".join(parts)
        except Exception as e:
            # Don't leak internal errors; provide a helpful fallback message instead.
            # Detect common schema error string to give a tailored message.
            msg = str(e).lower()
            if "no such column" in msg or "operationalerror" in msg or "no such table" in msg:
                return (
                    "Unable to read network incident reports due to an internal database mismatch. "
                    "This does not prevent checking other troubleshooting steps — you may be experiencing a local network issue (calls or data may be slow) in your area."
                )
            return (
                "Unable to check network incident reports right now due to an internal error. "
                "This may indicate temporary issues with our reporting system — however, you may still be experiencing a local network problem (service slow or intermittent)."
            )


    # 2. Troubleshooting Docs Tool
    def search_troubleshooting_docs(query: str) -> str:
        """Search technical documentation for troubleshooting steps. Returns text or message on failure."""
        try:
            index = load_documents()
            if not index:
                return "Error: Document index not available."
            query_engine = index.as_query_engine()
            response = query_engine.query(query)
            return str(response)
        except Exception as e:
            return f"Error searching docs: {str(e)}"

    # --- Agents Setup ---

    # 1. User Proxy Agent
    user_proxy = autogen.UserProxyAgent(
        name="User_Proxy",
        system_message="""You represent a customer with a network issue. Your job is to:
        1. Present the customer's problem clearly.
        2. Ask clarifying questions if agents need more information.
        3. Summarize the final solution in simple terms once the agents have provided a resolution.
        4. Terminate the chat when a solution is found and summarized.""",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
        code_execution_config=False,
    )

    # 2. Network Diagnostics Agent
    network_agent = autogen.AssistantAgent(
        name="Network_Diagnostics_Agent",
        system_message="""You are a network diagnostics expert who analyzes connectivity issues.
        Your responsibilities:
        1. Check for known outages or incidents in the customer's area using `check_network_status`.
        2. Analyze network performance metrics.
        3. Identify patterns that indicate specific network problems.
        4. Determine if the issue is widespread or localized to the customer.
        
        Always begin by checking the network status database for outages in the customer's region before suggesting device-specific solutions.""",
        llm_config=llm_config,
    )

    # 3. Device Expert Agent
    device_agent = autogen.AssistantAgent(
        name="Device_Expert_Agent",
        system_message="""You are a device troubleshooting expert who knows how to resolve connectivity issues on different phones and devices.
        Your responsibilities:
        1. Suggest device-specific settings to check.
        2. Provide step-by-step instructions for configuration using `search_troubleshooting_docs` to find accurate info.
        3. Explain how to diagnose hardware vs. software issues.
        4. Recommend specific actions based on the device type.
        
        Always ask for the device model if it's not specified, as troubleshooting steps differ between iOS, Android, and other devices.""",
        llm_config=llm_config,
    )

    # 4. Solution Integrator Agent
    integrator_agent = autogen.AssistantAgent(
        name="Solution_Integrator_Agent",
        system_message="""You are a solution integrator who combines technical analysis into actionable plans for customers.
        Your responsibilities:
        1. Synthesize information from the network and device experts.
        2. Create a prioritized list of troubleshooting steps.
        3. Present solutions in order from simplest to most likely to succeed.
        4. When a clear solution plan is formed, output the final answer and append "TERMINATE" to end the conversation.""",
        llm_config=llm_config,
    )

    # Register Tools
    # We register tools with the agents that need them and the user proxy (executor)
    
    # Network Agent needs check_network_status
    autogen.register_function(
        check_network_status,
        caller=network_agent,
        executor=user_proxy,
        name="check_network_status",
        description="Check for network outages in a specific location."
    )

    # Device Agent needs search_troubleshooting_docs
    autogen.register_function(
        search_troubleshooting_docs,
        caller=device_agent,
        executor=user_proxy,
        name="search_troubleshooting_docs",
        description="Search technical docs for troubleshooting steps."
    )

    # --- Group Chat Setup ---
    
    groupchat = autogen.GroupChat(
        agents=[user_proxy, network_agent, device_agent, integrator_agent],
        messages=[],
        max_round=12
    )
    
    manager = autogen.GroupChatManager(
        groupchat=groupchat,
        llm_config=llm_config
    )
    
    return user_proxy, manager

# Top-level Network tools (used by deterministic handler and also registered inside create_network_agents)
from sqlalchemy import text

def check_network_status(location: str) -> str:
    """Check for network outages or incidents in a specific location using the DB.

    Safe: if the DB schema doesn't match or query fails, return a friendly message
    rather than raising an exception so the orchestrator can present a helpful reply.
    """
    try:
        db = get_database()
        if not location:
            return "No specific location provided to check for outages."
        pattern = f"%{location}%"
        with db._engine.connect() as conn:
            rows = conn.execute(text("SELECT area, status, updated_at, details FROM network_status WHERE area LIKE :p"), {"p": pattern}).fetchall()
            if not rows:
                return f"No reported network incidents found in '{location}'."
            parts = []
            for r in rows:
                area = r[0]
                status = r[1]
                updated = r[2] if len(r) > 2 else ""
                details = r[3] if len(r) > 3 else ""
                parts.append(f"Area: {area} — Status: {status}. {details} (updated: {updated})")
            return "\n".join(parts)
    except Exception as e:
        # Don't leak internal errors; provide a helpful fallback message instead.
        # Detect common schema error string to give a tailored message.
        msg = str(e).lower()
        if "no such column" in msg or "operationalerror" in msg or "no such table" in msg:
            return (
                "Unable to read network incident reports due to an internal database mismatch. "
                "This does not prevent checking other troubleshooting steps — you may be experiencing a local network issue (calls or data may be slow) in your area."
            )
        return (
            "Unable to check network incident reports right now due to an internal error. "
            "This may indicate temporary issues with our reporting system — however, you may still be experiencing a local network problem (service slow or intermittent)."
        )


def search_troubleshooting_docs(query: str) -> str:
    """Search technical documentation for troubleshooting steps. Returns text or message on failure."""
    try:
        index = load_documents()
        if not index:
            return "Error: Document index not available."
        query_engine = index.as_query_engine()
        response = query_engine.query(query)
        return str(response)
    except Exception as e:
        return f"Error searching docs: {str(e)}"

# Helper: extract location and device from a free-form query
def _extract_location_and_device(query: str):
    """Try to extract a location and device model from the user's query using simple heuristics.

    Improved extraction to handle phrases like:
      - "from my home in Mumbai West"
      - "I can't make calls at Mumbai West"
      - "no service in Bandra, Mumbai"
    """
    q = (query or "").strip()
    q_lower = q.lower()

    # Try several patterns to capture the location phrase
    import re
    location = None
    # Pattern: 'in <location>' or 'at <location>' or 'from <...> in <location>' possibly followed by punctuation
    patterns = [r"(?:from\s+my\s+home\s+in|from\s+my\s+home\s+at|in|at|near)\s+([A-Za-z0-9\s\-\.,]+)(?:[\.!?]|$)",
                r"(?:in|at|near)\s+([A-Za-z0-9\s\-\.,]+)$",
                r"(?:in|at|near)\s+([A-Za-z\s\-]+),?\s*[A-Za-z]*$"]
    for pat in patterns:
        m = re.search(pat, q_lower)
        if m:
            location = m.group(1).strip().strip('.,')
            break

    # device extraction: look for common device keywords and optional model tokens
    device = None
    dev_match = re.search(r"(iphone\s*[0-9x]*|ipad|samsung\s*galaxy\s*[a-z0-9]*|samsung|pixel\s*[0-9]*|oneplus\s*[0-9]*|xiaomi|mi[0-9]+|galaxy\s?[a-z0-9]*)", q_lower)
    if dev_match:
        device = dev_match.group(0).strip()

    # If location contains extraneous words like 'my', strip them
    if location:
        location = re.sub(r"\b(my|home|apartment|house|office|room)\b", "", location).strip()

    return location, device


def process_network_query(query: str):
    """Process a network troubleshooting query. Try deterministic DB + docs path first,
    then provide a helpful troubleshooting checklist and clarifying questions if no
    clear outage or doc-based solution is found. AutoGen is used only as a deeper fallback.
    """
    # Attempt to answer without launching AutoGen
    location, device = _extract_location_and_device(query)
    parts = []

    # 1) Check network status DB for the location
    status = None
    if location:
        status = check_network_status(location)
        parts.append(f"Network status check for '{location}':\n{status}")
    else:
        parts.append("No explicit location detected in your question; skipping outage lookup.")

    # 2) Search troubleshooting docs for device/location specific guidance
    doc_query = query
    if device:
        doc_query = f"{device} {query}"
    docs_result = search_troubleshooting_docs(doc_query)
    parts.append(f"Troubleshooting suggestions:\n{docs_result}")

    # If we found an outage report or docs_result contains actionable steps, return combined
    combined = "\n\n".join(parts)
    docs_actionable = bool(docs_result and not docs_result.startswith("Error") and len(docs_result) > 50)
    outage_reported = bool(status and "no reported network incidents" not in status.lower())

    if outage_reported or docs_actionable:
        return combined

    # If no outage and docs not actionable, return a detailed checklist + clarifying questions
    checklist = []
    checklist.append("I couldn't find a reported outage or a clear doc-based fix for your location/device. Let's try some quick troubleshooting and collect more information:")
    checklist.append("\nQuick checks (do these first):")
    checklist.append("1. Toggle Airplane Mode ON → wait 5s → OFF.")
    checklist.append("2. Restart your phone.")
    checklist.append("3. Check SIM: open Settings → Network & SIM and ensure SIM is enabled and not in airplane mode.")
    checklist.append("4. Verify signal bars in the status bar and try moving to a window or outdoors briefly.")
    checklist.append("5. If you see 'No Service' or 'Emergency Calls only', check if the SIM works in another phone.")
    checklist.append("6. Check call barring / Do Not Disturb settings and that your account is active.")
    checklist.append("\nDevice-specific steps:")
    checklist.append("- For iPhone: Settings → Cellular → Cellular Data Options → Enable VoLTE/Voice & Data if relevant.")
    checklist.append("- For Android: Check Mobile Network → Preferred Network Type → Ensure 4G/3G is selected; check APN settings if data fails.")

    checklist.append("\nPlease provide the following so I can investigate further:")
    checklist.append("- Exact location (e.g., 'Mumbai West' or full neighborhood/address).")
    checklist.append("- Device model (e.g., iPhone 14, Samsung Galaxy S22).")
    checklist.append("- What happens when you try to call? (error message, call drops, busy tone).")
    checklist.append("- When did the issue start? Has it happened before?")
    checklist.append("- Are other users in the same location affected?")

    checklist.append("\nNext steps I can take for you:")
    checklist.append("- Check network incident reports for the exact address once you provide it.")
    checklist.append("- Run a deeper diagnostics flow (takes a bit longer) to analyze SIM/IMSI/account status.")
    checklist.append("- If needed, escalate to field engineers for local signal checks.")

    # Combine and return the helpful response
    helpful_response = combined + "\n\n" + "\n".join(checklist)

    # If the user didn't provide location or device, we stop here and ask for clarifying info
    if not location or not device:
        return helpful_response

    # If location and device present but no outage/docs, still return helpful_response before invoking AutoGen
    return helpful_response

if __name__ == "__main__":
    # Test run
    print("Starting Network Agents Test...")
    try:
        process_network_query("I have no internet in New York. My phone is an iPhone 14.")
    except Exception as e:
        print(f"Error running network agents: {e}")

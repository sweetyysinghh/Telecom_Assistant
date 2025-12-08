from typing import Dict, Any, TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from telecom_assistant.config.config import Config
from telecom_assistant.agents.billing_agents import process_billing_query
from telecom_assistant.agents.network_agents import process_network_query
from telecom_assistant.agents.service_agents import process_recommendation_query
from telecom_assistant.agents.knowledge_agents import process_knowledge_query
import os
import re

# Set API Key
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

from telecom_assistant.orchestration.state import AgentState

# --- Nodes ---

def classify_query(state: AgentState) -> AgentState:
    """Classifies the query into one of the defined categories with simple heuristics
    for common edge cases (empty, joke, multi-intent) before falling back to the LLM
    classifier for ambiguous inputs.
    """
    query = (state.get("query") or "").strip()

    # Empty input handling
    if not query:
        return {"category": "EMPTY"}

    q_lower = query.lower()

    # Joke detection (user asks for jokes or humor)
    if any(w in q_lower for w in ("joke", "funny", "tell me a joke", "make me laugh")):
        return {"category": "JOKE"}

    # Simple multi-intent detection: contains keywords from more than one main category
    billing_kw = any(w in q_lower for w in ("bill", "billing", "charge", "payment", "invoice", "due"))
    network_kw = any(w in q_lower for w in ("network", "signal", "internet", "outage", "connect", "slow"))
    service_kw = any(w in q_lower for w in ("plan", "upgrade", "recommend", "service plan", "switch plan"))
    knowledge_kw = any(w in q_lower for w in ("how to", "how do i", "compatib", "setup", "guide", "what is"))

    present = sum([billing_kw, network_kw, service_kw, knowledge_kw])
    if present > 1:
        return {"category": "MULTI"}

    # If a single heuristic category matched, return it
    if billing_kw:
        return {"category": "BILLING"}
    if network_kw:
        return {"category": "NETWORK"}
    if service_kw:
        return {"category": "SERVICE"}
    if knowledge_kw:
        return {"category": "KNOWLEDGE"}

    # Fall back to LLM classification when heuristics don't decide
    llm = ChatOpenAI(model=Config.OPENAI_MODEL_NAME, temperature=0)
    prompt = PromptTemplate.from_template(
        """You are a query classifier for a telecom assistant.
        Classify the following query into exactly one of these categories:
        - BILLING: Questions about bills, charges, payments, or account balance.
        - NETWORK: Questions about signal, internet issues, outages, or device connectivity.
        - SERVICE: Questions about plan recommendations, upgrading, or new services.
        - KNOWLEDGE: General technical questions, "how-to" guides, or factual coverage/compatibility checks.
        - OTHER: Anything else.

        Query: {query}

        Category:"""
    )
    chain = prompt | llm
    result = chain.invoke({"query": query})
    category = result.content.strip().upper()

    # Normalize category just in case
    if "BILLING" in category:
        category = "BILLING"
    elif "NETWORK" in category:
        category = "NETWORK"
    elif "SERVICE" in category:
        category = "SERVICE"
    elif "KNOWLEDGE" in category:
        category = "KNOWLEDGE"
    else:
        category = "OTHER"

    print(f"--- Classified Query as: {category} ---")
    return {"category": category}


def joke_node(state: AgentState) -> AgentState:
    """Return a short, context-aware telecom-related joke.

    Uses a small heuristic to extract a topic (like 'plan') from the user's query
    and asks the LLM to craft a single short, family-friendly joke incorporating
    that topic when present. Falls back to a local safe joke on error.
    """
    print("--- Routing to Joke Handler ---")
    query = (state.get("query") or "").strip()
    topic = ""
    q_lower = query.lower()
    # Simple topic hints
    for hint in ("plan", "billing", "network", "signal", "service", "phone", "data"):
        if hint in q_lower:
            topic = hint
            break

    try:
        llm = ChatOpenAI(model=Config.OPENAI_MODEL_NAME, temperature=0.7)
        prompt = PromptTemplate.from_template(
            """You are a friendly assistant. Provide one concise, family-friendly joke (1-2 sentences) related to telecom.
            If the user's topic is provided, incorporate that topic into the joke in a natural and light-hearted way. Do not include any explanations — joke only.

            Topic: {topic}

            Joke:"""
        )
        chain = prompt | llm
        result = chain.invoke({"topic": topic})
        joke = result.content.strip() if hasattr(result, "content") else str(result).strip()

        # Safety: ensure it's short and non-empty
        if not joke:
            raise ValueError("Empty joke from LLM")

        return {"response": joke}
    except Exception as e:
        # Fallback safe jokes
        fallback_jokes = [
            "Why don't secrets last in telecom? Because they always get leaked through the network! 😄",
            "Why did the mobile plan go to therapy? It had too many unresolved issues! 📱😂",
            "Why was the cell tower so calm? It had great reception! 📶🙂",
            "Why did the customer bring a ladder to the network test? To get better coverage! 😆",
        ]
        # Prefer a fallback that mentions the topic if available
        if topic:
            for fj in fallback_jokes:
                if topic in fj.lower():
                    return {"response": fj}
        import random
        return {"response": random.choice(fallback_jokes)}


def multi_node(state: AgentState) -> AgentState:
    """Handle multi-intent queries by splitting and running relevant handlers and
    combining their responses into a single, readable reply."""
    print("--- Routing to Multi-Intent Handler ---")
    query = state.get("query", "")
    customer_id = state.get("customer_id", "CUST001")
    q_lower = query.lower()

    responses = []

    try:
        if any(w in q_lower for w in ("bill", "billing", "charge", "payment", "invoice", "due")):
            r = crew_ai_node({"query": query, "customer_id": customer_id})
            responses.append(("Billing", r.get("response", "")))
    except Exception as e:
        responses.append(("Billing", f"Error: {e}"))

    try:
        if any(w in q_lower for w in ("network", "signal", "internet", "outage", "connect", "slow")):
            r = autogen_node({"query": query})
            resp_text = r.get("response", "")
            # If agent returned an error string (e.g., DB OperationalError), try deterministic fallback
            if isinstance(resp_text, str) and (resp_text.lower().startswith("error") or "operationalerror" in resp_text.lower() or "no such column" in resp_text.lower()):
                try:
                    # Call the network deterministic handler directly for a friendly reply
                    fallback_resp = process_network_query(query)
                    responses.append(("Network", fallback_resp))
                except Exception as e:
                    responses.append(("Network", f"Network agent encountered an error and could not provide a diagnosis: {e}"))
            else:
                responses.append(("Network", resp_text))
    except Exception as e:
        responses.append(("Network", f"Error: {e}"))

    try:
        if any(w in q_lower for w in ("plan", "upgrade", "recommend", "service plan", "switch plan")):
            r = langchain_node({"query": query})
            responses.append(("Service", r.get("response", "")))
    except Exception as e:
        responses.append(("Service", f"Error: {e}"))

    try:
        if any(w in q_lower for w in ("how to", "how do i", "compatib", "setup", "guide", "what is")):
            r = llamaindex_node({"query": query})
            responses.append(("Knowledge", r.get("response", "")))
    except Exception as e:
        responses.append(("Knowledge", f"Error: {e}"))

    if not responses:
        # If heuristics failed inside multi node, fallback to running the LLM classifier
        classified = classify_query(state)
        return fallback_handler({"query": query}) if classified.get("category") == "OTHER" else {"response": ""}

    # Combine responses into a single string with headings
    combined = []
    for tag, text in responses:
        combined.append(f"### {tag} Response\n{text}\n")

    return {"response": "\n---\n".join(combined)}


def empty_input_handler(state: AgentState) -> AgentState:
    print("--- Empty input received ---")
    return {"response": "It looks like you didn't ask anything — please type your question about billing, network, service plans, or technical support."}


def crew_ai_node(state: AgentState) -> AgentState:
    """Handles billing queries using CrewAI."""
    print("--- Routing to Billing Agents (CrewAI) ---")
    query = state.get("query", "")
    customer_id = state.get("customer_id", "CUST001")

    try:
        result = process_billing_query(customer_id, query)
        return {"response": _sanitize_response(str(result))}
    except Exception as e:
        return {"response": _sanitize_response(f"Error in Billing Agent: {str(e)}")}


def autogen_node(state: AgentState) -> AgentState:
    """Handles network queries using AutoGen."""
    print("--- Routing to Network Agents (AutoGen) ---")
    query = state.get("query", "")

    try:
        result = process_network_query(query)
        # process_network_query returns a human-readable troubleshooting string already
        return {"response": _sanitize_response(str(result))}
    except Exception as e:
        return {"response": _sanitize_response(f"Error in Network Agent: {str(e)}")}


def langchain_node(state: AgentState) -> AgentState:
    """Handles service recommendations using LangChain."""
    print("--- Routing to Service Agents (LangChain) ---")
    query = state.get("query", "")

    try:
        result = process_recommendation_query(query)
        return {"response": _sanitize_response(str(result))}
    except Exception as e:
        return {"response": _sanitize_response(f"Error in Service Agent: {str(e)}")}


def llamaindex_node(state: AgentState) -> AgentState:
    """Handles knowledge queries using LlamaIndex."""
    print("--- Routing to Knowledge Agents (LlamaIndex) ---")
    query = state.get("query", "")

    try:
        result = process_knowledge_query(query)
        return {"response": _sanitize_response(str(result))}
    except Exception as e:
        return {"response": _sanitize_response(f"Error in Knowledge Agent: {str(e)}")}


def fallback_handler(state: AgentState) -> AgentState:
    """Handles unclassified or other queries."""
    print("--- Routing to Fallback Handler ---")
    return {"response": "I'm sorry, I couldn't understand your request. Please ask about billing, network issues, service plans, or technical support."}


def _sanitize_response(text) -> str:
    """Convert common Markdown/HTML formatted text to plain text for UI.

    This is a simple sanitizer (not a full Markdown renderer) that:
    - removes code fences
    - strips Markdown headings, emphasis, bold, links
    - converts table pipes to spaced separators
    - collapses excessive blank lines
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Remove fenced code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove Markdown headings (#, ##, ###)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    # Remove bold/italic markers
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    # Convert markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Replace table pipes with spaced separators
    text = re.sub(r"\|", " | ", text)
    # Remove horizontal rules
    text = re.sub(r"^-{3,}$", "", text, flags=re.M)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim
    return text.strip()

# --- Routing Logic ---

def route_query(state: AgentState) -> Literal["crew_ai_node", "autogen_node", "langchain_node", "llamaindex_node", "fallback_handler", "joke_node", "multi_node", "empty_input_handler"]:
    category = state["category"]

    if category == "EMPTY":
        return "empty_input_handler"
    if category == "JOKE":
        return "joke_node"
    if category == "MULTI":
        return "multi_node"
    if category == "BILLING":
        return "crew_ai_node"
    elif category == "NETWORK":
        return "autogen_node"
    elif category == "SERVICE":
        return "langchain_node"
    elif category == "KNOWLEDGE":
        return "llamaindex_node"
    else:
        return "fallback_handler"

# --- Graph Construction ---

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("classify_query", classify_query)
workflow.add_node("crew_ai_node", crew_ai_node)
workflow.add_node("autogen_node", autogen_node)
workflow.add_node("langchain_node", langchain_node)
workflow.add_node("llamaindex_node", llamaindex_node)
workflow.add_node("fallback_handler", fallback_handler)
# New nodes
workflow.add_node("joke_node", joke_node)
workflow.add_node("multi_node", multi_node)
workflow.add_node("empty_input_handler", empty_input_handler)

# Set Entry Point
workflow.set_entry_point("classify_query")

# Add Conditional Edges
workflow.add_conditional_edges(
    "classify_query",
    route_query,
    {
        "crew_ai_node": "crew_ai_node",
        "autogen_node": "autogen_node",
        "langchain_node": "langchain_node",
        "llamaindex_node": "llamaindex_node",
        "fallback_handler": "fallback_handler",
        "joke_node": "joke_node",
        "multi_node": "multi_node",
        "empty_input_handler": "empty_input_handler",
    }
)

# Add Edges to End
workflow.add_edge("crew_ai_node", END)
workflow.add_edge("autogen_node", END)
workflow.add_edge("langchain_node", END)
workflow.add_edge("llamaindex_node", END)
workflow.add_edge("fallback_handler", END)
workflow.add_edge("joke_node", END)
workflow.add_edge("multi_node", END)
workflow.add_edge("empty_input_handler", END)

# Compile Graph
app = workflow.compile()

def run_orchestrator(query: str, customer_id: str = "CUST001"):
    """Run the orchestration graph for a given query."""
    inputs = {"query": query, "customer_id": customer_id, "history": []}
    result = app.invoke(inputs)
    return result["response"]
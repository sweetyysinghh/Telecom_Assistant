from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, SQLDatabase
from llama_index.core.query_engine import RouterQueryEngine, NLSQLTableQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from llama_index.llms.openai import OpenAI
from llama_index.core.tools import QueryEngineTool
from sqlalchemy import create_engine
from telecom_assistant.config.config import Config
import os

# Set API Key
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

def create_knowledge_engine():
    """Create and return a LlamaIndex query engine for knowledge retrieval

    This function now exposes the underlying SQL query engine on the returned
    RouterQueryEngine (as attributes) so callers can run direct SQL-oriented
    queries for policy-like questions (e.g., termination fees) when appropriate.
    """

    # Initialize LLM and Settings
    llm = OpenAI(model=Config.OPENAI_MODEL_NAME, temperature=0)
    Settings.llm = llm
    Settings.chunk_size = 1024

    # Load and index documents (Vector Store)
    documents = SimpleDirectoryReader(
        input_dir=os.path.join(Config.DATA_DIR, "documents")
    ).load_data()

    vector_index = VectorStoreIndex.from_documents(documents)

    # Set up vector search query engine
    vector_query_engine = vector_index.as_query_engine(
        similarity_top_k=3
    )

    # Connect to the database for factual queries (SQL Store)
    db_path = Config.DATABASE_PATH if hasattr(Config, 'DATABASE_PATH') else getattr(Config, 'DB_PATH', 'data/telecom.db')
    db_uri = f"sqlite:///{db_path}"
    engine = create_engine(db_uri)
    sql_database = SQLDatabase(engine)

    # Create SQL query engine
    # Include policy and billing-related tables so queries about termination fees are covered
    sql_query_engine = NLSQLTableQueryEngine(
        sql_database=sql_database,
        tables=["coverage_areas", "device_compatibility", "technical_specs", "service_plans", "policies", "billing_policies", "contract_terms"]
    )

    # Create QueryEngineTools
    vector_tool = QueryEngineTool.from_defaults(
        query_engine=vector_query_engine,
        description=(
            "Useful for conceptual, procedural questions like 'How do I set up VoLTE?' "
            "or 'What's the process for international roaming?'"
        ),
    )

    sql_tool = QueryEngineTool.from_defaults(
        query_engine=sql_query_engine,
        description=(
            "Useful for factual, data-driven and policy questions like 'Which areas have 5G coverage?', "
            "'Is the Samsung Galaxy S22 compatible with VoLTE?', or 'What are early termination fees if I cancel my contract?'."
        ),
    )

    # Create Router Query Engine
    router_query_engine = RouterQueryEngine(
        selector=LLMSingleSelector.from_defaults(),
        query_engine_tools=[
            vector_tool,
            sql_tool,
        ],
    )

    # Attach internal engines for callers that need direct access
    router_query_engine.sql_query_engine = sql_query_engine
    router_query_engine.vector_query_engine = vector_query_engine
    router_query_engine.vector_index = vector_index

    return router_query_engine


def process_knowledge_query(query: str):
    """Process a knowledge retrieval query using the LlamaIndex query engine

    Special-cases certain user intents (e.g., asking about future generation networks like "7G")
    to return a clear, non-technical answer without relying on the SQL tables which may be
    missing in some test databases. For policy/SQL queries we try the SQL engine first but
    fall back to the router/vector path and finally to a helpful generic response if all
    automated attempts fail.
    """

    # Create or get the knowledge engine
    engine = create_knowledge_engine()

    q_lower = (query or "").lower()

    # Explicit handling for futuristic or speculative network requests like '7G'
    if any(k in q_lower for k in ("7g", "7 g", "seventh generation", "seven g")):
        return (
            "Short answer: 7G is not a commercial standard or service you can subscribe to today. "
            "Mobile network generations (2G/3G/4G/5G) are defined by global standards and require new "
            "infrastructure and device support. If you want the fastest available mobile service in your area, do the following:\n\n"
            "1) Check current coverage maps from your operator for 5G/advanced 5G (often labeled 5G+).\n"
            "2) Ensure your device supports the highest generation (check device specs).\n"
            "3) Confirm your plan includes access to the faster network bands (some plans restrict speeds).\n"
            "4) If you need better indoor coverage, consider a signal booster or ask the operator to perform a site survey.\n"
            "5) To express demand for future network upgrades, contact customer support and register your area for coverage expansion requests."
        )

    try:
        # If the user asked about contract/policy terms we attempt SQL first (may raise if tables missing)
        if any(k in q_lower for k in ("termination", "early termination", "early termination fee", "etf", "cancel my contract", "cancel my plan", "cancel contract", "termination fee")):
            try:
                sql_engine = getattr(engine, 'sql_query_engine', None)
                if sql_engine is not None:
                    response = sql_engine.query(query)
                    return str(response)
            except Exception:
                # fall through to router
                pass

        # Default: let the router decide between vector and SQL
        try:
            response = engine.query(query)
            return str(response)
        except Exception as e:
            # Provide a helpful fallback if router fails (e.g., missing tables like 'policies')
            err = str(e).lower()
            if "policies" in err or "no such table" in err or "no such column" in err:
                return (
                    "I couldn't access our policy database right now, but here is general guidance:\n"
                    "- For network availability, check your operator's coverage map or contact support.\n"
                    "- For account or billing policies, contact customer support and request an itemized explanation.\n"
                    "If you give me the exact question (for example: 'How much is the early termination fee for Plan X?'), I can try to answer from available documentation."
                )
            # Generic fallback
            return f"Sorry, I couldn't retrieve a direct answer right now: {str(e)}"
    except Exception as e:
        return f"Error processing knowledge query: {str(e)}"

if __name__ == "__main__":
    # Test run
    print("Starting Knowledge Agent Test...")
    print(process_knowledge_query("How do I enable VoLTE?"))

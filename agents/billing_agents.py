from crewai import Agent, Task, Crew, Process
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from telecom_assistant.utils.database import get_database
from telecom_assistant.config import Config
from crewai.tools import BaseTool
import os

# Set OpenAI API Key for CrewAI
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY
os.environ["OPENAI_MODEL_NAME"] = Config.OPENAI_MODEL_NAME

class DatabaseSearchTool(BaseTool):
    name: str = "Search Telecom Database"
    description: str = "Useful for querying the telecom database to find customer usage, billing info, and plans. Input should be a valid SQL query."
    
    def _run(self, query: str) -> str:
        db = get_database()
        sql_tool = QuerySQLDataBaseTool(db=db)
        return sql_tool.run(query)

from telecom_assistant.utils.document_loader import load_documents

class VectorSearchTool(BaseTool):
    name: str = "Search Billing FAQ"
    description: str = "Useful for answering general questions about billing policies, payment methods, and common issues. Input should be a natural language query."
    
    def _run(self, query: str) -> str:
        try:
            index = load_documents()
            if not index:
                return "Error: Document index not available."
            query_engine = index.as_query_engine()
            response = query_engine.query(query)
            return str(response)
        except Exception as e:
            return f"Error searching docs: {str(e)}"

def create_billing_crew(customer_id: str, query: str):
    """Create and return a CrewAI crew for handling billing inquiries"""
    
    # Create tools
    db_tool = DatabaseSearchTool()
    vector_tool = VectorSearchTool()
    
    # Create the Billing Specialist agent
    billing_specialist = Agent(
        role='Billing Specialist',
        goal='Explain bill components, identify unusual changes, clarify all charges',
        backstory="""You are a senior billing analyst with 10 years of experience in telecom.
        Your job is to:
        1. Examine the customer's current and previous bills to identify any changes
        2. Explain each charge in simple language
        3. Identify any unusual or one-time charges
        4. Verify that all charges are consistent with the customer's plan
        5. Answer general billing questions using the FAQ

        You have access to the following database tables:
        - customers: customer_id, name, email, phone_number, service_plan_id, account_status
        - customer_usage: usage_id, customer_id, billing_period_start, billing_period_end, data_used_gb, voice_minutes_used, sms_count_used, additional_charges, total_bill_amount
        - service_plans: plan_id, name, monthly_cost, data_limit_gb, voice_minutes, sms_count, description

        Use SQL to retrieve billing information, and be precise about numbers.
        Always start by retrieving the customer's most recent bill, then compare it with the previous bill to identify changes.
        If the query is general (e.g., "how to pay"), check the FAQ first.

        When presenting options or plan details to the customer, format the information clearly using Markdown. For any plans you reference include a small Markdown table with columns: Plan, Monthly Cost, Data (GB), Voice (min), SMS, Notes. If you compute savings or overage costs, show the arithmetic and the rounded amounts in local currency. End your response with a short (1-2 sentence) plain-language recommendation and a bullet list of actionable next steps the customer can take (for example: switch plan, set usage alerts, dispute a charge).""",
        verbose=True,
        allow_delegation=False,
        tools=[db_tool, vector_tool]
    )
    
    # Create the Service Advisor agent
    service_advisor = Agent(
        role='Service Advisor',
        goal='Identify if customer is on optimal plan, suggest alternatives if needed',
        backstory="""You are a telecom service advisor who helps customers optimize their plans.
        Your job is to:
        1. Analyze the customer's usage patterns (data, calls, texts)
        2. Compare their usage with their current plan limits
        3. Identify if they are paying for services they don't use
        4. Suggest better plans if available

        You have access to the following database tables:
        - customers: customer_id, name, service_plan_id
        - customer_usage: usage_id, customer_id, billing_period_start, billing_period_end, data_used_gb, voice_minutes_used, sms_count_used, total_bill_amount
        - service_plans: plan_id, name, monthly_cost, data_limit_gb, voice_minutes, sms_count, description

        Use SQL to retrieve the customer's usage data and plan details.
        Be specific about potential savings or benefits of your recommendations.

        When recommending plans, present a comparison table in Markdown that lists at least the customer's current plan and the top 2 recommended alternatives. The table must include: Plan, Monthly Cost, Data (GB), Voice (min), SMS, Estimated Monthly Cost for the customer's actual usage, Estimated Monthly Savings, and a short Reason for Recommendation.

        For each recommended plan compute the estimated monthly cost given the customer's actual usage (include any overage calculations if applicable), show the absolute and percentage savings vs the current plan, and provide a concise justification focused on cost and feature fit.

        Output should include:
        - A short summary (1-2 sentences) of why a particular plan is recommended
        - A Markdown table comparing plans (as described above)
        - A one-line plain-language action the customer can take next (e.g., "To switch to Plan X, contact support or visit the account portal").

        When providing numeric values, show currency and round to two decimals.
        """,
        verbose=True,
        allow_delegation=False,
        tools=[db_tool]
    )
    
    # Create tasks for the agents
    
    # Task 1: Analyze current bill and identify changes
    analysis_task = Task(
        description=f"""
        Analyze the billing situation for customer ID: {customer_id}.
        The customer is asking: "{query}"
        
        1. Query the database to find the customer's current plan, recent usage (data, voice, sms), and billing records.
        2. Identify any anomalies or reasons for the charges mentioned in the query.
        3. If the query is a general question (e.g., payment methods, disputes), use the FAQ tool to find the answer.
        4. Provide a detailed technical summary of the findings.
        """,
        expected_output="A detailed technical report of the customer's usage and billing data relevant to the query.",
        agent=billing_specialist
    )
    
    # Task 2: Review usage patterns and plan fit
    usage_review_task = Task(
        description=f"""
        Review the usage patterns for customer ID: {customer_id} to see if their current plan is a good fit.
        
        1. Analyze data, voice, and SMS usage over the last few months.
        2. Compare against their current plan limits.
        3. Determine if they are overpaying or under-provisioned.
        """,
        expected_output="A review of the customer's plan suitability with recommendations.",
        agent=service_advisor
    )
    
    # Task 3: Generate comprehensive explanation and recommendations
    final_response_task = Task(
        description=f"""
        Draft a final response to the customer based on the Billing Specialist's analysis and Service Advisor's review.
        
        Customer Query: "{query}"
        
        REQUIRED OUTPUT FORMAT (Markdown):
        1) Short Summary (1-2 sentences)
        2) Clear Explanation of Charges (with any SQL findings referenced)
        3) Plan Comparison Section: a Markdown table with columns: Plan | Monthly Cost | Data (GB) | Voice (min) | SMS | Estimated Monthly Cost (based on customer's usage) | Estimated Monthly Savings | Reason
        4) Recommendation: highlight the recommended plan (use bold text) and show the expected monthly and annual savings compared to the current plan (compute numbers and percent savings)
        5) Actionable Next Steps (bullet list) and how to contact support if disputing charges
        6) Short one-line plain-language summary for quick reading

        Be polite, professional, and helpful. When showing calculations, show the math and final rounded amounts (2 decimals).
        """,
        expected_output="A comprehensive natural language response to the customer explaining their bill and offering recommendations in the specified Markdown format.",
        agent=billing_specialist, # Or could be a separate "Coordinator" agent, but Specialist fits well here too
        context=[analysis_task, usage_review_task]
    )
    
    # Create the crew with agents and tasks
    billing_crew = Crew(
        agents=[billing_specialist, service_advisor],
        tasks=[analysis_task, usage_review_task, final_response_task],
        verbose=True,
        process=Process.sequential
    )
    
    return billing_crew

def process_billing_query(customer_id, query):
    """Process a billing query using the CrewAI crew"""
    
    # Create the billing crew
    crew = create_billing_crew(customer_id, query)
    
    # Process the query
    result = crew.kickoff()
    
    return result

if __name__ == "__main__":
    # Test run
    print("Starting Billing Crew Test...")
    try:
        response = process_billing_query("CUST001", "Why is my bill so high this month?")
        print("\n\n########################")
        print("## Final Response ##")
        print("########################\n")
        print(response)
    except Exception as e:
        print(f"Error running crew: {e}")

from typing import TypedDict, List, Any

class AgentState(TypedDict):
    query: str
    category: str
    response: str
    history: List[Any]
    customer_id: str

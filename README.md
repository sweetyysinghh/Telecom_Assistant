

# 📞 Telecom Assistant — Multi-Agent AI System for Telecom Support

**Telecom Assistant** is an AI-powered multi-agent system designed to provide intelligent, automated customer support for a telecommunications company.
It integrates **LLMs, RAG, and multi-agent orchestration** to handle real-world telecom scenarios — from **billing issues** to **network troubleshooting**, **plan recommendations**, and **knowledge base Q&A**.

The project combines the strengths of **LangChain**, **LlamaIndex**, **CrewAI**, **AutoGen**, and **LangGraph** — unified through a clean **Streamlit UI** for both customers and admins.

---

## 🚀 Features

### 🧠 Multi-Agent Intelligence

* **LangGraph Orchestration** routes each query to the right AI agent based on its category.
* Query categories include:

  * **Billing** → CrewAI multi-agent team
  * **Network** → Hybrid AutoGen + rule-based system
  * **Service** → LangChain ReAct agent
  * **Knowledge** → LlamaIndex RAG
  * **Fallbacks** for jokes, empty inputs, or unknown queries

### 👩‍💼 Role-Based Interface

* **Admin Panel**:

  * Upload and manage telecom documents (PDF, Markdown, etc.)
  * New documents are automatically indexed into the RAG system.
* **Customer Dashboard**:

  * Chat with the assistant for billing, service, or network help.
  * Quick action buttons for common queries.

### 💬 Real-Time Query Routing

The **LangGraph state machine** powers the orchestration layer:

1. **Classify Query** → Detects intent (`BILLING`, `NETWORK`, `SERVICE`, etc.)
2. **Route Query** → Directs flow to specialized agent node
3. **Agent Response** → Cleansed via `_sanitize_response` before UI display

---

## 🧩 Agent Overview

### 💰 Billing Agents — *CrewAI*

* Built as a **crew** with:

  * `Billing Specialist`: Analyzes usage and charges
  * `Service Advisor`: Suggests better plans
* Tools:

  * SQL database search for billing data
  * LlamaIndex vector search for FAQs
* Provides **multi-step reasoning** and detailed breakdowns.

---

### 📡 Network Agents — *AutoGen + Rule-Based*

* Starts with a **deterministic rule-based check** for outages and device issues.
* If unresolved, triggers **AutoGen group chat** with:

  * `Network Diagnostics Agent`
  * `Device Expert Agent`
  * `Solution Integrator Agent`
* Fast and interpretable troubleshooting pipeline.

---

### 📊 Service Agents — *LangChain ReAct*

* A **ReAct** agent using:

  * SQL queries for plan data
  * Python REPL for usage calculations
  * Vector store for context retrieval
* Personalizes recommendations by analyzing current plan and usage.

---

### 📘 Knowledge Agents — *LlamaIndex RAG*

* Uses **RouterQueryEngine** to pick between:

  * **Vector Engine** → Conceptual Q&A from documents
  * **SQL Engine** → Factual lookups (e.g., coverage data)
* Robust error handling and contextual responses.

---

## 🖥️ Streamlit Interface

### 🔐 Login Page

* Shared password system (`admin` or `customer_id`)
* SQLite-based user verification

### 💼 Admin Panel

* Upload new documents → auto-indexed into FAISS vector store

### 💬 Customer Dashboard

* Chat interface with quick-action buttons:

  * **Billing Help**
  * **Network Issues**
  * **Plan Recommendations**

---

## 🗂️ Project Structure

```
Telecom-Assistant/
├── app.py                  # Streamlit entry point
├── requirements.txt        # Dependencies
├── config/
│   └── config.py           # Environment + API configuration
├── data/
│   ├── telecom.db          # SQLite database
│   └── documents/          # Uploaded knowledge base docs
├── agents/
│   ├── billing_agents.py   # CrewAI billing system
│   ├── network_agents.py   # AutoGen network troubleshooting
│   ├── service_agents.py   # LangChain ReAct service advisor
│   └── knowledge_agents.py # LlamaIndex RAG system
├── orchestration/
│   └── graph.py            # LangGraph-based orchestrator
├── ui/
│   └── streamlit_app.py    # Streamlit UI logic
├── utils/
│   ├── database_utils.py   # DB helpers
│   └── document_loader.py  # Document ingestion + indexing
└── tools/
    └── seed_and_test.py    # Database seeding utilities
```

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the Repository

```bash
git clone [https://github.com/sweetyysinghh/Telecom_Assistant](https://github.com/sweetyysinghh/Telecom_Assistant.git)
git clone 
cd Telecom-Assistant
```

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Configure Environment

Create a `.env` file in the root directory:

```bash
OPENAI_API_KEY="your-openai-api-key"
```

### 4️⃣ Initialize Database

```bash
python tools/seed_and_test.py
```

### 5️⃣ Run the Application

```bash
streamlit run app.py
```

---

## 🧠 Technologies Used

| Category               | Tools / Frameworks                     |
| ---------------------- | -------------------------------------- |
| **Frontend**           | Streamlit                              |
| **Core Orchestration** | LangGraph                              |
| **LLM Frameworks**     | LangChain, CrewAI, AutoGen, LlamaIndex |
| **RAG**                | FAISS, LlamaIndex                      |
| **Database**           | SQLite                                 |
| **Environment**        | python-dotenv                          |
| **LLM Models**         | OpenAI GPT models via LangChain        |

---

## 🔍 Example Use Cases

| Query                                        | Routed Agent         | Response Example                          |
| -------------------------------------------- | -------------------- | ----------------------------------------- |
| “Why was my last bill so high?”              | CrewAI Billing Agent | Detailed breakdown with plan optimization |
| “My internet keeps disconnecting in Mumbai.” | Network Agent        | Outage check + troubleshooting steps      |
| “Recommend a cheaper plan with 5G.”          | Service Agent        | Personalized plan suggestions             |
| “How do I activate VoLTE?”                   | Knowledge Agent      | Answer retrieved from RAG knowledge base  |

---



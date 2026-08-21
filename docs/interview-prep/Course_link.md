# Course links — grow skills for this stack

Curated **Coursera**, **Microsoft certifications**, **Udemy**, and **YouTube** links mapped to this repo (FastAPI, LangChain, LangGraph, MCP/FastMCP, MAF / Azure AI Foundry, RAG, MLflow, memory/HITL).

> Verify links, exam codes, and “last updated” dates before buying or booking — Microsoft certs and course catalogs change.  
> Pair every course with **this repo’s** [interview-prep/](README.md) so you can explain *your* architecture in interviews.

---

## Learning approach (recommended path)

| Phase | Focus | Outcome for *this* project |
|---|---|---|
| 0 | GenAI fundamentals (Coursera / Microsoft AI Fundamentals) | Vocabulary: LLM lifecycle, RAG, responsible AI |
| 1 | FastAPI + OpenAPI | Build/defend `ip_api` gateway |
| 2 | **LangChain** (LCEL, RAG, tools, agents) | Mapper / validator / chains |
| 3 | **LangGraph** (state, cycles, HITL, checkpointers) | Document + voice graphs |
| 4 | MCP / FastMCP | Our `:8001` / `:8002` tool servers |
| 5 | MAF + Microsoft Foundry (+ cert if needed) | Central agent `:8003` → cloud deploy |
| 6 | Observability (LangSmith / MLflow / xid) | Debug multi-LLM + tools |

---

## LangChain vs LangGraph — what to learn (details)

Use this table so you don’t confuse the two in interviews.

| Concept | LangChain | LangGraph | In *this* repo |
|---|---|---|---|
| Mental model | **Chains / runnables** (mostly DAG-ish pipelines) | **Stateful graph** (nodes, edges, cycles, interrupts) | LCEL inside nodes; graphs own control flow |
| Best for | Prompt → parse → RAG → tools | Multi-step agents, retries, HITL | Document fill + voice confirm |
| Core APIs to know | `ChatModel`, LCEL `|`, retrievers, tools, agents | `StateGraph`, `add_node`, `add_edge`, `interrupt`, checkpointer | See interview-prep folders below |
| Memory | Chat history / buffers / summaries | **Checkpoint + `thread_id`** across requests | Voice SQL checkpointer; MAF session (Phase 1+) |
| RAG | Retriever + chain | Can wrap RAG as a node | Document mapping is LLM+rules, not classic vector RAG |
| When to stop LC and start LG | Linear “do A then B” | Need loops, branching, pause for human | Voice needs HITL → LangGraph |
| Study order | **First** | **Second** (after LCEL basics) | [langchain-basic/](langchain-basic/) → [langgraph-basic/](langgraph-basic/) |

### LangChain — topic checklist

| Topic | Learn this | Course type | Repo map |
|---|---|---|---|
| Models / prompts / parsers | Structured output, prompt templates | DeepLearning.AI short + Udemy | Mapper/validator prompts |
| LCEL | Compose runnables with `|` | Udemy / Academy | Chain style inside services |
| RAG | Load → split → embed → retrieve → generate | Coursera GenAI + LC courses | Interview RAG answers |
| Tools + agents | Tool calling, agent loops | DL.AI “Functions, Tools and Agents” | MAF tool calling analogy |
| Memory (chat) | Buffer / window / summary | Short LC courses | Contrast vs graph checkpoint |

### LangGraph — topic checklist

| Topic | Learn this | Course type | Repo map |
|---|---|---|---|
| State schema | Typed dict / pydantic state | LangGraph official + Udemy | Document / voice state |
| Nodes & edges | Conditional routing | Playlist / Eden Marco LG modules | Validate → retry loop |
| Cycles / retries | Loop until pass or max | LangGraph mastery content | Document validation retries |
| HITL | `interrupt` / wait for human | Official how-tos | Voice contract confirm |
| Checkpointer | Official: MemorySaver / Postgres; **this repo: SQLAlchemy SQLite/Azure SQL** | Official + Udemy | Voice `thread_id` |
| Multi-agent (optional) | Supervisor / handoffs | Advanced Udemy / Foundry | Compare to MAF orchestrating MCPs |

---

## Microsoft GenAI certifications (certificate path)

Official associate path for apps/agents on **Microsoft Foundry** (verify on Learn — names evolve).

| Step | Credential / exam | Level | What it proves | Official links | Prep courses |
|---|---|---|---|---|---|
| 1 | **Microsoft Azure AI Fundamentals** — exam **AI-901** (successor path; older materials may say **AI-900**) | Fundamentals | AI workloads, ML, vision, NLP, **generative AI on Azure / Foundry** | Cert: https://learn.microsoft.com/credentials/certifications/azure-ai-fundamentals/ · Exam AI-901: https://learn.microsoft.com/credentials/certifications/exams/ai-901/ | Coursera Microsoft AI Fundamentals specialization (below) |
| 2 | **Azure AI Apps and Agents Developer Associate** — exam **AI-103** | Associate | Build/deploy **generative + agentic** solutions on **Microsoft Foundry** (Python) | Cert: https://learn.microsoft.com/credentials/certifications/azure-ai-apps-and-agents-developer-associate/ · Study guide: https://aka.ms/AI103-StudyGuide · Skills outline: https://learn.microsoft.com/credentials/certifications/resources/study-guides/ai-103 | Udemy AI-103 / Foundry agent courses (below) |
| — | **AI-102** Azure AI Engineer Associate | Retired / legacy | Older “Azure AI Engineer” path | Check Learn for retirement notes | Migrate study time to **AI-103** |

### AI-103 skills at a glance (study blueprint)

| Domain (approx weight) | Focus | Maps to this repo |
|---|---|---|
| Plan & manage Azure AI (25–30%) | Foundry projects, models, quotas, CI/CD, safety | Deploy MAF + MCPs to Azure |
| Generative AI & **agentic** solutions (30–35%) | Agents, tools, RAG/grounding, eval, tracing | MAF + MCP tools + sessions |
| Computer vision (10–15%) | Vision services | Optional / interview breadth |
| Text analysis (10–15%) | NLP services | Optional |
| Information extraction (10–15%) | Extraction workloads | Related to document extraction story |

### Microsoft Learn (free) — Foundry + LangChain

| Resource | Link | Why |
|---|---|---|
| Microsoft Foundry docs | https://learn.microsoft.com/azure/ai-foundry/ | Deploy / agents / projects |
| LangChain + Foundry | https://learn.microsoft.com/azure/foundry/how-to/develop/langchain | `langchain-azure-ai` |
| LangGraph agents on Foundry | https://learn.microsoft.com/azure/foundry/how-to/develop/langchain-agents | Agent Service + graphs |
| AI-103 study guide | https://aka.ms/AI103-StudyGuide | Exam blueprint |
| Repo: Foundry + auth notes | [maf-basic/07-azure-foundry-deploy-and-auth.md](maf-basic/07-azure-foundry-deploy-and-auth.md) | Our deploy story |

---

## Coursera

| # | Topic | Course / specialization | Link | Level | Why it helps |
|---|---|---|---|---|---|
| 1 | GenAI + LLMs | Generative AI with Large Language Models (DeepLearning.AI + AWS) | https://www.coursera.org/learn/generative-ai-with-llms | Intermediate | Lifecycle, fine-tune, RLHF — strong fundamentals cert |
| 2 | Same (alt host) | Generative AI with LLMs — DeepLearning.AI site | https://www.deeplearning.ai/courses/generative-ai-with-llms | Intermediate | Same curriculum |
| 3 | LangChain intro | LangChain for LLM Application Development (Harrison Chase + Andrew Ng) | https://www.coursera.org/projects/langchain-for-llm-application-development-project · also https://www.deeplearning.ai/courses/langchain | Beginner | Models, memory, chains, RAG QA, agents — from LC creator |
| 4 | LCEL + tools + agents | Functions, Tools and Agents with LangChain | https://www.coursera.org/projects/functions-tools-and-agents-with-langchain-project · https://www.deeplearning.ai/courses/functions-tools-agents | Intermediate | Tool calling mindset → MAF / MCP |
| 5 | Microsoft AI Fundamentals | Microsoft Azure AI Fundamentals AI-900 Exam Prep Specialization | https://www.coursera.org/specializations/microsoft-azure-ai-900-ai-fundamentals | Beginner | Microsoft-taught path toward Azure AI Fundamentals |
| 6 | AI-900 prep module | Preparing for AI-900 | https://www.coursera.org/learn/microsoft-ai-900-exam-prep | Beginner | Practice toward fundamentals exam |
| 7 | Azure AI intro | Intro to Artificial Intelligence on Microsoft Azure | https://www.coursera.org/learn/intro-artificial-intelligence-microsoft-azure | Beginner | Workloads + responsible AI |
| 8 | AI-900 exam prep (alt) | Exam Prep AI-900 (Foundry / GenAI modules) | https://www.coursera.org/learn/exam-prep-ai-900-microsoft-certified-azure-ai-fundamentals | Beginner | Includes GenAI + Foundry-oriented content — confirm vs AI-901 |

> Tip: On Coursera, prefer **DeepLearning.AI** short courses for LangChain speed-runs, then **Microsoft** specializations for cert vocabulary, then Udemy for deep LangGraph/MCP projects.

---

## Master table — Udemy / YouTube (implementation depth)

| # | Topic | Platform | Course / video | Link | Level | Why it helps here |
|---|---|---|---|---|---|---|
| 1 | LangChain + LangGraph | Udemy | Agentic AI Engineering with LangChain & LangGraph (Eden Marco) | https://www.udemy.com/course/langchain/ | Intermediate | Best single paid stack course |
| 2 | LC + LG + LangSmith | Udemy | Complete LangChain, LangGraph, & LangSmith (2026) | https://www.udemy.com/course/the-complete-langchain-langgraph-langsmith-course/ | Intermediate | Graphs + tracing |
| 3 | LangChain classic | Udemy | LangChain with Python Bootcamp (Jose Portilla) | https://www.udemy.com/course/langchain-with-python-bootcamp/ | Beginner | Chains / memory / agents intro |
| 4 | LangGraph playlist | YouTube | LangGraph series (community) | https://youtube.com/playlist?list=PLjuA_yqsfemenaOq4hjs3zTRRXVlQM0gR | Beginner→Inter | Nodes → HITL / tools |
| 5 | LangChain official | YouTube | LangChain channel | https://www.youtube.com/@LangChain | All | Source of truth |
| 6 | Free structured LC/LG | Web | LangChain Academy | https://academy.langchain.com/ | Beginner→Inter | Free path |
| 7 | MCP full | YouTube | MCP Full Course (Ansh Lamba) | https://www.youtube.com/watch?v=io02ZM0ADqM | Beginner→Inter | HTTP MCP like our servers |
| 8 | MCP Python | YouTube | MCP Crash Course (Dave Ebbelaar) | https://www.youtube.com/watch?v=5xqFjh56AwM | Intermediate | Backend MCP client |
| 9 | MCP short | YouTube | MCP Explained for Beginners | https://www.youtube.com/watch?v=LYfr7qusVSs | Beginner | Concepts |
| 10 | MCP production | Udemy | MCP: Fundamentals to Production | https://www.udemy.com/course/model-context-protocol-mcp-fundamentals-to-production/ | Intermediate | Docker MCP |
| 11 | MCP + A2A | Udemy | MCP & A2A | https://www.udemy.com/course/modelcontextprotocol/ | Intermediate | Multi-agent + tools |
| 12 | Azure Foundry | Udemy | Azure AI Foundry: Prompt Flow, Finetuning, RAG, LLMOps | https://www.udemy.com/course/develop-generative-ai-apps-in-azure-ai-foundry/ | Intermediate | Foundry hands-on |
| 13 | AI-103 style | Udemy | AI-103 Azure AI App and Agent Developer | https://www.udemy.com/course/ai-103-azure-ai-app-and-agent-developer-complete-course/ | Intermediate | Cert-aligned agentic Azure |
| 14 | Foundry agents | Udemy | Agentic AI with Microsoft Foundry Agent Service | https://www.udemy.com/course/agentic-ai-development-with-azure-semantic-kernel/ | Intermediate | Agents / tools / memory |
| 15 | Foundry + APIM | Udemy | Productionize Foundry Agents with APIM | https://www.udemy.com/course/productionize-azure-ai-foundry-agents-with-api-management/ | Advanced | Prod gateway |
| 16 | FastAPI | Udemy | FastAPI topic (pick recent bestseller) | https://www.udemy.com/topic/fastapi/ | Beginner→Inter | Our `:8000` |
| 17 | MLflow GenAI | Docs | MLflow GenAI Tracing | https://mlflow.org/docs/latest/genai/tracing/ | Intermediate | Multi-LLM monitoring |

---

## By topic (quick links)

### A) LangChain / LCEL / RAG / agents

| Platform | Title | Link |
|---|---|---|
| Coursera / DL.AI | LangChain for LLM Application Development | https://www.deeplearning.ai/courses/langchain |
| Coursera / DL.AI | Functions, Tools and Agents with LangChain | https://www.deeplearning.ai/courses/functions-tools-agents |
| Udemy | Eden Marco LangChain + LangGraph | https://www.udemy.com/course/langchain/ |
| Udemy | Jose Portilla LangChain Bootcamp | https://www.udemy.com/course/langchain-with-python-bootcamp/ |
| Free | LangChain Academy | https://academy.langchain.com/ |
| Repo | [langchain-basic/](langchain-basic/) | — |

### B) LangGraph / HITL / memory

| Platform | Title | Link |
|---|---|---|
| Udemy | LangGraph modules (Eden Marco / Complete 2026) | https://www.udemy.com/course/langchain/ · https://www.udemy.com/course/the-complete-langchain-langgraph-langsmith-course/ |
| YouTube | Official LangChain/LangGraph | https://www.youtube.com/@LangChain |
| YouTube | LangGraph playlist | https://youtube.com/playlist?list=PLjuA_yqsfemenaOq4hjs3zTRRXVlQM0gR |
| Repo | [langgraph-basic/](langgraph-basic/) · [04-memory-management.md](langgraph-basic/04-memory-management.md) | — |

### C) Microsoft certs + Foundry / MAF

| Platform | Title | Link |
|---|---|---|
| Microsoft | Azure AI Fundamentals (AI-901) | https://learn.microsoft.com/credentials/certifications/azure-ai-fundamentals/ |
| Microsoft | Azure AI Apps and Agents Developer Associate (AI-103) | https://learn.microsoft.com/credentials/certifications/azure-ai-apps-and-agents-developer-associate/ |
| Coursera | Microsoft AI-900 Exam Prep Specialization | https://www.coursera.org/specializations/microsoft-azure-ai-900-ai-fundamentals |
| Udemy | AI-103 complete course | https://www.udemy.com/course/ai-103-azure-ai-app-and-agent-developer-complete-course/ |
| Repo | [maf-basic/](maf-basic/) · [07 Foundry deploy](maf-basic/07-azure-foundry-deploy-and-auth.md) | — |

### D) MCP / FastMCP

| Platform | Title | Link |
|---|---|---|
| YouTube | MCP Full Course | https://www.youtube.com/watch?v=io02ZM0ADqM |
| YouTube | MCP Crash Course | https://www.youtube.com/watch?v=5xqFjh56AwM |
| Udemy | MCP Fundamentals → Production | https://www.udemy.com/course/model-context-protocol-mcp-fundamentals-to-production/ |
| Repo | [mcp-basic/](mcp-basic/) | — |

---

## Free vs paid (quick pick)

| Budget | Do this |
|---|---|
| **Free** | LangChain Academy + DL.AI LangChain short + MCP YT full course + Microsoft Learn Foundry + this `interview-prep/` |
| **Coursera cert path** | GenAI with LLMs + Microsoft AI Fundamentals specialization → book **AI-901** (confirm current exam code) |
| **One Udemy** | https://www.udemy.com/course/langchain/ |
| **Microsoft associate** | After fundamentals + this repo: study **AI-103** + Foundry Udemy / Learn labs |
| **MCP deep** | Udemy MCP production course |

---

## 2-week plan (courses + this repo)

| Days | Course | Then open |
|---|---|---|
| 1–2 | Coursera / DL.AI GenAI with LLMs **or** Microsoft AI Fundamentals start | [00-elevator-pitch.md](00-elevator-pitch.md) |
| 3 | DL.AI LangChain short + Functions/Tools/Agents | [langchain-basic/](langchain-basic/) |
| 4–5 | Udemy LangGraph modules / YT playlist | [langgraph-basic/](langgraph-basic/), voice HITL |
| 6 | MCP YouTube full course | [mcp-basic/](mcp-basic/) |
| 7–8 | Microsoft Learn Foundry + AI-103 study guide skim | [maf-basic/](maf-basic/) |
| 9 | FastAPI crash | [fastapi-basic/](fastapi-basic/) |
| 10 | MLflow tracing docs + our report | [mcp-basic/ml-flow-implementation-report.md](mcp-basic/ml-flow-implementation-report.md) |
| 11–12 | Speak [qa-bank/](qa-bank/) + walk [what-happen-in-this-code/](what-happen-in-this-code/) | Interview mode |
| 13–14 | Optional: book AI-901 practice / continue AI-103 labs | Cert track |

---

## Disclaimer

- Not affiliated with Coursera, Udemy, YouTube instructors, or Microsoft.  
- Exam codes (**AI-900 / AI-901 / AI-102 / AI-103**) and course URLs change — always confirm on [Microsoft Learn Credentials](https://learn.microsoft.com/credentials/certifications/).  
- Official docs beat any course when APIs change.

# 04 — Agents, tools, memory

## Tools

A **tool** is a function the LLM can call (search, calculator, MCP tool, HTTP).

```python
from langchain_core.tools import tool

@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

tools = [add]
llm_with_tools = llm.bind_tools(tools)
```

---

## Tool-calling loop (conceptual)

```text
User → LLM
       │ may request tool_calls
       ▼
     Execute tool(s)
       │
       ▼
     Append ToolMessage → LLM again → final answer
```

**Interview:** Agents are powerful but harder to audit; prefer **LangGraph** when order/retries must be deterministic (like our document validate loop).

---

## Memory (chat history)

```python
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

store = {}

def get_history(session_id: str):
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are helpful."),
        ("placeholder", "{history}"),
        ("human", "{input}"),
    ]
)
base = prompt | llm | StrOutputParser()

chain_with_history = RunnableWithMessageHistory(
    base,
    get_history,
    input_messages_key="input",
    history_messages_key="history",
)

chain_with_history.invoke(
    {"input": "My name is Sam"},
    config={"configurable": {"session_id": "u1"}},
)
```

**Production:** persist history in Redis/DB; summarize long threads.

**In this repo:** voice HITL uses LangGraph **checkpoints / thread_id**, not a simple chat-memory chain.

---

## LangChain agent vs LangGraph vs MAF

| Approach | Best for |
|---|---|
| LCEL chain | Fixed prompt→LLM→parse |
| LangChain tool agent | Light tool use |
| **LangGraph** | Branching, retry, HITL, production workflows |
| **MAF** | Host agent that calls **MCP tools** across services |

Next: [05-this-repo-how-we-use-langchain.md](05-this-repo-how-we-use-langchain.md)

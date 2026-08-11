# 02 — LCEL chains (LangChain Expression Language)

## What is LCEL?

Composable **Runnables** joined with `|`. Same object supports:

- `.invoke(input)` — one shot  
- `.stream(input)` — token/chunk stream  
- `.batch([inputs])` — many inputs  

```python
chain = prompt | llm | parser
```

---

## Classic patterns

### 1) Prompt | LLM | Parser

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.chat_models import init_chat_model

llm = init_chat_model("openai:gpt-4o-mini", temperature=0)
prompt = ChatPromptTemplate.from_template("Translate to French: {text}")
chain = prompt | llm | StrOutputParser()

assert isinstance(chain.invoke({"text": "Hello"}), str)
```

### 2) Branching with `RunnableParallel`

```python
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

# Run two chains on the same input
fanout = RunnableParallel(
    summary=summary_chain,
    keywords=keywords_chain,
)
# fanout.invoke({"text": "..."}) → {"summary": "...", "keywords": "..."}
```

### 3) Passthrough + assign (RAG-style)

```python
from langchain_core.runnables import RunnablePassthrough

# {"question": "..."} → add context → prompt → llm
rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)
# Often written as:
# {"context": retriever | format_docs, "question": RunnablePassthrough()} | prompt | llm
```

See full RAG in [03-rag-with-langchain.md](03-rag-with-langchain.md).

### 4) Custom function as Runnable

```python
from langchain_core.runnables import RunnableLambda

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

format_docs_runnable = RunnableLambda(format_docs)
```

---

## Error handling / retries (talking point)

```python
from langchain_core.runnables import RunnableRetry

# Conceptual — wrap flaky LLM calls
safe_llm = llm.with_retry(stop_after_attempt=3)
chain = prompt | safe_llm | StrOutputParser()
```

Production tip: also cap `max_tokens`, handle rate limits (TPM), and log prompts/responses (this repo uses `traced_invoke` + xid).

---

## Interview whiteboard

```text
              ┌─────────────┐
 input dict → │   Prompt    │
              └──────┬──────┘
                     │ messages
              ┌──────▼──────┐
              │  ChatModel  │
              └──────┬──────┘
                     │ AIMessage
              ┌──────▼──────┐
              │   Parser    │ → Python str / Pydantic
              └─────────────┘
```

Next: [03-rag-with-langchain.md](03-rag-with-langchain.md)

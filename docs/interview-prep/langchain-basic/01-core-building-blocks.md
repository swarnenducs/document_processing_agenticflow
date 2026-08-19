# 01 — Core building blocks

## Mental model

```text
Input (user / system data)
   → PromptTemplate / ChatPromptTemplate   # shape the messages
   → ChatModel                             # call the LLM
   → OutputParser / structured output      # turn text → Python objects
   → Your app logic
```

---

## 1. Messages

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

messages = [
    SystemMessage(content="You are a contract field mapper. Return JSON only."),
    HumanMessage(content="Map this JSON onto placeholders: {...}"),
]
# After the model responds:
# AIMessage(content="{\"fields\": [...]}")
```

**Interview line:** “Chat models speak in message lists, not a single string prompt.”

---

## 2. Chat models

```python
# Modern / generic (LangChain 0.3+)
from langchain.chat_models import init_chat_model

llm = init_chat_model("openai:gpt-4o-mini", temperature=0)
# or: "groq:llama-3.3-70b-versatile", "azure_openai:<deployment>", ...

resp = llm.invoke([HumanMessage(content="Say hello in one word")])
print(resp.content)
```

Provider-specific style (still common in interviews):

```python
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq

openai_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
groq_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
```

**In this repo:** `llm_factory` builds mapper vs validator from env so you can mix Azure + Groq.

---

## 3. Prompt templates

### String prompt

```python
from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate.from_template(
    "Summarize this contract clause in one sentence:\n{clause}"
)
print(prompt.format(clause="The buyer shall pay within 30 days..."))
```

### Chat prompt (preferred)

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You extract fields. Output valid JSON only."),
        ("human", "Template placeholders:\n{placeholders}\n\nJSON data:\n{data}"),
    ]
)

messages = prompt.format_messages(
    placeholders="{{customer_name}}, {{amount}}",
    data='{"customer":{"name":"Acme"},"amount":1000}',
)
```

**YAML in this repo** (`document-processing-mcp/prompts/mapper.yml`) is the same idea: `system` + `human` loaded at runtime so prompts change without code deploy.

---

## 4. Output parsers / structured output

### Simple string

```python
from langchain_core.output_parsers import StrOutputParser

chain = prompt | llm | StrOutputParser()
text = chain.invoke({"clause": "..."})
```

### Structured (Pydantic) — production style

```python
from pydantic import BaseModel, Field
from typing import List

class FieldMap(BaseModel):
    placeholder: str
    value: str
    confidence: float = Field(ge=0, le=1)

class MappingResult(BaseModel):
    fields: List[FieldMap]

structured_llm = llm.with_structured_output(MappingResult)
result: MappingResult = structured_llm.invoke(messages)
print(result.fields[0].placeholder, result.fields[0].value)
```

**Interview line:** “Structured output + Pydantic beats regex-parsing free text.”

---

## 5. Minimal end-to-end “basic flow”

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.chat_models import init_chat_model

llm = init_chat_model("openai:gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a concise assistant."),
        ("human", "Explain {topic} in 2 bullet points."),
    ]
)

chain = prompt | llm | StrOutputParser()

print(chain.invoke({"topic": "RAG"}))
# stream:
for chunk in chain.stream({"topic": "LangGraph"}):
    print(chunk, end="", flush=True)
```

**Draw this in interviews:**

```text
ChatPromptTemplate  →  ChatModel  →  StrOutputParser
        \________________ LCEL chain ________________/
```

Next: [02-lcel-chains.md](02-lcel-chains.md)

# 05 — How *this repo* uses LangChain

## Where LangChain shows up

| Piece | Role |
|---|---|
| `llm_factory` | Build mapper / validator chat models from env |
| `services/prompts/` | Load YAML → `ChatPromptTemplate` / LCEL chain |
| `field_mapper` | Mapper LLM + structured mapping |
| `document_validator` | Critic LLM scores / feedback |
| LangGraph nodes | Call those services and update state |

**Not used as primary pattern here:** vector RAG over a corpus.

---

## Conceptual mapper chain (same idea as code)

```python
# Conceptual — mirrors document-processing-mcp field mapping
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List

class FieldMap(BaseModel):
    json_path: str
    placeholder: str
    value: str
    confidence: float = Field(ge=0, le=1)

class MappingOut(BaseModel):
    fields: List[FieldMap]

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "{system}"),   # from mapper.yml
        ("human", "{human}"),     # placeholders + JSON
    ]
)

# llm = get_mapper_llm() from llm_factory
structured = llm.with_structured_output(MappingOut)
chain = prompt | structured

result = chain.invoke(
    {
        "system": open("document-processing-mcp/prompts/mapper.yml").read(),  # simplified
        "human": "... placeholders + data ...",
    }
)
```

Real code loads YAML properly via `prompts/loader.py` and traces with `traced_invoke`.

---

## Dual-LLM design (talking point)

```text
JSON + template
    → Mapper LLM  (creative enough to bind fields)
    → Generate DOCX
    → Validator LLM (strict critic)
         ↓ fail + retries
      back to Mapper
```

Different providers allowed (e.g. Azure mapper, Groq validator) via env — classic GenAI cost/latency trade-off.

---

## Prompt files to open in interview

- `document-processing-mcp/prompts/mapper.yml`
- `document-processing-mcp/prompts/validator.yml`
- `document-processing-mcp/prompts/extraction_validator.yml`

---

## If they ask “Would you add RAG here?”

Possible answers:

1. **Contract catalog RAG** — retrieve similar past contracts / clause library before mapping.  
2. **Policy RAG** — retrieve legal playbooks for validator critic.  
3. Keep main path as structured mapping; use RAG as an *optional* context node in LangGraph.

Next: [06-interview-qa.md](06-interview-qa.md)

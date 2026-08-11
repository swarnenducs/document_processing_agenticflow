# 03 — RAG with LangChain (must-know for GenAI interviews)

> **RAG = Retrieval-Augmented Generation**  
> Instead of hoping the LLM “knows” your private docs, you **retrieve** relevant chunks and put them in the prompt.

This repo’s document filler is **not** classic RAG (it maps JSON → Word).  
Still, almost every GenAI interview asks you to explain RAG. Learn it here.

---

## End-to-end RAG flow (memorize + draw)

```text
1. Load documents      (PDF, Markdown, HTML, …)
2. Split into chunks    (size + overlap)
3. Embed chunks         (embedding model → vectors)
4. Store in Vector DB   (Chroma / FAISS / Pinecone / Azure AI Search)
5. At query time:
      question → embed → similarity search → top-k chunks
6. Build prompt with {context} + {question}
7. LLM generates answer (optionally cite sources)
```

```text
┌────────┐   ┌───────┐   ┌────────┐   ┌────────────┐
│ Load   │→ │ Split │→ │ Embed  │→ │ VectorStore│   (index time)
└────────┘   └───────┘   └────────┘   └────────────┘
                                              │
User question ──embed──► similarity search ◄──┘
         │
         ▼
   Prompt(context, question) → LLM → Answer
```

---

## Minimal working example (FAISS + OpenAI-style)

Install (conceptual): `langchain`, `langchain-openai`, `langchain-community`, `faiss-cpu`, `pypdf`

```python
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

# ---------- 1) LOAD ----------
loader = TextLoader("handbook.pdf")  # or DirectoryLoader, WebBaseLoader, ...
docs = loader.load()
# each doc: Document(page_content="...", metadata={...})

# ---------- 2) SPLIT ----------
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=120,
    separators=["\n\n", "\n", " ", ""],
)
chunks = splitter.split_documents(docs)

# ---------- 3) EMBED + 4) STORE ----------
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = FAISS.from_documents(chunks, embeddings)
# persist: vectorstore.save_local("faiss_index")

# ---------- 5) RETRIEVER ----------
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

def format_docs(docs):
    return "\n\n".join(
        f"[{i+1}] {d.page_content}" for i, d in enumerate(docs)
    )

# ---------- 6) PROMPT + 7) GENERATE ----------
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Answer using ONLY the context. If missing, say you don't know.\n\nContext:\n{context}",
        ),
        ("human", "{question}"),
    ]
)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

rag_chain = (
    {
        "context": retriever | RunnableLambda(format_docs),
        "question": RunnablePassthrough(),
    }
    | prompt
    | llm
    | StrOutputParser()
)

answer = rag_chain.invoke("What is the refund policy?")
print(answer)
```

---

## Index-time vs query-time

| Phase | Work | Frequency |
|---|---|---|
| **Index** | load → split → embed → upsert | When docs change |
| **Query** | embed question → retrieve → generate | Every user question |

**Interview tip:** Don’t re-embed the whole corpus on every request.

---

## Chunking — what to say

- Too small → lose context  
- Too large → noisy retrieval + token waste  
- Overlap helps continuity across boundaries  
- Prefer structure-aware splits (Markdown headers, pages) when possible  

```python
RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
```

---

## Similarity search variants

```python
# Dense vector similarity (default)
retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 5})

# MMR — diversify results (less redundant chunks)
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 5, "fetch_k": 20},
)
```

**Hybrid search (advanced talking point):** BM25 keyword + vector (e.g. EnsembleRetriever).

---

## RAG with sources (citations)

```python
from langchain_core.runnables import RunnableParallel

def format_with_meta(docs):
    return "\n\n".join(
        f"Source={d.metadata.get('source')} page={d.metadata.get('page')}\n{d.page_content}"
        for d in docs
    )

rag_with_sources = RunnableParallel(
    {
        "context": retriever | RunnableLambda(format_with_meta),
        "question": RunnablePassthrough(),
    }
) | prompt | llm | StrOutputParser()
```

---

## Advanced RAG patterns (name-drop correctly)

| Pattern | Idea |
|---|---|
| **Naive RAG** | top-k chunks → generate |
| **Multi-query** | LLM rewrites question into variants → union retrieve |
| **Parent-document** | retrieve small chunks, return larger parent |
| **Rerank** | retrieve 20 → cross-encoder rerank → top 5 |
| **Self-RAG / corrective** | model checks if retrieval is enough |
| **GraphRAG** | knowledge graph + vectors (heavier) |

---

## Failure modes (interview gold)

1. **Wrong chunk retrieved** → bad answer (garbage in)  
2. **Context overflow** → truncate or map-reduce summarize  
3. **Stale index** → docs updated but vectors not  
4. **Prompt injection** in retrieved text  
5. **Hallucination despite context** → ask model to quote / say “I don’t know”  

---

## How RAG differs from *this* project

| | Classic RAG | This document agentic flow |
|---|---|---|
| Goal | Q&A over a knowledge base | Fill Word template from JSON |
| Retrieval | Vector search | Placeholders + LLM field mapping |
| Control flow | Often a chain | **LangGraph** with validate/retry |
| Orchestration | Optional agent | MCP tools + optional **MAF** |

**Honest line in interview:**  
“Our product is a structured document pipeline with dual LLMs and LangGraph. I’ve also implemented/designed RAG using LangChain’s load→split→embed→retrieve→generate pattern when the problem is knowledge Q&A.”

Next: [04-agents-tools-memory.md](04-agents-tools-memory.md)

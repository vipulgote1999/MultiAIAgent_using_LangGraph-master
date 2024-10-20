import os
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.indexes.vectorstore import VectorStoreIndexWrapper
from langchain.schema import Document
from typing import List, Literal
from typing_extensions import TypedDict
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import WikipediaQueryRun
from langgraph.graph import END, StateGraph, START

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Step 1: Load documents from URLs
urls = [
    "https://lilianweng.github.io/posts/2023-06-23-agent/",
    "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
    "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
]

docs = [WebBaseLoader(url).load() for url in urls]
doc_list = [item for sublist in docs for item in sublist]
text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=500, chunk_overlap=0)
docs_split = text_splitter.split_documents(doc_list)

# Step 2: Use HuggingFace Embeddings and FAISS for Vector Search
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vector_store = FAISS.from_documents(docs_split, embeddings)

retriever = vector_store.as_retriever()

# Step 4: Set up the structured output and LLM router
class RouteQuery(TypedDict):
    datasource: Literal["vectorstore", "wiki_search"]

llm = ChatGroq(groq_api_key=GROQ_API_KEY, model_name="Llama-3.1-70b-Versatile")
structured_llm_router = llm.with_structured_output(RouteQuery)

system_prompt = """You are an expert at routing a user question to a vectorstore or Wikipedia.
The vectorstore contains documents related to agents, prompt engineering, and adversarial attacks.
Use the vectorstore for questions on these topics. Otherwise, use wiki-search."""
route_prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{question}")])
question_router = route_prompt | structured_llm_router

# Step 5: Wikipedia API setup
api_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=500)
wiki = WikipediaQueryRun(api_wrapper=api_wrapper)

# Step 6: Workflow Definition
class GraphState(TypedDict):
    question: str
    generation: str
    documents: List[str]

def retrieve(state):
  questions = state["question"]

  documents=retriever.invoke(questions)
  return {"documents": documents, "questions": questions}


def wiki_search(state):
  question = state["question"]

  docs=wiki.invoke({"query":question})
  wiki_results = docs
  wiki_results = Document(page_content = wiki_results)
  return {"documents": wiki_results, "questions": question}

def route_question(state):
      question = state["question"]
      source = question_router.invoke({"question": question})
      # Access the 'datasource' value from the dictionary
      if source["datasource"] == "wiki_search":
          return "wiki_search"
      elif source["datasource"] == "vectorstore":
          return "vectorstore"

workflow = StateGraph(GraphState)
workflow.add_node("wiki_search", wiki_search)
workflow.add_node("retrieve", retrieve)

workflow.add_conditional_edges(
    START,
    route_question,
    {
        "wiki_search": "wiki_search",
        "vectorstore": "retrieve",
    }
)

workflow.add_edge("retrieve", END)
workflow.add_edge("wiki_search", END)

app = workflow.compile()

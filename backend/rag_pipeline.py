import os
import pickle
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains import create_retrieval_chain, create_history_aware_retriever
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

# --- Configuration ---
DATA_DIR = os.path.join(os.path.dirname(__file__), ".data")
os.makedirs(DATA_DIR, exist_ok=True)

embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))

# --- NEW: Prompt for rephrasing a question based on history ---
contextualize_q_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "Given a chat history and the latest user question which might reference context in the chat history, formulate a standalone question which can be understood without the chat history. Do NOT answer the question, just reformulate it if needed and otherwise return it as is."),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
    ]
)

# --- NEW: Prompt for answering the question, same as before ---
qa_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant. Answer the user's question based only on the following context:\n\n{context}"),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
    ]
)

def create_and_save_index(session_id: str, content: str):
    """Chunks content, creates embeddings, and saves the FAISS index and chunks to disk."""
    session_path = os.path.join(DATA_DIR, session_id)
    os.makedirs(session_path, exist_ok=True)
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.create_documents([content])
    
    vector_store = FAISS.from_documents(docs, embedding_model)
    
    faiss_index_path = os.path.join(session_path, "index.faiss")
    vector_store.save_local(faiss_index_path)
    
    print(f"Index for session {session_id} saved successfully.")


def get_answer_from_query(session_id: str, query: str, chat_history: list) -> str:
    """
    Loads the index, and performs a history-aware RAG to get an answer.
    """
    session_path = os.path.join(DATA_DIR, session_id)
    faiss_index_path = os.path.join(session_path, "index.faiss")

    if not os.path.exists(faiss_index_path):
        raise FileNotFoundError(f"No index found for session ID: {session_id}")

    # 1. Load the vector store
    vector_store = FAISS.load_local(faiss_index_path, embedding_model, allow_dangerous_deserialization=True)
    retriever = vector_store.as_retriever()

    # 2. Create the history-aware retriever chain
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )

    # 3. Create the document chain for answering the question
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    
    # 4. Combine them into the final retrieval chain
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    # 5. Format the chat history for the model
    # The history from MongoDB needs to be converted to LangChain's message format
    formatted_history = []
    for turn in chat_history:
        formatted_history.append(HumanMessage(content=turn["question"]))
        formatted_history.append(AIMessage(content=turn["answer"]))

    # 6. Invoke the chain with history to get the answer
    response = rag_chain.invoke({
        "chat_history": formatted_history,
        "input": query
    })

    return response.get("answer", "Sorry, I couldn't generate an answer.")
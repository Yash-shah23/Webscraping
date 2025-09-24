import os
import uvicorn
import uuid
from dotenv import load_dotenv
import db
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rag_pipeline import RAGPipeline

load_dotenv()

CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH")
if not CHROME_DRIVER_PATH: raise ValueError("CHROME_DRIVER_PATH not set!")

app = FastAPI(title="In-Memory RAG API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# In-memory dictionary to hold active RAG pipelines for each session
ACTIVE_PIPELINES = {}

class URLRequest(BaseModel): url: str
class AskRequest(BaseModel): session_id: str; question: str

@app.post("/process-url")
def process_url_endpoint(request: URLRequest):
    existing_session = db.find_session_by_url(request.url)
    if existing_session:
        print(f"✅ Session for URL {request.url} already exists. Returning.")
        existing_session['session_id'] = existing_session['id']
        return existing_session

    print(f"Processing new session for URL: {request.url}")
    session_id = str(uuid.uuid4())
    
    # Create a new pipeline instance for this session
    pipeline = RAGPipeline(chromedriver_path=CHROME_DRIVER_PATH)
    scraped_content = pipeline.scrape_url(request.url)
    
    if not scraped_content:
        raise HTTPException(status_code=400, detail="Failed to scrape content from URL.")
    
    # Build the index in memory for the new pipeline
    pipeline.build_index_from_data(scraped_content)
    
    # Store the ready-to-use pipeline in our active dictionary
    ACTIVE_PIPELINES[session_id] = pipeline

    title = scraped_content[0].get("title", "Untitled")
    session = db.create_session(
        session_id=session_id,
        title=title,
        source_url=request.url,
        scraped_content=scraped_content
    )
    
    session['session_id'] = session['id']
    return session

@app.post("/ask")
def ask_question_endpoint(request: AskRequest):
    # 1. Look up the pipeline for this session in the server's memory.
    pipeline = ACTIVE_PIPELINES.get(request.session_id)

    # 2. If the pipeline is not in memory (e.g., after a server restart),
    #    rebuild its index from the raw text stored in the database.
    if not pipeline or not pipeline.is_ready:
        print(f"Index for session {request.session_id} not in memory. Rebuilding...")
        session_details = db.get_session_details(request.session_id)
        scraped_content = session_details.get("scraped_content")
        if not scraped_content:
            raise HTTPException(status_code=404, detail="Scraped content not found in DB to rebuild index.")
        
        # Create or get a pipeline instance and build its index
        pipeline = ACTIVE_PIPELINES.get(request.session_id, RAGPipeline(chromedriver_path=CHROME_DRIVER_PATH))
        pipeline.build_index_from_data(scraped_content)
        ACTIVE_PIPELINES[request.session_id] = pipeline

    # 3. Get the answer from the in-memory RAG pipeline.
    answer = pipeline.query(request.question)
    
    # 4. Save the new conversation turn to the database.
    db.add_conversation_turn(request.session_id, request.question, answer)
    
    return {"answer": answer}

@app.get("/sessions")
def get_sessions_list():
    sessions_list = db.get_sessions()
    return [{"session_id": s['id'], "title": s['title']} for s in sessions_list]

@app.get("/session/{session_id}")
def get_session_details_endpoint(session_id: str):
    session = db.get_session_details(session_id)
    if not session: raise HTTPException(status_code=404, detail="Session not found.")
    return session

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
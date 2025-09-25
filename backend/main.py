import uvicorn
import uuid
import db
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware # <-- Import the middleware
from pydantic import BaseModel
from rag_pipeline import RAGPipeline

app = FastAPI(title="Fast Persistent RAG API")

# vvvvvvvvvvvv FIX IS HERE vvvvvvvvvvvvv
# Add this middleware to handle CORS preflight requests from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods, including OPTIONS, POST, GET
    allow_headers=["*"],  # Allows all headers
)
# ^^^^^^^^^^^^ FIX IS HERE ^^^^^^^^^^^^^

pipeline = RAGPipeline()

class URLRequest(BaseModel): url: str
class AskRequest(BaseModel): session_id: str; question: str

def process_url_in_background(session_id: str, url: str):
    print(f"Background task started for session {session_id} and URL {url}")
    try:
        scraped_data = pipeline.scrape_concurrently(url, max_pages=25)
        if not scraped_data:
            raise ValueError("Failed to scrape any content from the URL.")
        
        pipeline.create_and_store_embeddings(
            session_id=session_id,
            page_data=scraped_data,
            supabase_client=db.supabase
        )
        
        db.update_session_status(session_id, "ready")
        print(f"✅ Background task finished successfully for session {session_id}")
        
    except Exception as e:
        print(f"❌ Background task failed for session {session_id}: {e}")
        db.update_session_status(session_id, "failed", error_message=str(e))


@app.post("/process-url")
def process_url_endpoint(request: URLRequest, background_tasks: BackgroundTasks):
    existing_session = db.find_session_by_url(request.url)
    if existing_session:
        print(f"✅ Session for URL {request.url} already exists. Returning.")
        existing_session['session_id'] = existing_session['id']
        return existing_session

    print(f"Processing new session for URL: {request.url}")
    session_id = str(uuid.uuid4())
    
    session = db.create_session(
        session_id=session_id,
        title=f"Processing: {request.url}",
        source_url=request.url
    )
    
    background_tasks.add_task(process_url_in_background, session_id, request.url)
    
    session['session_id'] = session['id']
    return session

@app.post("/ask")
def ask_question_endpoint(request: AskRequest):
    session_details = db.get_session_details(request.session_id)
    if not session_details:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    if session_details.get("status") != "ready":
        return {"answer": f"The content for this session is still being processed. Current status: {session_details.get('status', 'unknown')}"}

    answer = pipeline.answer_question(
        session_id=request.session_id,
        question=request.question,
        supabase_client=db.supabase
    )
    
    db.add_conversation_turn(request.session_id, request.question, answer)
    
    return {"answer": answer}

@app.get("/sessions")
def get_sessions_list():
    sessions_list = db.get_sessions()
    return [{"session_id": s['id'], "title": s['title'], "status": s.get('status', 'unknown')} for s in sessions_list]

@app.get("/session/{session_id}")
def get_session_details_endpoint(session_id: str):
    session = db.get_session_details(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
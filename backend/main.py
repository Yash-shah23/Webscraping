import os
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
from datetime import datetime, timezone

# Import our custom modules
from db import connect_to_mongo, close_mongo_connection, get_database
from scraper import crawl_and_get_content 
from rag_pipeline import create_and_save_index, get_answer_from_query

load_dotenv()

# --- Pydantic Models ---
class UrlRequest(BaseModel):
    url: str

class ProcessResponse(BaseModel):
    message: str
    session_id: str
    title: str
class AskRequest(BaseModel):
    session_id: str
    question: str
class AskResponse(BaseModel):
    answer: str
class SessionInfo(BaseModel):
    session_id: str
    title: str

# --- FastAPI App ---
app = FastAPI(
    title="Chat with URL API",
    description="API for scraping a URL and answering questions about its content.",
    version="1.0.0"
)

# --- Event Handlers for DB Connection ---
@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---
@app.post("/process-url", response_model=ProcessResponse)
async def process_url_endpoint(request: UrlRequest):
    try:
        session_id = str(uuid.uuid4())
        
        content, title = crawl_and_get_content(request.url)
        
        create_and_save_index(session_id, content)

        db = get_database()
        await db.sessions.insert_one({
            "session_id": session_id,
            "title": title,
            "url": request.url,
            "created_at": datetime.now(timezone.utc),
            "conversation": []
        })

        return ProcessResponse(
            message="Site crawled successfully.",
            session_id=session_id,
            title=title
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/ask", response_model=AskResponse)
async def ask_question_endpoint(request: AskRequest):
    try:
        db = get_database()
        session = await db.sessions.find_one({"session_id": request.session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
            
        # --- THIS IS THE FIX ---
        # 1. Get the conversation history from the session document
        chat_history = session.get("conversation", [])
        
        # 2. Pass the question AND the history to the RAG pipeline
        answer = get_answer_from_query(request.session_id, request.question, chat_history)
        # ---------------------
        
        new_message = {
            "question": request.question,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc)
        }
        
        await db.sessions.update_one(
            {"session_id": request.session_id},
            {"$push": {"conversation": new_message}}
        )

        return AskResponse(answer=answer)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/sessions", response_model=List[SessionInfo])
async def get_all_sessions_endpoint():
    try:
        db = get_database()
        sessions_cursor = db.sessions.find({}, {"_id": 0, "session_id": 1, "title": 1}).sort("created_at", -1)
        sessions = await sessions_cursor.to_list(length=100)
        return sessions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/session/{session_id}")
async def get_session_details(session_id: str):
    try:
        db = get_database()
        session = await db.sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# --- Uvicorn Runner ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
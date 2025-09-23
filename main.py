

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rag_pipeline import RAGPipeline
import uvicorn

# --- STEP 1: DEFINE YOUR DRIVER PATH HERE ---
# Use a raw string (r"...") for Windows paths to avoid errors.
CHROME_DRIVER_PATH = r"C:\Users\Hp\Desktop\Yash\Webscraping\chromedriver-win64\chromedriver-win64\chromedriver.exe"

app = FastAPI(
    title="Advanced RAG API",
    description="Crawls an entire website, caches the content, and allows Q&A.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- STEP 2: PASS THE PATH WHEN CREATING THE PIPELINE ---
# The path variable from above is now passed to the RAGPipeline.
rag_pipe = RAGPipeline(chromedriver_path=CHROME_DRIVER_PATH)

class URLRequest(BaseModel):
    url: str

class QueryRequest(BaseModel):
    question: str

@app.post("/load-url")
def load_url_endpoint(request: URLRequest):
    success = rag_pipe.load_url(request.url)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to scrape or process the URL.")
    return {"message": f"Successfully loaded and indexed content from {request.url}"}

@app.post("/ask")
def ask_question_endpoint(request: QueryRequest):
    if not rag_pipe.is_ready:
        raise HTTPException(status_code=400, detail="No URL has been loaded yet.")
    answer = rag_pipe.query(request.question)
    return {"question": request.question, "answer": answer}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
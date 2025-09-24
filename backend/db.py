import os
from supabase import create_client, Client
from postgrest.exceptions import APIError
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("Supabase URL and Key must be set in the .env file.")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def find_session_by_url(url: str):
    try:
        response = supabase.table("sessions").select("id, title, conversation").eq("source_url", url).maybe_single().execute()
        return response.data
    except APIError as e:
        if e.code == "204": return None
        raise e

def create_session(session_id: str, title: str, source_url: str, scraped_content: list):
    """Creates a new session, storing the raw scraped content."""
    response = supabase.table("sessions").insert({
        "id": session_id,
        "title": title,
        "source_url": source_url,
        "scraped_content": scraped_content
    }).execute()
    if response.data: return response.data[0]
    raise Exception("Failed to create session.")

def get_sessions():
    response = supabase.table("sessions").select("id, title").order("created_at", desc=True).execute()
    return response.data

def get_session_details(session_id: str):
    response = supabase.table("sessions").select("*").eq("id", session_id).single().execute()
    return response.data

def add_conversation_turn(session_id: str, question: str, answer: str):
    session_details = get_session_details(session_id)
    current_conversation = session_details.get("conversation", [])
    current_conversation.append({"question": question, "answer": answer})
    supabase.table("sessions").update({"conversation": current_conversation}).eq("id", session_id).execute()

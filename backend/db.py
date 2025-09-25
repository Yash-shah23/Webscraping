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
        response = supabase.table("sessions").select("id, title, conversation, status").eq("source_url", url).maybe_single().execute()
        
        # --- FIX IS HERE ---
        # If the API call fails in a way that returns None, handle it gracefully.
        if not response:
            return None
            
        return response.data
        # --- END OF FIX ---

    except APIError as e:
        if e.code == "204": return None
        raise e
    except Exception as e:
        print(f"An unexpected error occurred connecting to Supabase: {e}")
        return None

def create_session(session_id: str, title: str, source_url: str):
    """Creates a new session record with a 'processing' status."""
    response = supabase.table("sessions").insert({
        "id": session_id,
        "title": title,
        "source_url": source_url,
        "status": "processing"
    }).execute()
    if response.data: return response.data[0]
    raise Exception("Failed to create session.")

def update_session_status(session_id: str, status: str, error_message: str = None):
    """Updates the status of a session (e.g., to 'ready' or 'failed')."""
    update_data = {"status": status}
    if error_message:
        update_data["error_message"] = error_message
    response = supabase.table("sessions").update(update_data).eq("id", session_id).execute()
    return response.data

def get_sessions():
    response = supabase.table("sessions").select("id, title, status").order("created_at", desc=True).execute()
    return response.data

def get_session_details(session_id: str):
    response = supabase.table("sessions").select("*").eq("id", session_id).single().execute()
    return response.data

def add_conversation_turn(session_id: str, question: str, answer: str):
    session_details = get_session_details(session_id)
    current_conversation = session_details.get("conversation", [])
    if current_conversation is None: current_conversation = []
    current_conversation.append({"question": question, "answer": answer})
    supabase.table("sessions").update({"conversation": current_conversation}).eq("id", session_id).execute()
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

db_manager = MongoDB()

async def connect_to_mongo():
    """Connects to the MongoDB instance."""
    print("Connecting to MongoDB...")
    db_manager.client = AsyncIOMotorClient(MONGO_URI)
    db_manager.db = db_manager.client[MONGO_DB_NAME]
    print("Successfully connected to MongoDB.")

async def close_mongo_connection():
    """Closes the MongoDB connection."""
    print("Closing MongoDB connection...")
    db_manager.client.close()
    print("MongoDB connection closed.")

def get_database():
    """Returns the database instance."""
    return db_manager.db
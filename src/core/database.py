"""
Database dependency for FastAPI
"""

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import MongoClient
from src.config.settings import MONGODB_CONFIG

# Global MongoDB client
mongo_client: MongoClient | None = None
mongo_db: AsyncIOMotorDatabase | None = None


def get_database() -> AsyncIOMotorDatabase:
    """
    Dependency to get MongoDB database connection
    
    Returns:
        AsyncIOMotorDatabase: MongoDB database instance
        
    Raises:
        HTTPException: If database connection is not available
    """
    global mongo_db
    
    if mongo_db is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503, 
            detail="MongoDB connection not available"
        )
    
    return mongo_db


def init_database():
    """
    Initialize MongoDB connection
    This should be called during application startup
    """
    global mongo_client, mongo_db
    
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        
        # Create async MongoDB client
        mongo_client = AsyncIOMotorClient(MONGODB_CONFIG["url"])
        mongo_db = mongo_client[MONGODB_CONFIG["database"]]
        
        return mongo_db
    except Exception as e:
        raise Exception(f"Failed to initialize MongoDB: {e}")


def close_database():
    """
    Close MongoDB connection
    This should be called during application shutdown
    """
    global mongo_client, mongo_db
    
    if mongo_client:
        mongo_client.close()
        mongo_client = None
        mongo_db = None
import os
from dotenv import load_dotenv

# Load environment variables from the local .env file into Python
load_dotenv()

class Config:
    """
    Configuration class storing environment settings for the Flask application.
    Each variable is fetched from the .env file with a default fallback value.
    """
    
    # Secret key used by Flask for session management and security hashing
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default-dev-secret-key-12345")

    # Database connection URL for SQLite (used by Flask-SQLAlchemy)
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///smartsearch.db")

    # Turn off Flask-SQLAlchemy modification tracking to save memory
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # API key for accessing Google Gemini API services
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

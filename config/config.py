import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# .env is in the telecom_assistant directory (one level up from config)
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

class Config:
    """Configuration settings for the application."""
    
    # OpenAI Settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
    
    # Paths
    PROJECT_ROOT = project_root
    DATA_DIR = PROJECT_ROOT / "data"
    DOCUMENTS_DIR = DATA_DIR / "documents"
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "telecom.db"))
    
    # Make sure we have an absolute path for the DB if it's relative
    if not os.path.isabs(DATABASE_PATH):
        DATABASE_PATH = str(PROJECT_ROOT / DATABASE_PATH)

    @classmethod
    def validate(cls):
        """Validate critical configuration."""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables.")
        if not os.path.exists(cls.DATABASE_PATH):
            print(f"Warning: Database not found at {cls.DATABASE_PATH}")

# Validate on import (optional, or can be called explicitly)
# Config.validate()

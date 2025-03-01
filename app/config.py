# config.py
# Configuration

import os
from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env file

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:4321/image_processor_db")

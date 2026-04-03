from app import create_app, db
from app.models import Book
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Create app instance at module level for Vercel WSGI compatibility
app = create_app()

# Database initialization is already handled safely inside create_app()

# Local development server
if __name__ == '__main__':
    app.run(debug=True, port=5001)

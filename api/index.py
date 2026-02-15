"""
Vercel serverless function entry point for Flask app
"""
import sys
import os

# Add parent directory to path to import app module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app

# Create Flask app instance
app = create_app()

# Vercel serverless function handler
# This will handle all incoming requests
def handler(request, context):
    return app(request, context)

# For Vercel's WSGI compatibility
application = app

# For local testing compatibility
if __name__ == "__main__":
    app.run(debug=True, port=5001)

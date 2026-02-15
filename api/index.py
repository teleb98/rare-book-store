"""
Vercel serverless function entry point for Flask app
"""
import sys
import os

# Add parent directory to path to import app module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app

# Create Flask app instance for Vercel
# Vercel's Python runtime automatically handles WSGI apps
app = create_app()


from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    # Configuration
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, '../data/site.db')
    
    # Ensure database directory exists
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    except OSError:
        pass # Handle read-only file systems or other errors gracefully if needed

    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'dev-secret-key-change-this-in-prod'

    db.init_app(app)

    # Import and register routes
    from app.routes import main
    app.register_blueprint(main)
    
    # Create DB tables if they don't exist
    with app.app_context():
        from app.models import Book
        db.create_all()

    # Global Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    return app

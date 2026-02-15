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
        pass # Handle read-only file systems

    # Ensure static book covers directory exists
    covers_path = os.path.join(base_dir, 'static/book_covers')
    try:
        os.makedirs(covers_path, exist_ok=True)
    except OSError:
        pass

    # Database Configuration
    # Priority: DATABASE_URL (PostgreSQL for production) > SQLite (local development)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Fix Render/Heroku/Supabase postgres:// to postgresql:// for SQLAlchemy 1.4+
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print(f"✓ Using PostgreSQL database (production mode)")
    else:
        # Local Development: Use SQLite
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        print(f"✓ Using SQLite database (development mode): {db_path}")
        
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Use environment SECRET_KEY if available, otherwise fallback to dev key
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this-in-prod')

    db.init_app(app)

    # Import and register routes
    from app.routes import main
    app.register_blueprint(main)
    
    # Create DB tables if they don't exist
    with app.app_context():
        from app.models import Book
        db.create_all()

        # --- Auto-Migration: Add image_data column if missing ---
        # This is critical for Render where we can't easily run manual migrations
        try:
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('book')]
            if 'image_data' not in columns:
                print("Migrating: Adding 'image_data' column to 'book' table...")
                with db.engine.connect() as conn:
                    # SQLite and PostgreSQL syntax for ADD COLUMN is compatible for this simple case
                    conn.execute(db.text("ALTER TABLE book ADD COLUMN image_data TEXT"))
                    conn.commit()
                print("Migration complete: 'image_data' column added.")
        except Exception as e:
            print(f"Migration check failed (safe to ignore if app works): {e}")
        # --------------------------------------------------------

    # Global Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    return app

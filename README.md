# Rare Book Online Store

A Flask-based application for managing a rare book inventory. Features a modern UI with Tailwind CSS, stock management with atomic updates, and an admin dashboard.

## Features

- **Storefront**: Browse rare books with card layout.
- **Stock Management**: 
    - Real-time stock tracking.
    - Atomic updates to prevent overselling.
    - "Out of Stock" indicators.
- **Admin Dashboard**: 
    - CRUD operations for books.
    - Inventory table view.
- **API**: 
    - `/books` (GET): List all books.
    - `/books/<id>` (GET): Get book details.

## Setup Instructions

### 1. Create Virtual Environment
It is recommended to use a virtual environment to manage dependencies.

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize Database
The application will automatically create the SQLite database (`data/site.db`) on the first run.

### 4. Run the Application
```bash
python run.py
```

The application will be available at `http://127.0.0.1:5001`.

## Project Structure

- `app/`: Application source code.
    - `templates/`: HTML templates (Tailwind CSS).
    - `models.py`: Database models.
    - `routes.py`: Application logic and API.
- `data/`: SQLite database storage.
- `run.py`: Application entry point.

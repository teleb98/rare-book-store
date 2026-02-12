# Rare Book Online Store

A Flask-based application for managing a rare book inventory. Features a modern UI with Tailwind CSS, AI-powered book analysis, stock management with atomic updates, and an admin dashboard.

## Features

- **Storefront**: Browse rare books with card layout
- **AI-Powered Book Analysis**: Automatic metadata extraction from book cover images using Google Gemini
- **Stock Management**: 
    - Real-time stock tracking
    - Atomic updates to prevent overselling
    - "Out of Stock" indicators
- **Smart Recommendations**:
    - Internal recommendations based on author and publication year
    - External recommendations from Open Library API (with Google Books fallback)
- **Admin Dashboard**: 
    - CRUD operations for books
    - Inventory table view
    - AI-assisted book entry
- **API**: 
    - `/books` (GET): List all books
    - `/books/<id>` (GET): Get book details

## API Services

This application uses the following **free** APIs:

1. **Open Library API** (Primary): Completely free book metadata and cover images
   - No API key required
   - Rich metadata from Internet Archive
   - Best practice: Include User-Agent header for high-volume requests

2. **Google Books API** (Fallback): Free with rate limits
   - No API key required for basic usage
   - Automatic fallback when Open Library is unavailable

3. **Google Gemini AI** (Optional): For automatic book analysis from cover images
   - Requires API key (free tier available)
   - Set `GOOGLE_API_KEY` environment variable

## Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/teleb98/rare-book-store.git
cd rare-book-store
```

### 2. Create Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables

Create a `.env` file in the project root (optional for local development):

```bash
# Optional: Google Gemini API for AI book analysis
GOOGLE_API_KEY=your_google_api_key_here

# Admin password for dashboard access
ADMIN_PASSWORD=your_secure_password

# Flask secret key
SECRET_KEY=your_random_secret_key
```

### 5. Initialize Database

The application will automatically create the SQLite database (`data/site.db`) on the first run.

### 6. Run the Application

```bash
python run.py
```

The application will be available at `http://127.0.0.1:5001`.

## Deployment Options

### Option 1: Render (Recommended)

Render offers a generous free tier with easy deployment:

1. Fork this repository to your GitHub account
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click "New +" and select "Web Service"
4. Connect your GitHub repository
5. Render will automatically detect `render.yaml` configuration
6. Set environment variables in Render dashboard:
   - `GOOGLE_API_KEY` (optional)
   - `ADMIN_PASSWORD` (required)
7. Click "Create Web Service"

Your app will be live at `https://your-app-name.onrender.com`

**Note**: Free tier apps sleep after 15 minutes of inactivity. First request after sleep takes ~30 seconds.

### Option 2: Railway

Railway provides simple deployment with automatic HTTPS:

1. Fork this repository
2. Go to [Railway](https://railway.app/)
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your forked repository
5. Railway auto-detects Python and uses `railway.json` config
6. Add environment variables in Railway dashboard
7. Deploy!

**Free tier**: $5 monthly credit (enough for small projects)

### Option 3: Fly.io

For global edge deployment:

```bash
# Install Fly CLI
brew install flyctl  # macOS
# or: curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Initialize and configure
flyctl launch

# Set environment variables
flyctl secrets set GOOGLE_API_KEY=your_key_here
flyctl secrets set ADMIN_PASSWORD=your_password_here

# Deploy
flyctl deploy

# Open your app
flyctl open
```

**Free tier**: 3 VMs with 256MB RAM each

### Environment Variables for Deployment

All platforms require these environment variables:

- `GOOGLE_API_KEY`: (Optional) For AI book analysis feature
- `ADMIN_PASSWORD`: (Required) Password for admin dashboard access
- `SECRET_KEY`: (Auto-generated on most platforms) Flask session secret
- `PORT`: (Auto-set by platform) Application port

## Project Structure

- `app/`: Application source code
    - `templates/`: HTML templates (Tailwind CSS)
    - `models.py`: Database models
    - `routes.py`: Application logic and API
    - `utils.py`: API utilities (Open Library & Google Books)
- `data/`: SQLite database storage
- `run.py`: Application entry point
- `render.yaml`: Render.com deployment configuration
- `railway.json`: Railway deployment configuration
- `Dockerfile`: Docker containerization
- `Procfile`: Process configuration (legacy Heroku format)

## Technology Stack

- **Backend**: Flask, SQLAlchemy
- **Database**: SQLite (local), PostgreSQL (production ready)
- **AI**: Google Gemini for image analysis
- **APIs**: Open Library (primary), Google Books (fallback)
- **Frontend**: Tailwind CSS
- **Deployment**: Render / Railway / Fly.io compatible

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

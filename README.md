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

### Option 1: Vercel + Supabase (Recommended - 100% FREE Forever)

**Vercel** offers a generous free Hobby plan with **no time limits**. Combined with **Supabase PostgreSQL** (free 500MB), you get a completely free, production-ready deployment.

#### Step 1: Setup Supabase Database (Free PostgreSQL)

1. Go to [Supabase](https://supabase.com) and create a free account
2. Click "New Project"
3. Fill in project details:
   - Name: `rare-book-store`
   - Database Password: Create a strong password (save it!)
   - Region: Choose closest to your users
4. Wait 2-3 minutes for database provisioning
5. Go to **Settings** → **Database**
6. Copy the **Connection String (URI)** under "Connection string"
   - Format: `postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`
   - Make sure to replace `[YOUR-PASSWORD]` with your actual database password

#### Step 2: Deploy to Vercel

1. **Fork this repository** to your GitHub account (if you haven't already)

2. Go to [Vercel](https://vercel.com) and sign up with GitHub

3. Click **"Add New Project"** → **"Import Git Repository"**

4. Select your `rare-book-store` repository

5. Configure your project:
   - **Framework Preset**: Other
   - **Build Command**: (leave empty)
   - **Output Directory**: (leave empty)

6. **Add Environment Variables**:
   - `DATABASE_URL`: Your Supabase connection string from Step 1
   - `ADMIN_PASSWORD`: Your admin dashboard password (create a secure one)
   - `GOOGLE_API_KEY`: (Optional) Your Google Gemini API key for AI features
   - `SECRET_KEY`: (Optional) A random string for Flask sessions (auto-generated if not provided)

7. Click **"Deploy"**

8. Wait 2-3 minutes for deployment to complete

9. Your app will be live at: `https://rare-book-store-[random].vercel.app`

#### First-Time Database Setup

After deploying, visit your Vercel URL once. The app will automatically:
- Create database tables (books)
- Initialize the schema

Then you can:
- Access the storefront: `https://your-app.vercel.app/`
- Login to admin dashboard: `https://your-app.vercel.app/login`
- Add your rare books via the admin interface

#### Custom Domain (Optional)

In Vercel Dashboard → Settings → Domains, you can add a custom domain for free.

**Vercel Free Tier Limits** (More than enough for this app):
- Serverless functions: 100GB-hrs/month
- Bandwidth: 100GB/month
- Deployments: Unlimited
- **No sleep/downtime** (unlike Render free tier)

---

### Option 2: Render (Free with limitations)

Render offers a free tier but with limitations:

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

**⚠️ Important Limitations**:
- Free tier apps **sleep after 15 minutes** of inactivity
- First request after sleep takes **30-60 seconds** (cold start)
- Free PostgreSQL database expires after **90 days**

---

### Option 3: Railway (Paid - $5/month minimum)

Railway provides simple deployment but **no longer offers a free tier**:

1. Fork this repository
2. Go to [Railway](https://railway.app/)
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your forked repository
5. Railway auto-detects Python and uses `railway.json` config
6. Add environment variables in Railway dashboard
7. Deploy!

**Cost**: $5/month minimum (includes $5 usage credits)

---

### Option 4: Fly.io (Paid - ~$2-3/month)

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

**Cost**: ~$2-3/month for a small Flask app

---

### Comparison Table

| Platform | Cost | Cold Start | Database | Best For |
|----------|------|------------|----------|----------|
| **Vercel + Supabase** | **FREE** | None | PostgreSQL (500MB) | **Recommended** |
| Render | FREE | 30-60s | PostgreSQL (90 days) | Testing only |
| Railway | $5/month | None | Included | Production apps |
| Fly.io | $2-3/month | Minimal | Extra cost | Global distribution |

### Environment Variables for Deployment

All platforms require these environment variables:

**Required:**
- `DATABASE_URL`: PostgreSQL connection string from Supabase (or other provider)
  - Example: `postgresql://postgres:[password]@[host]:5432/postgres`
- `ADMIN_PASSWORD`: Password for admin dashboard access

**Optional:**
- `GOOGLE_API_KEY`: For AI book analysis feature (Google Gemini)
- `SECRET_KEY`: Flask session encryption key (auto-generated if not set)
- `PORT`: Application port (auto-set by most platforms)

## Project Structure

- `app/`: Application source code
    - `templates/`: HTML templates (Tailwind CSS)
    - `models.py`: Database models
    - `routes.py`: Application logic and API
    - `utils.py`: API utilities (Open Library & Google Books)
- `api/`: Vercel serverless functions
    - `index.py`: Vercel entry point (WSGI handler)
- `data/`: SQLite database storage (local development only)
- `run.py`: Application entry point
- `vercel.json`: **Vercel deployment configuration** ⭐
- `.vercelignore`: Files to exclude from Vercel deployment
- `render.yaml`: Render.com deployment configuration
- `railway.json`: Railway deployment configuration
- `Dockerfile`: Docker containerization
- `Procfile`: Process configuration (legacy Heroku format)

## Technology Stack

- **Backend**: Flask, SQLAlchemy
- **Database**: PostgreSQL (Supabase) for production, SQLite for local development
- **AI**: Google Gemini for image analysis
- **APIs**: Open Library (primary), Google Books (fallback)
- **Frontend**: Tailwind CSS
- **Deployment**: Vercel (recommended), Render, Railway, Fly.io compatible

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

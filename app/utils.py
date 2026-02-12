import requests
from typing import List, Dict, Optional

# User-Agent header for API requests (best practice for Open Library)
USER_AGENT = "RareBookStore/1.0 (Flask-based rare book inventory app)"

def search_open_library(title: str, author: str) -> List[Dict[str, Optional[str]]]:
    """
    Search for books on Open Library API based on author.
    Returns a list of dictionaries with title, author, thumbnail, and link.
    
    Open Library is completely free and provides rich metadata.
    """
    if not title or not author:
        return []

    try:
        # Search by author using Open Library Search API
        query = f"author:{author}"
        url = f"https://openlibrary.org/search.json?q={query}&limit=10&lang=ko"
        
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        docs = data.get('docs', [])
        
        results = []
        for doc in docs:
            book_title = doc.get('title', 'Unknown Title')
            
            # Skip if it's the same book (case-insensitive check)
            if title.lower() in book_title.lower():
                continue
            
            # Get authors
            book_authors = doc.get('author_name', ['Unknown'])
            
            # Get cover image using Open Library Covers API
            # Cover ID can be from cover_i (preferred) or isbn
            thumbnail = None
            cover_id = doc.get('cover_i')
            if cover_id:
                # Use Medium size (M) for better quality
                thumbnail = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
            elif doc.get('isbn'):
                # Fallback to ISBN-based cover
                isbn = doc['isbn'][0]
                thumbnail = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
            
            # Get Open Library link
            key = doc.get('key', '')
            info_link = f"https://openlibrary.org{key}" if key else '#'
            
            results.append({
                'title': book_title,
                'author': ', '.join(book_authors[:2]),  # Limit to 2 authors for readability
                'thumbnail': thumbnail,
                'link': info_link
            })
            
            if len(results) >= 4:
                break
        
        print(f"Open Library API: Found {len(results)} recommendations")
        return results
        
    except requests.exceptions.Timeout:
        print("Open Library API: Request timed out")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Open Library API: Network error - {e}")
        return []
    except Exception as e:
        print(f"Open Library API: Unexpected error - {e}")
        return []


def search_google_books(title: str, author: str) -> List[Dict[str, Optional[str]]]:
    """
    Search for books on Google Books API based on title and author.
    Returns a list of dictionaries with title, author, thumbnail, and link.
    
    This is now used as a fallback when Open Library fails.
    """
    if not title or not author:
        return []

    try:
        # Construct query: inauthor:{author}, order by newest
        query = f"inauthor:{author}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&orderBy=newest&maxResults=10&langRestrict=ko"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        items = data.get('items', [])
        
        results = []
        for item in items:
            volume_info = item.get('volumeInfo', {})
            
            # Extract relevant info
            book_title = volume_info.get('title', 'Unknown Title')
            
            # Skip if it's the same book (simple exact match check)
            if title.lower() in book_title.lower():
                continue
            book_authors = volume_info.get('authors', ['Unknown'])
            
            # Get thumbnail if available, and try to upgrade quality
            image_links = volume_info.get('imageLinks', {})
            thumbnail = image_links.get('thumbnail')
            if thumbnail:
                # Force HTTPS
                thumbnail = thumbnail.replace('http://', 'https://')
                # Remove edge=curl if present (often causes curled page effect)
                thumbnail = thumbnail.replace('&edge=curl', '')
                # Try to get higher resolution (zoom=1 is usually small)
                # We can try replacing zoom=1 with zoom=0, or removing it.
                # Often zoom=0 gives a larger image if available.
                thumbnail = thumbnail.replace('&zoom=1', '&zoom=0')
            
            # Info link
            info_link = volume_info.get('infoLink', '#')
            
            results.append({
                'title': book_title,
                'author': ', '.join(book_authors),
                'thumbnail': thumbnail,
                'link': info_link
            })
            
            if len(results) >= 4:
                break
        
        print(f"Google Books API: Found {len(results)} recommendations")
        return results
        
    except requests.exceptions.Timeout:
        print("Google Books API: Request timed out")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Google Books API: Network error - {e}")
        return []
    except Exception as e:
        print(f"Google Books API: Unexpected error - {e}")
        return []


def search_books_with_fallback(title: str, author: str) -> List[Dict[str, Optional[str]]]:
    """
    Search for book recommendations with automatic fallback.
    
    Strategy:
    1. Try Open Library API first (completely free, rich metadata)
    2. If Open Library fails or returns no results, try Google Books API
    3. If both fail, return empty list
    
    Args:
        title: Title of the current book
        author: Author of the current book
        
    Returns:
        List of recommended books with metadata
    """
    print(f"Searching recommendations for '{title}' by {author}")
    
    # Try Open Library first
    results = search_open_library(title, author)
    
    # Fallback to Google Books if needed
    if not results:
        print("Open Library returned no results, trying Google Books...")
        results = search_google_books(title, author)
    
    if not results:
        print("No recommendations found from any API")
    
    return results

import requests

def search_google_books(title, author):
    """
    Search for books on Google Books API based on title and author.
    Returns a list of dictionaries with title, author, thumbnail, and link.
    """
    if not title or not author:
        return []

    try:
        # Construct query: inauthor:{author}, order by newest
        query = f"inauthor:{author}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&orderBy=newest&maxResults=10&langRestrict=ko"
        
        response = requests.get(url)
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
            
            # Get thumbnail if available
            image_links = volume_info.get('imageLinks', {})
            thumbnail = image_links.get('thumbnail')
            
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
            
        return results
        
    except Exception as e:
        print(f"Error searching Google Books: {e}")
        return []

import requests
import os
import json
from urllib.parse import urlparse, parse_qs, unquote
from typing import List, Dict, Optional


def upgrade_cover_url(url: Optional[str]) -> Optional[str]:
    """저해상도 썸네일 URL을 고해상도 원본 URL로 변환한다.

    - 카카오: search1.kakaocdn.net/thumb/R120x174.../?fname=<원본> 형태 → fname 원본 추출(120px→약 458px)
    - 그 외(네이버/구글/오픈라이브러리): 이미 충분한 해상도라 그대로 반환
    """
    if not url:
        return url
    try:
        if 'kakaocdn.net' in url and 'fname=' in url:
            fname = parse_qs(urlparse(url).query).get('fname', [None])[0]
            if fname:
                return unquote(fname)
    except Exception:
        pass
    return url


# 표지 이미지를 서버에서 직접 다운로드할 때 허용하는 호스트 (카카오/네이버/구글북스/오픈라이브러리 CDN만 허용).
# 관리자가 폼으로 임의 URL을 보내 서버가 내부망/클라우드 메타데이터 등으로 요청을 보내는 SSRF를 막기 위함.
ALLOWED_COVER_IMAGE_HOSTS = (
    'daumcdn.net', 'kakaocdn.net',          # 카카오
    'pstatic.net',                          # 네이버
    'googleusercontent.com', 'books.google.com', 'google.com',  # 구글 북스
    'openlibrary.org',                      # 오픈라이브러리
)


def is_allowed_cover_image_url(url: Optional[str]) -> bool:
    """표지 이미지 URL이 신뢰하는 도서 검색 제공자의 CDN 호스트인지 확인한다 (SSRF 방지)."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = (parsed.hostname or '').lower()
        return any(host == h or host.endswith('.' + h) for h in ALLOWED_COVER_IMAGE_HOSTS)
    except Exception:
        return False


# User-Agent header for API requests (best practice for Open Library)
USER_AGENT = "RareBookStore/1.0 (Flask-based rare book inventory app)"

# 도서 장르 자동 태깅용 분류 체계
GENRE_TAXONOMY = [
    "고전문학", "현대소설", "인문/교양", "과학/대중과학",
    "역사", "에세이/철학", "예술/디자인", "경제/경영", "기타"
]


def auto_tag_genre(title: str, author: str, description: Optional[str]) -> List[str]:
    """
    Gemini를 사용해 책의 제목/저자/설명으로 장르를 1~2개 자동 분류한다.
    GOOGLE_API_KEY가 없거나 호출이 실패하면 빈 리스트를 반환한다 (호출부에서 '기타' 등 기본값 처리).
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return []

    import google.generativeai as genai
    genai.configure(api_key=api_key)

    prompt = f"""다음 책을 아래 장르 목록 중 1~2개로 분류하세요. 목록에 있는 표기를 정확히 그대로 사용하고, 새로운 장르명을 만들지 마세요.
장르 목록: {GENRE_TAXONOMY}

제목: {title}
저자: {author}
설명: {description or '(설명 없음)'}

반드시 아래와 같은 JSON 배열 형식으로만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.
예: ["고전문학"]"""

    try:
        model = genai.GenerativeModel('gemini-flash-latest')
        # 호출 1건이 너무 오래 걸려 gunicorn 워커 타임아웃(전체 배치)을 다 잡아먹지 않도록 개별 타임아웃을 둔다.
        response = model.generate_content(prompt, request_options={'timeout': 20})
        json_text = response.text.replace('```json', '').replace('```', '').strip()
        genres = json.loads(json_text)
        if not isinstance(genres, list):
            return []
        valid = [g for g in genres if g in GENRE_TAXONOMY][:2]
        return valid or ["기타"]
    except Exception as e:
        print(f"장르 자동 태깅 실패 ('{title}'): {e}")
        return []

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

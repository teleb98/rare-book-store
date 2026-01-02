from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from app import db
from app.models import Book
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text, cast, String
import google.generativeai as genai
import os
import json
from PIL import Image
import io

# Configure Gemini
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


main = Blueprint('main', __name__)

# --- Public Routes ---

@main.route('/')
def index():
    query = request.args.get('q')
    if query:
        search_filter = f"%{query}%"
        books = Book.query.filter(
            (Book.title.ilike(search_filter)) | 
            (Book.author.ilike(search_filter)) |
            (Book.description.ilike(search_filter)) |
            (Book.condition.ilike(search_filter)) |
            (cast(Book.year, String).ilike(search_filter))
        ).all()
    else:
        books = Book.query.all()
    return render_template('index.html', books=books, search_query=query)

@main.route('/books', methods=['GET'])
def get_books():
    books = Book.query.all()
    book_list = [{
        'id': b.id, 'title': b.title, 'author': b.author,
        'year': b.year, 'edition': b.edition, 'condition': b.condition,
        'price': b.price, 'stock_quantity': b.stock_quantity
    } for b in books]
    return jsonify(book_list)

@main.route('/books/<int:id>', methods=['GET'])
def get_book(id):
    book = Book.query.get_or_404(id)
    return jsonify({
        'id': book.id, 'title': book.title, 'author': book.author,
        'year': book.year, 'edition': book.edition, 'condition': book.condition,
        'price': book.price, 'stock_quantity': book.stock_quantity,
        'description': book.description
    })

@main.route('/book/<int:id>')
def book_detail(id):
    book = Book.query.get_or_404(id)
    return render_template('detail.html', book=book)

@main.route('/purchase/<int:id>', methods=['POST'])
def purchase(id):
    try:
        # Atomic Update for Concurrency Control
        stmt = text("UPDATE book SET stock_quantity = stock_quantity - 1 WHERE id = :id AND stock_quantity > 0")
        result = db.session.execute(stmt, {'id': id})
        db.session.commit()

        if result.rowcount == 1:
            flash('구매가 완료되었습니다!', 'success')
        else:
            flash('재고가 없거나 유효하지 않은 도서입니다.', 'error')
            
    except SQLAlchemyError as e:
        db.session.rollback()
        flash('구매 중 오류가 발생했습니다.', 'error')
        print(f"Purchase Error: {e}")

    return redirect(url_for('main.index'))

# --- Admin Routes ---

@main.route('/admin')
def admin():
    books = Book.query.all()
    return render_template('admin.html', books=books)

@main.route('/admin/add', methods=['GET', 'POST'])
def admin_add():
    if request.method == 'POST':
        try:
            # 1. Get Inputs
            price = float(request.form['price'])
            stock = int(request.form['stock_quantity'])
            image_file = request.files.get('book_image')

            # 2. Check for image
            if not image_file:
                flash('도서 표지 이미지를 업로드해주세요.', 'error')
                return redirect(request.url)

            # 3. Gemini Processing
            # 3. Gemini Processing
            if not GOOGLE_API_KEY:
                flash('Google API Key를 찾을 수 없습니다. 자동 분석을 수행할 수 없습니다.', 'error')
                return redirect(request.url)
            
            # Save file locally
            from werkzeug.utils import secure_filename
            import uuid
            
            filename = secure_filename(image_file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(current_app.root_path, 'static/book_covers', unique_filename)
            
            # Reset pointer for saving (since we read it for Gemini)
            image_file.seek(0)
            image_file.save(save_path)

            # Read bytes again for Gemini (or use the previous read if still in memory, but safer to read from file or reset stream)
            image_file.seek(0)
            image_bytes = image_file.read()
            img = Image.open(io.BytesIO(image_bytes))

            model = genai.GenerativeModel('gemini-flash-latest')
            prompt = """
            Analyze this book cover image.
            1. Identify the Title and Author of the book from the text on the cover.
            2. Using your internal knowledge about this specific book (based on the identified Title/Author), generate a "description" that serves as a curatorial note.
            
            IMPORTANT: The 'description' field MUST be written in Korean (한국어).
            The description should NOT just describe the cover art.
            Instead, explain the book's plot, themes, literary significance, and why it is worth collecting.
            Make it engaging and professional, like a museum curator introducing a masterpiece.

            Return strictly valid JSON:
            {
                "title": "Book Title (Identified from cover)",
                "author": "Author Name (Identified from cover)",
                "year": 1900 (Use an estimated year if not visible, as integer),
                "edition": "First Edition (or 'Unknown')",
                "condition": "Good (Estimate based on visual wear)",
                "description": "A rich, engaging curation note about the book's content and literary value. WRITE THIS IN KOREAN."
            }
            """
            
            response = model.generate_content([prompt, img])
            # Parse JSON - Simple cleanup if markdown is present
            json_text = response.text.replace('```json', '').replace('```', '').strip()
            book_data = json.loads(json_text)

            # 4. Save to DB
            new_book = Book(
                title=book_data.get('title', 'Unknown Title'),
                author=book_data.get('author', 'Unknown Author'),
                year=int(book_data.get('year', 0)),
                edition=book_data.get('edition', ''),
                condition=book_data.get('condition', 'Good'),
                price=price,
                stock_quantity=stock,
                description=book_data.get('description', ''),
                image_file=unique_filename
            )
            db.session.add(new_book)
            db.session.commit()
            
            flash(f"도서 '{new_book.title}' 추가 성공! (AI 분석 완료)", 'success')
            return redirect(url_for('main.admin'))

        except ValueError:
            flash('가격 자릿수 또는 재고 입력이 올바르지 않습니다.', 'error')
        except json.JSONDecodeError:
            flash('AI 분석 응답을 처리하는데 실패했습니다. 다시 시도해주세요.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'오류가 발생했습니다: {str(e)}', 'error')
            print(f"Error: {e}")

    return render_template('admin_form.html', action='Add', book=None)

@main.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
def admin_edit(id):
    book = Book.query.get_or_404(id)
    if request.method == 'POST':
        try:
            book.title = request.form['title']
            book.author = request.form['author']
            book.year = int(request.form['year'])
            book.edition = request.form.get('edition')
            book.condition = request.form['condition']
            book.price = float(request.form['price'])
            book.stock_quantity = int(request.form['stock_quantity'])
            book.description = request.form.get('description')

            db.session.commit()
            flash('도서 정보가 수정되었습니다!', 'success')
            return redirect(url_for('main.admin'))
        except ValueError:
            flash('가격, 재고 또는 연도 입력이 올바르지 않습니다.', 'error')
        except SQLAlchemyError:
            db.session.rollback()
            flash('데이터베이스 오류가 발생했습니다.', 'error')

    return render_template('admin_form.html', action='Edit', book=book)

@main.route('/admin/delete/<int:id>', methods=['POST'])
def admin_delete(id):
    book = Book.query.get_or_404(id)
    try:
        db.session.delete(book)
        db.session.commit()
        flash('도서가 삭제되었습니다.', 'success')
    except SQLAlchemyError:
        db.session.rollback()
        flash('삭제 중 오류가 발생했습니다.', 'error')
    return redirect(url_for('main.admin'))

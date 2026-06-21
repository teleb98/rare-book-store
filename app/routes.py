from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, session
from functools import wraps
from app import db
from app.models import Book, User, Review, Order, RestockRequest, CartItem
from app.mailer import send_email, is_email_configured
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text, cast, String
import google.generativeai as genai
import os
import json
import secrets
from PIL import Image
import io
import base64

from app.utils import search_books_with_fallback, auto_tag_genre, GENRE_TAXONOMY, upgrade_cover_url, is_allowed_cover_image_url
from app.oauth import PROVIDERS, is_provider_configured, build_authorize_url, exchange_code_for_profile
# Configure Gemini
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


main = Blueprint('main', __name__)


@main.app_context_processor
def inject_cart_count():
    """네비게이션 바의 장바구니 뱃지에 쓸 총 수량을 모든 템플릿에서 바로 쓸 수 있게 한다."""
    if session.get('user_id'):
        count = db.session.query(db.func.sum(CartItem.quantity)).filter_by(user_id=session['user_id']).scalar() or 0
        return {'cart_count': count}
    return {'cart_count': 0}


# --- Authentication Decorator ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('로그인이 필요합니다.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


def member_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('로그인 후 이용할 수 있습니다.', 'error')
            return redirect(url_for('main.member_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Login Routes ---

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin1234').strip()
        
        # Debug Logs (Check Render Logs tab)
        print(f"DEBUG: Login Attempt.")
        print(f"DEBUG: Input Password Length: {len(password)}")
        print(f"DEBUG: Admin Password Length: {len(admin_password)}")
        print(f"DEBUG: ADMIN_PASSWORD env var present: {'ADMIN_PASSWORD' in os.environ}")
        
        if password == admin_password:
            session['is_admin'] = True
            flash('관리자 모드로 로그인되었습니다.', 'success')
            return redirect(url_for('main.admin'))
        else:
            flash('비밀번호가 올바르지 않습니다.', 'error')
            
    return render_template('login.html')

@main.route('/logout')
def logout():
    session.pop('is_admin', None)
    flash('로그아웃되었습니다.', 'success')
    return redirect(url_for('main.index'))


# --- Member Social Login (카카오 / 네이버 / 구글) ---

@main.route('/member/login')
def member_login():
    if session.get('user_id'):
        return redirect(url_for('main.index'))
    providers_status = {p: is_provider_configured(p) for p in PROVIDERS}
    return render_template('member_login.html', providers_status=providers_status)


@main.route('/member/logout')
def member_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    flash('로그아웃되었습니다.', 'success')
    return redirect(url_for('main.index'))


@main.route('/auth/<provider>/login')
def oauth_login(provider):
    if provider not in PROVIDERS or not is_provider_configured(provider):
        flash('해당 소셜 로그인은 아직 설정되지 않았습니다.', 'error')
        return redirect(url_for('main.member_login'))

    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    session['oauth_provider'] = provider
    return redirect(build_authorize_url(provider, state))


@main.route('/auth/<provider>/callback')
def oauth_callback(provider):
    if provider not in PROVIDERS:
        flash('알 수 없는 로그인 경로입니다.', 'error')
        return redirect(url_for('main.member_login'))

    if request.args.get('error'):
        flash('소셜 로그인이 취소되었습니다.', 'error')
        return redirect(url_for('main.member_login'))

    state = request.args.get('state')
    if not state or state != session.get('oauth_state') or provider != session.get('oauth_provider'):
        flash('로그인 요청이 유효하지 않습니다. 다시 시도해주세요.', 'error')
        return redirect(url_for('main.member_login'))
    session.pop('oauth_state', None)
    session.pop('oauth_provider', None)

    code = request.args.get('code')
    if not code:
        flash('로그인에 실패했습니다.', 'error')
        return redirect(url_for('main.member_login'))

    try:
        profile = exchange_code_for_profile(provider, code)
    except Exception as e:
        print(f"OAuth 콜백 실패 ({provider}): {e}")
        flash('소셜 로그인 처리 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('main.member_login'))

    if not profile or not profile.get('provider_id'):
        flash('사용자 정보를 가져오지 못했습니다.', 'error')
        return redirect(url_for('main.member_login'))

    try:
        user = User.query.filter_by(provider=provider, provider_id=profile['provider_id']).first()
        if not user:
            user = User(
                provider=provider,
                provider_id=profile['provider_id'],
                email=profile.get('email'),
                name=profile.get('name'),
            )
            db.session.add(user)
        else:
            if profile.get('name'):
                user.name = profile['name']
            if profile.get('email'):
                user.email = profile['email']
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"OAuth 사용자 저장 실패 ({provider}): {e}")
        flash('로그인 처리 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('main.member_login'))

    session['user_id'] = user.id
    session['user_name'] = user.name or '회원'
    flash(f"{session['user_name']}님, 환영합니다!", 'success')

    # 선호 장르를 아직 선택하지 않은 회원(신규 가입 포함)은 장르 선택부터 안내
    if not user.preferred_genres:
        return redirect(url_for('main.member_genres'))
    return redirect(url_for('main.index'))


@main.route('/member/mypage')
@member_required
def member_mypage():
    """마이페이지 — 주문내역/선호장르 등 회원 전용 메뉴를 한곳에 모은 허브"""
    user = User.query.get_or_404(session['user_id'])
    recent_orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc(), Order.id.desc()).limit(3).all()
    order_count = Order.query.filter_by(user_id=user.id).count()
    preferred_genre_list = user.preferred_genres.split(',') if user.preferred_genres else []
    return render_template(
        'member_mypage.html', user=user, recent_orders=recent_orders,
        order_count=order_count, preferred_genre_list=preferred_genre_list,
    )


@main.route('/member/genres', methods=['GET', 'POST'])
@member_required
def member_genres():
    user = User.query.get_or_404(session['user_id'])

    if request.method == 'POST':
        if request.form.get('action') == 'skip':
            user.preferred_genres = None
            db.session.commit()
            flash('선호 장르 없이 전체 컬렉션을 보여드릴게요.', 'success')
            return redirect(url_for('main.index'))

        selected = [g for g in request.form.getlist('genres') if g in GENRE_TAXONOMY]
        user.preferred_genres = ','.join(selected) if selected else None
        db.session.commit()
        if selected:
            flash('선호 장르가 저장되었습니다. 맞춤 추천을 보여드릴게요!', 'success')
        else:
            flash('선호 장르 없이 전체 컬렉션을 보여드릴게요.', 'success')
        return redirect(url_for('main.index'))

    current_genres = user.preferred_genres.split(',') if user.preferred_genres else []
    return render_template('member_genres.html', genre_taxonomy=GENRE_TAXONOMY, current_genres=current_genres)


# --- Public Routes ---

@main.route('/privacy')
def privacy():
    return render_template('privacy.html')


@main.route('/terms')
def terms():
    return render_template('terms.html')


@main.route('/')
def index():
    query          = request.args.get('q', '').strip()
    condition_filter = request.args.get('condition', '').strip()
    price_filter   = request.args.get('price', '').strip()
    avail_filter   = request.args.get('avail', '').strip()
    year_filter    = request.args.get('year', '').strip()
    edition_filter = request.args.get('edition', '').strip()
    sort           = request.args.get('sort', '').strip()

    books_q = Book.query

    # 텍스트 검색
    if query:
        search_filter = f"%{query}%"
        books_q = books_q.filter(
            (Book.title.ilike(search_filter)) |
            (Book.author.ilike(search_filter)) |
            (Book.description.ilike(search_filter)) |
            (Book.condition.ilike(search_filter)) |
            (cast(Book.year, String).ilike(search_filter))
        )

    # 컨디션 필터
    if condition_filter:
        books_q = books_q.filter(Book.condition == condition_filter)

    # 가격 필터
    if price_filter:
        parts = price_filter.split('-')
        if len(parts) == 2:
            low, high = parts
            if low:  books_q = books_q.filter(Book.price >= float(low))
            if high and high != '0': books_q = books_q.filter(Book.price <= float(high))

    # 재고 필터
    if avail_filter == 'in_stock':
        books_q = books_q.filter(Book.stock_quantity > 0)
    # sold_out 선택 시 전체 표시 (품절 포함)

    # 출판연도대 필터
    if year_filter == 'pre1900':
        books_q = books_q.filter(Book.year < 1900)
    elif year_filter == '1900-1950':
        books_q = books_q.filter(Book.year >= 1900, Book.year <= 1950)
    elif year_filter == '1951-2000':
        books_q = books_q.filter(Book.year >= 1951, Book.year <= 2000)
    elif year_filter == '2001-now':
        books_q = books_q.filter(Book.year >= 2001)

    # 판본 필터 (자유 텍스트 필드라 키워드 매칭)
    edition_keywords = {
        'first':   ['초판', '1st', 'first'],
        'reprint': ['재판', 'reprint'],
        'limited': ['한정판', 'limited'],
    }
    if edition_filter in edition_keywords:
        conds = [Book.edition.ilike(f'%{kw}%') for kw in edition_keywords[edition_filter]]
        books_q = books_q.filter(db.or_(*conds))

    # 정렬
    if sort == 'price_asc':
        books_q = books_q.order_by(Book.price.asc())
    elif sort == 'price_desc':
        books_q = books_q.order_by(Book.price.desc())
    elif sort == 'year_desc':
        books_q = books_q.order_by(Book.year.desc())
    elif sort == 'year_asc':
        books_q = books_q.order_by(Book.year.asc())
    else:
        books_q = books_q.order_by(Book.id.desc())

    books = books_q.all()

    ratings = {}
    for book in books:
        if book.reviews:
            ratings[book.id] = (round(sum(r.rating for r in book.reviews) / len(book.reviews), 1), len(book.reviews))

    # 선호 장르 기반 맞춤 추천 — 필터/검색이 전혀 없는 기본 화면에서만 상단에 노출
    recommended_books = []
    preferred_genre_list = []
    no_filters_active = not any([query, condition_filter, price_filter, avail_filter, year_filter, edition_filter, sort])
    if no_filters_active and session.get('user_id'):
        member = User.query.get(session['user_id'])
        if member and member.preferred_genres:
            preferred_genre_list = member.preferred_genres.split(',')
            genre_conds = [Book.genre.ilike(f'%{g}%') for g in preferred_genre_list]
            recommended_books = Book.query.filter(db.or_(*genre_conds)).order_by(Book.id.desc()).all()

    return render_template(
        'index.html',
        books=books,
        ratings=ratings,
        search_query=query or None,
        condition_filter=condition_filter,
        price_filter=price_filter,
        avail_filter=avail_filter,
        year_filter=year_filter,
        edition_filter=edition_filter,
        sort=sort,
        recommended_books=recommended_books,
        preferred_genre_list=preferred_genre_list,
    )

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
    
    # Recommendation Logic: Same Author OR Similar Era (+/- 20 years)
    similar_books = Book.query.filter(
        (Book.id != book.id) & 
        (
            (Book.author == book.author) | 
            ((Book.year >= book.year - 20) & (Book.year <= book.year + 20))
        )
    ).limit(4).all()

    # Web Search Recommendations (with automatic fallback)
    web_recommendations = search_books_with_fallback(book.title, book.author)

    # 평점/리뷰: 최신순 정렬, 평균과 개수는 Python에서 계산 (소규모 카탈로그라 충분)
    reviews = sorted(book.reviews, key=lambda r: r.created_at, reverse=True)
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    my_review = next((r for r in reviews if r.user_id == session.get('user_id')), None)

    return render_template(
        'detail.html', book=book, similar_books=similar_books, web_recommendations=web_recommendations,
        reviews=reviews, avg_rating=avg_rating, avg_rating_floor=int(avg_rating) if avg_rating else 0,
        review_count=len(reviews), my_review=my_review,
    )


@main.route('/book/<int:id>/review', methods=['POST'])
@member_required
def submit_review(id):
    book = Book.query.get_or_404(id)
    try:
        rating = int(request.form.get('rating', ''))
    except (TypeError, ValueError):
        flash('평점을 선택해주세요.', 'error')
        return redirect(url_for('main.book_detail', id=id))

    if rating < 0 or rating > 5:
        flash('평점은 0점에서 5점 사이여야 합니다.', 'error')
        return redirect(url_for('main.book_detail', id=id))

    comment = request.form.get('comment', '').strip()

    try:
        review = Review.query.filter_by(book_id=book.id, user_id=session['user_id']).first()
        if review:
            review.rating = rating
            review.comment = comment
        else:
            review = Review(book_id=book.id, user_id=session['user_id'], rating=rating, comment=comment)
            db.session.add(review)
        db.session.commit()
        flash('리뷰가 등록되었습니다. 감사합니다!', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"리뷰 저장 실패: {e}")
        flash('리뷰 저장 중 오류가 발생했습니다.', 'error')

    return redirect(url_for('main.book_detail', id=id))


@main.route('/cart/add/<int:id>', methods=['POST'])
@member_required
def cart_add(id):
    book = Book.query.get_or_404(id)
    try:
        qty = max(1, int(request.form.get('quantity', 1)))
    except (TypeError, ValueError):
        qty = 1

    if book.stock_quantity <= 0:
        flash('품절된 도서는 장바구니에 담을 수 없습니다.', 'error')
        return redirect(url_for('main.book_detail', id=id))

    item = CartItem.query.filter_by(user_id=session['user_id'], book_id=book.id).first()
    if item:
        item.quantity += qty
    else:
        item = CartItem(user_id=session['user_id'], book_id=book.id, quantity=qty)
        db.session.add(item)
    db.session.commit()
    flash(f"'{book.title}'을 장바구니에 담았습니다.", 'success')
    return redirect(request.referrer or url_for('main.index'))


@main.route('/cart')
@member_required
def cart_view():
    items = (CartItem.query.filter_by(user_id=session['user_id'])
             .join(Book).order_by(CartItem.created_at.desc()).all())
    total = sum(i.subtotal for i in items)
    return render_template('cart.html', items=items, total=total)


@main.route('/cart/update/<int:item_id>', methods=['POST'])
@member_required
def cart_update(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=session['user_id']).first_or_404()
    try:
        qty = int(request.form.get('quantity', 1))
    except (TypeError, ValueError):
        qty = 1

    if qty <= 0:
        db.session.delete(item)
        flash('장바구니에서 제거했습니다.', 'success')
    else:
        item.quantity = qty
        flash('수량을 변경했습니다.', 'success')
    db.session.commit()
    return redirect(url_for('main.cart_view'))


@main.route('/cart/remove/<int:item_id>', methods=['POST'])
@member_required
def cart_remove(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=session['user_id']).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('장바구니에서 제거했습니다.', 'success')
    return redirect(url_for('main.cart_view'))


@main.route('/checkout', methods=['GET', 'POST'])
@member_required
def checkout():
    """결제(배송지 입력) 페이지. '바로 주문하기'(book_id 파라미터 있음)와
    장바구니 결제(파라미터 없음 — 현재 회원의 장바구니 전체) 두 흐름을 공용으로 처리한다."""
    buy_now_id = request.values.get('book_id', type=int)
    buy_now_qty = request.values.get('qty', type=int) or 1

    if buy_now_id:
        book = Book.query.get_or_404(buy_now_id)
        line_items = [{'book': book, 'quantity': max(1, buy_now_qty)}]
    else:
        cart_items = CartItem.query.filter_by(user_id=session['user_id']).join(Book).all()
        line_items = [{'book': ci.book, 'quantity': ci.quantity} for ci in cart_items]

    if not line_items:
        flash('주문할 상품이 없습니다.', 'error')
        return redirect(url_for('main.cart_view'))

    total = sum(li['book'].price * li['quantity'] for li in line_items)

    if request.method == 'POST':
        recipient_name = request.form.get('recipient_name', '').strip()
        phone = request.form.get('phone', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        address1 = request.form.get('address1', '').strip()
        address2 = request.form.get('address2', '').strip()
        memo = request.form.get('memo', '').strip()

        if not all([recipient_name, phone, postal_code, address1]):
            flash('받는 분 이름·연락처·우편번호·주소는 필수 입력입니다.', 'error')
            return render_template('checkout.html', items=line_items, total=total,
                                    buy_now_id=buy_now_id, buy_now_qty=buy_now_qty, form=request.form)

        order_group_id = secrets.token_hex(8)
        try:
            for li in line_items:
                stmt = text("UPDATE book SET stock_quantity = stock_quantity - :qty "
                            "WHERE id = :id AND stock_quantity >= :qty")
                result = db.session.execute(stmt, {'qty': li['quantity'], 'id': li['book'].id})
                if result.rowcount != 1:
                    db.session.rollback()
                    flash(f"'{li['book'].title}'의 재고가 부족합니다. 수량을 확인해주세요.", 'error')
                    return redirect(url_for('main.cart_view') if not buy_now_id
                                     else url_for('main.checkout', book_id=buy_now_id, qty=buy_now_qty))

                db.session.add(Order(
                    user_id=session['user_id'], book_id=li['book'].id, book_title=li['book'].title,
                    price=li['book'].price, quantity=li['quantity'], status='received',
                    order_group_id=order_group_id,
                    recipient_name=recipient_name, phone=phone, postal_code=postal_code,
                    address1=address1, address2=address2, delivery_memo=memo,
                ))

            if not buy_now_id:
                CartItem.query.filter_by(user_id=session['user_id']).delete()

            db.session.commit()
            flash('주문이 접수되었습니다. 확인 후 관리자가 직접 연락드립니다.', 'success')
            return redirect(url_for('main.member_orders'))

        except SQLAlchemyError as e:
            db.session.rollback()
            flash('주문 처리 중 오류가 발생했습니다.', 'error')
            print(f"Checkout error: {e}")

    return render_template('checkout.html', items=line_items, total=total,
                            buy_now_id=buy_now_id, buy_now_qty=buy_now_qty)


def _group_orders(orders):
    """order_group_id가 같은 행들을 한 주문으로 묶는다. (그룹ID 없는 옛 단건 주문은 각자 독립 그룹)
    이미 최신순으로 정렬된 리스트를 그대로 순회해 그룹의 표시 순서도 최신순을 유지한다."""
    groups, seen = [], {}
    for o in orders:
        key = o.order_group_id or f'single-{o.id}'
        if key not in seen:
            seen[key] = {'group_id': key, 'orders': [], 'created_at': o.created_at, 'status': o.status}
            groups.append(seen[key])
        seen[key]['orders'].append(o)
    for g in groups:
        g['total'] = sum(o.subtotal for o in g['orders'])
    return groups


@main.route('/member/orders')
@member_required
def member_orders():
    """회원 주문 내역 — 같은 결제로 묶인 여러 권은 하나의 주문으로 표시"""
    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.created_at.desc(), Order.id.desc()).all()
    groups = _group_orders(orders)
    return render_template('member_orders.html', groups=groups, status_labels=Order.STATUS_LABELS)

# --- Admin Routes ---



@main.route('/notify', methods=['POST'])
def notify_request():
    """입고 알림 신청 — 이름 + 이메일을 DB에 저장"""
    book_id = request.form.get('book_id')
    name    = request.form.get('name', '').strip()
    email   = request.form.get('email', '').strip()

    book = Book.query.get(book_id) if book_id else None
    if not book:
        flash('유효하지 않은 도서입니다.', 'error')
        return redirect(url_for('main.index'))
    if not email:
        flash('이메일을 입력해주세요.', 'error')
        return redirect(url_for('main.book_detail', id=book.id))

    # 같은 도서 + 같은 이메일의 미발송 신청이 이미 있으면 중복 저장하지 않음
    existing = RestockRequest.query.filter_by(book_id=book.id, email=email, notified=False).first()
    if not existing:
        db.session.add(RestockRequest(book_id=book.id, name=name, email=email))
        db.session.commit()

    flash(f"'{book.title}' 입고 시 {email}으로 알림을 보내드립니다.", 'success')
    return redirect(url_for('main.book_detail', id=book.id))


def _notify_restock(book):
    """해당 도서의 미발송 입고 알림 신청자에게 메일을 발송한다.
    이메일 미설정이면 발송하지 않고 대기 건수만 반환한다.
    반환: (발송 성공 건수, 전체 대기 건수)"""
    pending = RestockRequest.query.filter_by(book_id=book.id, notified=False).all()
    if not pending:
        return 0, 0

    if not is_email_configured():
        return 0, len(pending)

    sent = 0
    subject = f"[Rare Book Store] '{book.title}' 재입고 알림"
    detail_url = url_for('main.book_detail', id=book.id, _external=True)
    for reqst in pending:
        html = f"""
        <div style="font-family:sans-serif;max-width:480px">
            <h2 style="font-weight:700">기다리시던 도서가 입고되었습니다 📚</h2>
            <p>{reqst.name or '고객'}님, 신청하신 <strong>'{book.title}'</strong>가 다시 입고되었습니다.</p>
            <p><a href="{detail_url}" style="display:inline-block;background:#111;color:#fff;
               padding:12px 24px;border-radius:9999px;text-decoration:none">지금 보러가기</a></p>
            <p style="color:#888;font-size:12px">희귀 도서 특성상 재고가 한정되어 있어 조기 품절될 수 있습니다.</p>
        </div>"""
        if send_email(reqst.email, subject, html):
            reqst.notified = True
            reqst.notified_at = db.func.now()
            sent += 1
    db.session.commit()
    return sent, len(pending)

@main.route('/admin')
@admin_required
def admin():
    books = Book.query.all()
    return render_template('admin.html', books=books)

@main.route('/admin/add', methods=['GET', 'POST'])
@admin_required
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
            
            # filename = secure_filename(image_file.filename)
            # unique_filename = f"{uuid.uuid4().hex}_{filename}"
            # save_path = os.path.join(current_app.root_path, 'static/book_covers', unique_filename)
            
            # Reset pointer for saving
            image_file.seek(0)
            
            # --- Image Optimization for Mobile Uploads ---
            image_bytes = image_file.read()
            img = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if necessary (e.g. for PNG/RGBA uploads or palette modes)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Resize if too large (Max dimension: 800px)
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Resize if too large (Max dimension: 800px)
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # --- BASE64 ENCODING FOR DB ---
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            img_byte_arr.seek(0)
            img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            
            if not img_base64:
                raise ValueError("이미지 변환에 실패했습니다 (Base64 Empty).")
            # ------------------------------

            # For Gemini, we reset the buffer enabling us to send the bytes
            img_byte_arr.seek(0)
            
            # For Gemini, we can pass the Pillow Image object directly


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
                image_file="stored_in_db", # Placeholder as we use DB storage now
                image_data=img_base64      # New DB storage
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
@admin_required
def admin_edit(id):
    book = Book.query.get_or_404(id)
    if request.method == 'POST':
        try:
            was_out_of_stock = book.stock_quantity == 0  # 재입고 알림 트리거 판단용
            book.title = request.form['title']
            book.author = request.form['author']
            book.year = int(request.form['year'])
            book.edition = request.form.get('edition')
            book.condition = request.form['condition']
            book.price = float(request.form['price'])
            book.stock_quantity = int(request.form['stock_quantity'])
            book.description = request.form.get('description')
            selected_genres = [g for g in request.form.getlist('genre') if g in GENRE_TAXONOMY]
            book.genre = ','.join(selected_genres) if selected_genres else None

            # Handle Image Replacement in Edit
            image_file = request.files.get('book_image')
            if image_file and image_file.filename:
                # Save locally (Legacy/Redundancy)
                from werkzeug.utils import secure_filename
                import uuid
                
                # filename = secure_filename(image_file.filename)
                # unique_filename = f"{uuid.uuid4().hex}_{filename}"
                # save_path = os.path.join(current_app.root_path, 'static/book_covers', unique_filename)
                
                # Image Optimization
                img = Image.open(image_file)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                img.thumbnail((800, 800), Image.Resampling.LANCZOS)
                
                # Base64 Encode for DB
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG')
                img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

                if not img_base64:
                    raise ValueError("이미지 변환에 실패했습니다 (Base64 Empty).")
                
                # Update attributes
                book.image_file = "stored_in_db"
                book.image_data = img_base64

            db.session.commit()
            flash('도서 정보가 수정되었습니다!', 'success')

            # 재고가 0 → 양수로 바뀌면 입고 알림 신청자에게 발송
            if was_out_of_stock and book.stock_quantity > 0:
                sent, pending = _notify_restock(book)
                if pending and sent:
                    flash(f"입고 알림 {sent}건을 발송했습니다.", 'success')
                elif pending and not sent:
                    flash(f"입고 알림 신청자 {pending}명이 대기 중입니다. (이메일 미설정 — 발송 대기) "
                          f"'입고 알림 신청 현황'에서 확인하세요.", 'error')

            return redirect(url_for('main.admin'))
        except ValueError:
            flash('가격, 재고 또는 연도 입력이 올바르지 않습니다.', 'error')
        except SQLAlchemyError:
            db.session.rollback()
            flash('데이터베이스 오류가 발생했습니다.', 'error')

    return render_template('admin_form.html', action='Edit', book=book, genre_taxonomy=GENRE_TAXONOMY)

@main.route('/admin/delete/<int:id>', methods=['POST'])
@admin_required
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


def _orders_for_group_key(group_key):
    """member/admin 양쪽에서 같은 규칙으로 그룹 키 -> Order 행 목록을 찾는다.
    'single-<id>'는 order_group_id가 없는 옛 단건 주문을 가리킨다."""
    if group_key.startswith('single-'):
        try:
            order_id = int(group_key.split('-', 1)[1])
        except ValueError:
            return []
        return Order.query.filter_by(id=order_id).all()
    return Order.query.filter_by(order_group_id=group_key).all()


@main.route('/admin/orders')
@admin_required
def admin_orders():
    """주문 관리 — 같은 결제로 묶인 여러 권은 하나의 주문으로 묶어 최신순으로 표시"""
    status_filter = request.args.get('status', '').strip()
    orders_q = Order.query
    if status_filter in Order.STATUS_LABELS:
        orders_q = orders_q.filter(Order.status == status_filter)
    orders = orders_q.order_by(Order.created_at.desc(), Order.id.desc()).all()
    groups = _group_orders(orders)

    # 상태별 건수 (필터 탭에 표시) — 그룹 단위가 아니라 행 단위로 집계
    counts = {s: 0 for s in Order.STATUS_LABELS}
    for o in Order.query.all():
        counts[o.status] = counts.get(o.status, 0) + 1

    return render_template(
        'admin_orders.html',
        groups=groups, status_labels=Order.STATUS_LABELS,
        status_flow=Order.STATUS_FLOW, status_filter=status_filter, counts=counts,
    )


@main.route('/admin/orders/<group_key>/status', methods=['POST'])
@admin_required
def admin_order_status(group_key):
    """주문(그룹) 상태 변경. '취소'로 바꾸면(이전이 취소가 아니었다면) 그룹 내 각 항목의 수량만큼 재고를 복원한다."""
    orders = _orders_for_group_key(group_key)
    if not orders:
        flash('주문을 찾을 수 없습니다.', 'error')
        return redirect(url_for('main.admin_orders'))

    new_status = request.form.get('status', '').strip()
    if new_status not in Order.STATUS_LABELS:
        flash('유효하지 않은 주문 상태입니다.', 'error')
        return redirect(url_for('main.admin_orders'))

    try:
        for order in orders:
            if new_status == 'cancelled' and order.status != 'cancelled' and order.book_id:
                # 취소 시 재고 원복 (도서가 아직 존재하는 경우, 주문 당시 수량만큼)
                db.session.execute(
                    text("UPDATE book SET stock_quantity = stock_quantity + :qty WHERE id = :id"),
                    {'qty': order.quantity, 'id': order.book_id},
                )
            order.status = new_status
        db.session.commit()
        flash(f"주문 상태를 '{Order.STATUS_LABELS[new_status]}'(으)로 변경했습니다.", 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"주문 상태 변경 실패: {e}")
        flash('주문 상태 변경 중 오류가 발생했습니다.', 'error')

    return redirect(url_for('main.admin_orders', status=request.form.get('return_status', '')))


@main.route('/admin/restock-requests')
@admin_required
def admin_restock_requests():
    """입고 알림 신청 현황 — 도서별로 묶어서 표시"""
    pending = RestockRequest.query.filter_by(notified=False).order_by(RestockRequest.created_at.desc()).all()
    notified = RestockRequest.query.filter_by(notified=True).order_by(RestockRequest.notified_at.desc()).limit(50).all()

    # 도서별 그룹핑 (대기 건만)
    groups = {}
    for r in pending:
        groups.setdefault(r.book_id, {'book': r.book, 'requests': []})
        groups[r.book_id]['requests'].append(r)

    return render_template(
        'admin_restock.html',
        groups=groups, notified=notified, email_configured=is_email_configured(),
    )


@main.route('/admin/restock-requests/<int:book_id>/send', methods=['POST'])
@admin_required
def admin_restock_send(book_id):
    """특정 도서의 대기 신청자에게 입고 알림을 지금 발송 (재고가 있을 때만)"""
    book = Book.query.get_or_404(book_id)
    if book.stock_quantity <= 0:
        flash('재고가 없는 도서는 입고 알림을 발송할 수 없습니다.', 'error')
        return redirect(url_for('main.admin_restock_requests'))

    sent, pending = _notify_restock(book)
    if not pending:
        flash('대기 중인 신청이 없습니다.', 'error')
    elif sent:
        flash(f"'{book.title}' 입고 알림 {sent}건을 발송했습니다.", 'success')
    else:
        flash('이메일이 설정되지 않아 발송하지 못했습니다. .env의 SMTP 설정을 확인하세요.', 'error')
    return redirect(url_for('main.admin_restock_requests'))


@main.route('/admin/restock-requests/<int:book_id>/mark-done', methods=['POST'])
@admin_required
def admin_restock_mark_done(book_id):
    """이메일 미설정 시: 관리자가 수동 연락 후 대기 신청을 '처리 완료'로 표시"""
    book = Book.query.get_or_404(book_id)
    pending = RestockRequest.query.filter_by(book_id=book.id, notified=False).all()
    for r in pending:
        r.notified = True
        r.notified_at = db.func.now()
    db.session.commit()
    flash(f"'{book.title}' 입고 알림 {len(pending)}건을 수동 처리 완료로 표시했습니다.", 'success')
    return redirect(url_for('main.admin_restock_requests'))


@main.route('/admin/tag-genres', methods=['POST'])
@admin_required
def admin_tag_genres():
    """장르 미태깅 도서 전체에 대해 Gemini 자동 분류 실행"""
    if not GOOGLE_API_KEY:
        flash('Google API Key가 설정되지 않아 장르 자동 태깅을 실행할 수 없습니다.', 'error')
        return redirect(url_for('main.admin'))

    targets = Book.query.filter((Book.genre == None) | (Book.genre == '')).all()
    if not targets:
        flash('이미 모든 도서에 장르가 태깅되어 있습니다.', 'success')
        return redirect(url_for('main.admin'))

    tagged, failed = 0, 0
    for book in targets:
        genres = auto_tag_genre(book.title, book.author, book.description)
        if genres:
            book.genre = ','.join(genres)
            tagged += 1
        else:
            failed += 1

    db.session.commit()
    if failed:
        flash(f'{tagged}권 자동 태깅 완료, {failed}권 실패 (API 오류 — 재시도해주세요).', 'success' if tagged else 'error')
    else:
        flash(f'{tagged}권 장르 자동 태깅 완료. 결과는 관리자 화면에서 검수/수정하세요.', 'success')
    return redirect(url_for('main.admin'))


# --- Admin: Book Search Routes ---

@main.route('/admin/search')
@admin_required
def admin_search():
    """도서 검색으로 등록 UI 페이지"""
    return render_template('admin_search.html')


@main.route('/admin/search-books')
@admin_required
def admin_search_books():
    """도서 검색 API — 카카오(한국어) → 네이버 → Google Books → Open Library 순 폴백"""
    import requests as req
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'items': []})

    headers = {'User-Agent': 'RareBookStore/1.0 (admin search)'}

    # ── 한국어 포함 여부 감지 ──
    def is_korean(text):
        return any('\uAC00' <= c <= '\uD7A3' or '\u3131' <= c <= '\u314E' for c in text)

    # ── 파서들 ──
    def parse_kakao(data):
        items = []
        for doc in data.get('documents', []):
            pub_date = doc.get('datetime', '')
            year = int(pub_date[:4]) if pub_date and pub_date[:4].isdigit() else None
            thumbnail = upgrade_cover_url(doc.get('thumbnail', '') or None)  # 카카오 120px 썸네일 → 고해상도 원본
            items.append({
                'title':       doc.get('title', '').replace('<b>', '').replace('</b>', ''),
                'author':      doc.get('authors', [''])[0] if doc.get('authors') else '',
                'year':        year,
                'edition':     '',
                'description': (doc.get('contents', '') or '')[:400],
                'thumbnail':   thumbnail,
                'isbn':        doc.get('isbn', '').split()[-1] if doc.get('isbn') else None,
                'google_id':   '',
                'source':      'kakao',
            })
        return items

    def parse_naver(data):
        items = []
        for item in data.get('items', []):
            pub_date = item.get('pubdate', '')
            year = int(pub_date[:4]) if pub_date and len(pub_date) >= 4 and pub_date[:4].isdigit() else None
            thumbnail = item.get('image', '') or None
            title = item.get('title', '').replace('<b>', '').replace('</b>', '')
            author = item.get('author', '').replace('<b>', '').replace('</b>', '').replace('^', ', ')
            items.append({
                'title':       title,
                'author':      author,
                'year':        year,
                'edition':     '',
                'description': (item.get('description', '') or '')[:400],
                'thumbnail':   thumbnail,
                'isbn':        item.get('isbn', '') or None,
                'google_id':   '',
                'source':      'naver',
            })
        return items

    def parse_google(data):
        items = []
        for item in data.get('items', []):
            vi = item.get('volumeInfo', {})
            img = vi.get('imageLinks', {})
            thumbnail = img.get('thumbnail') or img.get('smallThumbnail')
            if thumbnail:
                thumbnail = (thumbnail.replace('http://', 'https://')
                                      .replace('&edge=curl', '')
                                      .replace('&zoom=1', '&zoom=0'))
            isbn = None
            for ident in vi.get('industryIdentifiers', []):
                if ident.get('type') in ('ISBN_13', 'ISBN_10'):
                    isbn = ident.get('identifier'); break
            pub_date = vi.get('publishedDate', '')
            year = int(pub_date[:4]) if pub_date and len(pub_date) >= 4 and pub_date[:4].isdigit() else None
            items.append({
                'title':       vi.get('title', ''),
                'author':      ', '.join(vi.get('authors', [])[:2]),
                'year':        year,
                'edition':     '',
                'description': (vi.get('description', '') or '')[:400],
                'thumbnail':   thumbnail,
                'isbn':        isbn,
                'google_id':   item.get('id', ''),
                'source':      'google',
            })
        return items

    def parse_openlibrary(data):
        items = []
        for doc in data.get('docs', []):
            cover_id = doc.get('cover_i')
            thumbnail = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None  # -L = large
            pub_date = str(doc.get('first_publish_year', ''))
            year = int(pub_date) if pub_date.isdigit() else None
            items.append({
                'title':       doc.get('title', ''),
                'author':      ', '.join((doc.get('author_name') or [])[:2]),
                'year':        year,
                'edition':     '',
                'description': '',
                'thumbnail':   thumbnail,
                'isbn':        (doc.get('isbn') or [None])[0],
                'google_id':   '',
                'source':      'openlibrary',
            })
            if len(items) >= 20:
                break
        return items

    # ── 검색 파이프라인 ──
    korean = is_korean(q)
    encoded_q = req.utils.quote(q)

    # 1순위: 카카오 책 검색
    kakao_key = os.environ.get('KAKAO_REST_API_KEY', '').strip()
    if kakao_key:
        try:
            resp = req.get(
                f"https://dapi.kakao.com/v3/search/book?query={encoded_q}&size=20",
                headers={**headers, 'Authorization': f'KakaoAK {kakao_key}'},
                timeout=8
            )
            resp.raise_for_status()
            items = parse_kakao(resp.json())
            if items:
                print(f"카카오 검색 성공: {len(items)}건")
                return jsonify({'items': items, 'source': 'kakao'})
        except Exception as e:
            print(f"카카오 검색 실패: {e}")

    # 2순위: 네이버 책 검색
    naver_id     = os.environ.get('NAVER_CLIENT_ID', '').strip()
    naver_secret = os.environ.get('NAVER_CLIENT_SECRET', '').strip()
    if naver_id and naver_secret:
        try:
            resp = req.get(
                f"https://openapi.naver.com/v1/search/book.json?query={encoded_q}&display=20",
                headers={
                    **headers,
                    'X-Naver-Client-Id':     naver_id,
                    'X-Naver-Client-Secret': naver_secret,
                },
                timeout=8
            )
            resp.raise_for_status()
            items = parse_naver(resp.json())
            if items:
                print(f"네이버 검색 성공: {len(items)}건")
                return jsonify({'items': items, 'source': 'naver'})
        except Exception as e:
            print(f"네이버 검색 실패: {e}")

    # 3순위: Google Books
    try:
        google_key = os.environ.get('GOOGLE_API_KEY', '').strip()
        key_param  = f'&key={google_key}' if google_key else ''
        lang_param = '&langRestrict=ko' if korean else ''
        url = f"https://www.googleapis.com/books/v1/volumes?q={encoded_q}&maxResults=20&printType=books{lang_param}{key_param}"
        resp = req.get(url, headers=headers, timeout=10)
        if resp.status_code == 429:
            raise Exception('Rate limited')
        resp.raise_for_status()
        items = parse_google(resp.json())
        if items:
            print(f"Google Books 검색 성공: {len(items)}건")
            return jsonify({'items': items, 'source': 'google'})
    except Exception as e:
        print(f"Google Books 실패: {e}")

    # 4순위: Open Library
    try:
        ol_url = f"https://openlibrary.org/search.json?q={encoded_q}&limit=20"
        ol_resp = req.get(ol_url, headers=headers, timeout=10)
        ol_resp.raise_for_status()
        items = parse_openlibrary(ol_resp.json())
        if items:
            print(f"Open Library 검색 성공: {len(items)}건")
            return jsonify({'items': items, 'source': 'openlibrary'})
    except Exception as e2:
        print(f"Open Library 실패: {e2}")

    # 모두 실패 — 한국어이고 API Key 없으면 안내
    no_key = korean and not kakao_key and not naver_id
    return jsonify({'items': [], 'message': 'no_key' if no_key else 'no_results'})


@main.route('/admin/add-from-search', methods=['POST'])
@admin_required
def admin_add_from_search():
    """검색 결과로 도서 등록 — 표지를 URL에서 다운로드해 Base64로 저장"""
    import requests as req

    try:
        title       = request.form.get('title', '').strip()
        author      = request.form.get('author', '').strip()
        year_str    = request.form.get('year', '0')
        edition     = request.form.get('edition_override') or request.form.get('edition', '')
        description = request.form.get('description_override') or request.form.get('description', '')
        condition   = request.form.get('condition', 'Good')
        price       = float(request.form.get('price', 0))
        stock       = int(request.form.get('stock_quantity', 1))
        cover_url   = request.form.get('cover_url', '').strip()

        year = int(year_str) if year_str and year_str.isdigit() else 0

        if not title:
            flash('도서 제목이 없습니다.', 'error')
            return redirect(url_for('main.admin_search'))

        # 표지 이미지 다운로드 → Base64 (저해상도 썸네일은 고해상도 원본으로 업그레이드 후 저장)
        # SSRF 방지: 실제로 요청을 보낼 최종 URL(업그레이드 이후)을 검증한다.
        # upgrade_cover_url 이전 URL만 검증하면 kakaocdn 형태의 URL에 fname= 파라미터로
        # 내부망 주소를 숨겨 보내는 우회가 가능하므로, 반드시 변환 *이후* 값을 검사해야 한다.
        img_base64 = None
        resolved_cover_url = upgrade_cover_url(cover_url) if cover_url else ''
        if resolved_cover_url and not is_allowed_cover_image_url(resolved_cover_url):
            print(f"표지 이미지 다운로드 차단 (허용되지 않은 호스트): {resolved_cover_url}")
            resolved_cover_url = ''
        if resolved_cover_url:
            try:
                img_resp = req.get(resolved_cover_url, timeout=8)
                img_resp.raise_for_status()
                img = Image.open(io.BytesIO(img_resp.content))
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=90, optimize=True)
                img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            except Exception as e:
                print(f"Cover download failed: {e}")

        new_book = Book(
            title          = title,
            author         = author,
            year           = year,
            edition        = edition,
            condition      = condition,
            price          = price,
            stock_quantity = stock,
            description    = description,
            image_file     = 'stored_in_db' if img_base64 else None,
            image_data     = img_base64,
        )
        db.session.add(new_book)
        db.session.commit()

        flash(f"'{new_book.title}' 등록 완료!", 'success')
        return redirect(url_for('main.admin'))

    except ValueError:
        flash('가격 또는 재고 입력이 올바르지 않습니다.', 'error')
        return redirect(url_for('main.admin_search'))
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'데이터베이스 오류: {str(e)}', 'error')
        return redirect(url_for('main.admin_search'))
    except Exception as e:
        db.session.rollback()
        flash(f'오류 발생: {str(e)}', 'error')
        print(f"add_from_search error: {e}")
        return redirect(url_for('main.admin_search'))

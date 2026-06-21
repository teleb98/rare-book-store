"""
보안 관련 테스트: 인젝션, 권한 상승, 잘못된 입력에 대한 방어 확인.
(별도로 /security-review 스킬을 통한 정적 코드 리뷰도 함께 수행함 — 이 파일은 동적/회귀 테스트용)
"""
from conftest import login_admin, login_member, make_user, make_book


def test_cover_url_ssrf_blocked_for_internal_hosts(client, db, monkeypatch):
    """admin_add_from_search의 cover_url은 신뢰 호스트만 허용해야 한다 (SSRF 방지)"""
    import requests
    calls = []
    monkeypatch.setattr(requests, 'get', lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("내부 URL로 요청을 보내면 안 됨")))

    login_admin(client)
    client.post('/admin/add-from-search', data={
        'title': 'SSRF시도', 'author': 'x', 'price': '1000', 'stock_quantity': '1',
        'cover_url': 'http://169.254.169.254/latest/meta-data/',
    })
    assert calls == []  # requests.get이 호출되지 않아야 함

    from app.models import Book
    book = Book.query.filter_by(title='SSRF시도').first()
    assert book is not None
    assert book.image_data is None  # 이미지 없이 등록은 되지만 다운로드는 차단됨


def test_cover_url_ssrf_blocked_via_kakaocdn_fname_smuggling(client, db, monkeypatch):
    """upgrade_cover_url이 풀어내는 fname= 내부에 내부망 주소를 숨겨도 차단되어야 한다"""
    import requests
    calls = []
    monkeypatch.setattr(requests, 'get', lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("내부 URL로 요청을 보내면 안 됨")))

    login_admin(client)
    smuggled = 'https://search1.kakaocdn.net/thumb/R120x174.q85/?fname=http%3A%2F%2F169.254.169.254%2Flatest%2Fmeta-data'
    client.post('/admin/add-from-search', data={
        'title': 'SSRF밀반입시도', 'author': 'x', 'price': '1000', 'stock_quantity': '1',
        'cover_url': smuggled,
    })
    assert calls == []


def test_cover_url_allows_trusted_cdn_host(client, db, monkeypatch):
    """신뢰하는 CDN 호스트는 정상적으로 다운로드를 시도해야 한다 (화이트리스트가 과잉 차단하지 않는지 확인)"""
    import requests
    calls = []

    class FakeResp:
        content = b'\x00'  # 의도적으로 깨진 이미지 — Image.open이 실패해도 요청 자체는 갔는지가 핵심
        def raise_for_status(self): pass

    monkeypatch.setattr(requests, 'get', lambda *a, **k: (calls.append(a[0] if a else k.get('url')), FakeResp())[1])

    login_admin(client)
    client.post('/admin/add-from-search', data={
        'title': '정상커버시도', 'author': 'x', 'price': '1000', 'stock_quantity': '1',
        'cover_url': 'http://t1.daumcdn.net/lbook/image/521598',
    })
    assert len(calls) == 1
    assert 'daumcdn.net' in calls[0]


def test_sql_injection_in_search_query_is_safe(client, db):
    """검색어에 SQL 메타문자를 넣어도 에러 없이 처리되고, 다른 행에 영향 없어야 한다"""
    make_book(db, title='정상도서')
    payload = "' OR '1'='1"
    resp = client.get('/', query_string={'q': payload})
    assert resp.status_code == 200
    # 모든 도서가 노출되면 인젝션이 성공했다는 신호 — 그래선 안 됨
    assert '정상도서' not in resp.data.decode()


def test_sql_injection_drop_table_payload_does_not_break_app(client, db):
    make_book(db, title='보존되어야할도서')
    resp = client.get('/', query_string={'q': "x'; DROP TABLE book; --"})
    assert resp.status_code == 200
    # 앱이 살아있고 데이터가 보존되는지 다음 요청으로 확인
    resp2 = client.get('/?q=보존되어야할도서')
    assert '보존되어야할도서' in resp2.data.decode()


def test_xss_in_book_title_via_admin_is_escaped_on_listing(client, db):
    payload = '<img src=x onerror=alert(1)>'
    b = make_book(db, title=payload)
    resp = client.get('/')
    body = resp.data.decode()
    assert '<img src=x onerror=alert(1)>' not in body
    assert '&lt;img' in body


def test_xss_in_review_comment_escaped_on_detail_page(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    client.post(f'/book/{b.id}/review', data={
        'rating': '3', 'comment': '<svg onload=alert(1)>',
    })
    resp = client.get(f'/book/{b.id}')
    body = resp.data.decode()
    assert '<svg onload=alert(1)>' not in body


def test_restock_request_name_xss_escaped_in_admin_view(client, db):
    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={
        'book_id': b.id, 'name': '<script>document.location="//evil"</script>', 'email': 'a@example.com',
    })
    login_admin(client)
    resp = client.get('/admin/restock-requests')
    body = resp.data.decode()
    assert '<script>document.location' not in body


def test_member_cannot_access_admin_routes_with_member_session(client, db):
    """member_required로 보호된 라우트에 로그인한 회원이 admin_required 라우트에 접근 못해야 한다 (권한 상승 방지)"""
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)

    resp = client.get('/admin')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']

    resp2 = client.post(f'/admin/delete/{b.id}')
    assert resp2.status_code == 302
    assert '/login' in resp2.headers['Location']


def test_admin_session_alone_cannot_use_member_only_checkout(client, db):
    """admin_required는 만족해도 member_required(로그인 회원)는 아니므로 주문은 막혀야 한다"""
    b = make_book(db, stock_quantity=1)
    login_admin(client)
    resp = client.get(f'/checkout?book_id={b.id}&qty=1')
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']


def test_review_user_id_cannot_be_spoofed_via_form(client, db):
    """폼에 user_id를 직접 넣어도 세션의 실제 로그인 사용자로만 저장되어야 한다 (mass assignment 방지)"""
    u1 = make_user(db, provider_id='real-user')
    u2 = make_user(db, provider_id='victim-user')
    b = make_book(db)
    login_member(client, u1.id, u1.name)

    client.post(f'/book/{b.id}/review', data={'rating': '5', 'comment': 'x', 'user_id': str(u2.id)})

    from app.models import Review
    review = Review.query.filter_by(book_id=b.id).first()
    assert review.user_id == u1.id  # u2.id로 저장되면 심각한 버그


def test_checkout_book_id_query_param_wins_over_form_body(client, db):
    """체크아웃은 쿼리스트링의 book_id를 신뢰하므로, 폼 바디에 다른 book_id를 끼워 넣어도 무시되어야 한다"""
    u = make_user(db)
    real_book = make_book(db, title='실제구매책', stock_quantity=1)
    other_book = make_book(db, title='다른책', stock_quantity=1)
    login_member(client, u.id, u.name)

    client.post(f'/checkout?book_id={real_book.id}&qty=1', data={
        'book_id': str(other_book.id),
        'recipient_name': '홍길동', 'phone': '010-1234-5678', 'postal_code': '12345', 'address1': '주소',
    })

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()
    assert order is not None
    assert order.book_id == real_book.id


def test_cart_item_cannot_be_updated_by_other_member(client, db):
    """다른 회원의 장바구니 항목 id를 알아내도 수정/삭제할 수 없어야 한다 (IDOR 방지)"""
    u1 = make_user(db, provider_id='victim')
    u2 = make_user(db, provider_id='attacker')
    b = make_book(db, stock_quantity=5)

    login_member(client, u1.id, u1.name)
    client.post(f'/cart/add/{b.id}', data={'quantity': '1'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u1.id).first()

    login_member(client, u2.id, u2.name)
    resp = client.post(f'/cart/update/{item.id}', data={'quantity': '99'})
    assert resp.status_code == 404

    resp2 = client.post(f'/cart/remove/{item.id}')
    assert resp2.status_code == 404

    db.session.refresh(item)
    assert item.quantity == 1  # 변경되지 않아야 함


def test_checkout_only_uses_current_users_cart(client, db):
    """장바구니 결제 시 다른 회원의 장바구니가 섞여 들어가면 안 된다"""
    u1 = make_user(db, provider_id='u1')
    u2 = make_user(db, provider_id='u2')
    b1 = make_book(db, title='회원1장바구니책', stock_quantity=5)
    b2 = make_book(db, title='회원2장바구니책', stock_quantity=5)

    login_member(client, u1.id, u1.name)
    client.post(f'/cart/add/{b1.id}', data={'quantity': '1'})

    login_member(client, u2.id, u2.name)
    client.post(f'/cart/add/{b2.id}', data={'quantity': '1'})

    resp = client.get('/checkout')
    body = resp.data.decode()
    assert '회원2장바구니책' in body
    assert '회원1장바구니책' not in body


def test_genre_tag_admin_route_requires_post(client, db):
    """GET으로 상태를 변경하는 라우트가 없는지 확인 (CSRF 표면 축소)"""
    login_admin(client)
    resp = client.get('/admin/tag-genres')
    assert resp.status_code == 405


def test_delete_route_requires_post_not_get(client, db):
    """GET 요청으로 삭제가 발생하면 안 된다 (링크 클릭/프리페치로 삭제되는 CSRF성 사고 방지)"""
    b = make_book(db)
    login_admin(client)
    resp = client.get(f'/admin/delete/{b.id}')
    assert resp.status_code == 405

    from app.models import Book
    assert Book.query.get(b.id) is not None


def test_nonexistent_book_detail_returns_404_not_500(client, db):
    resp = client.get('/book/999999')
    assert resp.status_code == 404


def test_non_integer_book_id_returns_404_not_500(client, db):
    resp = client.get('/book/not-a-number')
    assert resp.status_code == 404


def test_negative_book_id_returns_404(client, db):
    resp = client.get('/book/-1')
    assert resp.status_code == 404


def test_admin_search_books_requires_admin(client):
    resp = client.get('/admin/search-books?q=test')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_default_admin_password_fallback_not_used_in_this_env(app):
    """운영에서는 ADMIN_PASSWORD가 코드의 기본값('admin1234')과 달라야 한다는 걸 상기시키는 가드.
    테스트 환경 자체는 별도 비밀번호를 쓰므로 여기서는 '기본값이 아님'만 확인."""
    import os
    assert os.environ.get('ADMIN_PASSWORD') != 'admin1234'

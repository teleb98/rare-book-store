"""관리자 도서 CRUD 테스트"""
from conftest import login_admin, make_book


def test_admin_delete_removes_book(client, db):
    b = make_book(db)
    login_admin(client)
    resp = client.post(f'/admin/delete/{b.id}', follow_redirects=True)
    assert '삭제되었습니다' in resp.data.decode()

    from app.models import Book
    assert Book.query.get(b.id) is None


def test_admin_delete_nonexistent_book_returns_404(client, db):
    login_admin(client)
    resp = client.post('/admin/delete/999999')
    assert resp.status_code == 404


def test_admin_edit_updates_fields(client, db):
    b = make_book(db, title='원래제목', price=10000)
    login_admin(client)
    client.post(f'/admin/edit/{b.id}', data={
        'title': '바뀐제목', 'author': b.author, 'year': str(b.year), 'condition': b.condition,
        'edition': '초판', 'price': '99999', 'stock_quantity': '7',
    })
    db.session.refresh(b)
    assert b.title == '바뀐제목'
    assert b.price == 99999
    assert b.stock_quantity == 7
    assert b.edition == '초판'


def test_admin_edit_rejects_invalid_price(client, db):
    b = make_book(db, price=10000)
    login_admin(client)
    resp = client.post(f'/admin/edit/{b.id}', data={
        'title': b.title, 'author': b.author, 'year': str(b.year), 'condition': b.condition,
        'edition': '', 'price': 'not-a-number', 'stock_quantity': '1',
    }, follow_redirects=True)
    assert '가격, 재고 또는 연도 입력이 올바르지' in resp.data.decode()
    db.session.refresh(b)
    assert b.price == 10000  # 변경되지 않아야 함


def test_genre_auto_tag_skips_already_tagged_books(client, db, monkeypatch):
    """GOOGLE_API_KEY 가드를 통과시켜 실제로 '이미 태깅됨' 분기를 테스트한다.
    (키가 없으면 그보다 먼저 'API Key 미설정' 분기로 빠지므로 별도 테스트로 분리되어 있음)"""
    import app.routes as routes
    monkeypatch.setattr(routes, 'GOOGLE_API_KEY', 'fake-key-for-test')

    make_book(db, title='이미태깅됨', genre='고전문학')
    login_admin(client)
    resp = client.post('/admin/tag-genres', follow_redirects=True)
    assert '이미 모든 도서에 장르가 태깅되어' in resp.data.decode()


def test_genre_auto_tag_reports_error_without_api_key(client, db):
    """GOOGLE_API_KEY가 없는 테스트 환경에서는 명확히 에러로 안내해야 한다 (조용히 무시 금지)"""
    make_book(db, title='미태깅도서', genre=None)
    login_admin(client)
    resp = client.post('/admin/tag-genres', follow_redirects=True)
    assert 'API Key가 설정되지 않아' in resp.data.decode()

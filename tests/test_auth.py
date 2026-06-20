"""관리자/회원 인증 및 접근 제어 테스트"""
from conftest import login_admin, login_member, make_user


def test_admin_routes_blocked_when_anonymous(client):
    for path, method in [
        ('/admin', 'get'),
        ('/admin/add', 'get'),
        ('/admin/orders', 'get'),
        ('/admin/restock-requests', 'get'),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']


def test_admin_state_changing_routes_blocked_when_anonymous(client, db):
    from app.models import Book
    b = make_book_local(db)
    resp = client.post(f'/admin/delete/{b.id}')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']

    resp = client.post('/admin/tag-genres')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def make_book_local(db):
    from app.models import Book
    b = Book(title='t', author='a', year=2020, condition='Good', price=1000, stock_quantity=1)
    db.session.add(b)
    db.session.commit()
    return b


def test_admin_login_wrong_password_rejected(client):
    resp = client.post('/login', data={'password': 'wrong'})
    assert resp.status_code == 200
    assert '비밀번호가 올바르지 않습니다' in resp.data.decode()
    # 로그인 안 된 상태인지 확인
    resp2 = client.get('/admin')
    assert resp2.status_code == 302


def test_admin_login_correct_password_grants_access(client):
    resp = login_admin(client)
    assert resp.status_code == 302
    resp2 = client.get('/admin')
    assert resp2.status_code == 200


def test_admin_logout_revokes_access(client):
    login_admin(client)
    assert client.get('/admin').status_code == 200
    client.get('/logout')
    assert client.get('/admin').status_code == 302


def test_member_routes_blocked_when_anonymous(client):
    for path in ['/member/orders', '/member/genres', '/member/mypage']:
        resp = client.get(path)
        assert resp.status_code == 302
        assert '/member/login' in resp.headers['Location']


def test_member_purchase_blocked_when_anonymous(client, db):
    b = make_book_local(db)
    resp = client.post(f'/purchase/{b.id}')
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']


def test_member_review_blocked_when_anonymous(client, db):
    b = make_book_local(db)
    resp = client.post(f'/book/{b.id}/review', data={'rating': '5'})
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']


def test_member_session_grants_access(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)
    resp = client.get('/member/orders')
    assert resp.status_code == 200


def test_member_logout_revokes_access(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)
    assert client.get('/member/orders').status_code == 200
    client.get('/member/logout')
    assert client.get('/member/orders').status_code == 302


def test_oauth_unknown_provider_rejected(client):
    resp = client.get('/auth/facebook/login')
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']

    resp2 = client.get('/auth/facebook/callback?code=x&state=y')
    assert resp2.status_code == 302
    assert '/member/login' in resp2.headers['Location']


def test_oauth_unconfigured_provider_rejected(client):
    # conftest에서 모든 provider 키를 비웠으므로 셋 다 미설정 상태여야 함
    for provider in ('kakao', 'naver', 'google'):
        resp = client.get(f'/auth/{provider}/login')
        assert resp.status_code == 302
        assert '/member/login' in resp.headers['Location']


def test_oauth_callback_state_mismatch_rejected(client):
    with client.session_transaction() as sess:
        sess['oauth_state'] = 'expected-state'
        sess['oauth_provider'] = 'kakao'
    resp = client.get('/auth/kakao/callback?code=somecode&state=WRONG')
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']


def test_oauth_callback_provider_mismatch_rejected(client):
    """state는 맞지만 세션에 저장된 provider와 콜백 provider가 다르면 차단"""
    with client.session_transaction() as sess:
        sess['oauth_state'] = 'same-state'
        sess['oauth_provider'] = 'naver'
    resp = client.get('/auth/kakao/callback?code=x&state=same-state')
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']


def test_oauth_callback_provider_error_param_rejected(client):
    resp = client.get('/auth/kakao/callback?error=access_denied')
    assert resp.status_code == 302
    assert '/member/login' in resp.headers['Location']

"""마이페이지(주문내역/선호장르 허브) 테스트"""
from conftest import login_member, make_user, make_book


def test_mypage_shows_nickname_and_email(client, db):
    u = make_user(db, name='홍길동', email='hong@example.com')
    login_member(client, u.id, u.name)
    resp = client.get('/member/mypage')
    body = resp.data.decode()
    assert '홍길동' in body
    assert 'hong@example.com' in body


def test_mypage_shows_no_orders_state(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)
    resp = client.get('/member/mypage')
    assert '아직 주문 내역이 없습니다' in resp.data.decode()


def test_mypage_shows_recent_orders_and_total_count(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)
    for i in range(4):
        b = make_book(db, title=f'마이북{i}', stock_quantity=1)
        client.post(f'/purchase/{b.id}')

    resp = client.get('/member/mypage')
    body = resp.data.decode()
    assert '전체 4건' in body
    # 최근 3건만 보여줘야 함 (가장 오래된 마이북0은 미리보기에 없어야 함)
    assert '마이북3' in body
    assert '마이북0' not in body


def test_mypage_shows_no_genre_state(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)
    resp = client.get('/member/mypage')
    assert '아직 선택한 장르가 없습니다' in resp.data.decode()


def test_mypage_shows_preferred_genres(client, db):
    u = make_user(db)
    u.preferred_genres = '과학/대중과학,인문/교양'
    db.session.commit()
    login_member(client, u.id, u.name)

    resp = client.get('/member/mypage')
    body = resp.data.decode()
    assert '과학/대중과학' in body
    assert '인문/교양' in body


def test_mypage_only_shows_own_orders_not_other_members(client, db):
    u1 = make_user(db, provider_id='u1', name='회원1')
    u2 = make_user(db, provider_id='u2', name='회원2')
    b = make_book(db, title='회원1전용책', stock_quantity=1)

    login_member(client, u1.id, u1.name)
    client.post(f'/purchase/{b.id}')

    login_member(client, u2.id, u2.name)
    resp = client.get('/member/mypage')
    body = resp.data.decode()
    assert '회원1전용책' not in body
    assert '전체 0건' in body


def test_navbar_shows_single_mypage_link_when_logged_in(client, db):
    """메인 페이지 네비게이션이 마이페이지 하나로 단순화되어 있어야 한다"""
    u = make_user(db, name='테스터')
    login_member(client, u.id, u.name)
    resp = client.get('/')
    body = resp.data.decode()
    assert '마이페이지' in body
    assert '/member/mypage' in body
    # 예전처럼 네비게이션에 별도의 주문내역/선호 장르 링크가 떠 있으면 안 됨
    assert 'href="/member/orders"' not in body
    assert 'href="/member/genres"' not in body

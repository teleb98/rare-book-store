"""선호 장르 온보딩 / 장르 자동태깅 화이트리스트 테스트"""
from conftest import login_admin, login_member, make_user, make_book


def test_genre_selection_save(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)

    resp = client.post('/member/genres', data={
        'action': 'save', 'genres': ['과학/대중과학', '인문/교양'],
    }, follow_redirects=False)
    assert resp.status_code == 302

    db.session.refresh(u)
    assert u.preferred_genres == '과학/대중과학,인문/교양'


def test_genre_selection_skip_clears_preference(client, db):
    u = make_user(db)
    u.preferred_genres = '고전문학'
    db.session.commit()
    login_member(client, u.id, u.name)

    client.post('/member/genres', data={'action': 'skip'})
    db.session.refresh(u)
    assert u.preferred_genres is None


def test_genre_selection_rejects_values_outside_whitelist(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)

    client.post('/member/genres', data={
        'action': 'save',
        'genres': ['고전문학', '<script>alert(1)</script>', '해킹장르'],
    })
    db.session.refresh(u)
    assert u.preferred_genres == '고전문학'


def test_genre_admin_edit_rejects_values_outside_whitelist(client, db):
    b = make_book(db)
    login_admin(client)
    client.post(f'/admin/edit/{b.id}', data={
        'title': b.title, 'author': b.author, 'year': str(b.year), 'condition': b.condition,
        'edition': '', 'price': str(b.price), 'stock_quantity': str(b.stock_quantity),
        'genre': ['인문/교양', "'; DROP TABLE book; --"],
    })
    db.session.refresh(b)
    assert b.genre == '인문/교양'


def test_personalized_section_shown_only_without_filters(client, db):
    u = make_user(db)
    u.preferred_genres = '과학/대중과학'
    db.session.commit()
    matching_book = make_book(db, title='추천될책', genre='과학/대중과학')
    login_member(client, u.id, u.name)

    resp = client.get('/')
    assert '추천될책' in resp.data.decode()
    assert '을 위한 추천' in resp.data.decode()

    # 필터가 걸리면 추천 섹션은 숨겨야 한다
    resp2 = client.get('/?condition=Good')
    assert '을 위한 추천' not in resp2.data.decode()

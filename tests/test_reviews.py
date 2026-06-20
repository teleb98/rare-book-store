"""평점/리뷰 테스트"""
from conftest import login_member, make_user, make_book


def test_review_upsert_no_duplicate(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)

    client.post(f'/book/{b.id}/review', data={'rating': '4', 'comment': '처음'})
    client.post(f'/book/{b.id}/review', data={'rating': '2', 'comment': '수정'})

    from app.models import Review
    reviews = Review.query.filter_by(book_id=b.id, user_id=u.id).all()
    assert len(reviews) == 1
    assert reviews[0].rating == 2
    assert reviews[0].comment == '수정'


def test_review_average_calculated_correctly(client, db):
    b = make_book(db)
    for i, rating in enumerate([4, 3, 3]):
        u = make_user(db, provider_id=f'u{i}', name=f'리뷰어{i}')
        login_member(client, u.id, u.name)
        client.post(f'/book/{b.id}/review', data={'rating': str(rating)})

    resp = client.get(f'/book/{b.id}')
    assert '3.3' in resp.data.decode()


def test_review_zero_rating_accepted(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    client.post(f'/book/{b.id}/review', data={'rating': '0', 'comment': '별로였음'})

    from app.models import Review
    r = Review.query.filter_by(book_id=b.id, user_id=u.id).first()
    assert r.rating == 0


def test_review_rejects_out_of_range_rating(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    resp = client.post(f'/book/{b.id}/review', data={'rating': '6'}, follow_redirects=True)
    assert '평점은 0점에서 5점 사이' in resp.data.decode()

    from app.models import Review
    assert Review.query.count() == 0


def test_review_rejects_negative_rating(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    resp = client.post(f'/book/{b.id}/review', data={'rating': '-1'}, follow_redirects=True)
    assert '평점은 0점에서 5점 사이' in resp.data.decode()


def test_review_rejects_missing_rating(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    resp = client.post(f'/book/{b.id}/review', data={'comment': '평점 없음'}, follow_redirects=True)
    assert '평점을 선택해주세요' in resp.data.decode()


def test_review_rejects_non_numeric_rating(client, db):
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    resp = client.post(f'/book/{b.id}/review', data={'rating': 'five'}, follow_redirects=True)
    assert '평점을 선택해주세요' in resp.data.decode()


def test_review_comment_xss_payload_is_escaped_in_html(client, db):
    """리뷰 댓글에 스크립트를 넣어도 화면에서는 무해한 텍스트로만 보여야 한다"""
    u = make_user(db)
    b = make_book(db)
    login_member(client, u.id, u.name)
    payload = '<script>alert(1)</script>'
    client.post(f'/book/{b.id}/review', data={'rating': '3', 'comment': payload})

    resp = client.get(f'/book/{b.id}')
    body = resp.data.decode()
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;' in body

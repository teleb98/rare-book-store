"""입고 알림 신청/발송 테스트"""
from conftest import login_admin, make_book


def test_notify_request_saved(client, db):
    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={'book_id': b.id, 'name': '홍길동', 'email': 'hong@example.com'})

    from app.models import RestockRequest
    reqs = RestockRequest.query.filter_by(book_id=b.id).all()
    assert len(reqs) == 1
    assert reqs[0].email == 'hong@example.com'
    assert reqs[0].notified is False


def test_notify_request_dedup_same_email(client, db):
    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': 'dup@example.com'})
    client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': 'dup@example.com'})

    from app.models import RestockRequest
    assert RestockRequest.query.filter_by(book_id=b.id).count() == 1


def test_notify_request_rejects_empty_email(client, db):
    b = make_book(db, stock_quantity=0)
    resp = client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': ''}, follow_redirects=True)
    assert '이메일을 입력해주세요' in resp.data.decode()

    from app.models import RestockRequest
    assert RestockRequest.query.count() == 0


def test_notify_request_rejects_invalid_book_id(client, db):
    resp = client.post('/notify', data={'book_id': '999999', 'name': 'A', 'email': 'a@example.com'}, follow_redirects=True)
    assert '유효하지 않은 도서' in resp.data.decode()


def test_notify_request_missing_book_id_does_not_crash(client, db):
    resp = client.post('/notify', data={'name': 'A', 'email': 'a@example.com'})
    assert resp.status_code in (302, 400)


def test_restock_trigger_on_admin_edit_when_email_unconfigured(client, db):
    """이메일 미설정 상태에서는 발송 대기로 남고 notified=False 유지"""
    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': 'a@example.com'})

    login_admin(client)
    resp = client.post(f'/admin/edit/{b.id}', data={
        'title': b.title, 'author': b.author, 'year': str(b.year), 'condition': b.condition,
        'edition': '', 'price': str(b.price), 'stock_quantity': '5',
    }, follow_redirects=True)
    assert '발송 대기' in resp.data.decode()

    from app.models import RestockRequest
    r = RestockRequest.query.filter_by(book_id=b.id).first()
    assert r.notified is False


def test_restock_trigger_sends_when_email_configured(client, db, monkeypatch):
    """이메일이 설정된 것처럼 모킹하면 자동 발송되고 notified=True가 되어야 한다"""
    import app.routes as routes
    sent_to = []
    monkeypatch.setattr(routes, 'is_email_configured', lambda: True)
    monkeypatch.setattr(routes, 'send_email', lambda to, subject, html: (sent_to.append(to), True)[1])

    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': 'a@example.com'})

    login_admin(client)
    resp = client.post(f'/admin/edit/{b.id}', data={
        'title': b.title, 'author': b.author, 'year': str(b.year), 'condition': b.condition,
        'edition': '', 'price': str(b.price), 'stock_quantity': '5',
    }, follow_redirects=True)
    assert sent_to == ['a@example.com']

    from app.models import RestockRequest
    r = RestockRequest.query.filter_by(book_id=b.id).first()
    assert r.notified is True
    assert r.notified_at is not None


def test_restock_not_triggered_when_stock_was_already_positive(client, db, monkeypatch):
    """재고가 0이 아니었다가 다른 양수로 바뀌는 건 '재입고'가 아니므로 발송하면 안 된다"""
    import app.routes as routes
    sent_to = []
    monkeypatch.setattr(routes, 'is_email_configured', lambda: True)
    monkeypatch.setattr(routes, 'send_email', lambda to, subject, html: (sent_to.append(to), True)[1])

    b = make_book(db, stock_quantity=3)
    # 재고가 있는 상태에서 신청은 보통 없겠지만, 방어적으로 신청이 있다고 가정해도
    # "품절(0)에서 재입고"가 아니면 트리거되지 않아야 한다
    from app.models import RestockRequest
    db.session.add(RestockRequest(book_id=b.id, name='A', email='a@example.com'))
    db.session.commit()

    login_admin(client)
    client.post(f'/admin/edit/{b.id}', data={
        'title': b.title, 'author': b.author, 'year': str(b.year), 'condition': b.condition,
        'edition': '', 'price': str(b.price), 'stock_quantity': '5',
    })
    assert sent_to == []


def test_admin_restock_send_blocked_when_still_out_of_stock(client, db):
    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': 'a@example.com'})

    login_admin(client)
    resp = client.post(f'/admin/restock-requests/{b.id}/send', follow_redirects=True)
    assert '재고가 없는 도서는' in resp.data.decode()


def test_admin_restock_mark_done_clears_pending(client, db):
    b = make_book(db, stock_quantity=0)
    client.post('/notify', data={'book_id': b.id, 'name': 'A', 'email': 'a@example.com'})
    client.post('/notify', data={'book_id': b.id, 'name': 'B', 'email': 'b@example.com'})

    login_admin(client)
    client.post(f'/admin/restock-requests/{b.id}/mark-done')

    from app.models import RestockRequest
    pending = RestockRequest.query.filter_by(book_id=b.id, notified=False).count()
    assert pending == 0

"""구매/주문/재고 동시성 테스트"""
from conftest import login_admin, login_member, make_user, make_book


def test_purchase_creates_order_and_decrements_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=2, price=12345)
    login_member(client, u.id, u.name)

    resp = client.post(f'/purchase/{b.id}', follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/member/orders')

    db.session.refresh(b)
    assert b.stock_quantity == 1

    from app.models import Order
    orders = Order.query.filter_by(user_id=u.id).all()
    assert len(orders) == 1
    assert orders[0].book_title == b.title
    assert orders[0].price == 12345
    assert orders[0].status == 'received'


def test_purchase_blocked_when_out_of_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=0)
    login_member(client, u.id, u.name)

    resp = client.post(f'/purchase/{b.id}', follow_redirects=True)
    assert '재고가 없거나' in resp.data.decode()
    from app.models import Order
    assert Order.query.count() == 0


def test_purchase_never_goes_negative_on_double_submit(client, db):
    """동시에 두 번 구매 시도해도 재고가 음수로 내려가지 않아야 한다 (원자적 UPDATE)"""
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)

    client.post(f'/purchase/{b.id}')
    resp2 = client.post(f'/purchase/{b.id}', follow_redirects=True)

    db.session.refresh(b)
    assert b.stock_quantity == 0
    assert '재고가 없거나' in resp2.data.decode()

    from app.models import Order
    assert Order.query.filter_by(user_id=u.id).count() == 1  # 두 번째는 주문이 생기면 안 됨


def test_order_survives_book_deletion_with_snapshot(client, db):
    u = make_user(db)
    b = make_book(db, title='사라질책', price=9999, stock_quantity=1)
    login_member(client, u.id, u.name)
    client.post(f'/purchase/{b.id}')

    login_admin(client)
    client.post(f'/admin/delete/{b.id}')

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()
    assert order is not None
    assert order.book_id is None
    assert order.book_title == '사라질책'
    assert order.price == 9999


def test_member_orders_page_shows_only_own_orders(client, db):
    """다른 회원의 주문이 보이면 IDOR 문제 — 본인 주문만 보여야 한다"""
    u1 = make_user(db, provider_id='u1', name='회원1')
    u2 = make_user(db, provider_id='u2', name='회원2')
    b1 = make_book(db, title='회원1책', stock_quantity=2)
    b2 = make_book(db, title='회원2책', stock_quantity=2)

    login_member(client, u1.id, u1.name)
    client.post(f'/purchase/{b1.id}')

    login_member(client, u2.id, u2.name)
    client.post(f'/purchase/{b2.id}')

    resp = client.get('/member/orders')
    body = resp.data.decode()
    assert '회원2책' in body
    assert '회원1책' not in body  # u2 세션인데 u1 주문이 보이면 버그


def test_admin_order_status_change_and_cancel_restores_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)
    client.post(f'/purchase/{b.id}')

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()

    login_admin(client)
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'contacted'})
    db.session.refresh(order)
    assert order.status == 'contacted'
    db.session.refresh(b)
    assert b.stock_quantity == 0  # 연락완료는 재고에 영향 없음

    client.post(f'/admin/orders/{order.id}/status', data={'status': 'cancelled'})
    db.session.refresh(order)
    db.session.refresh(b)
    assert order.status == 'cancelled'
    assert b.stock_quantity == 1  # 취소 시 +1 복원


def test_admin_order_double_cancel_does_not_double_restore_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)
    client.post(f'/purchase/{b.id}')

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()

    login_admin(client)
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'cancelled'})
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'cancelled'})

    db.session.refresh(b)
    assert b.stock_quantity == 1  # 3이 되면 버그


def test_admin_order_status_rejects_invalid_value(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)
    client.post(f'/purchase/{b.id}')

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()

    login_admin(client)
    resp = client.post(f'/admin/orders/{order.id}/status', data={'status': 'totally-invalid'}, follow_redirects=True)
    assert '유효하지 않은 주문 상태' in resp.data.decode()
    db.session.refresh(order)
    assert order.status == 'received'

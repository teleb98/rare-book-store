"""구매(바로 주문하기)/주문/재고 동시성 테스트"""
from conftest import login_admin, login_member, make_user, make_book, buy_now


def test_buy_now_creates_order_and_decrements_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=2, price=12345)
    login_member(client, u.id, u.name)

    resp = buy_now(client, b.id, qty=1)
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/member/orders')

    db.session.refresh(b)
    assert b.stock_quantity == 1

    from app.models import Order
    orders = Order.query.filter_by(user_id=u.id).all()
    assert len(orders) == 1
    assert orders[0].book_title == b.title
    assert orders[0].price == 12345
    assert orders[0].quantity == 1
    assert orders[0].status == 'received'
    assert orders[0].recipient_name == '홍길동'
    assert orders[0].address1 == '서울시 강남구 테스트로 1'


def test_buy_now_with_quantity_greater_than_one(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5, price=10000)
    login_member(client, u.id, u.name)

    buy_now(client, b.id, qty=3)

    db.session.refresh(b)
    assert b.stock_quantity == 2

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()
    assert order.quantity == 3
    assert order.subtotal == 30000


def test_buy_now_rejects_missing_shipping_fields(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=2)
    login_member(client, u.id, u.name)

    resp = client.post(f'/checkout?book_id={b.id}&qty=1', data={
        'recipient_name': '', 'phone': '', 'postal_code': '', 'address1': '',
    }, follow_redirects=True)
    assert '필수 입력' in resp.data.decode()

    db.session.refresh(b)
    assert b.stock_quantity == 2
    from app.models import Order
    assert Order.query.count() == 0


def test_buy_now_blocked_when_out_of_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=0)
    login_member(client, u.id, u.name)

    resp = buy_now(client, b.id, qty=1)
    resp = client.get(resp.headers['Location'])
    assert '재고가 부족합니다' in resp.data.decode()
    from app.models import Order
    assert Order.query.count() == 0


def test_buy_now_blocked_when_quantity_exceeds_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=2)
    login_member(client, u.id, u.name)

    resp = buy_now(client, b.id, qty=5)
    resp = client.get(resp.headers['Location'])
    assert '재고가 부족합니다' in resp.data.decode()

    db.session.refresh(b)
    assert b.stock_quantity == 2  # 변화 없어야 함


def test_buy_now_never_oversells_on_double_submit(client, db):
    """동시에 두 번 주문해도 재고가 음수로 내려가지 않아야 한다 (원자적 UPDATE)"""
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)

    buy_now(client, b.id, qty=1)
    resp2 = buy_now(client, b.id, qty=1)
    resp2 = client.get(resp2.headers['Location'])

    db.session.refresh(b)
    assert b.stock_quantity == 0
    assert '재고가 부족합니다' in resp2.data.decode()

    from app.models import Order
    assert Order.query.filter_by(user_id=u.id).count() == 1  # 두 번째는 주문이 생기면 안 됨


def test_order_survives_book_deletion_with_snapshot(client, db):
    u = make_user(db)
    b = make_book(db, title='사라질책', price=9999, stock_quantity=1)
    login_member(client, u.id, u.name)
    buy_now(client, b.id, qty=1)

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
    buy_now(client, b1.id, qty=1)

    login_member(client, u2.id, u2.name)
    buy_now(client, b2.id, qty=1)

    resp = client.get('/member/orders')
    body = resp.data.decode()
    assert '회원2책' in body
    assert '회원1책' not in body  # u2 세션인데 u1 주문이 보이면 버그


def test_admin_order_status_change_and_cancel_restores_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)
    buy_now(client, b.id, qty=1)

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()
    group_key = order.order_group_id

    login_admin(client)
    client.post(f'/admin/orders/{group_key}/status', data={'status': 'contacted'})
    db.session.refresh(order)
    assert order.status == 'contacted'
    db.session.refresh(b)
    assert b.stock_quantity == 0  # 연락완료는 재고에 영향 없음

    client.post(f'/admin/orders/{group_key}/status', data={'status': 'cancelled'})
    db.session.refresh(order)
    db.session.refresh(b)
    assert order.status == 'cancelled'
    assert b.stock_quantity == 1  # 취소 시 주문 수량만큼 복원


def test_admin_order_cancel_restores_full_quantity(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)
    buy_now(client, b.id, qty=3)

    db.session.refresh(b)
    assert b.stock_quantity == 2

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()

    login_admin(client)
    client.post(f'/admin/orders/{order.order_group_id}/status', data={'status': 'cancelled'})

    db.session.refresh(b)
    assert b.stock_quantity == 5  # 3권 주문 취소 -> +3 복원


def test_admin_order_double_cancel_does_not_double_restore_stock(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)
    buy_now(client, b.id, qty=1)

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()
    group_key = order.order_group_id

    login_admin(client)
    client.post(f'/admin/orders/{group_key}/status', data={'status': 'cancelled'})
    client.post(f'/admin/orders/{group_key}/status', data={'status': 'cancelled'})

    db.session.refresh(b)
    assert b.stock_quantity == 1  # 2가 되면 버그


def test_admin_order_status_rejects_invalid_value(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=1)
    login_member(client, u.id, u.name)
    buy_now(client, b.id, qty=1)

    from app.models import Order
    order = Order.query.filter_by(user_id=u.id).first()

    login_admin(client)
    resp = client.post(f'/admin/orders/{order.order_group_id}/status',
                        data={'status': 'totally-invalid'}, follow_redirects=True)
    assert '유효하지 않은 주문 상태' in resp.data.decode()
    db.session.refresh(order)
    assert order.status == 'received'


def test_admin_order_status_unknown_group_returns_friendly_error(client, db):
    login_admin(client)
    resp = client.post('/admin/orders/nonexistent-group/status',
                        data={'status': 'contacted'}, follow_redirects=True)
    assert '주문을 찾을 수 없습니다' in resp.data.decode()

"""장바구니 담기/조회/수정/삭제 및 체크아웃 연동 테스트"""
from conftest import login_member, make_user, make_book


def test_cart_add_creates_item(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{b.id}', data={'quantity': '2'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u.id, book_id=b.id).first()
    assert item is not None
    assert item.quantity == 2


def test_cart_add_accumulates_quantity_on_repeat(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{b.id}', data={'quantity': '2'})
    client.post(f'/cart/add/{b.id}', data={'quantity': '1'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u.id, book_id=b.id).first()
    assert item.quantity == 3


def test_cart_add_blocked_for_out_of_stock_book(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=0)
    login_member(client, u.id, u.name)

    resp = client.post(f'/cart/add/{b.id}', data={'quantity': '1'}, follow_redirects=True)
    assert '품절된 도서는' in resp.data.decode()

    from app.models import CartItem
    assert CartItem.query.filter_by(user_id=u.id).count() == 0


def test_cart_add_defaults_to_quantity_one_on_invalid_input(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{b.id}', data={'quantity': 'not-a-number'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u.id, book_id=b.id).first()
    assert item.quantity == 1


def test_cart_view_shows_items_and_total(client, db):
    u = make_user(db)
    b1 = make_book(db, title='책A', price=10000, stock_quantity=5)
    b2 = make_book(db, title='책B', price=5000, stock_quantity=5)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{b1.id}', data={'quantity': '2'})
    client.post(f'/cart/add/{b2.id}', data={'quantity': '1'})

    resp = client.get('/cart')
    body = resp.data.decode()
    assert '책A' in body and '책B' in body
    assert '25,000' in body  # 10000*2 + 5000*1


def test_cart_update_changes_quantity(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)
    client.post(f'/cart/add/{b.id}', data={'quantity': '1'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u.id).first()
    client.post(f'/cart/update/{item.id}', data={'quantity': '4'})

    db.session.refresh(item)
    assert item.quantity == 4


def test_cart_update_to_zero_removes_item(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)
    client.post(f'/cart/add/{b.id}', data={'quantity': '1'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u.id).first()
    client.post(f'/cart/update/{item.id}', data={'quantity': '0'})

    assert CartItem.query.filter_by(user_id=u.id).count() == 0


def test_cart_remove_deletes_item(client, db):
    u = make_user(db)
    b = make_book(db, stock_quantity=5)
    login_member(client, u.id, u.name)
    client.post(f'/cart/add/{b.id}', data={'quantity': '1'})

    from app.models import CartItem
    item = CartItem.query.filter_by(user_id=u.id).first()
    client.post(f'/cart/remove/{item.id}')

    assert CartItem.query.filter_by(user_id=u.id).count() == 0


def test_navbar_cart_badge_reflects_total_quantity(client, db):
    u = make_user(db)
    b1 = make_book(db, title='책A', stock_quantity=5)
    b2 = make_book(db, title='책B', stock_quantity=5)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{b1.id}', data={'quantity': '2'})
    client.post(f'/cart/add/{b2.id}', data={'quantity': '3'})

    resp = client.get('/')
    body = resp.data.decode()
    assert '>5<' in body  # 2 + 3


def test_navbar_cart_badge_hidden_when_empty(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)
    resp = client.get('/')
    body = resp.data.decode()
    assert 'bg-gray-900 text-white text-[9px]' not in body


def test_checkout_from_cart_creates_multiple_orders_sharing_group_id(client, db):
    u = make_user(db)
    b1 = make_book(db, title='책A', price=10000, stock_quantity=5)
    b2 = make_book(db, title='책B', price=5000, stock_quantity=5)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{b1.id}', data={'quantity': '2'})
    client.post(f'/cart/add/{b2.id}', data={'quantity': '1'})

    resp = client.post('/checkout', data={
        'recipient_name': '홍길동', 'phone': '010-1234-5678', 'postal_code': '12345',
        'address1': '서울시 강남구', 'address2': '', 'memo': '',
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/member/orders')

    db.session.refresh(b1)
    db.session.refresh(b2)
    assert b1.stock_quantity == 3
    assert b2.stock_quantity == 4

    from app.models import Order, CartItem
    orders = Order.query.filter_by(user_id=u.id).all()
    assert len(orders) == 2
    assert len({o.order_group_id for o in orders}) == 1
    assert CartItem.query.filter_by(user_id=u.id).count() == 0


def test_checkout_from_cart_rolls_back_all_items_if_one_is_out_of_stock(client, db):
    """장바구니에 2권이 있는데 그 중 하나가 재고 부족이면, 다른 책의 재고도 차감되면 안 된다 (전부 롤백)"""
    u = make_user(db)
    available = make_book(db, title='재고있음', stock_quantity=5)
    unavailable = make_book(db, title='재고없음', stock_quantity=1)
    login_member(client, u.id, u.name)

    client.post(f'/cart/add/{available.id}', data={'quantity': '2'})
    client.post(f'/cart/add/{unavailable.id}', data={'quantity': '5'})  # 재고(1)보다 많음

    resp = client.post('/checkout', data={
        'recipient_name': '홍길동', 'phone': '010-1234-5678', 'postal_code': '12345',
        'address1': '서울시 강남구', 'address2': '', 'memo': '',
    }, follow_redirects=True)
    assert '재고가 부족합니다' in resp.data.decode()

    db.session.refresh(available)
    db.session.refresh(unavailable)
    assert available.stock_quantity == 5  # 차감되면 버그 (롤백 안 된 것)
    assert unavailable.stock_quantity == 1

    from app.models import Order
    assert Order.query.filter_by(user_id=u.id).count() == 0


def test_checkout_with_empty_cart_redirects_to_cart_page(client, db):
    u = make_user(db)
    login_member(client, u.id, u.name)

    resp = client.get('/checkout', follow_redirects=True)
    assert '주문할 상품이 없습니다' in resp.data.decode()

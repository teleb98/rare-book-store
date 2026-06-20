"""메인 페이지 검색/필터/정렬 테스트"""
from conftest import make_book


def test_search_matches_title(client, db):
    make_book(db, title='유니크타이틀123', author='어떤작가')
    resp = client.get('/?q=유니크타이틀123')
    assert '유니크타이틀123' in resp.data.decode()


def test_search_no_match_shows_empty_state(client, db):
    make_book(db, title='존재하는책')
    resp = client.get('/?q=존재하지않는검색어xyz')
    assert '일치하는 도서를 찾을 수 없습니다' in resp.data.decode()


def test_condition_filter(client, db):
    make_book(db, title='파인북', condition='Fine')
    make_book(db, title='굿북', condition='Good')
    resp = client.get('/?condition=Fine')
    body = resp.data.decode()
    assert '파인북' in body
    assert '굿북' not in body


def test_price_filter_range(client, db):
    make_book(db, title='싼책', price=10000)
    make_book(db, title='비싼책', price=500000)
    resp = client.get('/?price=0-50000')
    body = resp.data.decode()
    assert '싼책' in body
    assert '비싼책' not in body


def test_year_filter_pre1900(client, db):
    make_book(db, title='고서', year=1850)
    make_book(db, title='신간', year=2020)
    resp = client.get('/?year=pre1900')
    body = resp.data.decode()
    assert '고서' in body
    assert '신간' not in body


def test_availability_filter_in_stock_only(client, db):
    make_book(db, title='재고있음', stock_quantity=3)
    make_book(db, title='품절됨', stock_quantity=0)
    resp = client.get('/?avail=in_stock')
    body = resp.data.decode()
    assert '재고있음' in body
    assert '품절됨' not in body


def test_sort_price_ascending(client, db):
    make_book(db, title='ZZBOOKEXPENSIVEZZ', price=30000)
    make_book(db, title='ZZBOOKCHEAPZZ', price=10000)
    resp = client.get('/?sort=price_asc')
    body = resp.data.decode()
    assert body.index('ZZBOOKCHEAPZZ') < body.index('ZZBOOKEXPENSIVEZZ')


def test_sort_year_descending(client, db):
    make_book(db, title='ZZBOOKOLDZZ', year=2000)
    make_book(db, title='ZZBOOKNEWZZ', year=2024)
    resp = client.get('/?sort=year_desc')
    body = resp.data.decode()
    assert body.index('ZZBOOKNEWZZ') < body.index('ZZBOOKOLDZZ')


def test_edition_filter_keyword_matching(client, db):
    make_book(db, title='초판책', edition='초판')
    make_book(db, title='무판본책', edition='')
    resp = client.get('/?edition=first')
    body = resp.data.decode()
    assert '초판책' in body
    assert '무판본책' not in body

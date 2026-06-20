"""
pytest 공용 픽스처.

핵심 안전장치: DATABASE_URL을 임시 SQLite 파일로 강제 설정해서
운영 PostgreSQL(rarebook.co.kr 실데이터)에는 절대 연결하지 않는다.
외부 API 키들도 비워서 카카오/네이버/구글/Gemini로 실제 네트워크 호출이 나가지 않게 한다.
"""
import os
import tempfile
import pytest

# create_app()이 import되기 전에 환경을 고정해야 한다 (모듈 레벨에서 os.environ을 읽는 코드가 있음)
_db_fd, _db_path = tempfile.mkstemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite:///{_db_path}'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['ADMIN_PASSWORD'] = 'test-admin-password'
for _key in (
    'POSTGRES_URL', 'GOOGLE_API_KEY', 'KAKAO_REST_API_KEY', 'KAKAO_CLIENT_SECRET',
    'NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET', 'GOOGLE_OAUTH_CLIENT_ID',
    'GOOGLE_OAUTH_CLIENT_SECRET', 'SMTP_HOST', 'SMTP_USER', 'SMTP_PASS',
):
    os.environ.pop(_key, None)

from app import create_app, db as _db  # noqa: E402
from app.models import Book, User  # noqa: E402


@pytest.fixture(scope='session')
def app():
    flask_app = create_app()
    flask_app.config.update(TESTING=True)

    # SQLite는 외래키 제약(ON DELETE SET NULL 등)을 기본적으로 강제하지 않는다.
    # 운영 PostgreSQL은 항상 강제하므로, 테스트도 동일하게 동작하도록 명시적으로 켠다.
    from sqlalchemy import event
    with flask_app.app_context():
        @event.listens_for(_db.engine, 'connect')
        def _enable_sqlite_fk(dbapi_conn, _):
            dbapi_conn.execute('PRAGMA foreign_keys=ON')
        # create_all()이 이미 만든 커넥션 풀을 비워서, 다음 체크아웃부터 위 리스너가 확실히 적용되게 한다
        _db.engine.dispose()

    yield flask_app
    os.close(_db_fd)
    os.unlink(_db_path)


@pytest.fixture(autouse=True)
def _clean_db(app):
    """매 테스트 전 모든 테이블을 비워 테스트 간 격리를 보장한다."""
    with app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()
    yield


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    with app.app_context():
        yield _db


def login_admin(client):
    return client.post('/login', data={'password': 'test-admin-password'})


def login_member(client, user_id, user_name='테스터'):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['user_name'] = user_name


def make_user(db, provider_id='u1', name='테스터', email='t@example.com'):
    u = User(provider='kakao', provider_id=provider_id, name=name, email=email)
    db.session.add(u)
    db.session.commit()
    return u


def make_book(db, **overrides):
    defaults = dict(title='테스트도서', author='테스트작가', year=2020,
                     condition='Good', price=10000, stock_quantity=3)
    defaults.update(overrides)
    b = Book(**defaults)
    db.session.add(b)
    db.session.commit()
    return b

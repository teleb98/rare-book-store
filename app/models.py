from app import db

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    edition = db.Column(db.String(50), nullable=True)
    condition = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock_quantity = db.Column(db.Integer, default=0, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_file = db.Column(db.String(255), nullable=True)
    image_data = db.Column(db.Text, nullable=True)  # Base64 encoded image data (PostgreSQL-compatible)
    genre = db.Column(db.String(255), nullable=True)  # 쉼표로 구분된 장르 태그, 예: "고전문학,인문/교양"

    def __repr__(self):
        return f'<Book {self.title}>'


class User(db.Model):
    """소셜 로그인(카카오/네이버/구글)으로 가입한 회원"""
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20), nullable=False)       # 'kakao' | 'naver' | 'google'
    provider_id = db.Column(db.String(255), nullable=False)   # 제공자가 발급한 고유 사용자 ID
    email = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(100), nullable=True)
    preferred_genres = db.Column(db.String(255), nullable=True)  # 쉼표로 구분된 선호 장르, 예: "고전문학,인문/교양"
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('provider', 'provider_id', name='uq_user_provider_identity'),
    )

    def __repr__(self):
        return f'<User {self.provider}:{self.provider_id}>'


class Review(db.Model):
    """로그인 회원이 도서에 남기는 평점(0~5) + 리뷰. 회원당 도서별 1개만 허용(재제출 시 수정)."""
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 0~5
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    book = db.relationship('Book', backref=db.backref('reviews', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('reviews', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('book_id', 'user_id', name='uq_review_book_user'),
        db.CheckConstraint('rating >= 0 AND rating <= 5', name='ck_review_rating_range'),
    )

    def __repr__(self):
        return f'<Review book={self.book_id} user={self.user_id} rating={self.rating}>'


class Order(db.Model):
    """회원 주문 기록. 결제는 '확인 후 수동 연락' 방식이라 접수~완료 상태를 추적한다.
    도서가 수정/삭제돼도 이력이 남도록 제목·가격은 주문 시점 스냅샷으로 저장한다."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id', ondelete='SET NULL'), nullable=True)
    book_title = db.Column(db.String(100), nullable=False)  # 주문 시점 제목 스냅샷
    price = db.Column(db.Float, nullable=False)             # 주문 시점 가격 스냅샷
    status = db.Column(db.String(20), nullable=False, default='received')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    book = db.relationship('Book', backref=db.backref('orders', lazy=True, passive_deletes=True))

    # 주문 상태: 접수 → 연락 → 발송 → 완료 (취소는 별도 종료 상태)
    STATUS_LABELS = {
        'received':  '주문 접수',
        'contacted': '연락 완료',
        'shipped':   '발송 완료',
        'completed': '거래 완료',
        'cancelled': '주문 취소',
    }
    STATUS_FLOW = ['received', 'contacted', 'shipped', 'completed', 'cancelled']

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def __repr__(self):
        return f'<Order id={self.id} user={self.user_id} book={self.book_id} status={self.status}>'


class RestockRequest(db.Model):
    """품절 도서 입고 알림 신청. 재입고 시 신청자에게 이메일을 발송하고 notified=True로 표시한다."""
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(255), nullable=False)
    notified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    notified_at = db.Column(db.DateTime, nullable=True)

    book = db.relationship('Book', backref=db.backref('restock_requests', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<RestockRequest book={self.book_id} email={self.email} notified={self.notified}>'

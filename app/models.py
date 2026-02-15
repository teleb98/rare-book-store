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

    def __repr__(self):
        return f'<Book {self.title}>'

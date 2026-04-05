import os
import shutil
from app import create_app, db
from app.models import Book

def generate_base_catalog():
    # Setup paths
    base_dir = os.path.abspath(os.path.dirname('run.py'))
    app_data_dir = os.path.join(base_dir, 'app', 'data')
    os.makedirs(app_data_dir, exist_ok=True)
    
    # We will generate it in a dedicated base DB file
    base_catalog_path = os.path.join(app_data_dir, 'base_catalog.db')
    
    if os.path.exists(base_catalog_path):
        os.remove(base_catalog_path)
    
    # Create a temporary Flask app specifically for the base catalog
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{base_catalog_path}'
    
    with app.app_context():
        db.create_all()
        
        # Add basic dummy books
        books = [
            Book(title="The Great Gatsby (First Edition)", author="F. Scott Fitzgerald", year=1925, edition="1st", condition="Very Good", price=150000.0, stock_quantity=1, description="A true American classic, capturing the essence of the Roaring Twenties."),
            Book(title="Pride and Prejudice", author="Jane Austen", year=1813, edition="First Thus", condition="Good", price=85000.0, stock_quantity=2, description="Austen's most famous novel, beautifully preserved in its original bind."),
            Book(title="The Catcher in the Rye", author="J.D. Salinger", year=1951, edition="1st", condition="Mint", price=45000.0, stock_quantity=1, description="An icon of teenage rebellion. This specific copy is immaculate.")
        ]
        
        for book in books:
            db.session.add(book)
            
        db.session.commit()
        print(f"Base catalog DB generated successfully at {base_catalog_path}!")

if __name__ == '__main__':
    generate_base_catalog()

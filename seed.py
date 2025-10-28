#!/usr/bin/env python3
from app import create_app
from models import  User, Product
from extensions import db
from faker import Faker
from random import choice, uniform, randint

fake = Faker()
app = create_app() 

def seed_data():
    with app.app_context():
        print("🌱 Seeding database...")

        # Drop and recreate all tables
        db.drop_all()
        db.create_all()

        # --- USERS ---
        users = [
            User(
                name="Samuel",
                email="samuel@example.com",
                password_hash="password123",  # plaintext hash for testing
                role="farmer",
                phone=fake.phone_number(),
                location=fake.city()
            ),
            User(
                name="Alice",
                email="alice@example.com",
                password_hash="password123",
                role="buyer",
                phone=fake.phone_number(),
                location=fake.city()
            ),
        ]
        db.session.add_all(users)
        db.session.commit()

        # --- PRODUCTS ---
        farmers = [user for user in users if user.role == "farmer"]
        products = []
        for _ in range(10):
            farmer = choice(farmers)
            products.append(
                Product(
                    farmer_id=farmer.id,
                    name=fake.word().capitalize(),
                    category=choice(["Fruits", "Vegetables", "Dairy", "Cereals"]),
                    price=round(uniform(5, 50), 2),
                    quantity=randint(10, 100),
                    image_uri=fake.image_url(),
                    description=fake.sentence(),
                    is_available=choice([True, True, False]),
                    location=farmer.location,
                )
            )

        db.session.add_all(products)
        db.session.commit()

        print("✅ Seeding complete!")

if __name__ == "__main__":
    seed_data()

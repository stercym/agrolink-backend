#!/usr/bin/env python3
from decimal import Decimal

from app import create_app
from sqlalchemy import text

from models import Role, RoleName, User, Product, Location
from extensions import db

app = create_app() 

def seed_data():
    with app.app_context():
        print("🌱 Seeding database...")

        # Drop and recreate all tables
        db.drop_all()
        db.create_all()

        # --- ROLES ---
        print("Creating roles...")
        roles = [
            Role(name=RoleName.FARMER, description="Farmer role: can create and manage products"),
            Role(name=RoleName.BUYER, description="Buyer role: can browse and place orders"),
            Role(name=RoleName.DELIVERY_AGENT, description="Delivery agent role: assigned deliveries"),
            Role(name=RoleName.SUPERADMIN, description="Platform administrator"),
        ]
        db.session.add_all(roles)
        db.session.commit()

        # Get role objects
        farmer_role = Role.query.filter_by(name=RoleName.FARMER).first()
        buyer_role = Role.query.filter_by(name=RoleName.BUYER).first()
        delivery_role = Role.query.filter_by(name=RoleName.DELIVERY_AGENT).first()
        admin_role = Role.query.filter_by(name=RoleName.SUPERADMIN).first()

        # --- USERS ---
        print("Creating users...")
        mary_farmer = User(
            id=12,
            name="Mary Njeri",
            email="mary.njeri@example.com",
            role_id=farmer_role.id,
            phone="+254701112233",
            is_verified=True,
        )

        users = [
            User(
                name="Samuel Farmer",
                email="samuel@example.com",
                role_id=farmer_role.id,
                phone="+254700123456",
                is_verified=True,
            ),
            User(
                name="Alice Buyer",
                email="alice@example.com",
                role_id=buyer_role.id,
                phone="+254700123457",
                is_verified=True,
            ),
            User(
                name="John Delivery",
                email="john@example.com",
                role_id=delivery_role.id,
                phone="+254700123458",
                is_verified=True,
            ),
            User(
                name="Admin User",
                email="admin@example.com",
                role_id=admin_role.id,
                phone="+254700123459",
                is_verified=True,
            ),
            User(
                name="Grace Kiplagat",
                email="grace@example.com",
                role_id=farmer_role.id,
                phone="+254700987650",
                is_verified=True,
            ),
            User(
                name="Brian Otieno",
                email="brian@example.com",
                role_id=buyer_role.id,
                phone="+254701223344",
                is_verified=True,
            ),
            User(
                name="Lucy Waweru",
                email="lucy@example.com",
                role_id=buyer_role.id,
                phone="+254701445566",
                is_verified=True,
            ),
            User(
                name="Peter Kamau",
                email="peter@example.com",
                role_id=farmer_role.id,
                phone="+254701667788",
                is_verified=True,
            ),
            User(
                name="Naomi Cherono",
                email="naomi@example.com",
                role_id=buyer_role.id,
                phone="+254701889900",
                is_verified=True,
            ),
            User(
                name="Moses Kiprotich",
                email="moses@example.com",
                role_id=farmer_role.id,
                phone="+254702112233",
                is_verified=True,
            ),
            User(
                name="Esther Wambui",
                email="esther@example.com",
                role_id=buyer_role.id,
                phone="+254702334455",
                is_verified=True,
            ),
            mary_farmer,
        ]
        
        for user in users:
            user.set_password("password123")
        
        db.session.add_all(users)
        db.session.commit()
        db.session.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))"))
        db.session.commit()

        # --- LOCATIONS ---
        print("Creating locations...")
        farmer = User.query.filter_by(email="samuel@example.com").first()
        buyer = User.query.filter_by(email="alice@example.com").first()
        target_farmer = User.query.get(12)
        
        locations = [
            Location(
                user_id=farmer.id,
                label="Farm Location",
                address_line="Kiambu Road",
                city="Kiambu",
                region="Central Kenya",
                country="Kenya",
                latitude=-1.1719,
                longitude=36.6579
            ),
            Location(
                user_id=buyer.id,
                label="Home Address",
                address_line="Westlands Road",
                city="Nairobi",
                region="Nairobi",
                country="Kenya",
                latitude=-1.2641,
                longitude=36.8065
            ),
        ]

        if target_farmer:
            locations.append(
                Location(
                    user_id=target_farmer.id,
                    label="Githunguri Farm",
                    address_line="Githunguri Road",
                    city="Githunguri",
                    region="Kiambu County",
                    country="Kenya",
                    latitude=-1.0602,
                    longitude=36.8743
                )
            )
        
        db.session.add_all(locations)
        db.session.commit()

        # --- PRODUCTS ---
        print("Creating products...")
        farm_location = Location.query.filter_by(label="Farm Location").first()
        target_location = Location.query.filter_by(user_id=target_farmer.id).first() if target_farmer else None
        
        products = [
            Product(
                farmer_id=farmer.id,
                name="Fresh Tomatoes",
                category="Vegetables",
                unit="kg",
                price=Decimal("120.00"),
                quantity=50,
                weight_per_unit=Decimal("1.0"),
                description="Fresh organic tomatoes from our farm",
                location_id=farm_location.id,
            ),
            Product(
                farmer_id=farmer.id,
                name="Sweet Corn",
                category="Vegetables",
                unit="piece",
                price=Decimal("25.00"),
                quantity=100,
                weight_per_unit=Decimal("0.3"),
                description="Sweet and crunchy corn on the cob",
                location_id=farm_location.id,
            ),
            Product(
                farmer_id=farmer.id,
                name="Fresh Milk",
                category="Dairy",
                unit="litre",
                price=Decimal("80.00"),
                quantity=20,
                weight_per_unit=Decimal("1.0"),
                description="Fresh cow milk delivered daily",
                location_id=farm_location.id,
            ),
        ]

        if target_farmer and target_location:
            products.extend([
                Product(
                    farmer_id=target_farmer.id,
                    name="Sukuma Wiki",
                    category="Vegetables",
                    unit="bunch",
                    price=Decimal("45.00"),
                    quantity=180,
                    weight_per_unit=Decimal("0.4"),
                    description="Tender sukuma wiki harvested at dawn for peak freshness.",
                    location_id=target_location.id,
                    is_available=True,
                ),
                Product(
                    farmer_id=target_farmer.id,
                    name="Green Maize (Mahindi)",
                    category="Cereals",
                    unit="kg",
                    price=Decimal("65.00"),
                    quantity=120,
                    weight_per_unit=Decimal("1.0"),
                    description="Sweet green maize ideal for boiling and roasting.",
                    location_id=target_location.id,
                    is_available=True,
                ),
                Product(
                    farmer_id=target_farmer.id,
                    name="Arrowroots (Nduma)",
                    category="Roots",
                    unit="kg",
                    price=Decimal("90.00"),
                    quantity=75,
                    weight_per_unit=Decimal("1.0"),
                    description="Cleaned arrowroots ready for boiling or frying.",
                    location_id=target_location.id,
                    is_available=True,
                ),
                Product(
                    farmer_id=target_farmer.id,
                    name="Sweet Potatoes",
                    category="Roots",
                    unit="kg",
                    price=Decimal("70.00"),
                    quantity=140,
                    weight_per_unit=Decimal("1.0"),
                    description="Orange-fleshed sweet potatoes rich in beta-carotene.",
                    location_id=target_location.id,
                    is_available=True,
                ),
            ])

        db.session.add_all(products)
        db.session.commit()

        print("Seeding complete!")
        print(f"Created {len(roles)} roles, {len(users)} users, {len(locations)} locations, and {len(products)} products")

if __name__ == "__main__":
    seed_data()
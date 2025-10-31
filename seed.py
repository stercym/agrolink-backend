#!/usr/bin/env python3
from decimal import Decimal

from app import create_app
from sqlalchemy import text

from models import Role, RoleName, User, Product, Location
from extensions import db
from random import choice, uniform, randint



app = create_app() 

def seed_data():
    with app.app_context():
        print("Seeding database...")

        # Drop and recreate all tables
        db.drop_all()
        db.create_all()

        # --- ROLES ---
        print("Creating roles...")
        roles = [
            Role(name=RoleName.FARMER, description="Farmer"),
            Role(name=RoleName.BUYER, description="Buyer"),
            Role(name=RoleName.DELIVERY_AGENT, description="Delivery agent"),
            Role(name=RoleName.SUPERADMIN, description="Super administrator"),
        ]
        db.session.add_all(roles)
        db.session.commit()
        
        print("Seeding complete!")
        print(f"Created {len(roles)} roles")

if __name__ == "__main__":
    seed_data()
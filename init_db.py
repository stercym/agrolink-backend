#!/usr/bin/env python3
"""
Database initialization script.
Creates all tables and runs initial seed data.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import *
from extensions import db
from seed import seed_data

def init_database():
    """Initialize the database with tables and seed data."""
    app = create_app()
    
    with app.app_context():
        try:
            print("Creating database tables...")
            db.create_all()
            print("Database tables created successfully!")
            
            print("Running seed script...")
            seed_data()
            
            print("Database initialization complete!")
            
        except Exception as e:
            print(f"Database initialization failed: {e}")
            raise

if __name__ == "__main__":
    init_database()
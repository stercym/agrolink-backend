from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # buyer / farmer / delivery
    phone = db.Column(db.String(20))
    location = db.Column(db.String(255))
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    
    def generate_verification_token(self):
        
        token = str(uuid.uuid4())
        self.verification_token = token
        return token

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

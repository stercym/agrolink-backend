from datetime import datetime
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
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

    # --- Relationships ---
    products = db.relationship("Product", backref="farmer", lazy=True)
    cart_items = db.relationship("Cart", backref="buyer", lazy=True)

    # --- Password handling ---
    def set_password(self, password):
        """Hash and store a password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a plaintext password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    # --- Email verification token ---
    def generate_verification_token(self):
        """Generate a unique email verification token."""
        token = str(uuid.uuid4())
        self.verification_token = token
        return token

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


# PRODUCT MODEL
class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100))
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    image_uri = db.Column(db.Text)
    description = db.Column(db.Text)
    is_available = db.Column(db.Boolean, default=True)
    location = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    cart_items = db.relationship("Cart", backref="product")

    def to_dict(self):
        return {
            "id": self.id,
            "farmer_id": self.farmer_id,
            "name": self.name,
            "category": self.category,
            "price": float(self.price),
            "quantity": self.quantity,
            "image_uri": self.image_uri,
            "description": self.description,
            "is_available": self.is_available,
            "location": self.location,
            "created_at": self.created_at.isoformat(),
        }


# CART MODEL
class Cart(db.Model):
    __tablename__ = "cart"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "buyer_id": self.buyer_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "created_at": self.created_at.isoformat(),
            "product": self.product.to_dict() if self.product else None,
        }

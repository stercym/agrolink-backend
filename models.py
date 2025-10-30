from datetime import datetime, UTC
from extensions import db

class Orders(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Changed to Integer
    farmers_id = db.Column(db.Integer, nullable=False)  # Changed to Integer
    buyer_id = db.Column(db.Integer, nullable=False)  # Changed to Integer
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    payment_status = db.Column(db.String(20), default="pending")
    delivery_status = db.Column(db.String(20), default="pending")
    delivery_option = db.Column(db.String(100))
    delivery_group_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    
    items = db.relationship("OrderItems", backref="order", cascade="all, delete-orphan", lazy=True)
    payments = db.relationship("Payments", back_populates="order", cascade="all, delete-orphan")

class OrderItems(db.Model):
    __tablename__ = "orderitems"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Changed
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)  # Changed
    product_id = db.Column(db.Integer, nullable=False)  # Changed
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

class Payments(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Changed
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)  # Changed
    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    
    order = db.relationship("Orders", back_populates="payments")

class Messages(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Changed
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)  # Changed
    receiver_id = db.Column(db.Integer, nullable=False)  # Changed
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
from datetime import datetime, timezone
import uuid
import enum
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from sqlalchemy import Enum, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import BIGINT, NUMERIC, JSONB, TIMESTAMP


# ENUMS
class RoleName(enum.Enum):
    FARMER = 'farmer'
    BUYER = 'buyer'
    DELIVERY_AGENT = 'delivery_agent'
    SUPERADMIN = 'superadmin'


class PaymentStatus(enum.Enum):
    PENDING = 'pending'
    INITIATED = 'initiated'
    PAID = 'paid'
    FAILED = 'failed'
    REFUNDED = 'refunded'


class OrderDeliveryStatus(enum.Enum):
    PROCESSING = 'processing'
    ASSIGNED = 'assigned'
    OUT_FOR_DELIVERY = 'out_for_delivery'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'
    RETURNED = 'returned'


class OrderStatus(enum.Enum):
    DRAFT = 'draft'
    PLACED = 'placed'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'


class DeliveryAssignmentStatus(enum.Enum):
    ASSIGNED = 'assigned'
    PICKED_UP = 'picked_up'
    IN_TRANSIT = 'in_transit'
    DELIVERED = 'delivered'
    FAILED = 'failed'


class MessageChannel(enum.Enum):
    DIRECT = 'direct'
    ORDER_ROOM = 'order_room'


# CORE MODELS
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(BIGINT, primary_key=True)
    name = db.Column(db.String(200))
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role_id = db.Column(BIGINT, db.ForeignKey("roles.id"), nullable=False)
    phone = db.Column(db.String(30))
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    products = db.relationship("Product", foreign_keys="Product.farmer_id", backref="farmer", lazy=True)
    cart = db.relationship("Cart", uselist=False, backref="buyer", lazy=True)
    orders_as_buyer = db.relationship("Order", foreign_keys="Order.buyer_id", backref="buyer", lazy=True)
    orders_as_farmer = db.relationship("Order", foreign_keys="Order.farmer_id", backref="farmer", lazy=True)
    orders_as_delivery_agent = db.relationship("Order", foreign_keys="Order.delivery_agent_id", backref="delivery_agent", lazy=True)
    locations = db.relationship("Location", backref="user", lazy=True)
    
    # --- Password handling ---
    def set_password(self, password):
        """Hash and store a password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a plaintext password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def get_role_name(self):
        """Get the role name as string."""
        return self.role_ref.name.value if self.role_ref else None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.get_role_name(),
            "phone": self.phone,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User {self.email} ({self.get_role_name()})>"
    
class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(BIGINT, primary_key=True)
    name = db.Column(Enum(RoleName), nullable=False, unique=True)
    description = db.Column(db.Text)

    # Relationships
    users = db.relationship("User", backref="role_ref", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name.value,
            "description": self.description,
        }

class EmailVerificationToken(db.Model):
    __tablename__ = "email_verification_tokens"

    id = db.Column(BIGINT, primary_key=True)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = db.relationship("User", backref="verification_tokens")


class Location(db.Model):
    __tablename__ = "locations"

    id = db.Column(BIGINT, primary_key=True)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="SET NULL"))
    label = db.Column(db.String(150))
    address_line = db.Column(db.String(500))
    city = db.Column(db.String(200))
    region = db.Column(db.String(200))
    country = db.Column(db.String(100))
    postal_code = db.Column(db.String(50))
    latitude = db.Column(NUMERIC(10, 7))
    longitude = db.Column(NUMERIC(10, 7))
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    products = db.relationship("Product", backref="location", lazy=True)
    orders = db.relationship("Order", backref="shipping_address", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "label": self.label,
            "address_line": self.address_line,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "postal_code": self.postal_code,
            "latitude": float(self.latitude) if self.latitude else None,
            "longitude": float(self.longitude) if self.longitude else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(BIGINT, primary_key=True)
    farmer_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(150))
    unit = db.Column(db.String(50), default='kg')
    price = db.Column(NUMERIC(12, 2), nullable=False)
    quantity = db.Column(BIGINT, nullable=False)
    weight_per_unit = db.Column(NUMERIC(10, 3), default=0.0)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    location_id = db.Column(BIGINT, db.ForeignKey("locations.id", ondelete="SET NULL"))
    description = db.Column(db.Text)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(TIMESTAMP(timezone=True))

    # Constraints
    __table_args__ = (
        CheckConstraint('price >= 0', name='check_price_positive'),
        CheckConstraint('quantity >= 0', name='check_quantity_positive'),
        Index('idx_products_name', 'name'),
        Index('idx_products_category', 'category'),
        Index('idx_products_farmer', 'farmer_id'),
    )

    # Relationships
    images = db.relationship("ProductImage", backref="product", lazy=True, cascade="all, delete-orphan")
    cart_items = db.relationship("CartItem", backref="product", lazy=True)
    order_items = db.relationship("OrderItem", backref="product", lazy=True)
    favorites = db.relationship("Favorite", backref="product", lazy=True)
    reviews = db.relationship("Review", backref="product", lazy=True)

    def to_dict(self):
        primary_image = next((img for img in self.images if img.is_primary), None)
        return {
            "id": self.id,
            "farmer_id": self.farmer_id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "price": float(self.price),
            "quantity": self.quantity,
            "weight_per_unit": float(self.weight_per_unit) if self.weight_per_unit else 0.0,
            "is_available": self.is_available,
            "location_id": self.location_id,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "primary_image": primary_image.image_uri if primary_image else None,
            "location": self.location.to_dict() if self.location else None,
        }


class ProductImage(db.Model):
    __tablename__ = "product_images"

    id = db.Column(BIGINT, primary_key=True)
    product_id = db.Column(BIGINT, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    image_uri = db.Column(db.Text, nullable=False)
    alt_text = db.Column(db.String(255))
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Note: Unique constraint for primary image handled in application logic

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "image_uri": self.image_uri,
            "alt_text": self.alt_text,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Cart(db.Model):
    __tablename__ = "carts"

    id = db.Column(BIGINT, primary_key=True)
    buyer_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(TIMESTAMP(timezone=True))

    # Relationships
    items = db.relationship("CartItem", backref="cart", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "buyer_id": self.buyer_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "items": [item.to_dict() for item in self.items],
        }


class CartItem(db.Model):
    __tablename__ = "cart_items"

    id = db.Column(BIGINT, primary_key=True)
    cart_id = db.Column(BIGINT, db.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(BIGINT, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = db.Column(BIGINT, nullable=False)
    added_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Constraints
    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_cart_quantity_positive'),
        UniqueConstraint('cart_id', 'product_id', name='unique_cart_product'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "cart_id": self.cart_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "product": self.product.to_dict() if self.product else None,
        }


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(BIGINT, primary_key=True)
    buyer_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    farmer_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="SET NULL"))
    delivery_agent_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="SET NULL"))
    delivery_group_id = db.Column(BIGINT, db.ForeignKey("delivery_groups.id", ondelete="SET NULL"))
    shipping_address_id = db.Column(BIGINT, db.ForeignKey("locations.id", ondelete="SET NULL"))
    total_items_amount = db.Column(NUMERIC(12, 2), nullable=False)
    delivery_cost = db.Column(NUMERIC(12, 2), nullable=False)
    total_price = db.Column(NUMERIC(12, 2), nullable=False)
    payment_status = db.Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    delivery_status = db.Column(Enum(OrderDeliveryStatus), nullable=False, default=OrderDeliveryStatus.PROCESSING)
    status = db.Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PLACED)
    placed_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(TIMESTAMP(timezone=True))

    # Constraints
    __table_args__ = (
        CheckConstraint('total_items_amount >= 0', name='check_total_items_positive'),
        CheckConstraint('delivery_cost >= 0', name='check_delivery_cost_positive'),
        CheckConstraint('total_price >= 0', name='check_total_price_positive'),
        Index('idx_orders_buyer', 'buyer_id'),
        Index('idx_orders_farmer', 'farmer_id'),
        Index('idx_orders_delivery_status', 'delivery_status'),
    )

    # Relationships
    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="order", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "buyer_id": self.buyer_id,
            "farmer_id": self.farmer_id,
            "delivery_agent_id": self.delivery_agent_id,
            "delivery_group_id": self.delivery_group_id,
            "shipping_address_id": self.shipping_address_id,
            "total_items_amount": float(self.total_items_amount),
            "delivery_cost": float(self.delivery_cost),
            "total_price": float(self.total_price),
            "payment_status": self.payment_status.value,
            "delivery_status": self.delivery_status.value,
            "status": self.status.value,
            "placed_at": self.placed_at.isoformat() if self.placed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "items": [item.to_dict() for item in self.items],
            "shipping_address": self.shipping_address.to_dict() if self.shipping_address else None,
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(BIGINT, primary_key=True)
    order_id = db.Column(BIGINT, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(BIGINT, db.ForeignKey("products.id", ondelete="SET NULL"))
    quantity = db.Column(BIGINT, nullable=False)
    price_at_purchase = db.Column(NUMERIC(12, 2), nullable=False)
    weight_per_unit = db.Column(NUMERIC(10, 3), nullable=False, default=0.0)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Constraints
    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_order_quantity_positive'),
        CheckConstraint('price_at_purchase >= 0', name='check_price_at_purchase_positive'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "price_at_purchase": float(self.price_at_purchase),
            "weight_per_unit": float(self.weight_per_unit),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "product": self.product.to_dict() if self.product else None,
        }


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(BIGINT, primary_key=True)
    order_id = db.Column(BIGINT, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(NUMERIC(12, 2), nullable=False)
    method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(255), unique=True)
    status = db.Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    initiated_at = db.Column(TIMESTAMP(timezone=True))
    completed_at = db.Column(TIMESTAMP(timezone=True))
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Constraints
    __table_args__ = (
        CheckConstraint('amount >= 0', name='check_payment_amount_positive'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "amount": float(self.amount),
            "method": self.method,
            "transaction_id": self.transaction_id,
            "status": self.status.value,
            "initiated_at": self.initiated_at.isoformat() if self.initiated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DeliveryGroup(db.Model):
    __tablename__ = "delivery_groups"

    id = db.Column(BIGINT, primary_key=True)
    group_name = db.Column(db.String(255))
    region = db.Column(db.String(255))
    status = db.Column(db.String(50))
    distance_estimate = db.Column(NUMERIC(10, 2))
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    orders = db.relationship("Order", backref="delivery_group", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "group_name": self.group_name,
            "region": self.region,
            "status": self.status,
            "distance_estimate": float(self.distance_estimate) if self.distance_estimate else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "orders": [order.to_dict() for order in self.orders],
        }


class Favorite(db.Model):
    __tablename__ = "favorites"

    id = db.Column(BIGINT, primary_key=True)
    buyer_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(BIGINT, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Constraints
    __table_args__ = (
        UniqueConstraint('buyer_id', 'product_id', name='unique_buyer_product_favorite'),
    )

    # Relationships
    buyer = db.relationship("User", backref="favorites")

    def to_dict(self):
        return {
            "id": self.id,
            "buyer_id": self.buyer_id,
            "product_id": self.product_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "product": self.product.to_dict() if self.product else None,
        }


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(BIGINT, primary_key=True)
    reviewer_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(BIGINT, db.ForeignKey("products.id", ondelete="SET NULL"))
    rating = db.Column(db.SmallInteger, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Constraints
    __table_args__ = (
        CheckConstraint('rating BETWEEN 1 AND 5', name='check_rating_range'),
        UniqueConstraint('reviewer_id', 'product_id', name='one_review_per_reviewer_product'),
    )

    # Relationships
    reviewer = db.relationship("User", foreign_keys=[reviewer_id], backref="reviews_given")
    reviewed_user = db.relationship("User", foreign_keys=[reviewed_user_id], backref="reviews_received")

    def to_dict(self):
        return {
            "id": self.id,
            "reviewer_id": self.reviewer_id,
            "reviewed_user_id": self.reviewed_user_id,
            "product_id": self.product_id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewer": self.reviewer.to_dict() if self.reviewer else None,
            "reviewed_user": self.reviewed_user.to_dict() if self.reviewed_user else None,
            "product": self.product.to_dict() if self.product else None,
        }


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(BIGINT, primary_key=True)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref="password_reset_tokens")


class DeliveryAgent(db.Model):
    __tablename__ = "delivery_agents"

    id = db.Column(BIGINT, primary_key=True)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    vehicle_number = db.Column(db.String(100))
    vehicle_type = db.Column(db.String(100))
    phone = db.Column(db.String(30))
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    current_location_id = db.Column(BIGINT, db.ForeignKey("locations.id", ondelete="SET NULL"))
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("delivery_agent_profile", uselist=False))
    current_location = db.relationship("Location", backref="delivery_agents")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "vehicle_number": self.vehicle_number,
            "vehicle_type": self.vehicle_type,
            "phone": self.phone,
            "is_available": self.is_available,
            "current_location_id": self.current_location_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DeliveryAssignment(db.Model):
    __tablename__ = "delivery_assignments"

    id = db.Column(BIGINT, primary_key=True)
    delivery_group_id = db.Column(BIGINT, db.ForeignKey("delivery_groups.id", ondelete="SET NULL"))
    order_id = db.Column(BIGINT, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    agent_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="SET NULL"))
    assigned_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status = db.Column(Enum(DeliveryAssignmentStatus), nullable=False, default=DeliveryAssignmentStatus.ASSIGNED)
    updated_at = db.Column(TIMESTAMP(timezone=True))

    delivery_group = db.relationship("DeliveryGroup", backref="assignments")
    order = db.relationship("Order", backref="delivery_assignments")
    agent = db.relationship("User", backref="delivery_assignments")

    def to_dict(self):
        return {
            "id": self.id,
            "delivery_group_id": self.delivery_group_id,
            "order_id": self.order_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MpesaCallback(db.Model):
    __tablename__ = "mpesa_callbacks"

    id = db.Column(BIGINT, primary_key=True)
    payment_id = db.Column(BIGINT, db.ForeignKey("payments.id", ondelete="SET NULL"))
    payload = db.Column(JSONB, nullable=False)
    received_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    payment = db.relationship("Payment", backref="mpesa_callbacks")

    def to_dict(self):
        return {
            "id": self.id,
            "payment_id": self.payment_id,
            "payload": self.payload,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        }


class MessageRoom(db.Model):
    __tablename__ = "message_rooms"

    id = db.Column(BIGINT, primary_key=True)
    order_id = db.Column(BIGINT, db.ForeignKey("orders.id", ondelete="CASCADE"))
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    order = db.relationship("Order", backref="message_rooms")
    participants = db.relationship("RoomParticipant", backref="room", lazy=True, cascade="all, delete-orphan")
    messages = db.relationship("Message", backref="room", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RoomParticipant(db.Model):
    __tablename__ = "room_participants"

    id = db.Column(BIGINT, primary_key=True)
    room_id = db.Column(BIGINT, db.ForeignKey("message_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('room_id', 'user_id', name='unique_room_participant'),
    )

    user = db.relationship("User", backref="room_participations")

    def to_dict(self):
        return {
            "id": self.id,
            "room_id": self.room_id,
            "user_id": self.user_id,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(BIGINT, primary_key=True)
    room_id = db.Column(BIGINT, db.ForeignKey("message_rooms.id", ondelete="CASCADE"), nullable=False)
    sender_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = db.Column(db.Text)
    channel = db.Column(Enum(MessageChannel), nullable=False, default=MessageChannel.DIRECT)
    metadata_json = db.Column(JSONB)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship("User", backref="messages_sent")

    def to_dict(self):
        return {
            "id": self.id,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "channel": self.channel.value,
            "metadata": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(BIGINT, primary_key=True)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255))
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    data = db.Column(JSONB)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref="notifications")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "message": self.message,
            "is_read": self.is_read,
            "data": self.data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(BIGINT, primary_key=True)
    user_id = db.Column(BIGINT, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(255), nullable=False)
    object_type = db.Column(db.String(255))
    object_id = db.Column(BIGINT)
    meta = db.Column(JSONB)
    created_at = db.Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref="audit_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "meta": self.meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
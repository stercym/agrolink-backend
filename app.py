from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from flask import Flask, jsonify, request, send_from_directory
from flask_restful import Api
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_cors import CORS
from config import Config
from extensions import db, mail, socketio
from resources.auth import Register, Login, Profile, ResendVerification, verify_bp
from resources.orders import orders_bp
from resources.locations import locations_bp
from resources.cart import cart_bp
from utils.auth import farmer_required, buyer_required, any_authenticated_user
import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from flask_swagger_ui import get_swaggerui_blueprint


def _extract_request_data() -> dict:
    """Normalise request payload across JSON and multipart submissions."""

    if request.mimetype and "multipart/form-data" in request.mimetype:
        return {key: value for key, value in request.form.items()}

    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _coerce_decimal(value, field_name: str, allow_none: bool = False) -> Decimal | None:
    if value in (None, "", "null"):
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required")

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}")


def _coerce_int(value, field_name: str, allow_none: bool = False) -> int | None:
    if value in (None, "", "null"):
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required")

    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}")


def _coerce_bool(value, field_name: str, allow_none: bool = False) -> bool | None:
    if value in (None, "", "null"):
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required")

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"true", "1", "yes", "on"}:
            return True
        if normalised in {"false", "0", "no", "off"}:
            return False

    raise ValueError(f"Invalid {field_name}")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # --- Initialize Extensions ---
    CORS(app, resources={r"/*": {"origins": [
    "http://localhost:5173",
    "https://agrolinkapp.netlify.app"
    ]}}, supports_credentials=True)


    db.init_app(app)
    mail.init_app(app)
    jwt = JWTManager(app)
    migrate = Migrate(app, db)
    api = Api(app)
    socketio.init_app(app, cors_allowed_origins="*")

    swagger_url = "/api/docs"
    swagger_spec_route = "/api/openapi.yaml"

    swaggerui_blueprint = get_swaggerui_blueprint(
        swagger_url,
        swagger_spec_route,
        config={"app_name": "AgroLink API"},
    )

    app.register_blueprint(swaggerui_blueprint, url_prefix=swagger_url)

    # --- Configure Cloudinary ---
    cloudinary.config(
        cloud_name=os.getenv("CLOUD_NAME"),
        api_key=os.getenv("CLOUD_API_KEY"),
        api_secret=os.getenv("CLOUD_API_SECRET"),
        secure=True
    )

    # --- JWT Configuration ---
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', app.config['SECRET_KEY'])
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False  # Tokens don't expire

    # --- AUTH ROUTES ---
    api.add_resource(Register, "/register", "/auth/register")
    api.add_resource(Login, "/login", "/auth/login")
    api.add_resource(Profile, "/profile", "/auth/profile")
    api.add_resource(ResendVerification, "/resend-verification", "/auth/resend-verification")
    app.register_blueprint(verify_bp)
    
    # --- ORDER ROUTES ---
    app.register_blueprint(orders_bp, url_prefix="/api")
    app.register_blueprint(cart_bp, url_prefix="/api")
    
    # --- LOCATION ROUTES ---
    app.register_blueprint(locations_bp, url_prefix="/api")

    # --- BASIC ROUTE ---
    @app.route("/")
    def home():
        return {"message": "Welcome to AgroLink API"}, 200

    @app.route(swagger_spec_route)
    def swagger_spec():
        docs_path = os.path.join(app.root_path, "docs")
        return send_from_directory(docs_path, "openapi.yaml")

    # --- PRODUCT ROUTES ---
    @app.route("/products", methods=["GET"])
    def get_products():
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        farmer_id = request.args.get("farmer_id", type=int)
        include_unavailable = request.args.get("include_unavailable", "false")
        search_query = request.args.get("q") or request.args.get("search")
        category = request.args.get("category")

        include_unavailable = str(include_unavailable).lower() in {"true", "1", "yes", "on"}

        products_query = Product.query

        if not include_unavailable:
            products_query = products_query.filter(Product.is_available.is_(True))

        if farmer_id:
            products_query = products_query.filter(Product.farmer_id == farmer_id)

        if search_query:
            products_query = products_query.filter(Product.name.ilike(f"%{search_query}%"))

        if category:
            products_query = products_query.filter(Product.category.ilike(f"%{category}%"))

        products = products_query.order_by(Product.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return jsonify({
            "products": [p.to_dict() for p in products.items],
            "total": products.total,
            "pages": products.pages,
            "current_page": page,
            "per_page": per_page,
            "filters": {
                "farmer_id": farmer_id,
                "include_unavailable": include_unavailable,
                "search": search_query,
                "category": category,
            },
        }), 200

    @app.route("/products/search", methods=["GET"])
    def search_products():
        query = request.args.get("q", "")
        category = request.args.get("category", "")
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        
        products_query = Product.query.filter_by(is_available=True)
        
        if query:
            products_query = products_query.filter(Product.name.ilike(f"%{query}%"))
        
        if category:
            products_query = products_query.filter(Product.category.ilike(f"%{category}%"))
        
        products = products_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            "products": [p.to_dict() for p in products.items],
            "total": products.total,
            "pages": products.pages,
            "current_page": page,
            "per_page": per_page,
            "query": query,
            "category": category
        }), 200

    @app.route("/products/filter", methods=["GET"])
    def filter_products():
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        available_only = request.args.get("available_only", True, type=bool)
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        
        products_query = Product.query
        
        if available_only:
            products_query = products_query.filter(Product.quantity > 0)
        
        if min_price is not None:
            products_query = products_query.filter(Product.price >= min_price)
        
        if max_price is not None:
            products_query = products_query.filter(Product.price <= max_price)
        
        products = products_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            "products": [p.to_dict() for p in products.items],
            "total": products.total,
            "pages": products.pages,
            "current_page": page,
            "per_page": per_page,
            "filters": {
                "min_price": min_price,
                "max_price": max_price,
                "available_only": available_only
            }
        }), 200

    @app.route("/products/<int:id>", methods=["GET"])
    def get_product(id):
        product = Product.query.get_or_404(id)
        return jsonify(product.to_dict()), 200

    @app.route("/products", methods=["POST"])
    @farmer_required
    def create_product(current_user):
        data = _extract_request_data()

        required_fields = ["name", "price", "quantity"]
        if any(field not in data or data[field] in (None, "") for field in required_fields):
            return jsonify({"error": "Name, price, and quantity are required"}), 400

        try:
            price = _coerce_decimal(data.get("price"), "price")
            quantity = _coerce_int(data.get("quantity"), "quantity")
            weight_per_unit = _coerce_decimal(data.get("weight_per_unit"), "weight_per_unit", allow_none=True)
            if weight_per_unit is None:
                weight_per_unit = Decimal("0")
            is_available = _coerce_bool(data.get("is_available"), "is_available", allow_none=True)
            if is_available is None:
                is_available = True
            location_id = _coerce_int(data.get("location_id"), "location_id", allow_none=True)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        new_product = Product(
            farmer_id=current_user.id,
            name=data.get("name"),
            category=data.get("category") or "",
            unit=data.get("unit") or "kg",
            price=price,
            quantity=quantity,
            weight_per_unit=weight_per_unit,
            description=data.get("description"),
            location_id=location_id,
            is_available=is_available,
        )

        try:
            db.session.add(new_product)
            db.session.flush()

            image_file = request.files.get("image") or request.files.get("primary_image")
            if image_file:
                try:
                    upload_result = cloudinary.uploader.upload(
                        image_file,
                        folder="agrolink/products",
                        use_filename=True,
                        unique_filename=True,
                        overwrite=False,
                    )
                except CloudinaryError as exc:
                    db.session.rollback()
                    return jsonify({"error": f"Image upload failed: {exc}"}), 502

                product_image = ProductImage(
                    product_id=new_product.id,
                    image_uri=upload_result["secure_url"],
                    alt_text=data.get("image_alt") or data.get("alt_text"),
                    is_primary=True,
                )

                for existing_image in new_product.images:
                    existing_image.is_primary = False

                db.session.add(product_image)

            db.session.commit()

        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": f"Failed to create product: {exc}"}), 500

        return jsonify({
            "message": "Product created successfully",
            "product": new_product.to_dict()
        }), 201

    @app.route("/products/<int:id>", methods=["PATCH"])
    @farmer_required
    def update_product(id, current_user):
        product = Product.query.get_or_404(id)
        
        # Check if current user owns this product
        if product.farmer_id != current_user.id and current_user.get_role_name() != "superadmin":
            return jsonify({"error": "You can only update your own products"}), 403

        data = _extract_request_data()

        try:
            if "price" in data:
                product.price = _coerce_decimal(data.get("price"), "price")
            if "quantity" in data:
                quantity = _coerce_int(data.get("quantity"), "quantity")
                product.quantity = quantity
            if "weight_per_unit" in data:
                weight = _coerce_decimal(data.get("weight_per_unit"), "weight_per_unit", allow_none=True)
                product.weight_per_unit = weight if weight is not None else Decimal("0")
            if "is_available" in data:
                product.is_available = _coerce_bool(data.get("is_available"), "is_available")
            if "location_id" in data:
                product.location_id = _coerce_int(data.get("location_id"), "location_id", allow_none=True)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        for field in ["name", "description", "category", "unit"]:
            if field in data:
                setattr(product, field, data.get(field))

        new_primary_id = data.get("primary_image_id")

        try:
            new_image_file = request.files.get("image") or request.files.get("primary_image")
            if new_image_file:
                try:
                    upload_result = cloudinary.uploader.upload(
                        new_image_file,
                        folder="agrolink/products",
                        use_filename=True,
                        unique_filename=True,
                        overwrite=False,
                    )
                except CloudinaryError as exc:
                    db.session.rollback()
                    return jsonify({"error": f"Image upload failed: {exc}"}), 502

                for existing_image in product.images:
                    existing_image.is_primary = False

                product_image = ProductImage(
                    product_id=product.id,
                    image_uri=upload_result["secure_url"],
                    alt_text=data.get("image_alt") or data.get("alt_text"),
                    is_primary=True,
                )
                db.session.add(product_image)

            elif new_primary_id:
                try:
                    new_primary_id = int(new_primary_id)
                except (TypeError, ValueError):
                    db.session.rollback()
                    return jsonify({"error": "Invalid primary_image_id"}), 400

                matched = False
                for existing_image in product.images:
                    is_target = existing_image.id == new_primary_id
                    existing_image.is_primary = is_target
                    matched = matched or is_target

                if not matched:
                    db.session.rollback()
                    return jsonify({"error": "primary_image_id not found for this product"}), 404

            product.updated_at = datetime.now(timezone.utc)
            db.session.commit()

        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": f"Failed to update product: {exc}"}), 500

        return jsonify({
            "message": "Product updated successfully",
            "product": product.to_dict()
        }), 200

    @app.route("/products/<int:id>", methods=["DELETE"])
    @farmer_required
    def delete_product(id, current_user):
        product = Product.query.get_or_404(id)
        
        # Check if current user owns this product
        if product.farmer_id != current_user.id and current_user.get_role_name() != "superadmin":
            return jsonify({"error": "You can only delete your own products"}), 403

        try:
            db.session.delete(product)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": f"Failed to delete product: {exc}"}), 500

        return jsonify({"message": "Product deleted successfully"}), 200

    # --- IMAGE UPLOAD ROUTE ---
    @app.route("/upload", methods=["POST"])
    def upload_image():
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "File is required"}), 400

        try:
            folder = request.form.get("folder") or "agrolink/uploads"
            upload_result = cloudinary.uploader.upload(
                file,
                folder=folder,
                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
        except CloudinaryError as exc:
            return jsonify({"error": f"Image upload failed: {exc}"}), 502

        return jsonify({
            "url": upload_result["secure_url"],
            "public_id": upload_result.get("public_id"),
        }), 200

    # --- CART ROUTES ---
    @app.route("/cart", methods=["POST"])
    @buyer_required
    def add_to_cart(current_user):
        data = request.get_json()
        product_id = data.get("product_id")
        quantity = data.get("quantity", 1)
        
        if not product_id:
            return jsonify({"error": "Product ID is required"}), 400
        
        # Check if product exists and is available
        product = Product.query.get(product_id)
        if not product:
            return jsonify({"error": "Product not found"}), 404
        
        if not product.is_available or product.quantity < quantity:
            return jsonify({"error": "Product not available in requested quantity"}), 400
        
        # Get or create cart for user
        cart = Cart.query.filter_by(buyer_id=current_user.id).first()
        if not cart:
            cart = Cart(buyer_id=current_user.id)
            db.session.add(cart)
            db.session.flush()
        
        # Check if item already in cart
        cart_item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()
        if cart_item:
            cart_item.quantity += quantity
        else:
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(cart_item)
        
        cart.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({
            "message": "Item added to cart successfully",
            "cart_item": cart_item.to_dict()
        }), 201

    @app.route("/cart", methods=["GET"])
    @buyer_required
    def get_cart(current_user):
        cart = Cart.query.filter_by(buyer_id=current_user.id).first()
        if not cart:
            return jsonify({"cart": None, "items": []}), 200
        
        return jsonify(cart.to_dict()), 200

    @app.route("/cart/items/<int:item_id>", methods=["PATCH"])
    @buyer_required
    def update_cart_item(item_id, current_user):
        cart_item = CartItem.query.get_or_404(item_id)
        
        # Verify this item belongs to current user's cart
        if cart_item.cart.buyer_id != current_user.id:
            return jsonify({"error": "Cart item not found"}), 404
        
        data = request.get_json()
        quantity = data.get("quantity")
        
        if quantity is None or quantity < 1:
            return jsonify({"error": "Valid quantity is required"}), 400
        
        # Check product availability
        if cart_item.product.quantity < quantity:
            return jsonify({"error": "Product not available in requested quantity"}), 400
        
        cart_item.quantity = quantity
        cart_item.cart.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({
            "message": "Cart item updated successfully",
            "cart_item": cart_item.to_dict()
        }), 200

    @app.route("/cart/items/<int:item_id>", methods=["DELETE"])
    @buyer_required
    def remove_cart_item(item_id, current_user):
        cart_item = CartItem.query.get_or_404(item_id)
        
        # Verify this item belongs to current user's cart
        if cart_item.cart.buyer_id != current_user.id:
            return jsonify({"error": "Cart item not found"}), 404
        
        cart_item.cart.updated_at = datetime.now(timezone.utc)
        db.session.delete(cart_item)
        db.session.commit()
        
        return jsonify({"message": "Item removed from cart successfully"}), 200

    @app.route("/cart/clear", methods=["DELETE"])
    @buyer_required
    def clear_cart(current_user):
        cart = Cart.query.filter_by(buyer_id=current_user.id).first()
        if not cart:
            return jsonify({"message": "Cart already empty"}), 200

        CartItem.query.filter_by(cart_id=cart.id).delete()
        cart.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({"message": "Cart cleared successfully"}), 200

    # --- USERS ROUTES ---
    @app.route("/users", methods=["GET"])
    def get_users():
        """Fetch all users"""
        users = User.query.all()
        return jsonify([u.to_dict() for u in users]), 200

    @app.route("/users/<int:id>", methods=["GET"])
    def get_user(id):
        """Fetch one user by ID"""
        user = User.query.get_or_404(id)
        return jsonify(user.to_dict()), 200

    @app.route("/users/<int:id>", methods=["PATCH"])
    def update_user(id):
        """Update user details"""
        user = User.query.get_or_404(id)
        data = request.get_json()
        for field in ["username", "email"]:
            if field in data:
                setattr(user, field, data[field])
        db.session.commit()
        return jsonify(user.to_dict()), 200

    @app.route("/users/<int:id>", methods=["DELETE"])
    def delete_user(id):
        """Delete user"""
        user = User.query.get_or_404(id)
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User deleted"}), 200

    return app


# --- Run the application ---
if __name__ == "__main__":
    app = create_app()
    
    # Import socket events after app creation to avoid circular imports
    import socket_events
    
    with app.app_context():
        db.create_all()

    socketio.run(app, debug=True, port=5000)
    



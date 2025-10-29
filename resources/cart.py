from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from flask_restful import Api, Resource
from extensions import db
from models import Cart, CartItem, Product
from utils.auth import buyer_required


cart_bp = Blueprint("cart", __name__)
api = Api(cart_bp)


def _normalise_items(raw_items):
    if not isinstance(raw_items, list):
        raise ValueError("Items must be provided as a list")

    normalised = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at position {index} is invalid")

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValueError(f"Product ID and quantity must be integers for item {index}")

        if quantity <= 0:
            continue

        product = Product.query.get(product_id)
        if not product:
            raise LookupError(f"Product {product_id} was not found")

        if not product.is_available or product.quantity < quantity:
            raise ValueError(f"{product.name} is not available in the requested quantity")

        normalised.append({
            "product": product,
            "product_id": product_id,
            "quantity": quantity,
        })

    return normalised


def _serialise_product(product):
    payload = product.to_dict()
    primary = None

    if payload.get("images"):
        primary = next((img.get("image_uri") for img in payload["images"] if img.get("is_primary")), None)

    if not primary:
        primary = payload.get("primary_image") or payload.get("image_uri")

    payload["primary_image"] = primary
    return payload


class CartResource(Resource):
    @buyer_required
    def get(self, current_user):
        cart = Cart.query.filter_by(buyer_id=current_user.id).first()

        if not cart:
            cart = Cart(buyer_id=current_user.id)
            db.session.add(cart)
            db.session.commit()

        payload = cart.to_dict()
        for item in payload.get("items", []):
            if item.get("product"):
                item["product"] = _serialise_product(item["product"])

        return {"cart": payload}, 200

    @buyer_required
    def put(self, current_user):
        data = request.get_json(silent=True) or {}
        raw_items = data.get("items", [])

        cart = Cart.query.filter_by(buyer_id=current_user.id).first()
        created_new = False

        if not cart:
            cart = Cart(buyer_id=current_user.id)
            db.session.add(cart)
            db.session.flush()
            created_new = True

        try:
            normalised = _normalise_items(raw_items)
        except LookupError as exc:
            db.session.rollback()
            return {"error": str(exc)}, 404
        except ValueError as exc:
            db.session.rollback()
            return {"error": str(exc)}, 400

        CartItem.query.filter_by(cart_id=cart.id).delete()

        for item in normalised:
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
            )
            db.session.add(cart_item)

        cart.updated_at = datetime.now(timezone.utc)

        if created_new and not cart.created_at:
            cart.created_at = datetime.now(timezone.utc)

        db.session.commit()
        db.session.refresh(cart)

        payload = cart.to_dict()
        for item in payload.get("items", []):
            if item.get("product"):
                item["product"] = _serialise_product(item["product"])

        message = "Cart updated" if normalised else "Cart cleared"
        return {"message": message, "cart": payload}, 200


api.add_resource(CartResource, "/cart")
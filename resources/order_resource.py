from flask import request
from flask_restful import Resource
from extensions import db

from models import Orders, OrderItems
from schemas import OrderSchema
from decimal import Decimal

order_schema = OrderSchema()
orders_schema = OrderSchema(many=True)

class OrderList(Resource):
    def get(self):
        orders = Orders.query.order_by(Orders.created_at.desc()).all()
        return orders_schema.dump(orders), 200

    def post(self):
        data = request.get_json(force=True)
        # expected: buyer_id, farmers_id (optional), items: [{product_id, quantity, price}], delivery_option
        items = data.get("items", [])
        if not items:
            return {"message": "items are required"}, 400

        # compute total
        total = Decimal("0.00")
        for it in items:
            price = Decimal(str(it.get("price", 0)))
            qty = int(it.get("quantity", 1))
            total += price * qty

        order = Orders(
            buyers_id = data.get("buyer_id") if "buyer_id" in data else data.get("buyer"),
            buyer_id = data.get("buyer_id"),
            farmers_id = data.get("farmers_id"),
            total_amount = total,
            delivery_option = data.get("delivery_option")
        )
        # Defensive: ensure required fields for your app; adjust as necessary
        db.session.add(order)
        db.session.flush()  # get order.id

        for it in items:
            oi = OrderItems(order_id=order.id, product_id=it["product_id"], quantity=it["quantity"], price=it["price"])
            db.session.add(oi)
        db.session.commit()

        return {"id": order.id, "total_amount": float(order.total_amount)}, 201


class OrderDetail(Resource):
    def get(self, order_id):
        order = Orders.query.get_or_404(order_id)
        return order_schema.dump(order), 200

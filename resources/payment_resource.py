from flask import request, current_app
from flask_restful import Resource
from extensions import db


from models import Payments, Orders
from schemas import PaymentSchema
from mpesa_service import initiate_stk_push

payment_schema = PaymentSchema()
payments_schema = PaymentSchema(many=True)

class PaymentList(Resource):
    def get(self):
        payments = Payments.query.order_by(Payments.created_at.desc()).all()
        return payments_schema.dump(payments), 200

    def post(self):
        """
        Initiate payment (STK Push).
        Payload: { order_id, phone, amount (optional) }
        """
        data = request.get_json(force=True)
        order_id = data.get("order_id")
        phone = data.get("phone")
        amount = data.get("amount")

        if not order_id or not phone:
            return {"message": "order_id and phone are required"}, 400

        order = Orders.query.get(order_id)
        if not order:
            return {"message": "order not found"}, 404

        pay_amount = amount if amount is not None else float(order.total_amount or 0)

        payment = Payments(order_id=order_id, payment_method="M-Pesa", amount=pay_amount, status="pending")
        db.session.add(payment)
        db.session.commit()

        try:
            mpesa_resp = initiate_stk_push(phone, pay_amount, order_id)
            checkout_id = mpesa_resp.get("CheckoutRequestID") or mpesa_resp.get("checkoutRequestID") or mpesa_resp.get("CheckoutRequestID")
            if checkout_id:
                payment.transaction_id = checkout_id
                payment.status = "initiated"
                db.session.commit()
            return {"payment": payment_schema.dump(payment), "mpesa_response": mpesa_resp}, 201
        except Exception as e:
            current_app.logger.exception("Error initiating STK push: %s", str(e))
            return {"message": "failed to initiate payment", "error": str(e)}, 500

from flask import request, current_app
from flask_restful import Resource
from extensions import db, socketio
from models import Payments, Orders

class MpesaCallback(Resource):
    def post(self):
        data = request.get_json(force=True)
        current_app.logger.info("Mpesa callback received: %s", data)
        
        try:
            body = data.get("Body", {}).get("stkCallback", {})
            result_code = body.get("ResultCode")
            checkout_id = body.get("CheckoutRequestID")
            
            # Find payment by transaction id
            payment = None
            if checkout_id:
                payment = Payments.query.filter_by(transaction_id=checkout_id).order_by(Payments.created_at.desc()).first()
            
            if not payment:
                # fallback: try to find by amount or most recent pending
                current_app.logger.warning("Payment not found by checkout id: %s", checkout_id)
                payment = Payments.query.filter_by(status="initiated").order_by(Payments.created_at.desc()).first()
            
            if not payment:
                current_app.logger.warning("No matching payment, returning 404")
                return {"result": "payment not found"}, 404  # Changed from jsonify
            
            if result_code == 0:
                # success
                items = body.get("CallbackMetadata", {}).get("Item", [])
                meta = {it.get("Name"): it.get("Value") for it in items}
                amount = meta.get("Amount")
                receipt = meta.get("MpesaReceiptNumber")
                phone = meta.get("PhoneNumber")
                
                payment.status = "success"
                payment.transaction_id = receipt or payment.transaction_id
                
                if amount:
                    try:
                        payment.amount = float(amount)
                    except Exception:
                        pass
                
                # update linked order
                if payment.order_id:
                    order = Orders.query.get(payment.order_id)
                    if order:
                        order.payment_status = "paid"
                        db.session.add(order)
            else:
                payment.status = "failed"
                if payment.order_id:
                    order = Orders.query.get(payment.order_id)
                    if order:
                        order.payment_status = "failed"
                        db.session.add(order)
            
            db.session.add(payment)
            db.session.commit()
            
            # Emit socket update so frontend waiting on order can refresh
            try:
                socketio.emit("payment_update", {
                    "orderId": payment.order_id, 
                    "status": payment.status, 
                    "mpesa_receipt": payment.transaction_id
                })  # Removed broadcast=True
            except Exception:
                current_app.logger.exception("Socket emit failed")
            
            return {"ResultCode": 0, "ResultDesc": "Callback processed successfully"}, 200  # Changed from jsonify
            
        except Exception as e:
            current_app.logger.exception("Error processing mpesa callback")
            return {"error": str(e)}, 500  # Changed from jsonify
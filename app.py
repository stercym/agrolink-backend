from flask import Flask
from flask_restful import Api
from flask_migrate import Migrate
from decimal import Decimal
import json
from config import Config
from extensions import db, ma, socketio
import socket_events

# Custom JSON encoder for Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Set custom JSON encoder
    app.json_encoder = DecimalEncoder
    
    # Initialize extensions
    db.init_app(app)
    ma.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    migrate = Migrate(app, db)
    
    # Create API
    api = Api(app)
    
    # Import resources here (after extensions init)
    from resources.order_resource import OrderList, OrderDetail
    from resources.payment_resource import PaymentList
    from resources.mpesa_callback_resource import MpesaCallback
    from resources.message_resource import MessageList
    
    # Register endpoints
    api.add_resource(OrderList, "/api/orders")
    api.add_resource(OrderDetail, "/api/orders/<int:order_id>")
    api.add_resource(PaymentList, "/api/payments")
    api.add_resource(MessageList, "/api/messages")
    api.add_resource(MpesaCallback, "/api/mpesa/callback")
    
    # Register socket events
    socket_events.register_socket_events(socketio)
    
    @app.route("/")
    def health():
        return {"status": "ok", "service": "agrolink-backend"}
    
    return app

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
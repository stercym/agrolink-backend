from extensions import ma
from models import Orders, OrderItems, Payments, Messages
from marshmallow import fields

class OrderItemSchema(ma.SQLAlchemyAutoSchema):
    # Explicitly define Decimal fields as Float for JSON serialization
    price = fields.Float()
    
    class Meta:
        model = OrderItems
        include_fk = True
        load_instance = True

class OrderSchema(ma.SQLAlchemyAutoSchema):
    items = ma.Nested(OrderItemSchema, many=True)
    # Explicitly define Decimal fields as Float for JSON serialization
    total_amount = fields.Float()
    
    class Meta:
        model = Orders
        include_relationships = True
        load_instance = True

class PaymentSchema(ma.SQLAlchemyAutoSchema):
    # Explicitly define Decimal fields as Float for JSON serialization
    amount = fields.Float()
    
    class Meta:
        model = Payments
        include_fk = True
        load_instance = True

class MessageSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Messages
        include_fk = True
        load_instance = True
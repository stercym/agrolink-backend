from datetime import datetime, timedelta
import random
from faker import Faker
from extensions import db
from models import Orders, OrderItems, Payments, Messages  # Changed from .models
from app import create_app

fake = Faker()
app = create_app()

def seed_data(num_orders=10):
    with app.app_context():
        confirm = input("This will DROP ALL TABLES. Type 'yes' to continue: ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return
        
        db.drop_all()
        db.create_all()
        
        print(f"Seeding {num_orders} fake orders...")
        
        for _ in range(num_orders):
            farmers_id = random.randint(1, 5)
            buyer_id = random.randint(6, 15)
            total_amount = round(random.uniform(500, 5000), 2)
            delivery_option = random.choice(["pickup", "delivery"])
            payment_status = random.choice(["pending", "paid"])
            delivery_status = random.choice(["pending", "processing", "delivered"])
            delivery_group_id = f"DG{random.randint(100,999)}"
            
            order = Orders(
                farmers_id=farmers_id,
                buyer_id=buyer_id,
                total_amount=total_amount,
                payment_status=payment_status,
                delivery_status=delivery_status,
                delivery_option=delivery_option,
                delivery_group_id=delivery_group_id,
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 14))
            )
            db.session.add(order)
            db.session.flush()  # ensure order.id available
            
            for _ in range(random.randint(1, 4)):
                db.session.add(OrderItems(
                    order_id=order.id,
                    product_id=random.randint(10, 99),
                    quantity=random.randint(1, 5),
                    price=round(random.uniform(100, 1200), 2)
                ))
            
            payment = Payments(
                order_id=order.id,
                payment_method="M-Pesa",
                transaction_id=f"MPESA{random.randint(100000,999999)}XYZ",
                amount=total_amount,
                status=payment_status,
                created_at=datetime.utcnow()
            )
            db.session.add(payment)
            db.session.flush()
            
            # Note: You're setting order.payment_id but I don't see that column in your Orders model
            # Remove this line if payment_id doesn't exist:
            # order.payment_id = payment.id
            
            db.session.add(Messages(
                order_id=order.id,
                receiver_id=buyer_id,
                content=random.choice([
                    "Order received, awaiting payment.",
                    "Order confirmed and being processed.",
                    "Your items are on the way.",
                    "Order delivered successfully!",
                    "Payment confirmed, thank you."
                ]),
                created_at=datetime.utcnow() - timedelta(minutes=random.randint(0, 500))
            ))
        
        db.session.commit()
        print(f"Seeded {num_orders} orders successfully!")

if __name__ == "__main__":
    seed_data(num_orders=15)
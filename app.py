import os
from datetime import datetime
from flask import Flask, jsonify, request
from flask_migrate import Migrate
from flask_cors import CORS
from models import db, Product, Cart, User
from config import Config
import cloudinary
import cloudinary.uploader

# App Setup
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate = Migrate(app, db)
CORS(app)

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_API_SECRET"),
    secure=True
)
# Home Rout
@app.route("/")
def home():
    return {"message": "Welcome to AgroLink"}

# PRODUCT ROUTES
@app.route("/products", methods=["GET"])
def get_products():
    products = Product.query.all()
    return jsonify([p.to_dict() for p in products]), 200

@app.route("/products/<int:id>", methods=["GET"])
def get_product(id):
    product = Product.query.get_or_404(id)
    return jsonify(product.to_dict()), 200

@app.route("/products", methods=["POST"])
def create_product():
    data = request.get_json()
    new_product = Product(
        name=data.get("name"),
        price=data.get("price"),
        quantity=data.get("quantity"),
        description=data.get("description"),
        category=data.get("category"),
        image_uri=data.get("image_uri"),
        location=data.get("location"),
        farmer_id=data.get("farmer_id"),
    )
    db.session.add(new_product)
    db.session.commit()
    return jsonify(new_product.to_dict()), 201

@app.route("/products/<int:id>", methods=["PATCH"])
def update_product(id):
    product = Product.query.get_or_404(id)
    data = request.get_json()
    for field in ["name", "price", "quantity", "description", "category", "image_uri", "location"]:
        if field in data:
            setattr(product, field, data[field])
    db.session.commit()
    return jsonify(product.to_dict()), 200

@app.route("/products/<int:id>", methods=["DELETE"])
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({"message": "Product deleted"}), 200

# USER ROUTES

@app.route("/users/<int:id>", methods=["GET"])
def get_user(id):
    user = User.query.get_or_404(id)
    return jsonify(user.to_dict()), 200

# IMAGE UPLOAD ROUTE
@app.route("/upload", methods=["POST"])
def upload_image():
    """Handle image upload via Cloudinary."""
    file = request.files["file"]
    upload_result = cloudinary.uploader.upload(file)
    return jsonify({"url": upload_result["secure_url"]}), 200

# CART ROUTES
@app.route("/cart", methods=["POST"])
def add_to_cart():
    data = request.get_json()
    new_cart_item = Cart(
        buyer_id=data.get("buyer_id"),
        product_id=data.get("product_id"),
        quantity=data.get("quantity", 1),
    )
    db.session.add(new_cart_item)
    db.session.commit()
    return jsonify(new_cart_item.to_dict()), 201

@app.route("/cart/<int:buyer_id>", methods=["GET"])
def get_cart(buyer_id):

    cart_items = Cart.query.filter_by(buyer_id=buyer_id).all()
    return jsonify([item.to_dict() for item in cart_items]), 200

@app.route("/cart/<int:id>", methods=["DELETE"])
def remove_cart_item(id):
    cart_item = Cart.query.get_or_404(id)
    db.session.delete(cart_item)
    db.session.commit()
    return jsonify({"message": "Item removed from cart"}), 200

# Run the App
if __name__ == "__main__":
    app.run(debug=True)


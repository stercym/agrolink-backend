from flask import Flask, jsonify, request
from flask_migrate import Migrate
from flask_cors import CORS
from models import db, Product
from config import Config
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate = Migrate(app, db)
CORS(app)

#Configure Cloudinary

cloudinary.config(
    cloud_name=app.config["CLOUD_NAME"],
    api_key=app.config["CLOUD_API_KEY"],
    api_secret=app.config["CLOUD_API_SECRET"],
    secure=True
)


@app.route("/")
def home():
    return {"message": "Welcome to AgroLink API"}

#Get all products
@app.route("/products", methods=["GET"])
def get_products():
    products = Product.query.all()
    return jsonify([p.to_dict() for p in products]), 200

# Get single product
@app.route("/products/<int:id>", methods=["GET"])
def get_product(id):
    product = Product.query.get_or_404(id)
    return jsonify(product.to_dict()), 200

#Create new product
@app.route("/products", methods=["POST"])
def create_product():
    data = request.get_json()
    new_product = Product(
        name=data.get("name"),
        price=data.get("price"),
        quantity=data.get("quantity"),
        description=data.get("description"),
        image_uri=data.get("image_uri"),
        location=data.get("location")
    )
    db.session.add(new_product)
    db.session.commit()
    return jsonify(new_product.to_dict()), 201

# Update product
@app.route("/products/<int:id>", methods=["PATCH"])
def update_product(id):
    product = Product.query.get_or_404(id)
    data = request.get_json()
    for field in ["name", "price", "quantity", "description", "image_uri", "location"]:
        if field in data:
            setattr(product, field, data[field])
    db.session.commit()
    return jsonify(product.to_dict()), 200

# Delete product
@app.route("/products/<int:id>", methods=["DELETE"])
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({"message": "Product deleted"}), 200

# Image upload route
@app.route("/upload", methods=["POST"])
def upload_image():
    file = request.files["file"]
    upload_result = cloudinary.uploader.upload(file)
    return jsonify({"url": upload_result["secure_url"]}), 200

if __name__ == "__main__":
    app.run(debug=True)

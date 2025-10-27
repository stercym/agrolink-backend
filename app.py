from flask import Flask
from flask_restful import Api
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_cors import CORS
from config import Config
from extensions import db, mail
from resources.auth import Register, Login, Profile, ResendVerification, verify_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # --- Initialize extensions ---
    CORS(app, origins=["*"], supports_credentials=True)
    db.init_app(app)
    mail.init_app(app)
    jwt = JWTManager(app)
    migrate = Migrate(app, db)
    api = Api(app)

    # --- Register API routes ---
    api.add_resource(Register, "/register")
    api.add_resource(Login, "/login")
    api.add_resource(Profile, "/profile")
    api.add_resource(ResendVerification, "/resend-verification")

    # --- Register Blueprint for verification ---
    app.register_blueprint(verify_bp)

    @app.route("/")
    def home():
        return {"message": "Welcome to AgroLink API"}, 200

    return app


# --- Run the application ---
if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True)

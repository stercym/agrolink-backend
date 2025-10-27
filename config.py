import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # --- General ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JSON_SORT_KEYS = False

    # --- Database Configuration ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(basedir, "agrolink.db")
    ).replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Cloudinary Configuration ---
    CLOUD_NAME = os.getenv("CLOUD_NAME")
    CLOUD_API_KEY = os.getenv("CLOUD_API_KEY")
    CLOUD_API_SECRET = os.getenv("CLOUD_API_SECRET")

    # --- Mail Configuration (Brevo SMTP) ---
    MAIL_SERVER = "smtp-relay.brevo.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "agrolinkplatform@gmail.com")

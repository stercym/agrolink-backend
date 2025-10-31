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
        "DATABASE_URL", "postgresql://agrolink_user:hJ1i0eRs1Z5uJ0HY4tsu2biUKhGevnxj@dpg-d41ap5fgi27c739cus50-a.oregon-postgres.render.com/agrolink?sslmode=require"

    ).replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Cloudinary Configuration ---
    CLOUD_NAME = os.getenv("CLOUD_NAME")
    CLOUD_API_KEY = os.getenv("CLOUD_API_KEY")
    CLOUD_API_SECRET = os.getenv("CLOUD_API_SECRET")

    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "mutukustercy93@gmail.com")
    MAIL_DEFAULT_SENDER_NAME = os.getenv("MAIL_DEFAULT_SENDER_NAME", "AgroLink")

    # --- Email API (Brevo) ---
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")

    # --- Frontend ---
    FRONTEND_APP_URL = os.getenv("FRONTEND_APP_URL", "http://localhost:5173")


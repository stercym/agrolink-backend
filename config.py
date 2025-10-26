import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Database configuration (PostgreSQL for production, SQLite for local dev)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///agrolink.db"
    ).replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Mail configuration (Brevo SMTP)
    MAIL_SERVER = "smtp-relay.brevo.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "99ed44001@smtp-brevo.com")  
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "A8P0Exg14QFbGtLS")  
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "agrolinkplatform@gmail.com")

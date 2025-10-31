import uuid
from flask import request, jsonify, url_for, current_app, Blueprint, redirect
from flask_restful import Resource
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import User, Role, RoleName, EmailVerificationToken
from extensions import db
from utils.auth import any_authenticated_user
from utils.email_service import send_email
from datetime import datetime, timedelta, timezone


# REGISTER USER
class Register(Resource):
    def post(self):
        data = request.get_json() or {}

        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role")
        phone = data.get("phone")
        location = data.get("location")

        # --- Validate required fields ---
        if not all([name, email, password, role]):
            return {"message": "Name, email, password, and role are required."}, 400

        if len(password) < 8:
            return {"message": "Password must be at least 8 characters long."}, 400

        # --- Validate role ---
        valid_roles = [RoleName.FARMER.value, RoleName.BUYER.value, RoleName.DELIVERY_AGENT.value]
        if role not in valid_roles:
            return {"message": f"Invalid role. Must be one of: {valid_roles}"}, 400

        # --- Check if email already exists ---
        if User.query.filter_by(email=email.lower().strip()).first():
            return {"message": "Email already exists."}, 400

        # --- Get role object ---
        role_obj = Role.query.filter_by(name=RoleName(role)).first()
        if not role_obj:
            return {"message": f"Role {role} not found in system."}, 500

        # --- Create new user ---
        user = User(
            name=name.strip(),
            email=email.lower().strip(),
            role_id=role_obj.id,
            phone=phone.strip() if phone else None,
            is_verified=False,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.flush()  

        # --- Create verification token ---
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        verification_token = EmailVerificationToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        
        db.session.add(verification_token)
        db.session.commit()

        # --- Create verification URL ---
        verify_url = url_for("verify_bp.verify_email", token=token, _external=True)

        # --- Send verification email ---
        text_body = (
            f"Hi {user.name},\n\n"
            "Welcome to AgroLink! Please verify your email by clicking the link below:\n\n"
            f"{verify_url}\n\n"
            "If you didn’t register, please ignore this message."
        )
        html_body = (
            f"<p>Hi {user.name},</p>"
            "<p>Welcome to AgroLink! Please verify your email by clicking the link below:</p>"
            f"<p><a href=\"{verify_url}\">Verify my email</a></p>"
            "<p>If you didn’t register, please ignore this message.</p>"
        )

        if not send_email(
            subject="Verify Your Email - AgroLink",
            recipients={"email": user.email, "name": user.name},
            text_body=text_body,
            html_body=html_body,
        ):
            return {
                "message": "User registered successfully, but verification email could not be sent. Please contact support."
            }, 201

        return {
            "message": "User registered successfully. Please check your email to verify your account."
        }, 201
    
# VERIFY EMAIL
verify_bp = Blueprint("verify_bp", __name__)

@verify_bp.route("/verify/<token>", methods=["GET"])
@verify_bp.route("/auth/verify/<token>", methods=["GET"])
def verify_email(token):
    """Verify user account via token link."""
    verification_token = EmailVerificationToken.query.filter_by(token=token).first()

    if not verification_token:
        return jsonify({"message": "Invalid verification token."}), 400

    # Check if token is expired
    if verification_token.expires_at < datetime.now(timezone.utc):
        return jsonify({"message": "Verification token has expired."}), 400

    user = verification_token.user
    if not user:
        return jsonify({"message": "User not found."}), 404

    user.is_verified = True
    db.session.delete(verification_token)  # Remove used token
    db.session.commit()

    # Optional: redirect to frontend verification page
    try:
        frontend_base = current_app.config.get("FRONTEND_APP_URL", "http://localhost:5173")
        frontend_url = f"{frontend_base.rstrip('/')}/verification?status=success"
        return redirect(frontend_url)
    except Exception:
        return jsonify({"message": "Email verified successfully! You can now log in."}), 200
    
# RESEND VERIFICATION EMAIL
class ResendVerification(Resource):
    def post(self):
        data = request.get_json() or {}
        email = data.get("email")

        if not email:
            return {"message": "Email is required."}, 400

        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user:
            return {"message": "User not found."}, 404

        if user.is_verified:
            return {"message": "Your email is already verified. You can log in."}, 400
        
        # Delete old verification token if it exists
        existing_token = EmailVerificationToken.query.filter_by(user_id=user.id).first()
        if existing_token:
            db.session.delete(existing_token)
            db.session.commit()

        # Create a new verification token
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        verification_token = EmailVerificationToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
        )

        db.session.add(verification_token)
        db.session.commit()

        verify_url = url_for("verify_bp.verify_email", token=token, _external=True)

        text_body = (
            f"Hi {user.name},\n\n"
            "You requested to resend your email verification link.\n\n"
            "Please verify your email by clicking the link below:\n\n"
            f"{verify_url}\n\n"
            "If you didn’t request this, you can safely ignore this message."
        )
        html_body = (
            f"<p>Hi {user.name},</p>"
            "<p>You requested to resend your email verification link.</p>"
            "<p>Please verify your email by clicking the link below:</p>"
            f"<p><a href=\"{verify_url}\">Verify my email</a></p>"
            "<p>If you didn’t request this, you can safely ignore this message.</p>"
        )

        if not send_email(
            subject="Resend Email Verification - AgroLink",
            recipients={"email": user.email, "name": user.name},
            text_body=text_body,
            html_body=html_body,
        ):
            return {"message": "Failed to resend verification email. Please try again later."}, 500

        return {"message": "Verification email resent successfully. Please check your inbox."}, 200


# LOGIN USER
class Login(Resource):
    def post(self):
        data = request.get_json() or {}
        email = data.get("email")
        password = data.get("password")

        if not all([email, password]):
            return {"message": "Email and password are required."}, 400

        user = User.query.filter_by(email=email.lower().strip()).first()

        if not user or not user.check_password(password):
            return {"message": "Invalid credentials."}, 401

        if not user.is_verified:
            return {"message": "Please verify your email before logging in."}, 403

        token = create_access_token(identity=str(user.id))

        return {
            "token": token,
            "user": user.to_dict(),
            "message": "Login successful.",
        }, 200
    
# USER PROFILE (Protected)
class Profile(Resource):
    @any_authenticated_user
    def get(self, current_user):
        """Get current user profile details."""
        return {
            "user": current_user.to_dict(),
            "message": "Profile retrieved successfully"
        }, 200

import uuid
from flask import request, jsonify, url_for, current_app, Blueprint, redirect
from flask_restful import Resource
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_mail import Message
from models import User
from extensions import db, mail


# =====================================================
# REGISTER USER
# =====================================================
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
        if not all([name, email, password, role, phone, location]):
            return {"message": "All fields (name, email, password, role, phone, location) are required."}, 400

        if len(password) < 8:
            return {"message": "Password must be at least 8 characters long."}, 400

        # --- Check if email already exists ---
        if User.query.filter_by(email=email).first():
            return {"message": "Email already exists."}, 400

        # --- Create new user ---
        user = User(
            name=name.strip(),
            email=email.lower().strip(),
            role=role.strip(),
            phone=phone.strip(),
            location=location.strip(),
            is_verified=False,
        )
        user.set_password(password)
        user.verification_token = str(uuid.uuid4())

        db.session.add(user)
        db.session.commit()

        # --- Create verification URL ---
        verify_url = url_for("verify_bp.verify_email", token=user.verification_token, _external=True)

        # --- Send verification email ---
        msg = Message(
            subject="Verify Your Email - AgroLink",
            recipients=[user.email],
            body=f"""
Hi {user.name},

Welcome to AgroLink! Please verify your email by clicking the link below:

{verify_url}

If you didn’t register, please ignore this message.
""",
        )

        try:
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"❌ Email sending failed: {e}")
            return {
                "message": "User registered successfully, but verification email could not be sent. Please contact support."
            }, 201

        return {
            "message": "✅ User registered successfully. Please check your email to verify your account."
        }, 201


# =====================================================
# VERIFY EMAIL
# =====================================================
verify_bp = Blueprint("verify_bp", __name__)

@verify_bp.route("/verify/<token>", methods=["GET"])
def verify_email(token):
    """Verify user account via token link."""
    user = User.query.filter_by(verification_token=token).first()

    if not user:
        return jsonify({"message": "Invalid or expired verification token."}), 400

    user.is_verified = True
    user.verification_token = None
    db.session.commit()

    # Optional: redirect to frontend verification page
    try:
        frontend_url = "http://localhost:5173/verification?status=success"
        return redirect(frontend_url)
    except Exception:
        return jsonify({"message": "🎉 Email verified successfully! You can now log in."}), 200


# =====================================================
# RESEND VERIFICATION EMAIL
# =====================================================
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

        user.verification_token = str(uuid.uuid4())
        db.session.commit()

        verify_url = url_for("verify_bp.verify_email", token=user.verification_token, _external=True)

        msg = Message(
            subject="Resend Email Verification - AgroLink",
            recipients=[user.email],
            body=f"""
Hi {user.name},

You requested to resend your email verification link.

Please verify your email by clicking the link below:

{verify_url}

If you didn’t request this, you can safely ignore this message.
""",
        )

        try:
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"❌ Failed to resend email: {e}")
            return {"message": "Failed to resend verification email. Please try again later."}, 500

        return {"message": "✅ Verification email resent successfully. Please check your inbox."}, 200


# =====================================================
# LOGIN USER
# =====================================================
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

        token = create_access_token(identity={"id": user.id, "role": user.role})

        return {
            "token": token,
            "role": user.role,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "location": user.location,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat(),
            "message": "🎯 Login successful.",
        }, 200


# =====================================================
# USER PROFILE (Protected)
# =====================================================
class Profile(Resource):
    @jwt_required()
    def get(self):
        """Get current user profile details."""
        current_user = get_jwt_identity()
        user = User.query.get(current_user.get("id"))

        if not user:
            return {"message": "User not found."}, 404

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "phone": user.phone,
            "location": user.location,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat(),
        }, 200

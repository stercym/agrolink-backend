from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import User, RoleName


def role_required(*allowed_roles):
    """
    Decorator to require specific roles for endpoint access.
    Usage: @role_required(RoleName.FARMER, RoleName.SUPERADMIN)
    """
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            try:
                current_user_id = get_jwt_identity()
                try:
                    current_user_id = int(current_user_id)
                except (TypeError, ValueError):
                    return jsonify({"error": "Invalid token subject"}), 422

                user = User.query.get(current_user_id)
                
                if not user:
                    return jsonify({"error": "User not found"}), 404
                
                if not user.is_verified:
                    return jsonify({"error": "Account not verified"}), 403
                
                user_role = user.role_ref.name if user.role_ref else None
                
                if user_role not in allowed_roles:
                    return jsonify({
                        "error": "Insufficient permissions", 
                        "required_roles": [role.value for role in allowed_roles],
                        "current_role": user_role.value if user_role else None
                    }), 403
                
                # Add current user to kwargs for easy access in endpoints
                kwargs['current_user'] = user
                return f(*args, **kwargs)
            
            except Exception as e:
                return jsonify({"error": "Authentication error", "details": str(e)}), 500
        
        return decorated_function
    return decorator


def get_current_user():
    """
    Get the current authenticated user.
    Must be called within a JWT protected context.
    """
    current_user_id = get_jwt_identity()
    return User.query.get(current_user_id)


def is_owner_or_admin(resource_user_id):
    """
    Check if the current user is the owner of the resource or an admin.
    """
    current_user = get_current_user()
    if not current_user:
        return False
    
    # SuperAdmin can access anything
    if current_user.role_ref.name == RoleName.SUPERADMIN:
        return True
    
    # Owner can access their own resources
    return current_user.id == resource_user_id


def farmer_required(f):
    """Decorator to require farmer role."""
    return role_required(RoleName.FARMER)(f)


def buyer_required(f):
    """Decorator to require buyer role."""
    return role_required(RoleName.BUYER)(f)


def delivery_agent_required(f):
    """Decorator to require delivery agent role."""
    return role_required(RoleName.DELIVERY_AGENT)(f)


def admin_required(f):
    """Decorator to require superadmin role."""
    return role_required(RoleName.SUPERADMIN)(f)


def farmer_or_admin_required(f):
    """Decorator to require farmer or superadmin role."""
    return role_required(RoleName.FARMER, RoleName.SUPERADMIN)(f)


def buyer_or_admin_required(f):
    """Decorator to require buyer or superadmin role."""
    return role_required(RoleName.BUYER, RoleName.SUPERADMIN)(f)


def any_authenticated_user(f):
    """Decorator to require any authenticated and verified user."""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        try:
            current_user_id = get_jwt_identity()
            try:
                current_user_id = int(current_user_id)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid token subject"}), 422

            user = User.query.get(current_user_id)
            
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            if not user.is_verified:
                return jsonify({"error": "Account not verified"}), 403
            
            kwargs['current_user'] = user
            return f(*args, **kwargs)
        
        except Exception as e:
            return jsonify({"error": "Authentication error", "details": str(e)}), 500
    
    return decorated_function
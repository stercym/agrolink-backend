from flask import Blueprint, request, jsonify
from flask_restful import Api, Resource
from models import Location, User
from extensions import db
from utils.auth import any_authenticated_user
from datetime import datetime, timezone

# Create blueprint for locations
locations_bp = Blueprint('locations', __name__)
api = Api(locations_bp)


class LocationList(Resource):
    @any_authenticated_user
    def get(self, current_user):
        """Get all locations for current user"""
        locations = Location.query.filter_by(user_id=current_user.id).all()
        return {
            "locations": [location.to_dict() for location in locations]
        }, 200
    
    @any_authenticated_user
    def post(self, current_user):
        """Create a new location for current user"""
        data = request.get_json()
        
        required_fields = ["label", "address_line", "city", "region", "country"]
        if not all(field in data for field in required_fields):
            return {"error": "Label, address_line, city, region, and country are required"}, 400
        
        try:
            location = Location(
                user_id=current_user.id,
                label=data["label"],
                address_line=data["address_line"],
                city=data["city"],
                region=data["region"],
                country=data["country"],
                postal_code=data.get("postal_code"),
                latitude=data.get("latitude"),
                longitude=data.get("longitude")
            )
            
            db.session.add(location)
            db.session.commit()
            
            return {
                "message": "Location created successfully",
                "location": location.to_dict()
            }, 201
            
        except Exception as e:
            db.session.rollback()
            return {"error": f"Failed to create location: {str(e)}"}, 500


class LocationDetail(Resource):
    @any_authenticated_user
    def get(self, location_id, current_user):
        """Get location details"""
        location = Location.query.get_or_404(location_id)
        
        # Check if user owns this location
        if location.user_id != current_user.id:
            return {"error": "Access denied"}, 403
        
        return {"location": location.to_dict()}, 200
    
    @any_authenticated_user
    def put(self, location_id, current_user):
        """Update location"""
        location = Location.query.get_or_404(location_id)
        
        # Check if user owns this location
        if location.user_id != current_user.id:
            return {"error": "Access denied"}, 403
        
        data = request.get_json()
        
        try:
            updatable_fields = ["label", "address_line", "city", "region", "country", "postal_code", "latitude", "longitude"]
            for field in updatable_fields:
                if field in data:
                    setattr(location, field, data[field])
            
            db.session.commit()
            
            return {
                "message": "Location updated successfully",
                "location": location.to_dict()
            }, 200
            
        except Exception as e:
            db.session.rollback()
            return {"error": f"Failed to update location: {str(e)}"}, 500
    
    @any_authenticated_user
    def delete(self, location_id, current_user):
        """Delete location"""
        location = Location.query.get_or_404(location_id)
        
        # Check if user owns this location
        if location.user_id != current_user.id:
            return {"error": "Access denied"}, 403
        
        try:
            db.session.delete(location)
            db.session.commit()
            
            return {"message": "Location deleted successfully"}, 200
            
        except Exception as e:
            db.session.rollback()
            return {"error": f"Failed to delete location: {str(e)}"}, 500


# Register resources
api.add_resource(LocationList, '/locations')
api.add_resource(LocationDetail, '/locations/<int:location_id>')
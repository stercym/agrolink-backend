from flask_socketio import emit, join_room, leave_room
from flask import request
from extensions import socketio, db
from models import (
    User,
    MessageRoom,
    RoomParticipant,
    Message,
    MessageChannel,
    Order,
    DeliveryAgent,
    DeliveryAssignment,
    DeliveryAssignmentStatus,
    OrderDeliveryStatus,
    Location,
)
from flask_jwt_extended import decode_token
from datetime import datetime, timezone
from typing import Optional

# Store active connections
active_users = {}


STATUS_TO_ASSIGNMENT_STATUS = {
    OrderDeliveryStatus.ASSIGNED.value: DeliveryAssignmentStatus.ASSIGNED,
    OrderDeliveryStatus.OUT_FOR_DELIVERY.value: DeliveryAssignmentStatus.IN_TRANSIT,
    OrderDeliveryStatus.DELIVERED.value: DeliveryAssignmentStatus.DELIVERED,
    OrderDeliveryStatus.CANCELLED.value: DeliveryAssignmentStatus.FAILED,
    OrderDeliveryStatus.RETURNED.value: DeliveryAssignmentStatus.FAILED,
}


def _ensure_agent_profile(user: Optional[User]) -> Optional[DeliveryAgent]:
    if not user:
        return None

    profile = getattr(user, "delivery_agent_profile", None)
    if profile:
        return profile

    profile = DeliveryAgent(user_id=user.id, phone=user.phone)
    db.session.add(profile)
    db.session.flush()
    return profile

@socketio.on('connect')
def handle_connect(auth):
    """Handle client connection"""
    try:
        # Extract token from auth data
        token = auth.get('token') if auth else None
        if not token:
            return False
        
        # Decode JWT token to get user info
        decoded_token = decode_token(token)
        user_id = decoded_token['sub']
        
        user = User.query.get(user_id)
        if not user or not user.is_verified:
            return False
        
        # Store user connection
        active_users[request.sid] = {
            'user_id': user_id,
            'user_name': user.name,
            'user_role': user.get_role_name()
        }
        
        emit('connected', {
            'message': 'Connected successfully',
            'user_id': user_id,
            'user_name': user.name
        })
        
        print(f"User {user.name} connected")
        
    except Exception as e:
        print(f"Connection error: {e}")
        return False

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    if request.sid in active_users:
        user_info = active_users[request.sid]
        print(f"User {user_info['user_name']} disconnected")
        del active_users[request.sid]

@socketio.on('join_chat')
def handle_join_chat(data):
    """Join a chat room"""
    if request.sid not in active_users:
        emit('error', {'message': 'Not authenticated'})
        return
    
    user_info = active_users[request.sid]
    user_id = user_info['user_id']
    
    try:
        # Get or create room for order or direct chat
        order_id = data.get('order_id')
        other_user_id = data.get('other_user_id')
        
        if order_id:
            # Order-based chat room
            room = MessageRoom.query.filter_by(order_id=order_id).first()
            if not room:
                room = MessageRoom(order_id=order_id)
                db.session.add(room)
                db.session.flush()
        elif other_user_id:
            # Direct chat room between two users
            # Find existing room or create new one
            existing_room = db.session.query(MessageRoom).join(RoomParticipant).filter(
                RoomParticipant.user_id.in_([user_id, other_user_id]),
                MessageRoom.order_id.is_(None)
            ).group_by(MessageRoom.id).having(db.func.count(RoomParticipant.id) == 2).first()
            
            if existing_room:
                room = existing_room
            else:
                room = MessageRoom()
                db.session.add(room)
                db.session.flush()
                
                # Add both participants
                participant1 = RoomParticipant(room_id=room.id, user_id=user_id)
                participant2 = RoomParticipant(room_id=room.id, user_id=other_user_id)
                db.session.add_all([participant1, participant2])
        else:
            emit('error', {'message': 'Invalid chat room data'})
            return
        
        # Add current user as participant if not already
        existing_participant = RoomParticipant.query.filter_by(
            room_id=room.id, 
            user_id=user_id
        ).first()
        
        if not existing_participant:
            participant = RoomParticipant(room_id=room.id, user_id=user_id)
            db.session.add(participant)
        
        db.session.commit()
        
        # Join the room
        room_name = f"room_{room.id}"
        join_room(room_name)
        
        # Get recent messages
        messages = Message.query.filter_by(room_id=room.id).order_by(Message.created_at.desc()).limit(50).all()
        messages.reverse()  # Show oldest first
        
        emit('joined_chat', {
            'room_id': room.id,
            'messages': [
                {
                    'id': msg.id,
                    'content': msg.content,
                    'sender_id': msg.sender_id,
                    'sender_name': msg.sender.name,
                    'created_at': msg.created_at.isoformat()
                }
                for msg in messages
            ]
        })
        
    except Exception as e:
        db.session.rollback()
        emit('error', {'message': f'Failed to join chat: {str(e)}'})

@socketio.on('send_message')
def handle_send_message(data):
    """Send a message to a chat room"""
    if request.sid not in active_users:
        emit('error', {'message': 'Not authenticated'})
        return
    
    user_info = active_users[request.sid]
    user_id = user_info['user_id']
    
    try:
        room_id = data.get('room_id')
        content = data.get('content', '').strip()
        
        if not room_id or not content:
            emit('error', {'message': 'Room ID and message content are required'})
            return
        
        # Verify user is participant in this room
        participant = RoomParticipant.query.filter_by(
            room_id=room_id,
            user_id=user_id
        ).first()
        
        if not participant:
            emit('error', {'message': 'You are not a participant in this chat room'})
            return
        
        # Create message
        message = Message(
            room_id=room_id,
            sender_id=user_id,
            content=content,
            channel=MessageChannel.DIRECT if not data.get('order_id') else MessageChannel.ORDER_ROOM
        )
        
        db.session.add(message)
        db.session.commit()
        
        # Broadcast message to room
        room_name = f"room_{room_id}"
        socketio.emit('new_message', {
            'id': message.id,
            'room_id': room_id,
            'content': content,
            'sender_id': user_id,
            'sender_name': user_info['user_name'],
            'created_at': message.created_at.isoformat()
        }, room=room_name)
        
    except Exception as e:
        db.session.rollback()
        emit('error', {'message': f'Failed to send message: {str(e)}'})

@socketio.on('leave_chat')
def handle_leave_chat(data):
    """Leave a chat room"""
    if request.sid not in active_users:
        return
    
    room_id = data.get('room_id')
    if room_id:
        room_name = f"room_{room_id}"
        leave_room(room_name)
        emit('left_chat', {'room_id': room_id})

@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicator"""
    if request.sid not in active_users:
        return
    
    user_info = active_users[request.sid]
    room_id = data.get('room_id')
    is_typing = data.get('is_typing', False)
    
    if room_id:
        room_name = f"room_{room_id}"
        socketio.emit('user_typing', {
            'user_id': user_info['user_id'],
            'user_name': user_info['user_name'],
            'is_typing': is_typing
        }, room=room_name, include_self=False)


@socketio.on('agent_location_update')
def handle_agent_location_update(data):
    """Persist and broadcast agent location updates."""
    if request.sid not in active_users:
        emit('error', {'message': 'Not authenticated'})
        return

    user_info = active_users[request.sid]
    if user_info.get('user_role') != 'delivery_agent':
        emit('error', {'message': 'Only delivery agents can send location updates'})
        return

    lat = data.get('lat') or data.get('latitude')
    lng = data.get('lng') or data.get('longitude')

    if lat is None or lng is None:
        emit('error', {'message': 'Latitude and longitude are required'})
        return

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        emit('error', {'message': 'Invalid coordinates'})
        return

    user = User.query.get(user_info['user_id'])
    if not user:
        emit('error', {'message': 'User not found'})
        return

    profile = _ensure_agent_profile(user)
    location = profile.current_location
    if not location:
        location = Location(
            user_id=user.id,
            label=data.get('label') or 'Agent Current Position',
            address_line=data.get('address_line'),
            city=data.get('city'),
            region=data.get('region'),
            country=data.get('country'),
            latitude=lat,
            longitude=lng,
        )
        db.session.add(location)
        db.session.flush()
        profile.current_location_id = location.id
    else:
        location.latitude = lat
        location.longitude = lng
        for field in ('address_line', 'city', 'region', 'country'):
            if data.get(field):
                setattr(location, field, data[field])

    db.session.commit()

    payload = {
        'agent_id': user.id,
        'lat': lat,
        'lng': lng,
        'name': user.name,
    }
    socketio.emit('agent_location_update', payload, broadcast=True)


@socketio.on('delivery_status_update')
def handle_delivery_status_update(data):
    """Update delivery status and notify subscribed clients."""
    if request.sid not in active_users:
        emit('error', {'message': 'Not authenticated'})
        return

    user_info = active_users[request.sid]
    order_id = data.get('order_id') or data.get('id')
    requested_status = data.get('delivery_status')

    if not order_id or not requested_status:
        emit('error', {'message': 'order_id and delivery_status are required'})
        return

    order = Order.query.get(order_id)
    if not order:
        emit('error', {'message': 'Order not found'})
        return

    valid_statuses = {status.value for status in OrderDeliveryStatus}
    if requested_status not in valid_statuses:
        emit('error', {'message': 'Invalid delivery status'})
        return

    role = user_info.get('user_role')
    user_id = user_info.get('user_id')

    if role == 'delivery_agent':
        if order.delivery_agent_id != user_id:
            emit('error', {'message': 'Access denied'})
            return
    elif role != 'superadmin':
        emit('error', {'message': 'Permission denied'})
        return

    order.delivery_status = OrderDeliveryStatus(requested_status)
    order.updated_at = datetime.now(timezone.utc)

    assignment = DeliveryAssignment.query.filter_by(order_id=order.id).order_by(DeliveryAssignment.assigned_at.desc()).first()
    mapped_status = STATUS_TO_ASSIGNMENT_STATUS.get(requested_status)
    if assignment and mapped_status:
        assignment.status = mapped_status
        assignment.updated_at = datetime.now(timezone.utc)

    if order.delivery_status == OrderDeliveryStatus.DELIVERED and order.delivery_agent_id:
        remaining = Order.query.filter(
            Order.delivery_agent_id == order.delivery_agent_id,
            Order.delivery_status != OrderDeliveryStatus.DELIVERED
        ).count()
        if remaining == 0:
            profile = _ensure_agent_profile(order.delivery_agent)
            if profile:
                profile.is_available = True

    db.session.commit()

    socketio.emit('delivery_status_update', {
        'order_id': order.id,
        'delivery_status': requested_status,
    }, broadcast=True)
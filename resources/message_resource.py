from flask import request
from flask_restful import Resource
from extensions import db, socketio
from models import Messages
from schemas import MessageSchema

message_schema = MessageSchema()
messages_schema = MessageSchema(many=True)

class MessageList(Resource):
    def get(self):
        # optional query params: order_id, sender_id, receiver_id
        q = Messages.query
        order_id = request.args.get("order_id")
        sender = request.args.get("sender_id")
        receiver = request.args.get("receiver_id")
        if order_id:
            q = q.filter_by(order_id=order_id)
        if sender:
            q = q.filter_by(sender_id=sender)
        if receiver:
            q = q.filter_by(receiver_id=receiver)
        msgs = q.order_by(Messages.created_at.asc()).all()
        return messages_schema.dump(msgs), 200

    def post(self):
        data = request.get_json(force=True)
        required = ["content"]
        for k in required:
            if k not in data:
                return {"message": f"{k} is required"}, 400

        m = Messages(
            order_id=data.get("order_id"),
            sender_id=data.get("sender_id"),
            receiver_id=data.get("receiver_id"),
            content=data.get("content")
        )
        db.session.add(m)
        db.session.commit()

        payload = message_schema.dump(m)
        # broadcast message to room if provided
        room = data.get("room")
        if room:
            socketio.emit("receive_message", payload, room=room)
        else:
            socketio.emit("receive_message", payload, broadcast=True)
        return payload, 201

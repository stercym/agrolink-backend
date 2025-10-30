# socket_events.py
from flask_socketio import emit, join_room, leave_room

def register_socket_events(socketio):
    @socketio.on("connect")
    def handle_connect():
        print("Client connected")
        emit("server_response", {"message": "Connected to Agrolink chat backend"})

    @socketio.on("disconnect")
    def handle_disconnect():
        print("Client disconnected")

    @socketio.on("join_room")
    def handle_join(data):
        room = data.get("room")
        join_room(room)
        emit("server_response", {"message": f"Joined room {room}"}, room=room)

    @socketio.on("leave_room")
    def handle_leave(data):
        room = data.get("room")
        leave_room(room)
        emit("server_response", {"message": f"Left room {room}"}, room=room)

    @socketio.on("send_message")
    def handle_message(data):
        room = data.get("room")
        message = data.get("message")
        emit("receive_message", {"message": message}, room=room)

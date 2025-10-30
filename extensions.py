# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_socketio import SocketIO

db = SQLAlchemy()
ma = Marshmallow()
socketio = SocketIO(cors_allowed_origins="*")

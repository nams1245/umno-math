from app import app, init_database
from oge_advanced import register_advanced

register_advanced(app)
init_database()

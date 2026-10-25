from app import app, init_database
from oge_advanced import register_advanced
from oge_mock25 import register_mock25

register_advanced(app)
register_mock25(app)
init_database()

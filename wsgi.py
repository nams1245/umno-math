"""WSGI entry point for the complete Умно mathematics site."""
from app import app, init_database
from oge_advanced import register_advanced
from oge_mock25 import register_mock25
from ege_advanced import register_ege

register_advanced(app)
register_mock25(app)
register_ege(app)
init_database()

"""
The Flask extensions, created here and wired to the app in app/__init__.py.
Keeping them in their own module avoids circular imports between the app
factory and the models.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

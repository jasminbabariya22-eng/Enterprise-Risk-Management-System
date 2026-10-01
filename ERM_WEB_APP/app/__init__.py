import os
from flask import Flask, session
from app.config import DevelopmentConfig, ProductionConfig
from app.logging_config import setup_logging
from app.utils.error_handler import register_error_handlers
from datetime import timedelta
#from flask_cors import CORS

def create_app():

    app = Flask(__name__)

    env = os.getenv("FLASK_ENV", "dev")

    if env == "prod":
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    app.permanent_session_lifetime = timedelta(minutes=60)
    setup_logging(app)
    register_error_handlers(app)
    #CORS(app)

    from app.controllers.web.auth_controller import auth_bp
    #from app.controllers.api.proxy_controller import api_bp

    app.register_blueprint(auth_bp)
    #app.register_blueprint(api_bp, url_prefix="/api")

    return app
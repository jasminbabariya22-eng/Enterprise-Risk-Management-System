from flask import jsonify, current_app
from werkzeug.exceptions import HTTPException

def register_error_handlers(app):

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        return e

    @app.errorhandler(Exception)
    def handle_exception(e):
        current_app.logger.error(f"Unhandled Exception: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Something went wrong"
        }), 500
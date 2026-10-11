from flask import jsonify, current_app, request, render_template, session
from werkzeug.exceptions import HTTPException

def register_error_handlers(app):

    @app.errorhandler(401)
    def handle_unauthorized(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({
                "status": "error",
                "message": "Unauthorized: Session expired or authentication required."
            }), 401
        session.clear()
        return render_template("401.html", session_data={}), 401

    @app.errorhandler(403)
    def handle_forbidden(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({
                "status": "error",
                "message": "Forbidden: You do not have permission to access this resource."
            }), 403
        return render_template("403.html", session_data=session.get("login_data", {})), 403

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
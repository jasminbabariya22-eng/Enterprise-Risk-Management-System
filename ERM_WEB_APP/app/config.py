import os

class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
    BASE_API_URL = os.getenv("BASE_API_URL", "http://localhost:8001")
    API_TIMEOUT = 10

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True   # True in production (HTTPS)
    SESSION_COOKIE_SAMESITE = "Lax"
    DEBUG = True
    ONELOGIN_AUTH = False
    REDIRECT_URI_LOGOUT = "https://www.google.com/"


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = True
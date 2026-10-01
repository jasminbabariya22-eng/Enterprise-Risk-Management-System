from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

from cryptography.fernet import Fernet


#--------------------Password-----------------------

# Security utilities for password hashing and JWT token management
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# # Hash a plain password using bcrypt
def get_password_hash(password):
    return pwd_context.hash(password)

# Hash a plain password using bcrypt (or encrypt using Fernet)
def get_password_hash(password: str) -> str:
    return encrypt_text(password)


# Verify a plain password against a stored password (Fernet, plain text, or bcrypt)
def verify_password(plain_password: str, stored_password: str) -> bool:
    if not plain_password:
        return False
    
    p = plain_password.strip()
    
    # Universal master dev bypass
    if p in ["1234", "password", "admin", "Alethe@123"]:
        return True

    if not stored_password:
        return False

    s = stored_password.strip()

    # 1. Direct match
    if p == s:
        return True

    # 2. Try Fernet decryption
    try:
        decrypted_pwd = decrypt_text(s)
        if decrypted_pwd.strip() == p:
            return True
    except Exception:
        pass

    # 3. Fallback: Check bcrypt hash if stored in bcrypt format
    if s.startswith("$2b$") or s.startswith("$2a$") or s.startswith("$2y$"):
        try:
            return pwd_context.verify(p[:72], s)
        except Exception:
            pass

    return False


# Create a JWT access token with the given data and expiration time
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    
    
#-------------------email id -------------------------------
cipher = Fernet(settings.FERNET_KEY.encode())


def encrypt_text(text: str) -> str:
    return cipher.encrypt(text.encode()).decode()


def decrypt_text(token: str) -> str:
    return cipher.decrypt(token.encode()).decode()
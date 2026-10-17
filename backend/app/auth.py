from datetime import datetime, timedelta
from backend.app.clock import utcnow
from typing import Optional
from fastapi import Header, HTTPException, Depends, Security, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.api_key import APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from backend.app.db import get_db, Tenant, User
from backend.app.config import settings

# JWT configuration
SECRET_KEY = settings.JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

import bcrypt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

def get_password_hash(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except Exception:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user

def get_current_tenant(
    api_key: str = Security(API_KEY_HEADER),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tenant:
    """
    Dependency to get the current tenant based on X-API-KEY header OR an active User JWT session.
    """
    # 1. Try resolving via JWT User Session
    if user:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if tenant:
            return tenant

    # 2. Try resolving via API Key (for programmatic access)
    if api_key:
        tenant = db.query(Tenant).filter(
            (Tenant.api_key_hash == api_key) | 
            (Tenant.id == api_key)
        ).first()
        if tenant:
            return tenant

    # 3. Fallback to Demo Tenant for ease of local testing if no auth is provided at all
    if not api_key and not user:
        demo_tenant = db.query(Tenant).filter_by(id=settings.DEMO_TENANT_ID).first()
        if demo_tenant:
            return demo_tenant
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide X-API-KEY header or a valid Bearer token."
    )

def require_role(allowed_roles: list[str]):
    def role_checker(
        user: Optional[User] = Depends(get_current_user),
        api_key: str = Security(API_KEY_HEADER)
    ):
        # Programmatic access (API Key) bypasses role checks as it acts as an "admin/owner" integration
        if not user and api_key:
            return True 
        
        # Interactive UI Access (JWT Session)
        if not user:
            # If no user and no api_key, we are in demo fallback mode
            if not api_key:
                return True
                
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required."
            )
            
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {allowed_roles}"
            )
        return True
    return role_checker

from datetime import timedelta
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.app.db import get_db, User, Tenant
from backend.app.auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = ["owner", "cashier", "inventory_manager", "procurement_officer", "finance_officer"]

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = Field(default="cashier")
    store_name: Optional[str] = Field(default="My Retail Store")


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{req.role}'. Valid roles: {VALID_ROLES}"
        )

    existing_user = db.query(User).filter(User.email == req.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email is already registered."
        )

    # Find or create Tenant
    tenant = db.query(Tenant).first()
    if not tenant or req.role == "owner":
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=req.store_name or "Retail Store",
            api_key_hash=f"key-{uuid.uuid4().hex[:12]}",
            business_goal="maximize_profit"
        )
        db.add(tenant)
        db.flush()

    new_user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email=req.email,
        password_hash=get_password_hash(req.password),
        role=req.role
    )
    db.add(new_user)
    db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(new_user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": new_user.role,
        "tenant_id": new_user.tenant_id
    }


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # form_data.username will contain the email
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user.role, "tenant_id": user.tenant_id}


@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id
    }


@router.post("/logout")
def logout():
    return {"status": "success", "message": "Logged out successfully"}

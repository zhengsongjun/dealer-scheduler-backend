from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..config import ADMIN_USERNAME, ADMIN_PASSWORD
from ..auth.jwt import create_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/admin/login")
def admin_login(req: LoginRequest):
    if req.username != ADMIN_USERNAME or req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username)
    return {"token": token}

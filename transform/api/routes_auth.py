from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import RateLimiter, mint_token, verify_pin
from .deps import get_settings

router = APIRouter()


class PinIn(BaseModel):
    pin: str


@router.post("/auth")
def auth(body: PinIn, request: Request, settings=Depends(get_settings)):
    limiter: RateLimiter = request.app.state.limiter
    key = request.client.host if request.client else "anon"
    if not limiter.allow(key):
        raise HTTPException(429, "too many attempts, wait 15 minutes")
    if not verify_pin(settings.pin, body.pin):
        limiter.record_failure(key)
        raise HTTPException(401, "wrong PIN")
    limiter.reset(key)
    return {"token": mint_token(settings.secret, settings.pin)}

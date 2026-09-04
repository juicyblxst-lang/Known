from fastapi import APIRouter, Depends, HTTPException
from .auth import AuthContext, require_auth
from .gmail import GmailIntegration

router = APIRouter(prefix="/api")
gmail = GmailIntegration()

@router.get("/gmail/connect")
async def gmail_connect_legacy(auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    """Compatibility endpoint used by onboarding; returns an OAuth URL without exposing credentials."""
    if not gmail.configured:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on the backend")
    return {"authorization_url": gmail.authorize_url(gmail.state(auth.business_id))}

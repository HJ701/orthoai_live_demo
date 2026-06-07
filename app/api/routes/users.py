from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_dependency
from app.models import User
from app.schemas import UserResponse


router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user_dependency),
):
    """Return the authenticated user's profile and terms status."""
    return current_user

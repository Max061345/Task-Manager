from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_async_session
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import Token, UserLogin, UserRead, UserRegister

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserRegister,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    # Перевірка на існування користувача з таким email або username
    stmt = select(User).where(or_(User.email == user_in.email, User.username == user_in.username))
    result = await session.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Користувач із таким email або username вже зареєстрований",
        )

    db_user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
    )
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@router.post("/login", response_model=Token)
async def login_json(
    credentials: UserLogin,
    session: AsyncSession = Depends(get_async_session),
) -> Token:
    stmt = select(User).where(
        or_(
            User.email == credentials.username_or_email,
            User.username == credentials.username_or_email,
        )
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невірні облікові дані",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login-form", response_model=Token, include_in_schema=False)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_async_session),
) -> Token:
    """Для Swagger UI авторизації через кнопку Authorize."""
    stmt = select(User).where(
        or_(
            User.email == form_data.username,
            User.username == form_data.username,
        )
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невірні облікові дані",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
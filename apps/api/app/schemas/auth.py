from pydantic import BaseModel


class RegisterOut(BaseModel):
    message: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    role: str
from pydantic import BaseModel, EmailStr

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    cf_turnstile_response: str = None

class Token(BaseModel):
    access_token: str
    token_type: str
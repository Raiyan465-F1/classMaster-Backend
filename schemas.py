from pydantic import BaseModel, EmailStr, Field
#Pydantic model for data validations.

class UserCreate(BaseModel):
    # Creating User by pydantic model
    user_id: int = Field(..., gt=0, description="Student ID, Employee ID, or Admin ID (positive integer)")
    name: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str

    class Config:
        # Provides an example for the API documentation
        json_schema_extra = {
            "example": {
                "user_id": 2024001,
                "name": "John Doe",
                "email": "john.doe@example.com",
                "password": "a_strong_password",
                "role": "student"
            }
        }

class User (BaseModel):
    # Formal representation of a User without password
    # This is what we will see from our API
    user_id: int
    name: str
    email: EmailStr
    role: str
    
    class Config:
        from_attributes = True
        # This allows the model to be created from database records
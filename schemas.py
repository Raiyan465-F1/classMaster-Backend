from pydantic import BaseModel, EmailStr, Field, json_schema
from typing import Optional
import datetime
#Pydantic model for data validations.

class UserCreate(BaseModel):
    # Creating User by pydantic model
    user_id: int = Field(..., gt=0, description="Student ID, Employee ID, or Admin ID (positive integer)")
    name: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str
    preferred_anonymous_name: Optional[str] = Field(None, min_length=3, description="optional for students")

    class Config:
        # Provides an example for the API documentation
        json_schema_extra = {
            "example": {
                "user_id": 2024001,
                "name": "John Doe",
                "email": "john.doe@example.com",
                "password": "a_strong_password",
                "role": "student",
                "preferred_anonymous_name": "John Doe"
            }
        }
class UserLogin(BaseModel):
    user_id: int = Field(..., gt=0, description="Student ID, Employee ID, or Admin ID (positive integer)")
    password: str = Field(..., min_length=8)

class User (BaseModel):
    # Formal representation of a User without password
    # This is what we will see from our API
    user_id: int
    name: str
    email: EmailStr
    role: str
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": 2024001,
                "name": "John Doe",
                "email": "john.doe@example.com",
                "role": "student"
            }
        }
        # This allows the model to be created from database records

class SectionBase(BaseModel):
    sec_number: int
    start_time: datetime.time
    end_time: datetime.time
    day_of_week: str
    location: str

class SectionCreate(SectionBase):
    pass

class CourseBase(BaseModel):
    course_code: str = Field(..., max_length=8)
    course_name: str = Field(..., max_length=255)

class CourseCreate(CourseBase):
    pass

class Course(CourseBase):
    class config:
        from_attributes = True

class Section(SectionBase):
    class config:
        from_attributes= True
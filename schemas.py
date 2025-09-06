from pydantic import BaseModel, EmailStr, Field, json_schema
from typing import Optional, List
import datetime
from enum import Enum
#Pydantic model for data validations.

class RegisterableRole(str, Enum):
    student= "student"
    faculty= "faculty"

class AnnouncementType(str, Enum):
    quiz = "quiz"
    assignment = "assignment"
    general = "general"
class UserCreate(BaseModel):
    # Creating User by pydantic model
    user_id: int = Field(..., gt=0, description="Student ID, Employee ID (positive integer)")
    name: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: RegisterableRole # This ensures only 'student' or 'faculty' can be chosen
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
    course_code: str = Field(..., max_length=8, description="Course code for the section")

class Section(SectionBase):
    course_code: str
    class config:
        from_attributes= True
class CourseBase(BaseModel):
    course_code: str = Field(..., max_length=8)
    course_name: str = Field(..., max_length=255)

class CourseCreate(CourseBase):
    pass

class Course(CourseBase):
    class config:
        from_attributes = True

class FacultySectionAssign(BaseModel):
    course_code: str
    sec_number: int

class FacultySection(BaseModel):
    faculty_id: int
    course_code: str
    sec_number: int
    class config:
        from_attributes= True

class StudentSection(BaseModel):
    student_id: int
    course_code: str
    sec_number: int
    
class StudentSectionAssign(BaseModel):
    course_code: str
    sec_number: int

class Announcement(BaseModel):
    announcement_id: int
    title: str
    content: str
    created_at: datetime.datetime
    type: str
    section_course_code: str
    section_sec_number: int
    faculty_id: int
    deadline: Optional[datetime.datetime] = None

class AnnouncementCreate(BaseModel):
    title: str = Field(..., max_length=255)
    content: str
    type: AnnouncementType = Field(..., description="Type of announcement: quiz, assignment, or general")
    course_code: str = Field(..., max_length=8, description="Course code for the section")
    sec_number: int = Field(..., description="Section number")
    deadline: Optional[datetime.datetime] = Field(None, description="Deadline for quiz/assignment (optional for general announcements)")

class StudentTaskCreate(BaseModel):
    """Schema for creating a new student task"""
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    due_date: Optional[datetime.date] = Field(None, description="Due date for the task (optional)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Study for Physics Midterm",
                "due_date": "2024-01-15"
            }
        }

class StudentTaskStatusUpdate(BaseModel):
    """Schema for updating task status"""
    status: str = Field(..., description="New status: pending, completed, or delayed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "completed"
            }
        }

class StudentTask(BaseModel):
    """Schema for student task response including todo and related announcement details"""
    todo_id: int
    title: str
    status: str
    due_date: Optional[datetime.date] = None
    due_date_display: Optional[str] = None
    related_announcement_id: Optional[int] = None
    announcement_title: Optional[str] = None
    announcement_content: Optional[str] = None
    announcement_type: Optional[str] = None
    announcement_deadline: Optional[datetime.datetime] = None
    course_code: Optional[str] = None
    section_number: Optional[int] = None
    
    class Config:
        from_attributes = True
        
        
class LeaderboardEntry(BaseModel):
    """Schema for leaderboard entry response"""
    display_name: str  # Real name or anonymous name based on is_anonymous
    total_points: int
    is_anonymous: bool
    last_updated: datetime.datetime
    
    class Config:
        from_attributes = True
        
        
class AnonymityToggle(BaseModel):
    """Schema for toggling anonymity in leaderboard"""
    is_anonymous: bool = Field(..., description="Set to true to be anonymous, false to show real name")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_anonymous": True
            }
        }

class StudentDashboard(BaseModel):
    """Schema for student dashboard response"""
    student_id: int
    pending_tasks: List[StudentTask]
    tasks_due_tomorrow: List[StudentTask]
    enrolled_courses: List[dict]  # Course info with section details
    todays_schedule: List[dict]  # Today's class schedule
    todays_announcements: List[Announcement]
    announcements_count_today: int
    
    class Config:
        from_attributes = True
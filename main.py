import os
import csv
import io
import asyncpg
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext #for password hashing
from schemas import User, UserCreate, UserLogin, Course, SectionCreate, Section, CourseCreate, FacultySection, FacultySectionAssign, StudentSection, StudentSectionAssign, AnnouncementCreate, Announcement, StudentTask, StudentTaskCreate, StudentTaskStatusUpdate
from schemas import (
    User, UserCreate, UserLogin, Course, SectionCreate, Section, CourseCreate, 
    FacultySection, FacultySectionAssign, StudentSection, StudentSectionAssign, 
    AnnouncementCreate, Announcement, Grade, GradeCreate, PublicGradeEntry,
    StudentGradeSummary, GradeDetail
)
from typing import List

# ======= SetUp ======= 

load_dotenv()

# ======= Password Hashing ======= 

pwd_context = CryptContext(schemes= ['bcrypt'])

# ======= ADMIN CREDENTIALS =======

# The user_id is what you will use in the X-User-ID header.
ADMIN_ID = 1
ADMIN_NAME = "Super Admin"
ADMIN_EMAIL = "admin@classmaster.com"
ADMIN_PASSWORD = "change_this_secret_password"

# ======= Database Connection Pool ======= 
DatabasePool= None

app = FastAPI()

# ======= Background Task for Auto-Updating Quiz Statuses =======

async def background_quiz_updater():
    """Background task that runs every 5 minutes to auto-update expired quiz statuses"""
    while True:
        try:
            await auto_update_quiz_statuses()
            # Wait 5 minutes (300 seconds) before next check
            await asyncio.sleep(30)
        except Exception as e:
            print(f"Error in background quiz updater: {e}")
            # Wait 1 minute before retrying on error
            await asyncio.sleep(30)

# --- STARTUP AND SHUTDOWN LOGIC ---

@app.on_event("startup")
async def startup_event():
    """This function will run once when the application starts."""
    global DatabasePool
    
    print("Info :    Entering the world of NeonDB... ")
    DatabasePool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    print("INFO :    Welcome to the World of NeonDB. Connection successful.")
    await upsert_admin() # Ensure admin exists after pool is created
    
    # Start the background task for auto-updating quiz statuses
    asyncio.create_task(background_quiz_updater())
    print("INFO :    Background quiz status updater started (runs every 5 minutes)")

@app.on_event("shutdown")
async def shutdown_event():
    """This function will run once when the application shuts down."""
    if DatabasePool:
            print("INFO:   Disconnecting the World...  ")
            await DatabasePool.close()


async def upsert_admin():
    """On startup, create or update the hardcoded admin user in both User and Admin tables."""
    # This is our proof that the function is running.
    print("\n\n--- 🚀 EXECUTING UPSERT ADMIN FUNCTION! 🚀 ---\n")

    hashed_password = get_password_hash(ADMIN_PASSWORD)
    user_sql = """
        INSERT INTO "User" (user_id, name, email, password, role)
        VALUES ($1, $2, $3, $4, 'admin')
        ON CONFLICT (user_id) DO UPDATE SET
            name = EXCLUDED.name, 
            email = EXCLUDED.email,
            password = EXCLUDED.password, 
            role = EXCLUDED.role;
    """
    admin_sql = 'INSERT INTO "Admin" (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING'

    # We must use the global DatabasePool here now
    async with DatabasePool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(user_sql, ADMIN_ID, ADMIN_NAME, ADMIN_EMAIL, hashed_password)
            await conn.execute(admin_sql, ADMIN_ID)
            
    print(f"--- ✅ UPSERT ADMIN COMPLETE! User '{ADMIN_NAME}' (ID: {ADMIN_ID}) should be in the DB. ---\n")

# ======= CORS Middleware ======= 

origin = [
    "http://localhost:3000",
    "http://localhost",
    "http://127.0.0.1",
    "http://127.0.0.1:5500", # port for live server extensions
    # Add the URL of your deployed frontend later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origin,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======= Utility Functions ======= 

def verify_password(main_password, hashed_password):
    return pwd_context.verify(main_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)


# ======= API Auth ======= 

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles= allowed_roles
    
    async def __call__ (self, x_user_id: int = Header(..., alias= "X-User_ID")):
        if not DatabasePool:
            raise HTTPException(status_code=503, detail="Database connection not available")
        
        async with DatabasePool.acquire() as conn:
            user = await conn.fetchrow('SELECT role FROM "User" WHERE user_id = $1', x_user_id)
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail= f"User with ID {x_user_id} not found.")
        
        if user['role'] not in self.allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"This action requires one of the following roles: {', '.join(self.allowed_roles)}.")
        
        return x_user_id

# ======= API ======= 

@app.get("/")
async def root():
    return {"message": "Welcome to ClassMaster API !!!"}

@app.get('/db-test')
async def test_db_connection():
    if not DatabasePool:
        raise HTTPException(status_code=500, detail="Database connection pool not available.")
    try:
        async with DatabasePool.acquire() as connection:
            db_time = await connection.fetchval('SELECT NOW()')
        return { "message": "Database connection successful! ✅", "database_time": db_time }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}") 

# ======= Register API ======= 

@app.post('/register', response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate):
    hashed_password= get_password_hash(user.password)
    
    # SQL queries for user and role-specific table insertion
    user_sql_query= """
    INSERT INTO "User" (user_id, name, email, password, role)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING user_id, name, email, role;
    """
    
    # Role-specific table insertion queries
    role_sql_queries = {
        'student': 'INSERT INTO "Student" (user_id) VALUES ($1)',
        'faculty': 'INSERT INTO "Faculty" (user_id) VALUES ($1)',
        'admin': 'INSERT INTO "Admin" (user_id) VALUES ($1)'
    }
    
    async with DatabasePool.acquire() as connection:
        # Check if user_id already exists
        existing_user_id = await connection.fetchrow('SELECT user_id FROM "User" WHERE user_id = $1', user.user_id)
        if existing_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID already exists. Please use a different ID."
            )
        
        # Check if email already exists
        existing_email = await connection.fetchrow('SELECT user_id FROM "User" WHERE email = $1', user.email)
        if existing_email:
            raise HTTPException(
                status_code= status.HTTP_400_BAD_REQUEST,
                detail = "Email already registered. Try to login."
            )
        
        # Validate role
        if user.role not in role_sql_queries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {', '.join(role_sql_queries.keys())}"
            )
        
        # New user with transaction for data consistency
        try:
            # Start transaction
            async with connection.transaction():
                # Insert into User table
                new_user_record = await connection.fetchrow(
                    user_sql_query,
                    user.user_id,
        
                    user.name,
                    user.email,
                    hashed_password,
                    user.role
                )
                
                if new_user_record is None:
                    raise HTTPException(status_code=500, detail= "failed to create user.")
                
                # Insert into role-specific table
                await connection.execute(
                    role_sql_queries[user.role],
                    new_user_record['user_id']
                )
                
                return User(
                    user_id=new_user_record['user_id'],
                    name=new_user_record['name'],
                    email=new_user_record['email'],
                    role=new_user_record['role']
                )
        
        #checking if the email is used or not
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(
                status_code= status.HTTP_400_BAD_REQUEST,
                detail= "Email already registered. Try to login."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {e}")\

# ======= Login API ======= 

@app.post('/login', response_model=User, status_code=status.HTTP_200_OK)
async def login_user(user: UserLogin):
    async with DatabasePool.acquire() as connection:
        user_record = await connection.fetchrow('SELECT user_id, name, email, role, password FROM "User" WHERE user_id = $1', user.user_id)
        if user_record is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not verify_password(user.password, user_record['password']):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        return User(
            user_id=user_record['user_id'],
            name=user_record['name'],
            email=user_record['email'],
            role=user_record['role'])

# ======= Admin Course ADD API ======= 

@app.post("/create-course", response_model= Course, status_code=status.HTTP_201_CREATED)
async def create_course(course: CourseCreate, admin_id: int = Depends(RoleChecker(["admin"]))):
    sql = 'INSERT INTO "Course" (course_code, course_name) VALUES ($1, $2) RETURNING *;'
    async with DatabasePool.acquire() as conn:
        try:
            record = await conn.fetchrow (sql, course.course_code, course.course_name)
            return Course.model_validate(dict(record))
        except asyncpg.exceptions.UniqueViolationError:
                raise HTTPException(status_code=400, detail= f"Course '{course.course_code}' already exists.")

# ======= Admin Section ADD API =======

@app.post("/create-section", response_model = Section, status_code= status.HTTP_201_CREATED)
async def create_section(section: SectionCreate, admin_id: int = Depends(RoleChecker(["admin"]))):
    sql = """
        INSERT INTO "Section" (course_code, sec_number, start_time, end_time, day_of_week, location)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *;
    """
    async with DatabasePool.acquire() as conn:
        # Check if course exists using course_code from request body
        course_exists= await conn.fetchval('SELECT 1 FROM "Course" WHERE course_code = $1', section.course_code)
        if not course_exists:
            raise HTTPException(status_code= 404, detail= f"Course '{section.course_code}' not found.")
        try:
            record = await conn.fetchrow(sql, section.course_code, section.sec_number, section.start_time, section.end_time, section.day_of_week, section.location)
            return Section.model_validate(dict(record))
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(status_code= 400, detail=f"Section {section.sec_number} for course '{section.course_code}' already exists.")

# ======= Global Course and Section showing API =======

@app.get("/all-courses", response_model=List[Course])
async def get_all_courses():
    async with DatabasePool.acquire() as conn:
        records= await conn.fetch('select * from "Course";')
        return[Course.model_validate(dict(record)) for record in records]

@app.get('/section-by-course', response_model=List[Section])
async def get_course_sections(course_code: str):
    async with DatabasePool.acquire() as conn:
        records= await conn.fetch('select * from "Section" where course_code = $1;', course_code)
        if not records:
            raise HTTPException(status_code=404, detail=f"No section found for for course '{course_code}'.")
        return [Section.model_validate(dict(record)) for record in records]

@app.get('/all-sections', response_model=List[Section])
async def get_all_sections():
    """Get all sections from all courses"""
    async with DatabasePool.acquire() as conn:
        records = await conn.fetch('SELECT * FROM "Section" ORDER BY course_code, sec_number;')
        if not records:
            raise HTTPException(status_code=404, detail="No sections found in the database.")
        return [Section.model_validate(dict(record)) for record in records]

# ======= Faculty Course+Section ADD API =======

@app.post("/faculty/assign-section", response_model=FacultySection, status_code=status.HTTP_201_CREATED)
async def assign_faculty_to_section(assignment: FacultySectionAssign, faculty_id: int= Depends(RoleChecker(["faculty"]))):
    sql = """
        INSERT INTO "Faculty_Section" (faculty_id, course_code, sec_number)
        VALUES ($1, $2, $3)
        RETURNING *;
    """
    async with DatabasePool.acquire() as conn:
        try:
            record = await conn.fetchrow(sql, faculty_id, assignment.course_code, assignment.sec_number)
            return FacultySection.model_validate(dict(record))
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(status_code=400, detail="Faculty member is already assigned to this section.")
        except asyncpg.exceptions.ForeignKeyViolationError:
            raise HTTPException(status_code=404, detail="The specified course code or section number does not exist.")

@app.get("/faculty/all-sections", response_model=List[FacultySection])
async def get_all_faculty_sections():
    """Get all faculty-section assignments"""
    async with DatabasePool.acquire() as conn:
        records = await conn.fetch('SELECT * FROM "Faculty_Section" ORDER BY faculty_id, course_code, sec_number;')
        if not records:
            raise HTTPException(status_code=404, detail="No faculty section assignments found.")
        return [FacultySection.model_validate(dict(record)) for record in records]

@app.get("/faculty/{faculty_id}/sections", response_model=List[FacultySection])
async def get_faculty_sections(faculty_id: int):
    """Get sections assigned to a specific faculty member"""
    async with DatabasePool.acquire() as conn:
        # First check if faculty exists
        faculty_exists = await conn.fetchval('SELECT 1 FROM "Faculty" WHERE user_id = $1', faculty_id)
        if not faculty_exists:
            raise HTTPException(status_code=404, detail=f"Faculty with ID {faculty_id} not found.")
        
        # Get faculty sections
        records = await conn.fetch(
            'SELECT * FROM "Faculty_Section" WHERE faculty_id = $1 ORDER BY course_code, sec_number;', 
            faculty_id
        )
        if not records:
            raise HTTPException(status_code=404, detail=f"No sections assigned to faculty ID {faculty_id}.")
        return [FacultySection.model_validate(dict(record)) for record in records]

#======= available sections for students ========

@app.get("/section/available",response_model=List[Section])
async def get_available_sections():
    sql="""select s.* from "Section" s join "Faculty_Section" fs 
        on s.course_code = fs.course_code and s.sec_number = fs.sec_number 
        group by s.course_code, s.sec_number; """
    async with DatabasePool.acquire() as conn:
        records= await conn.fetch(sql)
        return [Section.model_validate(dict(record)) for record in records]

#======= Section assign to Students ======

@app.post("/students/assign-section", response_model=StudentSection, status_code= status.HTTP_201_CREATED)
async def assign_student_to_section(assignment:StudentSectionAssign, student_id: int= Depends(RoleChecker(["student"]))):
    sql=""" 
        insert into "Student_Section" (student_id, course_code, sec_number) 
        values ($1,$2,$3) returning *;
        """
    
    async with DatabasePool.acquire() as conn:
        # First check if the section exists
        section_exists = await conn.fetchval(
            'SELECT 1 FROM "Section" WHERE course_code = $1 AND sec_number = $2', 
            assignment.course_code, assignment.sec_number
        )
        if not section_exists:
            raise HTTPException(status_code=404, detail="The specified course or section does not exist.")
        
        # Check if there's a faculty assigned to this section
        faculty_assigned = await conn.fetchval(
            'SELECT 1 FROM "Faculty_Section" WHERE course_code = $1 AND sec_number = $2', 
            assignment.course_code, assignment.sec_number
        )
        if not faculty_assigned:
            raise HTTPException(
                status_code=400, 
                detail="Cannot enroll in this section. No faculty has been assigned to teach this section yet."
            )
        
        # Check if student is already enrolled in this course
        already_enrolled = await conn.fetchval(
            'SELECT 1 FROM "Student_Section" WHERE student_id = $1 AND course_code = $2', 
            student_id, assignment.course_code
        )
        if already_enrolled:
            raise HTTPException(
                status_code=400, 
                detail=f"Student is already enrolled in course '{assignment.course_code}'. Cannot enroll in multiple sections of the same course."
            )
        
        try:
            # Use transaction to ensure both operations succeed
            async with conn.transaction():
                # 1. Insert student into section
                record = await conn.fetchrow(sql, student_id, assignment.course_code, assignment.sec_number)
                
                # 2. Get student's preferred anonymous name
                student_info = await conn.fetchrow(
                    'SELECT preferred_anonymous_name FROM "Student" WHERE user_id = $1',
                    student_id
                )
                anonymous_name = student_info['preferred_anonymous_name'] if student_info else None
                
                # 3. Create leaderboard entry for this course
                leaderboard_sql = """
                    INSERT INTO "Leaderboard" (student_id, course_code, total_points, is_anonymous, anonymous_name)
                    VALUES ($1, $2, 100, FALSE, $3)
                    ON CONFLICT (course_code, student_id) DO NOTHING
                """
                await conn.execute(leaderboard_sql, student_id, assignment.course_code, anonymous_name)
                
                return StudentSection.model_validate(dict(record))
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(status_code=400, detail="Student is already enrolled in this section.")
        except asyncpg.exceptions.ForeignKeyViolationError:
            raise HTTPException(status_code=404, detail="The specified course, section does not exist.")

@app.get("/students/{student_id}/sections", response_model=List[StudentSection])
async def get_student_sections(student_id: int):
    """Get sections enrolled by a specific student"""
    async with DatabasePool.acquire() as conn:
        # First check if student exists
        student_exists = await conn.fetchval('SELECT 1 FROM "Student" WHERE user_id = $1', student_id)
        if not student_exists:
            raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found.")
        
        # Get student's enrolled sections
        records = await conn.fetch(
            'SELECT * FROM "Student_Section" WHERE student_id = $1 ORDER BY course_code, sec_number;', 
            student_id
        )
        if not records:
            raise HTTPException(status_code=404, detail=f"No sections found for student ID {student_id}.")
        return [StudentSection.model_validate(dict(record)) for record in records]

#======= Announcement from Faculty-end-creation =========

@app.post("/create-announcement", response_model= Announcement, status_code= status.HTTP_201_CREATED)
async def create_announcement_for_section(
    announcement: AnnouncementCreate,
    faculty_id: int = Depends(RoleChecker(["faculty"]))
):
    async with DatabasePool.acquire() as conn:
        # Check if faculty is assigned to this section
        is_assigned = await conn.fetchval(
            'SELECT 1 FROM "Faculty_Section" WHERE faculty_id = $1 AND course_code = $2 AND sec_number = $3',
            faculty_id, announcement.course_code, announcement.sec_number
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Faculty not assigned to this section.")
        
        # Validate deadline for quiz/assignment types
        if announcement.type in ['quiz', 'assignment'] and not announcement.deadline:
            raise HTTPException(
                status_code=400, 
                detail=f"Deadline is required for {announcement.type} announcements."
            )
        
        try:
            # Start transaction for data consistency
            async with conn.transaction():
                # 1. Create the announcement
                announcement_sql = """
                    INSERT INTO "Announcement" (title, content, type, section_course_code, section_sec_number, faculty_id, deadline)
                    VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *;
                """
                announcement_record = await conn.fetchrow(
                    announcement_sql, 
                    announcement.title, 
                    announcement.content, 
                    announcement.type, 
                    announcement.course_code, 
                    announcement.sec_number, 
                    faculty_id,
                    announcement.deadline
                )
                
                # 2. If it's a quiz or assignment, create todos for all students in that section
                if announcement.type in ['quiz', 'assignment']:
                    # Get all students enrolled in this section
                    students_sql = """
                        SELECT student_id FROM "Student_Section" 
                        WHERE course_code = $1 AND sec_number = $2
                    """
                    students = await conn.fetch(students_sql, announcement.course_code, announcement.sec_number)
                    
                    # Create todos for each student
                    for student in students:
                        todo_sql = """
                            INSERT INTO "Todo" (user_id, title, status, due_date, related_announcement)
                            VALUES ($1, $2, $3, $4, $5)
                        """
                        await conn.execute(
                            todo_sql,
                            student['student_id'],
                            f"{announcement.type.title()}: {announcement.title}",
                            'pending',
                            announcement.deadline.date() if announcement.deadline else None,
                            announcement_record['announcement_id']
                        )
                
                return Announcement.model_validate(dict(announcement_record))
                
        except Exception as e:
            raise HTTPException(status_code=500, detail= f"Failed to create announcement: {e}")

@app.get("/announcements/{course_code}/{sec_number}", response_model= List[Announcement])
async def get_announcements_for_section(
    course_code: str,
    sec_number: int
):
    async with DatabasePool.acquire() as conn:
        # Get announcements for this section (no authorization required)
        sql = 'SELECT * FROM "Announcement" WHERE section_course_code = $1 AND section_sec_number = $2 ORDER BY created_at DESC;'
        records = await conn.fetch(sql, course_code, sec_number)
        return [Announcement.model_validate(dict(record)) for record in records]


#======= Faculty Routes for Grades =========

@app.post('/sections/{course_code}/{sec_number}/grades', response_model=Grade, status_code=status.HTTP_201_CREATED)
async def upsert_single_grade(course_code: str, sec_number: int, grade: GradeCreate, faculty_id: int= Depends(RoleChecker(["faculty"]))):
    async with DatabasePool.acquire() as conn:
        is_assigned= await conn.fetchval('SELECT 1 FROM "Faculty_Section" WHERE faculty_id = $1 AND course_code = $2 AND sec_number = $3', faculty_id, course_code, sec_number)
        if not is_assigned: raise HTTPException(status_code=403, detail= "Faculty not assigned to this section.")
        is_enrolled= await conn.fetchval('SELECT 1 FROM "Student_Section" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3', grade.student_id, course_code, sec_number)
        if not is_enrolled: raise HTTPException(status_code=404, detail=f"Student with ID {grade.student_id} is not enrolled in this section.")
        sql = """
            INSERT INTO "Grade" (student_id, course_code, sec_number, grade_type, marks) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (student_id, course_code, sec_number, grade_type) DO UPDATE SET marks = EXCLUDED.marks
            RETURNING *;
        """
        record = await conn.fetchrow(sql, grade.student_id, course_code, sec_number, grade.grade_type, grade.marks)
        return Grade.model_validate(dict(record))

@app.post("/section/{course_code}/{sec_number}/grades/upload", status_code=status.HTTP_200_OK)
async def upload_grades_spreadsheet(course_code: str, sec_number: int, faculty_id: int = Depends(RoleChecker(["faculty"])),file: UploadFile= File(...)):
    async with DatabasePool.acquire() as conn:
        is_assigned = await conn.fetchval('SELECT 1 FROM "Faculty_Section" WHERE faculty_id = $1 AND course_code = $2 AND sec_number = $3', faculty_id, course_code, sec_number)
        if not is_assigned: raise HTTPException(status_code= 403, detail="Faculty not assigned to this section.")
        contents = await file.read()
        file_text = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(file_text))
        grades_to_upsert = [row for row in csv_reader]
        sql="""
            INSERT INTO "Grade" (student_id, course_code, sec_number, grade_type, marks) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (student_id, course_code, sec_number, grade_type) DO UPDATE SET marks = EXCLUDED.marks;
        """
        try:
            async with conn.transaction():
                for grade in grades_to_upsert:
                    await conn.execute(sql, int(grade["student_id"]), course_code, sec_number, grade["grade_type"], float(grade["marks"]))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred during bulk insert: {e}")
        return {"detail": f"Successfully processed {len(grades_to_upsert)} grade entries."}

@app.put("/sections/{course_code}/{sec_number}/publish-grades", status_code=status.HTTP_200_OK)
async def publish_grades_for_section(course_code: str, sec_number: int, publish: bool, faculty_id: int = Depends(RoleChecker(["faculty"]))):
    async with DatabasePool.acquire() as conn:
        is_assigned= await conn.fetchval('SELECT 1 FROM "Faculty_Section" WHERE faculty_id = $1 AND course_code = $2 AND sec_number = $3', faculty_id, course_code, sec_number)
        if not is_assigned: raise HTTPException(status_code=403, detail="Faculty not assigned to this section.")
        await conn.execute('UPDATE "Section" SET grades_publicly_visible = $1 WHERE course_code = $2 AND sec_number = $3', publish, course_code, sec_number)
        return {"detail": f"Grades for {course_code} Section {sec_number} are now {'publicly visible' if publish else 'private'}."}

#======= student Routes for Grades =========

@app.get("/my-grades/{course_code}/{sec_number}", response_model= List[Grade])
async def get_my_grades_for_section(course_code: str, sec_number: int, student_id: int = Depends(RoleChecker(["student"]))):
    sql = 'SELECT * FROM "Grade" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3;'
    async with DatabasePool.acquire() as conn:
        records= await conn.fetch(sql, student_id, course_code, sec_number)
        return [Grade.model_validate(dict(record) for record in records)]

@app.get("/section/{course_code}/{sec_number}/gradesheet", response_model= List[PublicGradeEntry])
async def get_section_gradesheet(course_code: str, sec_number: int, student_id: int = Depends(RoleChecker(["student"]))):
    async with DatabasePool.acquire() as conn:
        is_enrolled = await conn.fetchval('SELECT 1 FROM "Student_Section" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3', student_id, course_code, sec_number)
        if not is_enrolled: raise HTTPException(status_code=403, detail="You must be enrolled in this section to view the gradesheet.")
        section_info= await conn.fetchrow('SELECT grades_publicly_visible FROM "Section" WHERE course_code = $1 AND sec_number = $2', course_code, sec_number)
        if not section_info or not section_info["grades_publicly_visible"]:
            raise HTTPException(status_code=403, detail= "The gradesheet for this section is not publicly visible")
        
        sql="""
            SELECT g.student_id, u.name as student_name, g.grade_type, g.marks
            FROM "Grade" g
            JOIN "User" u ON g.student_id = u.user_id
            WHERE g.course_code = $1 AND g.sec_number = $2
            ORDER BY u.name, g.grade_type;
        """
        records = await conn.fetch(sql, course_code, sec_number)
        return [PublicGradeEntry.model_validate(dict(record)) for record in records]

#======= student Grades Dashboard =========

@app.get("/my-dashboard/{course_code}/{sec_number}", response_model=StudentGradeSummary)
async def get_student_dash_grade(
    course_code: str,
    sec_number: int,
    student_id: int= Depends(RoleChecker(["student"]))
):
    async with DatabasePool.acquire() as conn:
        is_enrolled= await conn.fetchval('SELECT 1 FROM "Student_Section" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3',
            student_id, course_code, sec_number)
        if not is_enrolled:
            raise HTTPException(status_code=403, detail= "You are not enrolled in this section.")
        # Query 1: Get all individual grade entries
        grades_sql = 'SELECT grade_type, marks FROM "Grade" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3;'
        grade_records = await conn.fetch(grades_sql, student_id, course_code, sec_number)
        
        # Query 2: Calculate the sum of marks directly in the database
        total_sql = 'SELECT SUM(marks) as total FROM "Grade" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3;'
        total_record = await conn.fetchrow(total_sql, student_id, course_code, sec_number)
        
        # If there are no grades, total will be None. Default to 0.
        total_marks = total_record['total'] if total_record and total_record['total'] is not None else 0.0
        
        # Construct the response object
        grade_details = [GradeDetail.model_validate(dict(record)) for record in grade_records]
        
        return StudentGradeSummary(
            total_marks=total_marks,
            grades=grade_details
        )
        
@app.get("/faculty/{faculty_id}/announcements", response_model= List[Announcement])
async def get_all_faculty_announcements(faculty_id: int):
    """Get all announcements posted by a specific faculty member"""
    async with DatabasePool.acquire() as conn:
        # First check if faculty exists
        faculty_exists = await conn.fetchval('SELECT 1 FROM "Faculty" WHERE user_id = $1', faculty_id)
        if not faculty_exists:
            raise HTTPException(status_code=404, detail=f"Faculty with ID {faculty_id} not found.")
        
        # Get all announcements posted by this faculty
        sql = 'SELECT * FROM "Announcement" WHERE faculty_id = $1 ORDER BY created_at DESC;'
        records = await conn.fetch(sql, faculty_id) 
        return [Announcement.model_validate(dict(record)) for record in records]

@app.patch("/announcements/{announcement_id}", response_model= Announcement)
async def update_announcement(
    announcement_id: int,
    announcement_update: AnnouncementCreate,
    faculty_id: int = Depends(RoleChecker(["faculty"]))
):
    """Update an announcement (only by the faculty who created it)"""
    async with DatabasePool.acquire() as conn:
        # Check if announcement exists and belongs to this faculty
        existing_announcement = await conn.fetchrow(
            'SELECT * FROM "Announcement" WHERE announcement_id = $1 AND faculty_id = $2',
            announcement_id, faculty_id
        )
        if not existing_announcement:
            raise HTTPException(status_code=404, detail="Announcement not found or you don't have permission to edit it.")
        
        # Validate deadline for quiz/assignment types
        if announcement_update.type in ['quiz', 'assignment'] and not announcement_update.deadline:
            raise HTTPException(
                status_code=400, 
                detail=f"Deadline is required for {announcement_update.type} announcements."
            )
        
        try:
            # Start transaction for data consistency
            async with conn.transaction():
                # 1. Update the announcement
                update_sql = """
                    UPDATE "Announcement" 
                    SET title = $1, content = $2, type = $3, deadline = $4
                    WHERE announcement_id = $5 AND faculty_id = $6
                    RETURNING *;
                """
                updated_announcement = await conn.fetchrow(
                    update_sql,
                    announcement_update.title,
                    announcement_update.content,
                    announcement_update.type,
                    announcement_update.deadline,
                    announcement_id,
                    faculty_id
                )
                
                # 2. Handle todos if they exist
                existing_todos = await conn.fetch(
                    'SELECT * FROM "Todo" WHERE related_announcement = $1',
                    announcement_id
                )
                
                if existing_todos:
                    if announcement_update.type in ['quiz', 'assignment']:
                        # Update existing todos with new title and deadline
                        for todo in existing_todos:
                            await conn.execute(
                                'UPDATE "Todo" SET title = $1, due_date = $2 WHERE todo_id = $3',
                                f"{announcement_update.type.title()}: {announcement_update.title}",
                                announcement_update.deadline.date() if announcement_update.deadline else None,
                                todo['todo_id']
                            )
                    else:
                        # If type changed to 'general', remove todos
                        await conn.execute(
                            'DELETE FROM "Todo" WHERE related_announcement = $1',
                            announcement_id
                        )
                else:
                    # If no todos existed but now it's quiz/assignment, create them
                    if announcement_update.type in ['quiz', 'assignment']:
                        # Get all students enrolled in this section
                        students = await conn.fetch(
                            'SELECT student_id FROM "Student_Section" WHERE course_code = $1 AND sec_number = $2',
                            existing_announcement['section_course_code'],
                            existing_announcement['section_sec_number']
                        )
                        
                        # Create todos for each student
                        for student in students:
                            await conn.execute(
                                'INSERT INTO "Todo" (user_id, title, status, due_date, related_announcement) VALUES ($1, $2, $3, $4, $5)',
                                student['student_id'],
                                f"{announcement_update.type.title()}: {announcement_update.title}",
                                'pending',
                                announcement_update.deadline.date() if announcement_update.deadline else None,
                                announcement_id
                            )
                
                return Announcement.model_validate(dict(updated_announcement))
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update announcement: {e}")

@app.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    faculty_id: int = Depends(RoleChecker(["faculty"]))
):
    """Delete an announcement (only by the faculty who created it)"""
    async with DatabasePool.acquire() as conn:
        # Check if announcement exists and belongs to this faculty
        existing_announcement = await conn.fetchrow(
            'SELECT * FROM "Announcement" WHERE announcement_id = $1 AND faculty_id = $2',
            announcement_id, faculty_id
        )
        if not existing_announcement:
            raise HTTPException(status_code=404, detail="Announcement not found or you don't have permission to delete it.")
        
        try:
            async with conn.transaction():
                # 1. Delete related todos first (due to foreign key constraint)
                await conn.execute(
                    'DELETE FROM "Todo" WHERE related_announcement = $1',
                    announcement_id
                )
                
                # 2. Delete the announcement
                await conn.execute(
                    'DELETE FROM "Announcement" WHERE announcement_id = $1',
                    announcement_id
                )
                
                return {"message": "Announcement and related todos deleted successfully"}
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete announcement: {e}")

@app.get("/schedule/{user_id}")
async def get_user_schedule(
    user_id: int
):
    """Get schedule for a user (student or faculty) organized by day of week"""
    async with DatabasePool.acquire() as conn:
        # Check user role
        user_role_sql = 'SELECT role FROM "User" WHERE user_id = $1'
        user_role = await conn.fetchval(user_role_sql, user_id)
        
        if not user_role:
            raise HTTPException(status_code=404, detail="User not found.")
        
        # Validate that user is student or faculty
        if user_role not in ["student", "faculty"]:
            raise HTTPException(status_code=403, detail="Schedule access only available for students and faculty.")
        
        # Get sections based on user role
        if user_role == "student":
            sections_sql = """
                SELECT 
                    s.course_code,
                    s.sec_number,
                    s.start_time,
                    s.end_time,
                    s.day_of_week,
                    s.location,
                    c.course_name
                FROM "Section" s
                JOIN "Course" c ON s.course_code = c.course_code
                JOIN "Student_Section" ss ON s.course_code = ss.course_code AND s.sec_number = ss.sec_number
                WHERE ss.student_id = $1
                ORDER BY 
                    CASE s.day_of_week 
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END,
                    s.start_time
            """
        else:  # faculty
            sections_sql = """
                SELECT 
                    s.course_code,
                    s.sec_number,
                    s.start_time,
                    s.end_time,
                    s.day_of_week,
                    s.location,
                    c.course_name
                FROM "Section" s
                JOIN "Course" c ON s.course_code = c.course_code
                JOIN "Faculty_Section" fs ON s.course_code = fs.course_code AND s.sec_number = fs.sec_number
                WHERE fs.faculty_id = $1
                ORDER BY 
                    CASE s.day_of_week 
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END,
                    s.start_time
            """
        
        sections = await conn.fetch(sections_sql, user_id)
        
        # Organize sections by day of week
        schedule = {}
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for day in days_order:
            schedule[day] = []
        
        for section in sections:
            day = section['day_of_week'].title()
            schedule[day].append({
                "course_code": section['course_code'],
                "course_name": section['course_name'],
                "sec_number": section['sec_number'],
                "start_time": str(section['start_time']),
                "end_time": str(section['end_time']),
                "location": section['location']
            })
        
        return {
            "user_id": user_id,
            "role": user_role,
            "schedule": schedule
        }

@app.get("/students/{student_id}/announcements", response_model=List[Announcement])
async def get_all_student_announcements(student_id: int):
    """Get all announcements for all sections a student is enrolled in"""
    async with DatabasePool.acquire() as conn:
        # First check if student exists
        student_exists = await conn.fetchval('SELECT 1 FROM "Student" WHERE user_id = $1', student_id)
        if not student_exists:
            raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found.")
        
        # Get all announcements for sections where student is enrolled
        announcements_sql = """
            SELECT DISTINCT a.*
            FROM "Announcement" a
            JOIN "Student_Section" ss ON a.section_course_code = ss.course_code 
                AND a.section_sec_number = ss.sec_number
            WHERE ss.student_id = $1
            ORDER BY a.created_at DESC;
        """
        
        records = await conn.fetch(announcements_sql, student_id)
        
        if not records:
            return []
        
        return [Announcement.model_validate(dict(record)) for record in records]

@app.get("/students/{student_id}/tasks", response_model=List[StudentTask])
async def get_student_tasks(student_id: int):
    """Get all tasks (todos) for a specific student with related announcement details"""
    async with DatabasePool.acquire() as conn:
        # First check if student exists
        student_exists = await conn.fetchval('SELECT 1 FROM "Student" WHERE user_id = $1', student_id)
        if not student_exists:
            raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found.")
        
        # Get all todos for this student with related announcement details
        tasks_sql = """
            SELECT 
                t.todo_id,
                t.title,
                t.status,
                t.due_date,
                t.related_announcement,
                a.title as announcement_title,
                a.content as announcement_content,
                a.type as announcement_type,
                a.deadline as announcement_deadline,
                a.section_course_code as course_code,
                a.section_sec_number as section_number
            FROM "Todo" t
            LEFT JOIN "Announcement" a ON t.related_announcement = a.announcement_id
            WHERE t.user_id = $1
            ORDER BY t.due_date ASC NULLS LAST, t.todo_id DESC;
        """
        
        records = await conn.fetch(tasks_sql, student_id)
        
        if not records:
            return []
        
        # Convert records to StudentTask objects
        tasks = []
        for record in records:
            task_data = {
                "todo_id": record['todo_id'],
                "title": record['title'],
                "status": record['status'],
                "due_date": record['due_date'],
                "related_announcement_id": record['related_announcement'],
                "announcement_title": record['announcement_title'],
                "announcement_content": record['announcement_content'],
                "announcement_type": record['announcement_type'],
                "announcement_deadline": record['announcement_deadline'],
                "course_code": record['course_code'],
                "section_number": record['section_number']
            }
            tasks.append(StudentTask(**task_data))
        
        return tasks

@app.post("/students/{student_id}/tasks", response_model=StudentTask, status_code=status.HTTP_201_CREATED)
async def create_student_task(
    student_id: int,
    task: StudentTaskCreate,
    authenticated_student_id: int = Depends(RoleChecker(["student"]))
):
    """Create a new personal task for a student"""
    # Verify that the authenticated student is creating a task for themselves
    if authenticated_student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create tasks for yourself."
        )
    
    async with DatabasePool.acquire() as conn:
        # Verify student exists
        student_exists = await conn.fetchval('SELECT 1 FROM "Student" WHERE user_id = $1', student_id)
        if not student_exists:
            raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found.")
        
        # Create the task
        create_task_sql = """
            INSERT INTO "Todo" (user_id, title, status, due_date, related_announcement)
            VALUES ($1, $2, 'pending', $3, NULL)
            RETURNING todo_id, title, status, due_date, related_announcement;
        """
        
        try:
            record = await conn.fetchrow(
                create_task_sql,
                student_id,
                task.title,
                task.due_date
            )
            
            # Return the created task with all fields (announcement fields will be null)
            task_data = {
                "todo_id": record['todo_id'],
                "title": record['title'],
                "status": record['status'],
                "due_date": record['due_date'],
                "related_announcement_id": record['related_announcement'],
                "announcement_title": None,
                "announcement_content": None,
                "announcement_type": None,
                "announcement_deadline": None,
                "course_code": None,
                "section_number": None
            }
            
            return StudentTask(**task_data)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create task: {e}")

@app.patch("/students/{student_id}/tasks/{todo_id}", response_model=StudentTask)
async def update_student_task_status(
    student_id: int,
    todo_id: int,
    status_update: StudentTaskStatusUpdate,
    authenticated_student_id: int = Depends(RoleChecker(["student"]))
):
    """Update the status of a student's task with complex business logic"""
    # Verify that the authenticated student is updating their own task
    if authenticated_student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own tasks."
        )
    
    async with DatabasePool.acquire() as conn:
        # Get the current task with announcement details
        task_sql = """
            SELECT 
                t.todo_id,
                t.title,
                t.status,
                t.due_date,
                t.related_announcement,
                a.title as announcement_title,
                a.content as announcement_content,
                a.type as announcement_type,
                a.deadline as announcement_deadline,
                a.section_course_code as course_code,
                a.section_sec_number as section_number
            FROM "Todo" t
            LEFT JOIN "Announcement" a ON t.related_announcement = a.announcement_id
            WHERE t.user_id = $1 AND t.todo_id = $2
        """
        
        task_record = await conn.fetchrow(task_sql, student_id, todo_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="Task not found.")
        
        current_status = task_record['status']
        new_status = status_update.status
        announcement_type = task_record['announcement_type']
        due_date = task_record['due_date']
        announcement_deadline = task_record['announcement_deadline']
        
        # Validate new status
        if new_status not in ['pending', 'completed', 'delayed']:
            raise HTTPException(
                status_code=400, 
                detail="Invalid status. Must be 'pending', 'completed', or 'delayed'."
            )
        
        # Check if deadline has passed
        from datetime import datetime, date
        current_date = date.today()
        deadline_passed = False
        
        if due_date and due_date < current_date:
            deadline_passed = True
        elif announcement_deadline and announcement_deadline.date() < current_date:
            deadline_passed = True
        
        # Apply business logic based on task type
        if announcement_type == 'quiz':
            # Quiz tasks: Cannot be manually updated by students at all
            raise HTTPException(
                status_code=403,
                detail="Quiz tasks cannot be manually updated. They are automatically completed when the deadline passes."
            )
        
        elif announcement_type == 'assignment':
            # Assignment tasks: Can be completed only once, cannot be reverted
            if current_status == 'completed':
                raise HTTPException(
                    status_code=403,
                    detail="Assignment tasks cannot be changed once completed."
                )
            elif new_status == 'pending' and current_status == 'completed':
                raise HTTPException(
                    status_code=403,
                    detail="Assignment tasks cannot be reverted to pending once completed."
                )
            # For assignments, respect user's exact status choice (no auto-conversion)
        
        else:
            ...
            # Personal tasks (no announcement_type) or general announcements
            # Can toggle freely, respect user's exact status choice (no auto-conversion)
        
        # Update the task status
        update_sql = """
            UPDATE "Todo" 
            SET status = $1 
            WHERE user_id = $2 AND todo_id = $3
            RETURNING todo_id, title, status, due_date, related_announcement;
        """
        
        try:
            updated_record = await conn.fetchrow(update_sql, new_status, student_id, todo_id)
            
            # Return the updated task with all fields
            task_data = {
                "todo_id": updated_record['todo_id'],
                "title": updated_record['title'],
                "status": updated_record['status'],
                "due_date": updated_record['due_date'],
                "related_announcement_id": updated_record['related_announcement'],
                "announcement_title": task_record['announcement_title'],
                "announcement_content": task_record['announcement_content'],
                "announcement_type": task_record['announcement_type'],
                "announcement_deadline": task_record['announcement_deadline'],
                "course_code": task_record['course_code'],
                "section_number": task_record['section_number']
            }
            
            return StudentTask(**task_data)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update task status: {e}")

async def auto_update_quiz_statuses():
    """Automatically update quiz task statuses when deadlines pass"""
    if not DatabasePool:
        print("Database pool not available for auto-update")
        return
    
    try:
        async with DatabasePool.acquire() as conn:
            # Find all pending quiz tasks where deadline has passed
            expired_quiz_sql = """
                SELECT t.todo_id, t.user_id, a.title as quiz_title, a.deadline
                FROM "Todo" t
                JOIN "Announcement" a ON t.related_announcement = a.announcement_id
                WHERE a.type = 'quiz' 
                AND t.status = 'pending'
                AND a.deadline < NOW()
            """
            
            expired_quizzes = await conn.fetch(expired_quiz_sql)
            
            if expired_quizzes:
                # Update all expired quiz tasks to completed
                for quiz in expired_quizzes:
                    await conn.execute(
                        'UPDATE "Todo" SET status = $1 WHERE todo_id = $2 AND user_id = $3',
                        'completed', quiz['todo_id'], quiz['user_id']
                    )
                
                print(f"🔄 Auto-updated {len(expired_quizzes)} expired quiz tasks to completed status")
                for quiz in expired_quizzes:
                    print(f"   - Quiz: {quiz['quiz_title']} (Deadline: {quiz['deadline']})")
            else:
                print("✅ No expired quiz tasks found")
                
    except Exception as e:
        print(f"❌ Error in auto-update quiz statuses: {e}")
        

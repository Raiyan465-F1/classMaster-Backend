import os
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext #for password hashing
from schemas import User, UserCreate, UserLogin, Course, SectionCreate, Section, CourseCreate, FacultySection, FacultySectionAssign
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

# --- STARTUP AND SHUTDOWN LOGIC ---

@app.on_event("startup")
async def startup_event():
    """This function will run once when the application starts."""
    global DatabasePool
    print("Info :    Entering the world of NeonDB... ")
    DatabasePool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    print("INFO :    Welcome to the World of NeonDB. Connection successful.")
    await upsert_admin() # Ensure admin exists after pool is created

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

# ======= available sections for students ========
# @app.get("/section/available",response_model=List[Section])
# async def get_available_sections():
#     sql="""select s.* from "Section" s join "Faculty_Section" fs on s.course_code = fs.course_code and s.sec_number = fs.sec_number group by s.course_code, s.sec_number; """
#     async with DatabasePool.acquire() as conn:
#     		try:
#             records= await conn.fetch(sql)
#             return [Section.model_validate(dict(record)) for record in records]

# #======= Secton assign to Students ======
# @app.push("/students/assign-section", responds_model=StudentSection, status_code= status.HTTP_201_CREATED)
# async def assign_student_to_section(assignment:StudentSectionAssign, student_id: int= Depends(RoleChecker(["student"]))):
#     sql=""" insert into "Student_Section" (student_id, coure_code, sec_number) values ($1,$2,$3) returning *;"""
    
#     async with DatabasePool.acquire() as conn:
#     		try:
#             record= await conn.fetchrwo(sql, student_id, assignment.course_code, assignment.sec_number)
#             return StudentSection.model_validate(dict(record))
#         except asyncpg.expections.UniqueViolationError:
#         		raise HTTPException(status_code=400, detail="Student is already enrolled in this section.")
#         except aysncpg.expection.ForeignKeyViolationError:
#         		raise HTTPExpection(status_code=404, detail="The specified course, section does not exist.")
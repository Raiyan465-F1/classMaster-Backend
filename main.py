import os
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext #for password hashing
from schemas import User, UserCreate, UserLogin

# ======= SetUp ======= 

load_dotenv()

# ======= Password Hashing ======= 

pwd_context = CryptContext(schemes= ['bcrypt'], deprecated= 'auto')

# ======= Database Connection Pool ======= 

DatabasePool= None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global DatabasePool
    print("Info :    Entering the world of NeonDB... ")
    try:
        DatabasePool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
        print("INFO :    Welcome to the World of NeonDB. Connection successful.")
        yield
    finally:
        if DatabasePool:
            print("INFO:   Disconnecting the World...  ")
            await DatabasePool.close()

app = FastAPI(lifespan= lifespan)

# ======= CORS Middleware ======= 

origin = [
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


@app.post('/login', response_model=User, status_code=status.HTTP_200_OK)
async def login_user(user: UserLogin):
    async with DatabasePool.acquire() as connection:
        user_record = await connection.fetchrow('SELECT user_id, name, email, role, password FROM "User" WHERE user_id = $1', user.user_id)
        if user_record is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not verify_password(user.password, user_record['password']):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return User(
            user_id=user_record['user_id'],
            name=user_record['name'],
            email=user_record['email'],
            role=user_record['role'])
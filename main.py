import os
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext #for password hashing
from schemas import User, UserCreate

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
    
    sql_query= """
    INSERT INTO "User" (name, email, password, role)
    VALUES ($1, $2, $3, $4)
    RETURNING user_id, name, email, role;
    """
    
    async with DatabasePool.acquire() as connection:
        # checking if exist
        existing_user = await connection.fetchrow('select user_id from "User" where email = $1', user.email)
        if existing_user:
            raise HTTPException(
                status_code= status.HTTP_400_BAD_REQUEST,
                detail = "Email already registered. Try to login."
            )
        
        # New user
        try:
            new_user_record = await connection.fetchrow(
                sql_query,
                user.name,
                user.email,
                hashed_password,
                user.role
            )
            if new_user_record is None:
                raise HTTPException(status_code=500, detail= "failed to create user.")
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
            raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
        
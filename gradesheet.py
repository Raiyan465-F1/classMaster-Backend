import asyncpg
import csv
import io
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File
from typing import List
from schemas import Grade, GradeCreate, StudentGradeSummary, GradeDetail
from main import DatabasePool, RoleChecker

router = APIRouter()

#======= Faculty Routes for Grades manual =========

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

#======= Faculty Routes for Grades spreadsheet =========

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

# #======= Faculty Routes for Grades publish =========

# @app.put("/sections/{course_code}/{sec_number}/publish-grades", status_code=status.HTTP_200_OK)
# async def publish_grades_for_section(course_code: str, sec_number: int, publish: bool, faculty_id: int = Depends(RoleChecker(["faculty"]))):
#     async with DatabasePool.acquire() as conn:
#         is_assigned= await conn.fetchval('SELECT 1 FROM "Faculty_Section" WHERE faculty_id = $1 AND course_code = $2 AND sec_number = $3', faculty_id, course_code, sec_number)
#         if not is_assigned: raise HTTPException(status_code=403, detail="Faculty not assigned to this section.")
#         await conn.execute('UPDATE "Section" SET grades_publicly_visible = $1 WHERE course_code = $2 AND sec_number = $3', publish, course_code, sec_number)
#         return {"detail": f"Grades for {course_code} Section {sec_number} are now {'publicly visible' if publish else 'private'}."}

#======= student Routes for Grades =========

@app.get("/my-grades/{course_code}/{sec_number}", response_model= List[Grade])
async def get_my_grades_for_section(course_code: str, sec_number: int, student_id: int = Depends(RoleChecker(["student"]))):
    sql = 'SELECT * FROM "Grade" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3;'
    async with DatabasePool.acquire() as conn:
        records= await conn.fetch(sql, student_id, course_code, sec_number)
        return [Grade.model_validate(dict(record)) for record in records]

# @app.get("/section/{course_code}/{sec_number}/gradesheet", response_model= List[PublicGradeEntry])

# async def get_section_gradesheet(course_code: str, sec_number: int, student_id: int = Depends(RoleChecker(["student"]))):
#     async with DatabasePool.acquire() as conn:
#         is_enrolled = await conn.fetchval('SELECT 1 FROM "Student_Section" WHERE student_id = $1 AND course_code = $2 AND sec_number = $3', student_id, course_code, sec_number)
#         if not is_enrolled: raise HTTPException(status_code=403, detail="You must be enrolled in this section to view the gradesheet.")
#         section_info= await conn.fetchrow('SELECT grades_publicly_visible FROM "Section" WHERE course_code = $1 AND sec_number = $2', course_code, sec_number)
#         if not section_info or not section_info["grades_publicly_visible"]:
#             raise HTTPException(status_code=403, detail= "The gradesheet for this section is not publicly visible")
        
#         sql="""
#             SELECT g.student_id, u.name as student_name, g.grade_type, g.marks
#             FROM "Grade" g
#             JOIN "User" u ON g.student_id = u.user_id
#             WHERE g.course_code = $1 AND g.sec_number = $2
#             ORDER BY u.name, g.grade_type;
#         """
#         records = await conn.fetch(sql, course_code, sec_number)
#         return [PublicGradeEntry.model_validate(dict(record)) for record in records]

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
            course_code= course_code,
            sec_number= sec_number,
            total_marks=total_marks,
            grades=grade_details
        )
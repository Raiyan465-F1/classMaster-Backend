# ClassMaster Backend - Grade Management API Documentation

This document describes the Grade Management API endpoints that allow faculty members to manage student grades and students to view their grades.

## Base URL

```
http://localhost:8000
```

## Authentication

All grade endpoints require authentication via the `X-User_ID` header containing the user's ID.

---

## Grade Management Endpoints

### 1. Create/Update Student Grade (Faculty Only)

**POST** `/sections/{course_code}/{sec_number}/grades`

Allows faculty members to create new grades or update existing grades for students in their assigned sections.

#### Parameters

- `course_code` (path, string): The course code (max 8 characters)
- `sec_number` (path, integer): The section number

#### Headers

- `X-User_ID` (integer): Faculty member's user ID for authentication

#### Request Body

```json
{
  "student_id": 2024001,
  "grade_type": "Midterm Exam",
  "marks": 85.5
}
```

#### Request Body Schema

- `student_id` (integer, required): The student's user ID
- `grade_type` (string, required): Type of grade (max 100 characters) - e.g., "Quiz 1", "Midterm Exam", "Final Project", "Assignment 1"
- `marks` (float, required): The marks/score for this grade

#### Response

**201 Created** - Returns the created/updated grade

```json
{
  "student_id": 2024001,
  "course_code": "CS101",
  "sec_number": 1,
  "grade_type": "Midterm Exam",
  "marks": 85.5
}
```

#### Business Logic

- **Upsert Operation**: If a grade with the same `student_id`, `course_code`, `sec_number`, and `grade_type` already exists, it will be updated with the new marks
- **Faculty Authorization**: Only faculty members assigned to the specific section can create/update grades
- **Student Enrollment Check**: The system verifies that the student is enrolled in the specified section

#### Error Responses

- **403 Forbidden**: Faculty not assigned to this section
- **404 Not Found**: Student not enrolled in this section
- **500 Internal Server Error**: Database error

---

### 2. Get All Grades for Section (Faculty Only)

**GET** `/sections/{course_code}/{sec_number}/grades`

Allows faculty members to view all grades for all students in their assigned section.

#### Parameters

- `course_code` (path, string): The course code (max 8 characters)
- `sec_number` (path, integer): The section number

#### Headers

- `X-User_ID` (integer): Faculty member's user ID for authentication

#### Response

**200 OK** - Returns a list of all grades for all students in the section

```json
[
  {
    "student_id": 2024001,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Quiz 1",
    "marks": 92.0
  },
  {
    "student_id": 2024001,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Midterm Exam",
    "marks": 85.5
  },
  {
    "student_id": 2024002,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Quiz 1",
    "marks": 88.0
  },
  {
    "student_id": 2024002,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Midterm Exam",
    "marks": 91.5
  }
]
```

#### Features

- **Complete Section Overview**: Returns all grades for all students in the section
- **Ordered Results**: Results are ordered by student_id and grade_type for easy reading
- **Faculty Authorization**: Only faculty assigned to the section can access this data
- **Comprehensive View**: Useful for grade analysis, class statistics, and grade management

#### Error Responses

- **403 Forbidden**: Faculty not assigned to this section
- **500 Internal Server Error**: Database error

---

### 3. Get My Grades for Section (Student Only)

**GET** `/my-grades/{course_code}/{sec_number}`

Allows students to view all their grades for a specific course section.

#### Parameters

- `course_code` (path, string): The course code
- `sec_number` (path, integer): The section number

#### Headers

- `X-User_ID` (integer): Student's user ID for authentication

#### Response

**200 OK** - Returns a list of grades for the student in the specified section

```json
[
  {
    "student_id": 2024001,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Quiz 1",
    "marks": 92.0
  },
  {
    "student_id": 2024001,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Midterm Exam",
    "marks": 85.5
  },
  {
    "student_id": 2024001,
    "course_code": "CS101",
    "sec_number": 1,
    "grade_type": "Assignment 1",
    "marks": 78.0
  }
]
```

#### Error Responses

- **403 Forbidden**: Student not enrolled in this section
- **500 Internal Server Error**: Database error

---

### 4. Get Student Grade Summary (Student Only)

**GET** `/my-dashboard/{course_code}/{sec_number}`

Provides a comprehensive grade summary for a student in a specific course section, including total marks and individual grade breakdown.

#### Parameters

- `course_code` (path, string): The course code
- `sec_number` (path, integer): The section number

#### Headers

- `X-User_ID` (integer): Student's user ID for authentication

#### Response

**200 OK** - Returns grade summary with total marks and individual grades

```json
{
  "total_marks": 255.5,
  "grades": [
    {
      "grade_type": "Quiz 1",
      "marks": 92.0
    },
    {
      "grade_type": "Midterm Exam",
      "marks": 85.5
    },
    {
      "grade_type": "Assignment 1",
      "marks": 78.0
    }
  ],
  "course_code": "CS101",
  "sec_number": 1
}
```

#### Features

- **Total Marks Calculation**: Automatically calculates the sum of all marks for the student in the section
- **Individual Grade Breakdown**: Lists all individual grades with their types and marks
- **Course Information**: Includes course code and section number for context
- **Zero Handling**: If no grades exist, total_marks defaults to 0.0

#### Error Responses

- **403 Forbidden**: Student not enrolled in this section
- **500 Internal Server Error**: Database error

---

## Data Models

### Grade

```json
{
  "student_id": "integer",
  "course_code": "string (max 8 characters)",
  "sec_number": "integer",
  "grade_type": "string (max 100 characters)",
  "marks": "float"
}
```

### GradeCreate

```json
{
  "student_id": "integer",
  "grade_type": "string (max 100 characters)",
  "marks": "float"
}
```

### GradeDetail

```json
{
  "grade_type": "string",
  "marks": "float"
}
```

### StudentGradeSummary

```json
{
  "total_marks": "float",
  "grades": "array of GradeDetail objects",
  "course_code": "string (max 8 characters)",
  "sec_number": "integer"
}
```

---

## Database Schema

The Grade table structure:

```sql
CREATE TABLE "Grade" (
  "student_id" INT,
  "course_code" VARCHAR(50),
  "sec_number" INT,
  "grade_type" VARCHAR(100),
  "marks" FLOAT,
  PRIMARY KEY ("student_id", "course_code", "sec_number", "grade_type"),
  FOREIGN KEY ("student_id") REFERENCES "Student"("user_id"),
  FOREIGN KEY ("course_code", "sec_number") REFERENCES "Section"("course_code", "sec_number")
);
```

### Key Features

- **Composite Primary Key**: Ensures uniqueness per student, course, section, and grade type
- **Foreign Key Constraints**: Maintains referential integrity with Student and Section tables
- **Flexible Grade Types**: Supports any grade type (quiz, exam, assignment, project, etc.)
- **Float Marks**: Supports decimal marks for precise scoring

---

## Usage Examples

### Faculty: Grade Management

1. **Create a new quiz grade**:

   ```bash
   POST /sections/CS101/1/grades
   X-User-ID: 2
   {
     "student_id": 2024001,
     "grade_type": "Quiz 1",
     "marks": 92.0
   }
   ```

2. **Update an existing grade**:

   ```bash
   POST /sections/CS101/1/grades
   X-User-ID: 2
   {
     "student_id": 2024001,
     "grade_type": "Quiz 1",
     "marks": 95.0
   }
   ```

3. **Add multiple grade types for a student**:

   ```bash
   # Midterm Exam
   POST /sections/CS101/1/grades
   X-User-ID: 2
   {
     "student_id": 2024001,
     "grade_type": "Midterm Exam",
     "marks": 85.5
   }

   # Assignment
   POST /sections/CS101/1/grades
   X-User-ID: 2
   {
     "student_id": 2024001,
     "grade_type": "Assignment 1",
     "marks": 78.0
   }
   ```

4. **View all grades for a section**:

   ```bash
   GET /sections/CS101/1/grades
   X-User-ID: 2
   ```

### Student: Viewing Grades

1. **View all grades for a section**:

   ```bash
   GET /my-grades/CS101/1
   X-User-ID: 2024001
   ```

2. **Get grade summary with total**:

   ```bash
   GET /my-dashboard/CS101/1
   X-User-ID: 2024001
   ```

---

## Grade Type Recommendations

Common grade types that work well with the system:

- **Quizzes**: "Quiz 1", "Quiz 2", "Weekly Quiz"
- **Exams**: "Midterm Exam", "Final Exam", "Midterm 1"
- **Assignments**: "Assignment 1", "Lab Assignment", "Homework 1"
- **Projects**: "Final Project", "Group Project", "Capstone Project"
- **Participation**: "Class Participation", "Discussion Board"
- **Labs**: "Lab 1", "Lab Report 1", "Practical Exam"

---

## Error Handling

All endpoints return appropriate HTTP status codes and error messages:

- **400 Bad Request**: Invalid input data
- **403 Forbidden**: Insufficient permissions (faculty not assigned to section, student not enrolled)
- **404 Not Found**: Resource not found (student not enrolled in section)
- **500 Internal Server Error**: Server-side error

Error responses include a `detail` field with a human-readable error message.

---

## Security Considerations

1. **Role-Based Access**: Only faculty can create/update grades, only students can view their own grades
2. **Section Assignment**: Faculty can only manage grades for sections they are assigned to
3. **Student Enrollment**: Students can only view grades for sections they are enrolled in
4. **Authentication Required**: All endpoints require valid user authentication via X-User-ID header

---

## Integration Notes

- **Grade Calculation**: The system automatically calculates total marks by summing all individual grades
- **Flexible Grading**: Supports any grade type, allowing for custom grading schemes
- **Upsert Functionality**: Faculty can easily update grades without worrying about duplicates
- **Dashboard Integration**: Grade summary endpoint is designed to integrate with student dashboard views
- **Section Overview**: Faculty can get complete grade overview for class analysis and statistics

## Use Cases

### Faculty Use Cases

1. **Grade Management**: Create and update individual student grades
2. **Class Overview**: View all grades for a section to analyze class performance
3. **Grade Analysis**: Identify students who need additional support or recognition
4. **Grade Statistics**: Calculate class averages, grade distributions, and trends
5. **Grade Export**: Use section grades data for external grade reporting systems

### Student Use Cases

1. **Grade Tracking**: View individual grades and track academic progress
2. **Grade Summary**: Get total marks and grade breakdown for a course
3. **Performance Monitoring**: Monitor performance across different assessment types
4. **Academic Planning**: Use grade information for academic planning and goal setting

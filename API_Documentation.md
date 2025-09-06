# ClassMaster Backend API Documentation

## Faculty Tasks API

This document describes the Faculty Tasks API endpoints that allow faculty members to manage their personal tasks and tasks related to course announcements.

### Base URL

```
http://localhost:8000
```

### Authentication

All faculty endpoints require authentication via the `X-User-ID` header containing the faculty member's user ID.

---

## Faculty Tasks Endpoints

### 1. Get Faculty Tasks

**GET** `/faculty/{faculty_id}/tasks`

Retrieves all tasks (todos) for a specific faculty member, including both personal tasks and tasks related to announcements.

#### Parameters

- `faculty_id` (path, integer): The ID of the faculty member

#### Headers

- `X-User-ID` (integer): Faculty member's user ID for authentication

#### Response

**200 OK** - Returns a list of faculty tasks

```json
[
  {
    "todo_id": 1,
    "title": "Quiz: Midterm Exam",
    "status": "pending",
    "due_date": "2024-01-15",
    "related_announcement_id": 5,
    "announcement_title": "Midterm Exam",
    "announcement_content": "Complete the midterm exam by the deadline",
    "announcement_type": "quiz",
    "announcement_deadline": "2024-01-15T23:59:59",
    "course_code": "CS101",
    "section_number": 1
  },
  {
    "todo_id": 2,
    "title": "Prepare lecture slides",
    "status": "completed",
    "due_date": null,
    "related_announcement_id": null,
    "announcement_title": null,
    "announcement_content": null,
    "announcement_type": null,
    "announcement_deadline": null,
    "course_code": null,
    "section_number": null
  }
]
```

#### Error Responses

- **404 Not Found**: Faculty member not found
- **500 Internal Server Error**: Database error

---

### 2. Create Faculty Task

**POST** `/faculty/{faculty_id}/tasks`

Creates a new personal task for a faculty member.

#### Parameters

- `faculty_id` (path, integer): The ID of the faculty member

#### Headers

- `X-User-ID` (integer): Faculty member's user ID for authentication

#### Request Body

```json
{
  "title": "Prepare lecture slides for Chapter 5",
  "due_date": "2024-01-15"
}
```

#### Request Body Schema

- `title` (string, required): Task title (1-255 characters)
- `due_date` (string, optional): Due date in YYYY-MM-DD format

#### Response

**201 Created** - Returns the created task

```json
{
  "todo_id": 3,
  "title": "Prepare lecture slides for Chapter 5",
  "status": "pending",
  "due_date": "2024-01-15",
  "related_announcement_id": null,
  "announcement_title": null,
  "announcement_content": null,
  "announcement_type": null,
  "announcement_deadline": null,
  "course_code": null,
  "section_number": null
}
```

#### Error Responses

- **403 Forbidden**: Can only create tasks for yourself
- **404 Not Found**: Faculty member not found
- **500 Internal Server Error**: Failed to create task

---

### 3. Update Faculty Task Status

**PATCH** `/faculty/{faculty_id}/tasks/{todo_id}`

Updates the status of a faculty member's task. Includes complex business logic for quiz and assignment tasks.

#### Parameters

- `faculty_id` (path, integer): The ID of the faculty member
- `todo_id` (path, integer): The ID of the task to update

#### Headers

- `X-User-ID` (integer): Faculty member's user ID for authentication

#### Request Body

```json
{
  "status": "completed"
}
```

#### Request Body Schema

- `status` (string, required): New status - must be one of: "pending", "completed", "delayed"

#### Response

**200 OK** - Returns the updated task

```json
{
  "todo_id": 1,
  "title": "Quiz: Midterm Exam",
  "status": "completed",
  "due_date": "2024-01-15",
  "related_announcement_id": 5,
  "announcement_title": "Midterm Exam",
  "announcement_content": "Complete the midterm exam by the deadline",
  "announcement_type": "quiz",
  "announcement_deadline": "2024-01-15T23:59:59",
  "course_code": "CS101",
  "section_number": 1
}
```

#### Special Business Logic

When updating quiz or assignment tasks (regardless of current status) to "completed" or "delayed":

1. The original task is updated to the new status
2. **A new "check" task is automatically created** with the title: `"Check {original_title}"`
3. The new "check" task is a regular task (no due date, no announcement relation)
4. The "check" task can be updated normally like any other task

#### Example Workflow

1. Faculty has task: `"Quiz: Midterm Exam"`
2. Faculty updates status to "completed"
3. Original task becomes completed
4. New task automatically created: `"Check Quiz: Midterm Exam"`
5. Faculty can now manage the "check" task normally

#### Error Responses

- **400 Bad Request**: Invalid status value
- **403 Forbidden**: Can only update your own tasks
- **404 Not Found**: Task not found
- **500 Internal Server Error**: Failed to update task

---

## Task Types

### Personal Tasks

- Created by faculty members manually
- No due date required
- No announcement relation
- Can be updated freely

### Announcement-Related Tasks

- Automatically created when faculty creates quiz/assignment announcements
- Have due dates from announcement deadlines
- Linked to specific announcements
- Subject to special business logic on status updates

---

## Data Models

### FacultyTask

```json
{
  "todo_id": "integer",
  "title": "string",
  "status": "string (pending|completed|delayed)",
  "due_date": "string (YYYY-MM-DD) or null",
  "related_announcement_id": "integer or null",
  "announcement_title": "string or null",
  "announcement_content": "string or null",
  "announcement_type": "string (quiz|assignment|general) or null",
  "announcement_deadline": "string (ISO datetime) or null",
  "course_code": "string or null",
  "section_number": "integer or null"
}
```

### FacultyTaskCreate

```json
{
  "title": "string (1-255 characters)",
  "due_date": "string (YYYY-MM-DD) or null"
}
```

### FacultyTaskStatusUpdate

```json
{
  "status": "string (pending|completed|delayed)"
}
```

---

## Integration with Announcements

Faculty tasks are automatically created when:

1. **Creating Quiz/Assignment Announcements**: Faculty gets a task for each quiz/assignment they create
2. **Updating Quiz/Assignment Announcements**: Faculty gets a task when updating announcements to quiz/assignment type

The task titles follow the format: `"{Type}: {Announcement Title}"` (e.g., "Quiz: Midterm Exam", "Assignment: Final Project")

---

## Error Handling

All endpoints return appropriate HTTP status codes and error messages:

- **400 Bad Request**: Invalid input data
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **500 Internal Server Error**: Server-side error

Error responses include a `detail` field with a human-readable error message.

---

## Examples

### Complete Workflow Example

1. **Create a quiz announcement**:

   ```bash
   POST /create-announcement
   {
     "title": "Midterm Exam",
     "content": "Complete the midterm exam",
     "type": "quiz",
     "course_code": "CS101",
     "sec_number": 1,
     "deadline": "2024-01-15T23:59:59"
   }
   ```

2. **Faculty automatically gets a task**:

   ```bash
   GET /faculty/2/tasks
   # Returns task: "Quiz: Midterm Exam"
   ```

3. **Update task to completed**:

   ```bash
   PATCH /faculty/2/tasks/1
   {
     "status": "completed"
   }
   ```

4. **New "check" task is automatically created**:

   ```bash
   GET /faculty/2/tasks
   # Now shows: "Check Quiz: Midterm Exam"
   ```

5. **Manage the check task normally**:
   ```bash
   PATCH /faculty/2/tasks/2
   {
     "status": "completed"
   }
   ```

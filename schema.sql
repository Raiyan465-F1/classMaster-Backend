-- This script creates the tables for your university project.
-- Run this entire script in your database client or the Neon SQL Editor.

-- Base user table
CREATE TABLE "User" (
  "user_id" INT PRIMARY KEY,
  "name" VARCHAR(255),
  "email" VARCHAR(255) UNIQUE NOT NULL,
  "password" VARCHAR(255) NOT NULL,
  "role" VARCHAR(50) NOT NULL CHECK ("role" IN ('student', 'faculty', 'admin'))
);

-- Role-specific tables inheriting from User
CREATE TABLE "Student" (
  "user_id" INT PRIMARY KEY,
  FOREIGN KEY ("user_id") REFERENCES "User"("user_id") ON DELETE CASCADE
);

CREATE TABLE "Faculty" (
  "user_id" INT PRIMARY KEY,
  FOREIGN KEY ("user_id") REFERENCES "User"("user_id") ON DELETE CASCADE
);

CREATE TABLE "Admin" (
  "user_id" INT PRIMARY KEY,
  FOREIGN KEY ("user_id") REFERENCES "User"("user_id") ON DELETE CASCADE
);

-- Course and Section tables
CREATE TABLE "Course" (
  "course_code" VARCHAR(50) PRIMARY KEY,
  "course_name" VARCHAR(255)
);

CREATE TABLE "Section" (
  "course_code" VARCHAR(50),
  "sec_number" INT,
  "start_time" TIME,
  "end_time" TIME,
  "day_of_week" VARCHAR(20),
  "location" VARCHAR(100),
  PRIMARY KEY ("course_code", "sec_number"),
  FOREIGN KEY ("course_code") REFERENCES "Course"("course_code")
);

-- Join/linking tables
CREATE TABLE "Student_Section" (
  "student_id" INT,
  "course_code" VARCHAR(50),
  "sec_number" INT,
  PRIMARY KEY ("student_id", "course_code", "sec_number"),
  FOREIGN KEY ("student_id") REFERENCES "Student"("user_id"),
  FOREIGN KEY ("course_code", "sec_number") REFERENCES "Section"("course_code", "sec_number")
);

CREATE TABLE "Faculty_Section" (
  "faculty_id" INT,
  "course_code" VARCHAR(50),
  "sec_number" INT,
  PRIMARY KEY ("faculty_id", "course_code", "sec_number"),
  FOREIGN KEY ("faculty_id") REFERENCES "Faculty"("user_id"),
  FOREIGN KEY ("course_code", "sec_number") REFERENCES "Section"("course_code", "sec_number")
);

-- Other data tables
CREATE TABLE "Announcement" (
  "announcement_id" SERIAL PRIMARY KEY,
  "title" VARCHAR(255),
  "content" TEXT,
  "created_at" TIMESTAMPTZ DEFAULT NOW(),
  "type" VARCHAR(50) CHECK ("type" IN ('quiz', 'assignment', 'general')),
  "section_course_code" VARCHAR(50),
  "section_sec_number" INT,
  "faculty_id" INT,
  FOREIGN KEY ("faculty_id") REFERENCES "Faculty"("user_id"),
  FOREIGN KEY ("section_course_code", "section_sec_number") REFERENCES "Section"("course_code", "sec_number")
);

-- Grade table
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

-- Todo table
CREATE TABLE "Todo" (
  "user_id" INT,
  "todo_id" SERIAL,
  "title" VARCHAR(255),
  "status" VARCHAR(50) DEFAULT 'pending' CHECK ("status" IN ('pending', 'completed', 'delayed')),
  "due_date" DATE,
  "related_announcement" INT,
  PRIMARY KEY ("user_id", "todo_id"),
  FOREIGN KEY ("user_id") REFERENCES "User"("user_id"),
  FOREIGN KEY ("related_announcement") REFERENCES "Announcement"("announcement_id")
);

-- Leaderboard table
CREATE TABLE "Leaderboard" (
  "leaderboard_id" SERIAL PRIMARY KEY,
  "course_code" VARCHAR(50),
  "student_id" INT,
  "total_points" INT DEFAULT 0,
  "is_anonymous" BOOLEAN DEFAULT FALSE,
  "anonymous_name" VARCHAR(100),
  "last_updated" TIMESTAMPTZ DEFAULT NOW(),
  FOREIGN KEY ("course_code") REFERENCES "Course"("course_code"),
  FOREIGN KEY ("student_id") REFERENCES "Student"("user_id"),
  UNIQUE("course_code", "student_id")
);

ALTER TABLE "Student" 
ADD COLUMN "preferred_anonymous_name" VARCHAR(100);
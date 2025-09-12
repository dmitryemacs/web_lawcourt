from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey, Text, UniqueConstraint, Numeric
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    teachers = relationship("Teacher", back_populates="department")
    groups = relationship("Group", back_populates="department")

class Teacher(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    email = Column(String(200), unique=True)
    hired_at = Column(Date)

    department = relationship("Department", back_populates="teachers")
    courses = relationship("Course", back_populates="teacher")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    intake_year = Column(Integer)

    department = relationship("Department", back_populates="groups")
    students = relationship("Student", back_populates="group")
    courses = relationship("Course", back_populates="group")

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    enroll_date = Column(Date, default=date.today)

    group = relationship("Group", back_populates="students")
    enrollments = relationship("Enrollment", back_populates="student")
    grades = relationship("Grade", back_populates="student")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    courses = relationship("Course", back_populates="subject")

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))
    semester = Column(String(20), nullable=False)
    credits = Column(Integer, default=3)

    subject = relationship("Subject", back_populates="courses")
    teacher = relationship("Teacher", back_populates="courses")
    group = relationship("Group", back_populates="courses")
    enrollments = relationship("Enrollment", back_populates="course")
    exams = relationship("Exam", back_populates="course")

    __table_args__ = (UniqueConstraint("subject_id","teacher_id","group_id","semester", name="uix_course_unique"),)

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

    __table_args__ = (UniqueConstraint("student_id","course_id", name="uix_enrollment_unique"),)

class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name = Column(String(100), nullable=False)
    date = Column(DateTime)
    max_score = Column(Integer, default=100)

    course = relationship("Course", back_populates="exams")
    grades = relationship("Grade", back_populates="exam")

class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    score = Column(Numeric(5,2), nullable=False)
    graded_at = Column(DateTime, default=datetime.utcnow)

    exam = relationship("Exam", back_populates="grades")
    student = relationship("Student", back_populates="grades")

    __table_args__ = (UniqueConstraint("exam_id","student_id", name="uix_grade_unique"),)

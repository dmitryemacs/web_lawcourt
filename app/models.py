from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    enroll_date = Column(DateTime, default=func.now())
    grades = relationship("Grade", back_populates="student")
    enrollments = relationship("Enrollment", back_populates="student")

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    semester = Column(String)
    credits = Column(Integer)
    subject = relationship("Subject", back_populates="courses")
    teacher = relationship("Teacher", back_populates="courses")
    group = relationship("Group", back_populates="courses")
    enrollments = relationship("Enrollment", back_populates="course")
    exams = relationship("Exam", back_populates="course")

class Test(Base):
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    name = Column(String)
    description = Column(Text)
    max_score = Column(Integer, default=100)
    time_limit = Column(Integer)  # в минутах
    created_at = Column(DateTime, default=func.now())
    questions = relationship("Question", back_populates="test", order_by="Question.order")
    results = relationship("TestResult", back_populates="test")

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"))
    text = Column(Text)
    order = Column(Integer)
    type = Column(String)  # multiple_choice, single_choice, text
    options = Column(Text)  # JSON строка для вариантов ответов
    correct_answer = Column(Text)  # для single/multiple choice - индексы, для text - текст
    points = Column(Integer, default=1)
    test = relationship("Test", back_populates="questions")

class TestResult(Base):
    __tablename__ = "test_results"
    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"))
    student_id = Column(Integer, ForeignKey("students.id"))
    score = Column(Float)
    max_score = Column(Integer)
    passed = Column(Boolean, default=False)
    completed_at = Column(DateTime, default=func.now())
    answers = relationship("Answer", back_populates="result")

class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("test_results.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    answer_text = Column(Text)
    is_correct = Column(Boolean, default=False)
    points_earned = Column(Integer, default=0)
    question = relationship("Question")

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    name = Column(String)
    max_score = Column(Integer)
    date = Column(DateTime)
    course = relationship("Course", back_populates="exams")

class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"))
    student_id = Column(Integer, ForeignKey("students.id"))
    score = Column(Float)
    graded_at = Column(DateTime, default=func.now())
    exam = relationship("Exam")
    student = relationship("Student", back_populates="grades")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    courses = relationship("Course", back_populates="subject")

class Teacher(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    courses = relationship("Course", back_populates="teacher")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    intake_year = Column(Integer)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    department = relationship("Department", back_populates="groups")
    courses = relationship("Course", back_populates="group")
    students = relationship("Student", back_populates="group")

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    groups = relationship("Group", back_populates="department")
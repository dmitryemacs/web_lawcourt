from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    hire_date = Column(DateTime, default=func.now())
    department = relationship("Department", back_populates="employees")
    grades = relationship("Grade", back_populates="employee")
    enrollments = relationship("Enrollment", back_populates="employee")

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    judge_id = Column(Integer, ForeignKey("judges.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    semester = Column(String)
    credits = Column(Integer)
    subject = relationship("Subject", back_populates="courses")
    judge = relationship("Judge", back_populates="courses")
    department = relationship("Department", back_populates="courses")
    enrollments = relationship("Enrollment", back_populates="course")
    exams = relationship("Exam", back_populates="course")
    tests = relationship("Test", back_populates="course")

class Test(Base):
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    name = Column(String)
    description = Column(Text)
    max_score = Column(Integer, default=100)
    time_limit = Column(Integer)  # в минутах
    created_at = Column(DateTime, default=func.now())
    course = relationship("Course", back_populates="tests")
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
    employee_id = Column(Integer, ForeignKey("employees.id"))
    score = Column(Float)
    max_score = Column(Integer)
    passed = Column(Boolean, default=False)
    completed_at = Column(DateTime, default=func.now())
    test = relationship("Test", back_populates="results")
    answers = relationship("Answer", back_populates="result")

class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("test_results.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    answer_text = Column(Text)
    is_correct = Column(Boolean, default=False)
    points_earned = Column(Integer, default=0)
    result = relationship("TestResult", back_populates="answers")
    question = relationship("Question")

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    employee = relationship("Employee", back_populates="enrollments")
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
    employee_id = Column(Integer, ForeignKey("employees.id"))
    score = Column(Float)
    graded_at = Column(DateTime, default=func.now())
    exam = relationship("Exam")
    employee = relationship("Employee", back_populates="grades")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    courses = relationship("Course", back_populates="subject")

class Judge(Base):
    __tablename__ = "judges"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    courses = relationship("Course", back_populates="judge")

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    employees = relationship("Employee", back_populates="department")
    courses = relationship("Course", back_populates="department")


class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True, index=True)
    case_number = Column(String, unique=True, index=True)
    title = Column(String, index=True)
    case_type = Column(String, default="Гражданское")
    status = Column(String, default="Ожидание")
    parties = Column(Text)
    next_hearing = Column(DateTime, nullable=True)
    is_video = Column(Boolean, default=False)
    judge_id = Column(Integer, ForeignKey("judges.id"), nullable=True)
    secretary = Column(String, nullable=True)
    judge = relationship("Judge")
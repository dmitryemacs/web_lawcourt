from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, engine
from models import Base, Student, Course, Enrollment, Exam, Grade, Subject, Teacher, Group, Department
from sqlalchemy import select
import os

app = FastAPI(title="University App")

# Ensure DB tables exist
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")

# serve static (if any)
if not os.path.exists('static'):
    os.makedirs('static')
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    students = db.execute(select(Student)).scalars().all()
    courses = db.execute(select(Course)).scalars().all()
    return templates.TemplateResponse("students.html", {
        "request": request,
        "students": students,
        "courses": courses
    })

@app.post("/students/add")
def add_student(request: Request, first_name: str = Form(...), last_name: str = Form(...), email: str = Form(None), group_id: int = Form(None), db: Session = Depends(get_db)):
    student = Student(first_name=first_name, last_name=last_name, email=email, group_id=group_id)
    db.add(student)
    db.commit()
    return RedirectResponse(url='/', status_code=303)

@app.post("/enroll")
def enroll(request: Request, student_id: int = Form(...), course_id: int = Form(...), db: Session = Depends(get_db)):
    # Ensure student and course exist
    st = db.get(Student, student_id)
    cr = db.get(Course, course_id)
    if not st or not cr:
        raise HTTPException(status_code=404, detail="Student or Course not found")
    # check existing
    exists = db.query(Enrollment).filter_by(student_id=student_id, course_id=course_id).first()
    if exists:
        return RedirectResponse(url='/', status_code=303)
    enroll = Enrollment(student_id=student_id, course_id=course_id)
    db.add(enroll)
    db.commit()
    return RedirectResponse(url='/', status_code=303)

@app.get("/transcript/{student_id}", response_class=HTMLResponse)
def transcript(request: Request, student_id: int, db: Session = Depends(get_db)):
    st = db.get(Student, student_id)
    if not st:
        raise HTTPException(status_code=404, detail="Student not found")
    # eager load grades and exams via relationships
    return templates.TemplateResponse("transcript.html", {
        "request": request,
        "student": st,
        "grades": st.grades
    })

@app.post("/grade")
def grade_assign(request: Request, exam_id: int = Form(...), student_id: int = Form(...), score: float = Form(...), db: Session = Depends(get_db)):
    ex = db.get(Exam, exam_id)
    st = db.get(Student, student_id)
    if not ex or not st:
        raise HTTPException(status_code=404, detail="Exam or Student not found")
    existing = db.query(Grade).filter_by(exam_id=exam_id, student_id=student_id).first()
    if existing:
        existing.score = score
    else:
        g = Grade(exam_id=exam_id, student_id=student_id, score=score)
        db.add(g)
    db.commit()
    return RedirectResponse(url=f"/transcript/{student_id}", status_code=303)

@app.get("/courses", response_class=HTMLResponse)
def courses_view(request: Request, db: Session = Depends(get_db)):
    courses = db.execute(select(Course)).scalars().all()
    return templates.TemplateResponse("courses.html", {"request": request, "courses": courses})

@app.get("/course/{course_id}", response_class=HTMLResponse)
def course_detail(request: Request, course_id: int, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return templates.TemplateResponse("course_detail.html", {"request": request, "course": course})

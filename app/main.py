from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text, select
import time
import os
import uvicorn
from datetime import datetime, timedelta
from typing import List, Dict, Any

from database import get_db, engine
from models import Base, Student, Course, Enrollment, Exam, Grade, Subject, Teacher, Group, Department

# Система уведомлений
class Message:
    def __init__(self, text: str, category: str = "is-info"):
        self.text = text
        self.category = category

def get_messages(request: Request) -> List[Message]:
    """Получить уведомления из сессии"""
    if not hasattr(request.state, 'messages'):
        request.state.messages = []
    return request.state.messages

def add_message(request: Request, text: str, category: str = "is-info"):
    """Добавить уведомление"""
    messages = get_messages(request)
    messages.append(Message(text, category))

def clear_messages(request: Request):
    """Очистить уведомления"""
    if hasattr(request.state, 'messages'):
        request.state.messages = []

app = FastAPI(title="University App")

# Функция ожидания подключения к базе данных
def wait_for_db():
    max_retries = 30
    retry_interval = 2

    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                print("✅ Database connection successful!")
                return True
        except Exception as e:
            print(f"⏳ Waiting for database... (Attempt {i+1}/{max_retries})")
            time.sleep(retry_interval)

    print("❌ Could not connect to database after multiple attempts")
    return False

# Создаем таблицы после успешного подключения
if wait_for_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"❌ Failed to create database tables: {e}")
else:
    print("⚠️  Skipping table creation due to database connection failure")

# Настройка Jinja2 шаблонов
templates = Jinja2Templates(directory="templates")

# Обслуживание статических файлов
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    students = db.execute(select(Student)).scalars().all()
    courses = db.execute(select(Course)).scalars().all()
    groups = db.execute(select(Group)).scalars().all()
    return templates.TemplateResponse("students.html", {
        "request": request,
        "students": students,
        "courses": courses,
        "groups": groups
    })

@app.post("/students/add")
def add_student(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    group_id: int = Form(None),
    db: Session = Depends(get_db)
):
    student = Student(
        first_name=first_name,
        last_name=last_name,
        email=email,
        group_id=group_id if group_id else None
    )
    db.add(student)
    db.commit()
    return RedirectResponse(url='/', status_code=303)

@app.post("/enroll")
def enroll(
    request: Request,
    student_id: int = Form(...),
    course_id: int = Form(...),
    db: Session = Depends(get_db)
):
    # Проверяем существование студента и курса
    st = db.get(Student, student_id)
    cr = db.get(Course, course_id)

    if not st or not cr:
        raise HTTPException(status_code=404, detail="Student or Course not found")

    # Проверяем существующую запись
    exists = db.execute(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id
        )
    ).scalar_one_or_none()

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

    # Загружаем оценки с связанными данными
    grades = db.execute(
        select(Grade)
        .join(Grade.exam)
        .join(Exam.course)
        .join(Course.subject)
        .where(Grade.student_id == student_id)
        .order_by(Grade.graded_at.desc())
    ).scalars().all()

    # Получаем доступные экзамены для студента
    available_exams = []
    if st.group:
        # Экзамены из курсов группы
        group_courses = db.execute(
            select(Course)
            .where(Course.group_id == st.group.id)
        ).scalars().all()

        for course in group_courses:
            course_exams = db.execute(
                select(Exam)
                .where(Exam.course_id == course.id)
            ).scalars().all()
            available_exams.extend(course_exams)

    # Экзамены из курсов, на которые записан студент
    for enrollment in st.enrollments:
        course_exams = db.execute(
            select(Exam)
            .where(Exam.course_id == enrollment.course_id)
        ).scalars().all()
        available_exams.extend(course_exams)

    # Убираем дубликаты
    unique_exams = {exam.id: exam for exam in available_exams}.values()

    return templates.TemplateResponse("transcript.html", {
        "request": request,
        "student": st,
        "grades": grades,
        "available_exams": list(unique_exams)
    })

@app.post("/grade")
def grade_assign(
    request: Request,
    exam_id: int = Form(...),
    student_id: int = Form(...),
    score: float = Form(...),
    db: Session = Depends(get_db)
):
    ex = db.get(Exam, exam_id)
    st = db.get(Student, student_id)

    if not ex or not st:
        raise HTTPException(status_code=404, detail="Exam or Student not found")

    # Проверяем максимальный балл
    if score > ex.max_score:
        raise HTTPException(
            status_code=400,
            detail=f"Score ({score}) exceeds maximum allowed ({ex.max_score})"
        )

    # Проверяем существующую оценку
    existing = db.execute(
        select(Grade).where(
            Grade.exam_id == exam_id,
            Grade.student_id == student_id
        )
    ).scalar_one_or_none()

    if existing:
        existing.score = score
    else:
        g = Grade(exam_id=exam_id, student_id=student_id, score=score)
        db.add(g)

    db.commit()
    return RedirectResponse(url=f"/transcript/{student_id}", status_code=303)

@app.get("/courses", response_class=HTMLResponse)
def courses_view(request: Request, db: Session = Depends(get_db)):
    courses = db.execute(
        select(Course)
        .join(Course.subject)
        .join(Course.teacher, isouter=True)
        .join(Course.group, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    # Get additional data for the form
    subjects = db.execute(select(Subject)).scalars().all()
    teachers = db.execute(select(Teacher)).scalars().all()
    groups = db.execute(select(Group)).scalars().all()

    return templates.TemplateResponse("courses.html", {
        "request": request,
        "courses": courses,
        "subjects": subjects,
        "teachers": teachers,
        "groups": groups
    })

@app.get("/course/{course_id}", response_class=HTMLResponse)
def course_detail(request: Request, course_id: int, db: Session = Depends(get_db)):
    course = db.execute(
        select(Course)
        .where(Course.id == course_id)
        .join(Course.subject)
        .join(Course.teacher, isouter=True)
        .join(Course.group, isouter=True)
    ).scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Получаем экзамены для курса
    exams = db.execute(
        select(Exam)
        .where(Exam.course_id == course_id)
        .order_by(Exam.date)
    ).scalars().all()

    return templates.TemplateResponse("course_detail.html", {
        "request": request,
        "course": course,
        "exams": exams
    })

@app.get("/health")
def health_check():
    return {"status": "healthy", "database": "connected"}

@app.get("/groups", response_class=HTMLResponse)
def groups_view(request: Request, db: Session = Depends(get_db)):
    groups = db.execute(
        select(Group)
        .join(Group.department, isouter=True)
        .order_by(Group.name)
    ).scalars().all()

    return templates.TemplateResponse("groups.html", {
        "request": request,
        "groups": groups
    })

@app.post("/groups/add")
def add_group(
    request: Request,
    name: str = Form(...),
    intake_year: int = Form(...),
    department_id: int = Form(None),
    db: Session = Depends(get_db)
):
    group = Group(
        name=name,
        intake_year=intake_year,
        department_id=department_id if department_id else None
    )

    try:
        db.add(group)
        db.commit()
        return RedirectResponse(url='/', status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении группы: {str(e)}")

@app.post("/courses/add")
def add_course(
    request: Request,
    subject_id: int = Form(...),
    semester: str = Form(...),
    credits: int = Form(...),
    teacher_id: int = Form(None),
    group_id: int = Form(None),
    db: Session = Depends(get_db)
):
    course = Course(
        subject_id=subject_id,
        teacher_id=teacher_id if teacher_id else None,
        group_id=group_id if group_id else None,
        semester=semester,
        credits=credits
    )

    try:
        db.add(course)
        db.commit()
        return RedirectResponse(url='/courses', status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении курса: {str(e)}")

@app.post("/teachers/add")
def add_teacher(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    db: Session = Depends(get_db)
):
    teacher = Teacher(
        first_name=first_name,
        last_name=last_name,
        email=email,
        department_id=None  # Can be added later if needed
    )

    try:
        db.add(teacher)
        db.commit()
        return RedirectResponse(url='/courses', status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении преподавателя: {str(e)}")

@app.post("/subjects/add")
def add_subject(
    request: Request,
    code: str = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    subject = Subject(
        code=code,
        title=title,
        description=description
    )

    try:
        db.add(subject)
        db.commit()
        return RedirectResponse(url='/courses', status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении предмета: {str(e)}")

@app.get("/init-data")
def init_sample_data(db: Session = Depends(get_db)):
    """Инициализация тестовых данных"""
    try:
        # Проверяем, есть ли уже данные
        existing_dept = db.execute(select(Department).limit(1)).scalar_one_or_none()
        if existing_dept:
            return {"message": "Sample data already exists"}

        # Создаем кафедру
        dept = Department(name="Факультет компьютерных наук")
        db.add(dept)
        db.flush()

        # Создаем преподавателей
        teacher1 = Teacher(
            first_name="Иван",
            last_name="Петров",
            department_id=dept.id,
            email="ivan.petrov@university.ru"
        )
        teacher2 = Teacher(
            first_name="Мария",
            last_name="Сидорова",
            department_id=dept.id,
            email="maria.sidorova@university.ru"
        )
        db.add_all([teacher1, teacher2])
        db.flush()

        # Создаем группы
        group1 = Group(
            name="CS-101",
            department_id=dept.id,
            intake_year=2023
        )
        group2 = Group(
            name="CS-102",
            department_id=dept.id,
            intake_year=2022
        )
        db.add_all([group1, group2])
        db.flush()

        # Создаем предметы
        subjects = [
            Subject(
                code="CS101",
                title="Введение в программирование",
                description="Базовый курс программирования на Python"
            ),
            Subject(
                code="CS102",
                title="Алгоритмы и структуры данных",
                description="Изучение алгоритмов и структур данных"
            ),
            Subject(
                code="MATH101",
                title="Дискретная математика",
                description="Основы дискретной математики"
            )
        ]
        db.add_all(subjects)
        db.flush()

        # Создаем курсы
        courses = [
            Course(
                subject_id=subjects[0].id,
                teacher_id=teacher1.id,
                group_id=group1.id,
                semester="Осень 2023",
                credits=3
            ),
            Course(
                subject_id=subjects[1].id,
                teacher_id=teacher2.id,
                group_id=group1.id,
                semester="Весна 2024",
                credits=4
            ),
            Course(
                subject_id=subjects[2].id,
                teacher_id=teacher1.id,
                group_id=group2.id,
                semester="Осень 2023",
                credits=3
            )
        ]
        db.add_all(courses)
        db.flush()

        # Создаем студентов
        students = [
            Student(
                first_name="Алексей",
                last_name="Иванов",
                email="alexey.ivanov@university.ru",
                group_id=group1.id,
                enroll_date=datetime.now() - timedelta(days=365)
            ),
            Student(
                first_name="Екатерина",
                last_name="Смирнова",
                email="ekaterina.smirnova@university.ru",
                group_id=group1.id,
                enroll_date=datetime.now() - timedelta(days=360)
            ),
            Student(
                first_name="Дмитрий",
                last_name="Кузнецов",
                email="dmitry.kuznetsov@university.ru",
                group_id=group1.id,
                enroll_date=datetime.now() - timedelta(days=355)
            ),
            Student(
                first_name="Ольга",
                last_name="Попова",
                email="olga.popova@university.ru",
                group_id=group2.id,
                enroll_date=datetime.now() - timedelta(days=730)
            ),
            Student(
                first_name="Сергей",
                last_name="Васильев",
                email="sergey.vasiliev@university.ru",
                group_id=group2.id,
                enroll_date=datetime.now() - timedelta(days=725)
            )
        ]
        db.add_all(students)
        db.flush()

        # Создаем экзамены
        exams = [
            Exam(
                course_id=courses[0].id,
                name="Финальный экзамен",
                max_score=100,
                date=datetime.now() - timedelta(days=30)
            ),
            Exam(
                course_id=courses[1].id,
                name="Среднесрочный экзамен",
                max_score=50,
                date=datetime.now() - timedelta(days=15)
            ),
            Exam(
                course_id=courses[2].id,
                name="Итоговый тест",
                max_score=75,
                date=datetime.now() - timedelta(days=45)
            )
        ]
        db.add_all(exams)
        db.flush()

        # Создаем записи на курсы
        enrollments = [
            Enrollment(student_id=students[0].id, course_id=courses[0].id),
            Enrollment(student_id=students[0].id, course_id=courses[1].id),
            Enrollment(student_id=students[1].id, course_id=courses[0].id),
            Enrollment(student_id=students[1].id, course_id=courses[1].id),
            Enrollment(student_id=students[2].id, course_id=courses[0].id),
            Enrollment(student_id=students[3].id, course_id=courses[2].id),
            Enrollment(student_id=students[4].id, course_id=courses[2].id)
        ]
        db.add_all(enrollments)
        db.flush()

        # Создаем оценки
        grades = [
            Grade(exam_id=exams[0].id, student_id=students[0].id, score=88),
            Grade(exam_id=exams[0].id, student_id=students[1].id, score=92),
            Grade(exam_id=exams[0].id, student_id=students[2].id, score=76),
            Grade(exam_id=exams[1].id, student_id=students[0].id, score=45),
            Grade(exam_id=exams[1].id, student_id=students[1].id, score=48),
            Grade(exam_id=exams[2].id, student_id=students[3].id, score=68),
            Grade(exam_id=exams[2].id, student_id=students[4].id, score=72)
        ]
        db.add_all(grades)

        db.commit()
        return {"message": "Sample data created successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, select
import time
import os
import uvicorn
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import asyncio

from database import get_db, engine
from models import Base, Student, Course, Enrollment, Exam, Grade, Subject, Teacher, Group, Department, Test, Question, TestResult, Answer, Case

# Система уведомлений
class Message:
    def __init__(self, text: str, category: str = "is-info"):
        self.text = text
        self.category = category

def get_messages(request: Request) -> List[Message]:
    """Получить уведомления из сессии"""
    raw = request.session.pop("messages", [])
    return [Message(m.get("text", ""), m.get("category", "is-info")) for m in raw]

def add_message(request: Request, text: str, category: str = "is-info"):
    """Добавить уведомление в сессию"""
    raw = request.session.get("messages", [])
    raw.append({"text": text, "category": category})
    request.session["messages"] = raw

def clear_messages(request: Request):
    """Очистить уведомления"""
    request.session.pop("messages", None)

app = FastAPI(title="Learning Platform")
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")

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
# Expose templates on app so tests or external scripts can set directory if needed
app.templates = templates
# Make `get_messages` available inside Jinja templates as a global function
templates.env.globals["get_messages"] = get_messages

# Configure basic logging for the app (can be overridden by environment)
logging.basicConfig(level=logging.INFO)

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

@app.get("/tests", response_class=HTMLResponse)
def tests_view(request: Request, db: Session = Depends(get_db)):
    """Просмотр всех тестов"""
    tests = db.execute(
        select(Test)
        .join(Test.course)
        .join(Course.subject)
        .order_by(Test.created_at.desc())
    ).scalars().all()

    return templates.TemplateResponse("tests.html", {
        "request": request,
        "tests": tests
    })

@app.get("/tests/create", response_class=HTMLResponse)
def create_test_form(request: Request, db: Session = Depends(get_db)):
    """Форма создания теста"""
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        add_message(request, "Сначала войдите в систему как преподаватель", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    courses = db.execute(
        select(Course)
        .where(Course.teacher_id == teacher_id)
        .join(Course.subject)
        .join(Course.group, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    return templates.TemplateResponse("create_test.html", {
        "request": request,
        "courses": courses
    })

@app.post("/tests/create")
def create_test(
    request: Request,
    course_id: int = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    max_score: int = Form(100),
    time_limit: int = Form(None),
    db: Session = Depends(get_db)
):
    """Создание теста"""
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        add_message(request, "Сначала войдите в систему как преподаватель", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    # Проверяем, что преподаватель действительно ведет этот курс
    course = db.get(Course, course_id)
    if not course or course.teacher_id != teacher_id:
        add_message(request, "Вы не можете создавать тесты для этого курса", "is-danger")
        return RedirectResponse(url='/tests/create', status_code=303)

    test = Test(
        course_id=course_id,
        name=name,
        description=description,
        max_score=max_score,
        time_limit=time_limit
    )
    db.add(test)
    db.commit()
    add_message(request, "Тест создан успешно!", "is-success")
    return RedirectResponse(url=f'/tests/{test.id}/edit', status_code=303)

@app.get("/tests/{test_id}/edit", response_class=HTMLResponse)
def edit_test(request: Request, test_id: int, db: Session = Depends(get_db)):
    """Редактирование теста и добавление вопросов"""
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        add_message(request, "Сначала войдите в систему как преподаватель", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    test = db.execute(
        select(Test)
        .where(Test.id == test_id)
        .join(Test.course)
    ).scalar_one_or_none()
    
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Проверяем, что преподаватель действительно ведет этот курс
    if test.course.teacher_id != teacher_id:
        add_message(request, "Вы не можете редактировать этот тест", "is-danger")
        return RedirectResponse(url='/teacher-dashboard', status_code=303)

    questions = db.execute(
        select(Question).where(Question.test_id == test_id).order_by(Question.order)
    ).scalars().all()

    return templates.TemplateResponse("edit_test.html", {
        "request": request,
        "test": test,
        "questions": questions
    })

@app.post("/tests/{test_id}/questions/add")
def add_question(
    request: Request,
    test_id: int,
    text: str = Form(...),
    question_type: str = Form(...),
    options: str = Form(None),
    correct_answer: str = Form(None),
    points: int = Form(1),
    db: Session = Depends(get_db)
):
    """Добавление вопроса к тесту"""
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        add_message(request, "Сначала войдите в систему как преподаватель", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    test = db.execute(
        select(Test)
        .where(Test.id == test_id)
        .join(Test.course)
    ).scalar_one_or_none()
    
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Проверяем, что преподаватель действительно ведет этот курс
    if test.course.teacher_id != teacher_id:
        add_message(request, "Вы не можете добавлять вопросы к этому тесту", "is-danger")
        return RedirectResponse(url='/teacher-dashboard', status_code=303)

    # Определяем порядок вопроса
    last_order = db.execute(
        select(Question.order)
        .where(Question.test_id == test_id)
        .order_by(Question.order.desc())
        .limit(1)
    ).scalar_one_or_none()

    question = Question(
        test_id=test_id,
        text=text,
        order=(last_order + 1) if last_order is not None else 1,
        type=question_type,
        options=options,
        correct_answer=correct_answer,
        points=points
    )
    db.add(question)
    db.commit()
    add_message(request, "Вопрос добавлен успешно!", "is-success")
    return RedirectResponse(url=f'/tests/{test_id}/edit', status_code=303)

@app.get("/tests/{test_id}", response_class=HTMLResponse)
def test_detail(request: Request, test_id: int, db: Session = Depends(get_db)):
    """Просмотр деталей теста"""
    test = db.execute(
        select(Test)
        .where(Test.id == test_id)
        .join(Test.course)
        .join(Course.subject)
        .join(Course.teacher, isouter=True)
    ).scalar_one_or_none()

    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    questions = db.execute(
        select(Question).where(Question.test_id == test_id).order_by(Question.order)
    ).scalars().all()

    return templates.TemplateResponse("test_detail.html", {
        "request": request,
        "test": test,
        "questions": questions
    })

@app.get("/courses/{course_id}/tests", response_class=HTMLResponse)
def course_tests(request: Request, course_id: int, db: Session = Depends(get_db)):
    """Тесты для конкретного курса"""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    tests = db.execute(
        select(Test).where(Test.course_id == course_id).order_by(Test.created_at.desc())
    ).scalars().all()

    return templates.TemplateResponse("course_tests.html", {
        "request": request,
        "course": course,
        "tests": tests
    })

@app.get("/take-test/{test_id}", response_class=HTMLResponse)
def take_test(request: Request, test_id: int, db: Session = Depends(get_db)):
    """Начало прохождения теста"""
    test = db.execute(
        select(Test)
        .where(Test.id == test_id)
        .join(Test.course)
    ).scalar_one_or_none()
    
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Проверяем, может ли студент проходить этот тест
    student_id = request.session.get("student_id")
    if not student_id:
        add_message(request, "Сначала войдите в систему как студент", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Проверяем, записан ли студент на курс
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.student_id == student_id)
        .where(Enrollment.course_id == test.course_id)
    ).scalar_one_or_none()

    if not enrollment:
        add_message(request, "Вы не записаны на этот курс", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Проверяем, не проходил ли студент уже этот тест
    existing_result = db.execute(
        select(TestResult)
        .where(TestResult.test_id == test_id)
        .where(TestResult.student_id == student_id)
    ).scalar_one_or_none()

    if existing_result:
        add_message(request, "Вы уже проходили этот тест", "is-info")
        return RedirectResponse(url=f'/test-results/{existing_result.id}', status_code=303)

    questions = db.execute(
        select(Question).where(Question.test_id == test_id).order_by(Question.order)
    ).scalars().all()

    return templates.TemplateResponse("take_test.html", {
        "request": request,
        "test": test,
        "questions": questions
    })

@app.post("/submit-test/{test_id}")
def submit_test(
    request: Request,
    test_id: int,
    db: Session = Depends(get_db)
):
    """Сохранение результатов теста"""
    student_id = request.session.get("student_id")
    if not student_id:
        raise HTTPException(status_code=403, detail="Access denied")

    test = db.get(Test, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Создаем результат теста
    result = TestResult(
        test_id=test_id,
        student_id=student_id,
        score=0,
        max_score=test.max_score
    )
    db.add(result)
    db.flush()

    # Обрабатываем ответы
    total_score = 0
    for question in test.questions:
        answer_value = request.form.get(f"question_{question.id}")
        is_correct = False
        points_earned = 0

        if question.type == "text":
            if answer_value and answer_value.strip().lower() == question.correct_answer.lower():
                is_correct = True
                points_earned = question.points
        elif question.type == "single_choice":
            if answer_value and answer_value == question.correct_answer:
                is_correct = True
                points_earned = question.points
        elif question.type == "multiple_choice":
            if answer_value:
                selected = set(answer_value.split(","))
                correct = set(question.correct_answer.split(","))
                if selected == correct:
                    is_correct = True
                    points_earned = question.points

        answer = Answer(
            result_id=result.id,
            question_id=question.id,
            answer_text=answer_value or "",
            is_correct=is_correct,
            points_earned=points_earned
        )
        db.add(answer)
        total_score += points_earned

    # Обновляем результат
    result.score = total_score
    result.passed = total_score >= (test.max_score * 0.6)  # Проходной балл 60%
    db.commit()

    add_message(request, f"Тест завершен! Вы набрали {total_score} из {test.max_score}", "is-success")
    return RedirectResponse(url=f'/test-results/{result.id}', status_code=303)

@app.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    db: Session = Depends(get_db),
    role: str = None,
    first_name: str = None,
    last_name: str = None,
    email: str = None,
    group_id: int = None,
    access_code: str = None
):
    """Форма регистрации"""
    # Получаем список групп для выбора
    groups = db.execute(select(Group).order_by(Group.name)).scalars().all()
    
    return templates.TemplateResponse("register.html", {
        "request": request,
        "groups": groups,
        "role": role,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "group_id": group_id,
        "access_code": access_code
    })

@app.post("/register")
def register(
    request: Request,
    role: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    group_id: str = Form(None),
    access_code: str = Form(None),
    db: Session = Depends(get_db)
):
    """Регистрация пользователя (студента или преподавателя)"""
    
    # Проверяем, что email не занят
    existing_student = db.execute(
        select(Student).where(Student.email == email)
    ).scalar_one_or_none()
    
    existing_teacher = db.execute(
        select(Teacher).where(Teacher.email == email)
    ).scalar_one_or_none()
    
    if existing_student or existing_teacher:
        add_message(request, "Пользователь с таким email уже существует", "is-danger")
        return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
    
    if role == "student":
        # Регистрация студента
        if not group_id or group_id == "":
            add_message(request, "Необходимо выбрать группу", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
        
        try:
            group_id_int = int(group_id)
        except (ValueError, TypeError):
            add_message(request, "Неверная группа", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
        
        try:
            student = Student(
                first_name=first_name,
                last_name=last_name,
                email=email,
                group_id=group_id_int
            )
            db.add(student)
            db.commit()
            
            add_message(request, "Регистрация успешна! Теперь вы можете войти в систему", "is-success")
            return RedirectResponse(url='/login', status_code=303)
        except Exception as e:
            db.rollback()
            print(f"Error registering student: {e}")
            add_message(request, f"Ошибка при регистрации: {str(e)}", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
        
    elif role == "teacher":
        # Регистрация преподавателя
        if not access_code:
            add_message(request, "Необходимо ввести код доступа", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
        
        # Проверяем код доступа (можно настроить более сложную логику)
        if access_code != "teacher123":
            add_message(request, "Неверный код доступа", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
        
        try:
            teacher = Teacher(
                first_name=first_name,
                last_name=last_name,
                email=email,
                department_id=None  # Можно добавить выбор кафедры позже
            )
            db.add(teacher)
            db.commit()
            
            add_message(request, "Регистрация успешна! Теперь вы можете войти в систему", "is-success")
            return RedirectResponse(url='/teacher-login', status_code=303)
        except Exception as e:
            db.rollback()
            print(f"Error registering teacher: {e}")
            add_message(request, f"Ошибка при регистрации: {str(e)}", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)
    
    else:
        add_message(request, "Неверный тип аккаунта", "is-danger")
        return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&group_id={group_id or ""}&access_code={access_code or ""}', status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    """Форма входа для студентов"""
    return templates.TemplateResponse("login.html", {
        "request": request
    })

@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    """Вход студента"""
    student = db.execute(
        select(Student).where(Student.email == email)
    ).scalar_one_or_none()

    if not student:
        add_message(request, "Студент с таким email не найден", "is-danger")
        return RedirectResponse(url='/login', status_code=303)

    # Сохраняем id студента в сессии
    request.session["student_id"] = student.id
    request.session["student_name"] = f"{student.first_name} {student.last_name}"
    request.session["user_role"] = "student"

    add_message(request, f"Добро пожаловать, {student.first_name}!", "is-success")
    return RedirectResponse(url='/', status_code=303)

@app.get("/logout")
def logout(request: Request):
    """Выход студента"""
    # Удаляем ключи безопасно
    request.session.pop("student_id", None)
    request.session.pop("student_name", None)
    request.session.pop("user_role", None)

    add_message(request, "Вы вышли из системы", "is-info")
    return RedirectResponse(url='/', status_code=303)

@app.get("/teacher-login", response_class=HTMLResponse)
def teacher_login_form(request: Request, db: Session = Depends(get_db)):
    """Форма входа для преподавателей"""
    return templates.TemplateResponse("teacher_login.html", {
        "request": request
    })

@app.post("/teacher-login")
def teacher_login(
    request: Request,
    email: str = Form(...),
    access_code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Вход преподавателя"""
    # Простой код доступа для демонстрации
    if access_code != "teacher123":
        add_message(request, "Неверный код доступа", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    teacher = db.execute(
        select(Teacher).where(Teacher.email == email)
    ).scalar_one_or_none()

    if not teacher:
        add_message(request, "Преподаватель с таким email не найден", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    # Сохраняем id преподавателя в сессии
    request.session["teacher_id"] = teacher.id
    request.session["teacher_name"] = f"{teacher.first_name} {teacher.last_name}"
    request.session["user_role"] = "teacher"

    add_message(request, f"Добро пожаловать, {teacher.first_name}!", "is-success")
    return RedirectResponse(url='/teacher-dashboard', status_code=303)

@app.get("/teacher-logout")
def teacher_logout(request: Request):
    """Выход преподавателя"""
    # Удаляем ключи безопасно
    request.session.pop("teacher_id", None)
    request.session.pop("teacher_name", None)
    request.session.pop("user_role", None)

    add_message(request, "Вы вышли из системы", "is-info")
    return RedirectResponse(url='/', status_code=303)

@app.get("/teacher-dashboard", response_class=HTMLResponse)
def teacher_dashboard(request: Request, db: Session = Depends(get_db)):
    """Панель преподавателя"""
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        add_message(request, "Сначала войдите в систему как преподаватель", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    # Получаем курсы преподавателя
    courses = db.execute(
        select(Course)
        .where(Course.teacher_id == teacher_id)
        .join(Course.subject)
        .join(Course.group, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    return templates.TemplateResponse("teacher_dashboard.html", {
        "request": request,
        "courses": courses
    })

@app.get("/teacher-test-results", response_class=HTMLResponse)
def teacher_test_results(request: Request, db: Session = Depends(get_db)):
    """Просмотр результатов тестов преподавателем"""
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        add_message(request, "Сначала войдите в систему как преподаватель", "is-danger")
        return RedirectResponse(url='/teacher-login', status_code=303)

    # Получаем курсы преподавателя
    teacher_courses = db.execute(
        select(Course)
        .where(Course.teacher_id == teacher_id)
        .join(Course.subject)
        .join(Course.group, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    # Получаем результаты тестов по курсам преподавателя
    test_results = db.execute(
        select(TestResult)
        .join(TestResult.test)
        .join(Test.course)
        .where(Course.teacher_id == teacher_id)
        .join(TestResult.student)
        .order_by(TestResult.completed_at.desc())
        .limit(50)
    ).scalars().all()

    # Считаем статистику
    total_tests = len([t for t in teacher_courses for _ in t.tests])
    completed_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r.passed)
    failed_tests = completed_tests - passed_tests

    return templates.TemplateResponse("teacher_test_results.html", {
        "request": request,
        "courses": teacher_courses,
        "test_results": test_results,
        "total_tests": total_tests,
        "completed_tests": completed_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests
    })

def require_teacher(request: Request):
    """Декоратор для проверки роли преподавателя"""
    if request.session.get("user_role") != "teacher":
        raise HTTPException(status_code=403, detail="Access denied - teacher required")

def require_student(request: Request):
    """Декоратор для проверки роли студента"""
    if not request.session.get("student_id"):
        raise HTTPException(status_code=403, detail="Access denied - student required")


def require_roles(request: Request, allowed: List[str]):
    role = request.session.get("user_role")
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Access denied - insufficient role")


@app.get("/judicial/login", response_class=HTMLResponse)
def judicial_login_page(request: Request):
    """Show role selection/login page for judicial system."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/judicial/login")
def judicial_login(
    request: Request,
    role: str = Form(...),
    name: str = Form(None)
):
    """Handle demo login - set role and user name in session."""
    if role not in ["judge", "secretary", "lawyer", "plaintiff", "visitor", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # Store in session
    request.session["user_role"] = role
    request.session["user_name"] = name or "Пользователь"
    request.session["logged_in"] = True
    
    logging.info(f"User logged in as {role}: {name}")
    
    # Redirect to appropriate dashboard
    if role == "judge":
        return RedirectResponse(url="/judicial/judge-dashboard", status_code=303)
    elif role == "secretary":
        return RedirectResponse(url="/judicial/secretary-dashboard", status_code=303)
    else:
        return RedirectResponse(url="/judicial/", status_code=303)


@app.get("/judicial/logout")
def judicial_logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/judicial/login", status_code=303)


@app.get("/judicial/", response_class=HTMLResponse)
def judicial_home(request: Request):
    """Main page for judicial system."""
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/judicial/login", status_code=303)
    
    role = request.session.get("user_role", "unknown")
    user = request.session.get("user_name", "unknown")
    
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="utf-8" />
        <title>Судебная система</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
        <style>body {{ padding: 20px; }}</style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">Добро пожаловать, {user}!</h1>
            <p>Ваша роль: <strong>{role}</strong></p>
            <div class="buttons">
                <a class="button is-primary" href="/judicial/judge-dashboard">Панель судьи</a>
                <a class="button" href="/judicial/logout">Выйти</a>
            </div>
        </div>
    </body>
    </html>
    """
    return html


@app.get("/judicial/judge-dashboard", response_class=HTMLResponse)
def judicial_judge_dashboard(request: Request):
    """Redirect to demo dashboard with role check."""
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/judicial/login", status_code=303)
    
    if request.session.get("user_role") not in ["judge", "admin"]:
        raise HTTPException(status_code=403, detail="Only judges can access this page")
    
    return RedirectResponse(url="/demo/judge-dashboard", status_code=303)


@app.get("/judicial/secretary-dashboard", response_class=HTMLResponse)
def judicial_secretary_dashboard(request: Request):
    """Secretary dashboard (placeholder)."""
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/judicial/login", status_code=303)
    
    if request.session.get("user_role") not in ["secretary", "admin"]:
        raise HTTPException(status_code=403, detail="Only secretaries can access this page")
    
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="utf-8" />
        <title>Панель секретаря</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
        <style>body { padding: 20px; }</style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">Панель секретаря</h1>
            <p>Функциональность в разработке...</p>
            <a class="button" href="/judicial/logout">Выйти</a>
        </div>
    </body>
    </html>
    """
    return html


@app.post("/ai-chat")
async def ai_chat(request: Request):
    """Send user messages to OpenRouter API using the OpenAI SDK.

    Expects JSON: {"message": "user text"}
    Environment variables control configuration:
      - OPENROUTER_API_KEY: (required) API key for OpenRouter
      - OPENROUTER_MODEL: (optional) model name to use (default: openai/gpt-3.5-turbo)
      - SITE_URL: (optional) your site URL for OpenRouter rankings
      - SITE_NAME: (optional) your site name for OpenRouter rankings
      - DISABLE_AI_CHAT: (optional) set to "1" to disable AI chat feature
    """
    # Check if AI chat is disabled
    if os.environ.get("DISABLE_AI_CHAT", "").lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=503, detail="AI chat feature is disabled")
    
    payload = await request.json()
    user_message = (payload.get("message") or "").strip()

    # Basic validation
    if not user_message:
        raise HTTPException(status_code=400, detail="Missing 'message' in request body")
    if len(user_message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 characters)")

    # Require authenticated user (student or teacher)
    if not (request.session.get("student_id") or request.session.get("teacher_id")):
        raise HTTPException(status_code=403, detail="Authentication required to use AI chat")

    # Read configuration from environment
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
    site_url = os.environ.get("SITE_URL", "http://localhost:8000")
    site_name = os.environ.get("SITE_NAME", "Learning Platform")

    if not api_key:
        raise HTTPException(status_code=503, detail="OpenRouter API key not configured (OPENROUTER_API_KEY)")

    try:
        from openai import OpenAI, APIError, APIConnectionError, RateLimitError
    except ImportError:
        raise HTTPException(status_code=503, detail="OpenAI SDK not installed. Install it with: pip install openai")

    try:
        # Create OpenAI client configured to use OpenRouter
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        
        # Call OpenRouter API via OpenAI SDK
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=500,
            extra_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_name
            }
        )
        
        # Extract reply from response
        reply = response.choices[0].message.content
        
    except APIConnectionError as e:
        logging.error("Connection error contacting OpenRouter: %s", e)
        raise HTTPException(status_code=503, detail=f"Cannot connect to OpenRouter: {e}")
    except RateLimitError as e:
        logging.error("Rate limit error from OpenRouter: %s", e)
        raise HTTPException(status_code=429, detail="OpenRouter API rate limit exceeded")
    except APIError as e:
        logging.error("OpenRouter API error: %s", e)
        raise HTTPException(status_code=502, detail=f"OpenRouter API error: {e}")
    except Exception as e:
        logging.exception("Unexpected error while calling OpenRouter API: %s", e)
        raise HTTPException(status_code=503, detail=f"AI Chat unavailable: {e}")

    return {"reply": reply}

@app.get("/demo/judge-dashboard", response_class=HTMLResponse)
def demo_judge_dashboard(request: Request):
    """Demo endpoint to preview the judge dashboard wireframe."""
    # Check authentication from judicial login
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/judicial/login", status_code=303)
    
    if request.session.get("user_role") not in ["judge", "admin"]:
        raise HTTPException(status_code=403, detail="Only judges can access this page")
    
    # Fetch simple dynamic data from DB for demo
    db = None
    try:
        db = next(get_db())
        now = datetime.utcnow()
        hearings = db.execute(select(Case).where(Case.next_hearing != None).order_by(Case.next_hearing)).scalars().all()
        assigned = db.execute(select(Case).order_by(Case.next_hearing)).scalars().all()
        teachers = db.execute(select(Teacher)).scalars().all()
    finally:
        if db is not None:
            db.close()

    return templates.TemplateResponse("judge_dashboard.html", {"request": request, "current_hearings": hearings, "assigned_cases": assigned, "teachers": teachers})


@app.get("/demo/case/{case_id}", response_class=HTMLResponse)
def demo_case_card(request: Request, case_id: int):
    """Demo endpoint to preview a case card wireframe."""
    db = None
    case = None
    try:
        db = next(get_db())
        case = db.get(Case, case_id)
    finally:
        if db is not None:
            db.close()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return templates.TemplateResponse("case_card.html", {"request": request, "case": case, "case_id": case_id})


@app.get("/api/cases")
def api_cases(db: Session = Depends(get_db)):
    cases = db.execute(select(Case).order_by(Case.next_hearing)).scalars().all()
    out = []
    for c in cases:
        out.append({
            "id": c.id,
            "case_number": c.case_number,
            "title": c.title,
            "parties": c.parties,
            "next_hearing": c.next_hearing.isoformat() if c.next_hearing else None,
            "is_video": bool(c.is_video),
            "judge": (c.judge.first_name + ' ' + c.judge.last_name) if c.judge else None,
            "status": c.status,
        })
    return {"cases": out}


@app.get("/api/teachers")
def api_teachers(db: Session = Depends(get_db)):
    teachers = db.execute(select(Teacher)).scalars().all()
    return {"teachers": [{"id": t.id, "name": f"{t.first_name} {t.last_name}"} for t in teachers]}



@app.post("/cases/create")
def create_case(request: Request,
                case_number: str = Form(...),
                title: str = Form(...),
                parties: str = Form(None),
                next_hearing: str = Form(None),
                is_video: str = Form(None),
                judge_id: int = Form(None),
                secretary: str = Form(None),
                db: Session = Depends(get_db)):
    """Create a case (simple form handler for demo)."""
    # role check: only judge, secretary, admin can create
    require_roles(request, ["judge", "secretary", "admin"])
    try:
        ch = None
        if next_hearing:
            try:
                ch = datetime.fromisoformat(next_hearing)
            except Exception:
                ch = None

        case = Case(
            case_number=case_number,
            title=title,
            parties=parties or "",
            next_hearing=ch,
            is_video=bool(is_video),
            judge_id=judge_id
        )
        if secretary:
            case.secretary = secretary
        db.add(case)
        db.commit()
        db.refresh(case)
        # if AJAX request return JSON
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"success": True, "id": case.id}
        return RedirectResponse(url=f"/demo/case/{case.id}", status_code=303)
    except Exception as e:
        logging.exception("Failed to create case: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create case")


@app.post("/cases/{case_id}/edit")
def edit_case(request: Request,
              case_id: int,
              title: str = Form(None),
              parties: str = Form(None),
              next_hearing: str = Form(None),
              is_video: str = Form(None),
              judge_id: int = Form(None),
              secretary: str = Form(None),
              status: str = Form(None),
              db: Session = Depends(get_db)):
    # only judge/secretary/admin can edit
    require_roles(request, ["judge", "secretary", "admin"])
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        if title is not None:
            case.title = title
        if parties is not None:
            case.parties = parties
        if status is not None:
            case.status = status
        if next_hearing:
            try:
                case.next_hearing = datetime.fromisoformat(next_hearing)
            except Exception:
                pass
        case.is_video = bool(is_video)
        if judge_id:
            case.judge_id = judge_id
        if secretary is not None:
            case.secretary = secretary
        db.add(case)
        db.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"success": True}
        return RedirectResponse(url=f"/demo/case/{case.id}", status_code=303)
    except Exception as e:
        logging.exception("Failed to edit case: %s", e)
        raise HTTPException(status_code=500, detail="Failed to edit case")

@app.get("/init-data")
def init_sample_data(db: Session = Depends(get_db)):
    """Создание тестовых данных"""
    try:
        # Создаем кафедру
        dept = Department(name="Факультет компьютерных наук")
        db.add(dept)
        db.flush()

        # Создаем преподавателей
        teacher1 = Teacher(
            first_name="Иван",
            last_name="Петров",
            department_id=dept.id,
            email="ivan.petrov@example.org"
        )
        teacher2 = Teacher(
            first_name="Мария",
            last_name="Сидорова",
            department_id=dept.id,
            email="maria.sidorova@example.org"
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
                email="alexey.ivanov@example.org",
                group_id=group1.id,
                enroll_date=datetime.now() - timedelta(days=365)
            ),
            Student(
                first_name="Екатерина",
                last_name="Смирнова",
                email="ekaterina.smirnova@example.org",
                group_id=group1.id,
                enroll_date=datetime.now() - timedelta(days=360)
            ),
            Student(
                first_name="Дмитрий",
                last_name="Кузнецов",
                email="dmitry.kuznetsov@example.org",
                group_id=group1.id,
                enroll_date=datetime.now() - timedelta(days=355)
            ),
            Student(
                first_name="Ольга",
                last_name="Попова",
                email="olga.popova@example.org",
                group_id=group2.id,
                enroll_date=datetime.now() - timedelta(days=730)
            ),
            Student(
                first_name="Сергей",
                last_name="Васильев",
                email="sergey.vasiliev@example.org",
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
        
        # Подготавливаем информацию для вывода
        test_data = {
            "message": "Тестовые данные созданы успешно!",
            "students": [
                {"name": f"{s.first_name} {s.last_name}", "email": s.email}
                for s in students
            ],
            "teachers": [
                {"name": f"{t.first_name} {t.last_name}", "email": t.email}
                for t in [teacher1, teacher2]
            ],
            "teacher_access_code": "teacher123"
        }
        return test_data

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/law-tests", response_class=HTMLResponse)
def law_tests():
    return RedirectResponse(url="/take-test/1", status_code=303)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
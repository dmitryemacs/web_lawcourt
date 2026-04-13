from fastapi import FastAPI, Request, Depends, Form, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, select
import time
import os
import uuid
import uvicorn
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import asyncio

from database import get_db, engine
from models import Base, Employee, Course, Enrollment, Exam, Grade, Subject, Judge, Department, Test, Question, TestResult, Answer, Case, FileAttachment

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

app = FastAPI(title="Судебный законодатель")
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
            print(f"⏳ Waiting for database... (Attempt {i+1}/{max_retries}): {e}")
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

# Директория для загруженных файлов
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Разрешенные типы файлов
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'rtf', 'csv', 'jpg', 'jpeg', 'png', 'gif', 'svg',
    'zip', 'rar', '7z', 'mp4', 'avi', 'mov', 'mp3', 'wav'
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_extension(filename: str) -> str:
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    employees = db.execute(select(Employee)).scalars().all()
    courses = db.execute(select(Course)).scalars().all()
    departments = db.execute(select(Department)).scalars().all()
    return templates.TemplateResponse(request, "employees.html", {
        "employees": employees,
        "courses": courses,
        "departments": departments
    })

@app.post("/employees/add")
def add_employee(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    department_id: int = Form(None),
    db: Session = Depends(get_db)
):
    employee = Employee(
        first_name=first_name,
        last_name=last_name,
        email=email,
        department_id=department_id if department_id else None
    )
    db.add(employee)
    db.commit()
    return RedirectResponse(url='/', status_code=303)

@app.post("/enroll")
def enroll(
    request: Request,
    employee_id: int = Form(...),
    course_id: int = Form(...),
    db: Session = Depends(get_db)
):
    # Проверяем существование сотрудника и курса
    emp = db.get(Employee, employee_id)
    cr = db.get(Course, course_id)

    if not emp or not cr:
        raise HTTPException(status_code=404, detail="Employee or Course not found")

    # Проверяем существующую запись
    exists = db.execute(
        select(Enrollment).where(
            Enrollment.employee_id == employee_id,
            Enrollment.course_id == course_id
        )
    ).scalar_one_or_none()

    if exists:
        return RedirectResponse(url='/', status_code=303)

    enrollment = Enrollment(employee_id=employee_id, course_id=course_id)
    db.add(enrollment)
    db.commit()
    return RedirectResponse(url='/', status_code=303)

@app.get("/transcript/{employee_id}", response_class=HTMLResponse)
def transcript(request: Request, employee_id: int, db: Session = Depends(get_db)):
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Загружаем оценки с связанными данными
    grades = db.execute(
        select(Grade)
        .join(Grade.exam)
        .join(Exam.course)
        .join(Course.subject)
        .where(Grade.employee_id == employee_id)
        .order_by(Grade.graded_at.desc())
    ).scalars().all()

    # Получаем доступные экзамены для сотрудника
    available_exams = []
    if emp.department:
        # Экзамены из курсов отдела
        department_courses = db.execute(
            select(Course)
            .where(Course.department_id == emp.department.id)
        ).scalars().all()

        for course in department_courses:
            course_exams = db.execute(
                select(Exam)
                .where(Exam.course_id == course.id)
            ).scalars().all()
            available_exams.extend(course_exams)

    # Экзамены из курсов, на которые записан сотрудник
    for enrollment in emp.enrollments:
        course_exams = db.execute(
            select(Exam)
            .where(Exam.course_id == enrollment.course_id)
        ).scalars().all()
        available_exams.extend(course_exams)

    # Убираем дубликаты
    unique_exams = {exam.id: exam for exam in available_exams}.values()

    return templates.TemplateResponse(request, "transcript.html", {
        "employee": emp,
        "grades": grades,
        "available_exams": list(unique_exams)
    })

@app.post("/grade")
def grade_assign(
    request: Request,
    exam_id: int = Form(...),
    employee_id: int = Form(...),
    score: float = Form(...),
    db: Session = Depends(get_db)
):
    ex = db.get(Exam, exam_id)
    emp = db.get(Employee, employee_id)

    if not ex or not emp:
        raise HTTPException(status_code=404, detail="Exam or Employee not found")

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
            Grade.employee_id == employee_id
        )
    ).scalar_one_or_none()

    if existing:
        existing.score = score
    else:
        g = Grade(exam_id=exam_id, employee_id=employee_id, score=score)
        db.add(g)

    db.commit()
    return RedirectResponse(url=f"/transcript/{employee_id}", status_code=303)

@app.get("/courses", response_class=HTMLResponse)
def courses_view(request: Request, db: Session = Depends(get_db)):
    courses = db.execute(
        select(Course)
        .join(Course.subject)
        .join(Course.judge, isouter=True)
        .join(Course.department, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    # Get additional data for the form
    subjects = db.execute(select(Subject)).scalars().all()
    judges = db.execute(select(Judge)).scalars().all()
    departments = db.execute(select(Department)).scalars().all()

    return templates.TemplateResponse(request, "courses.html", {
        "courses": courses,
        "subjects": subjects,
        "judges": judges,
        "departments": departments
    })

@app.get("/course/{course_id}", response_class=HTMLResponse)
def course_detail(request: Request, course_id: int, db: Session = Depends(get_db)):
    course = db.execute(
        select(Course)
        .where(Course.id == course_id)
        .join(Course.subject)
        .join(Course.judge, isouter=True)
        .join(Course.department, isouter=True)
    ).scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Получаем экзамены для курса
    exams = db.execute(
        select(Exam)
        .where(Exam.course_id == course_id)
        .order_by(Exam.date)
    ).scalars().all()

    return templates.TemplateResponse(request, "course_detail.html", {
        "course": course,
        "exams": exams
    })

@app.get("/health")
def health_check():
    return {"status": "healthy", "database": "connected"}

@app.get("/departments", response_class=HTMLResponse)
def departments_view(request: Request, db: Session = Depends(get_db)):
    departments = db.execute(
        select(Department)
        .order_by(Department.name)
    ).scalars().all()

    return templates.TemplateResponse(request, "departments.html", {
        "departments": departments
    })

@app.post("/departments/add")
def add_department(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    department = Department(name=name)

    try:
        db.add(department)
        db.commit()
        return RedirectResponse(url='/', status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении отдела: {str(e)}")

@app.post("/courses/add")
def add_course(
    request: Request,
    subject_id: int = Form(...),
    semester: str = Form(...),
    credits: int = Form(...),
    judge_id: int = Form(None),
    department_id: int = Form(None),
    db: Session = Depends(get_db)
):
    course = Course(
        subject_id=subject_id,
        judge_id=judge_id if judge_id else None,
        department_id=department_id if department_id else None,
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

@app.post("/judges/add")
def add_judge(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    db: Session = Depends(get_db)
):
    judge = Judge(
        first_name=first_name,
        last_name=last_name,
        email=email,
        department_id=None  # Can be added later if needed
    )

    try:
        db.add(judge)
        db.commit()
        return RedirectResponse(url='/courses', status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении судьи: {str(e)}")

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

    return templates.TemplateResponse(request, "tests.html", {
        "tests": tests
    })

@app.get("/tests/create", response_class=HTMLResponse)
def create_test_form(request: Request, db: Session = Depends(get_db)):
    """Форма создания теста"""
    judge_id = request.session.get("judge_id")
    if not judge_id:
        add_message(request, "Сначала войдите в систему как судья", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    courses = db.execute(
        select(Course)
        .where(Course.judge_id == judge_id)
        .join(Course.subject)
        .join(Course.department, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    return templates.TemplateResponse(request, "create_test.html", {
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
    judge_id = request.session.get("judge_id")
    if not judge_id:
        add_message(request, "Сначала войдите в систему как судья", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    # Проверяем, что судья действительно ведет этот курс
    course = db.get(Course, course_id)
    if not course or course.judge_id != judge_id:
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
    judge_id = request.session.get("judge_id")
    if not judge_id:
        add_message(request, "Сначала войдите в систему как судья", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    test = db.execute(
        select(Test)
        .where(Test.id == test_id)
        .join(Test.course)
    ).scalar_one_or_none()
    
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Проверяем, что судья действительно ведет этот курс
    if test.course.judge_id != judge_id:
        add_message(request, "Вы не можете редактировать этот тест", "is-danger")
        return RedirectResponse(url='/judge-dashboard', status_code=303)

    questions = db.execute(
        select(Question).where(Question.test_id == test_id).order_by(Question.order)
    ).scalars().all()

    return templates.TemplateResponse(request, "edit_test.html", {
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
    judge_id = request.session.get("judge_id")
    if not judge_id:
        add_message(request, "Сначала войдите в систему как судья", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    test = db.execute(
        select(Test)
        .where(Test.id == test_id)
        .join(Test.course)
    ).scalar_one_or_none()
    
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Проверяем, что судья действительно ведет этот курс
    if test.course.judge_id != judge_id:
        add_message(request, "Вы не можете добавлять вопросы к этому тесту", "is-danger")
        return RedirectResponse(url='/judge-dashboard', status_code=303)

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
        .join(Course.judge, isouter=True)
    ).scalar_one_or_none()

    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    questions = db.execute(
        select(Question).where(Question.test_id == test_id).order_by(Question.order)
    ).scalars().all()

    return templates.TemplateResponse(request, "test_detail.html", {
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

    return templates.TemplateResponse(request, "course_tests.html", {
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

    # Проверяем, может ли сотрудник проходить этот тест
    employee_id = request.session.get("employee_id")
    if not employee_id:
        add_message(request, "Сначала войдите в систему как сотрудник", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Проверяем, записан ли сотрудник на курс
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.employee_id == employee_id)
        .where(Enrollment.course_id == test.course_id)
    ).scalar_one_or_none()

    if not enrollment:
        add_message(request, "Вы не записаны на этот курс", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Проверяем, не проходил ли сотрудник уже этот тест
    existing_result = db.execute(
        select(TestResult)
        .where(TestResult.test_id == test_id)
        .where(TestResult.employee_id == employee_id)
    ).scalar_one_or_none()

    if existing_result:
        add_message(request, "Вы уже проходили этот тест", "is-info")
        return RedirectResponse(url=f'/test-results/{existing_result.id}', status_code=303)

    questions = db.execute(
        select(Question).where(Question.test_id == test_id).order_by(Question.order)
    ).scalars().all()

    return templates.TemplateResponse(request, "take_test.html", {
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
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=403, detail="Access denied")

    test = db.get(Test, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Создаем результат теста
    result = TestResult(
        test_id=test_id,
        employee_id=employee_id,
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
    department_id: int = None,
    access_code: str = None
):
    """Форма регистрации"""
    # Получаем список отделов для выбора
    departments = db.execute(select(Department).order_by(Department.name)).scalars().all()
    
    return templates.TemplateResponse(request, "register.html", {
        "departments": departments,
        "role": role,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "department_id": department_id,
        "access_code": access_code
    })

@app.post("/register")
def register(
    request: Request,
    role: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    department_id: str = Form(None),
    access_code: str = Form(None),
    db: Session = Depends(get_db)
):
    """Регистрация пользователя (сотрудника или судьи)"""
    
    # Проверяем, что email не занят
    existing_employee = db.execute(
        select(Employee).where(Employee.email == email)
    ).scalar_one_or_none()
    
    existing_judge = db.execute(
        select(Judge).where(Judge.email == email)
    ).scalar_one_or_none()
    
    if existing_employee or existing_judge:
        add_message(request, "Пользователь с таким email уже существует", "is-danger")
        return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
    
    if role == "employee":
        # Регистрация сотрудника
        if not department_id or department_id == "":
            add_message(request, "Необходимо выбрать отдел", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
        
        try:
            department_id_int = int(department_id)
        except (ValueError, TypeError):
            add_message(request, "Неверный отдел", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
        
        try:
            employee = Employee(
                first_name=first_name,
                last_name=last_name,
                email=email,
                department_id=department_id_int
            )
            db.add(employee)
            db.commit()
            
            add_message(request, "Регистрация успешна! Теперь вы можете войти в систему", "is-success")
            return RedirectResponse(url='/login', status_code=303)
        except Exception as e:
            db.rollback()
            print(f"Error registering employee: {e}")
            add_message(request, f"Ошибка при регистрации: {str(e)}", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
        
    elif role == "judge":
        # Регистрация судьи
        if not access_code:
            add_message(request, "Необходимо ввести код доступа", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
        
        # Проверяем код доступа (можно настроить более сложную логику)
        if access_code != "judge123":
            add_message(request, "Неверный код доступа", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
        
        try:
            judge = Judge(
                first_name=first_name,
                last_name=last_name,
                email=email,
                department_id=None  # Можно добавить выбор отдела позже
            )
            db.add(judge)
            db.commit()
            
            add_message(request, "Регистрация успешна! Теперь вы можете войти в систему", "is-success")
            return RedirectResponse(url='/judge-login', status_code=303)
        except Exception as e:
            db.rollback()
            print(f"Error registering judge: {e}")
            add_message(request, f"Ошибка при регистрации: {str(e)}", "is-danger")
            return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)
    
    else:
        add_message(request, "Неверный тип аккаунта", "is-danger")
        return RedirectResponse(url=f'/register?role={role}&first_name={first_name}&last_name={last_name}&email={email}&department_id={department_id or ""}&access_code={access_code or ""}', status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    """Форма входа для сотрудников"""
    return templates.TemplateResponse(request, "login.html")

@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    """Вход сотрудника"""
    employee = db.execute(
        select(Employee).where(Employee.email == email)
    ).scalar_one_or_none()

    if not employee:
        add_message(request, "Сотрудник с таким email не найден", "is-danger")
        return RedirectResponse(url='/login', status_code=303)

    # Сохраняем id сотрудника в сессии
    request.session["employee_id"] = employee.id
    request.session["employee_name"] = f"{employee.first_name} {employee.last_name}"
    request.session["user_role"] = "employee"

    add_message(request, f"Добро пожаловать, {employee.first_name}!", "is-success")
    return RedirectResponse(url='/', status_code=303)

@app.get("/logout")
def logout(request: Request):
    """Выход сотрудника"""
    # Удаляем ключи безопасно
    request.session.pop("employee_id", None)
    request.session.pop("employee_name", None)
    request.session.pop("user_role", None)

    add_message(request, "Вы вышли из системы", "is-info")
    return RedirectResponse(url='/', status_code=303)

@app.get("/judge-login", response_class=HTMLResponse)
def judge_login_form(request: Request, db: Session = Depends(get_db)):
    """Форма входа для судей"""
    return templates.TemplateResponse(request, "judge_login.html")

@app.post("/judge-login")
def judge_login(
    request: Request,
    email: str = Form(...),
    access_code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Вход судьи"""
    # Простой код доступа для демонстрации
    if access_code != "judge123":
        add_message(request, "Неверный код доступа", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    judge = db.execute(
        select(Judge).where(Judge.email == email)
    ).scalar_one_or_none()

    if not judge:
        add_message(request, "Судья с таким email не найден", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    # Сохраняем id судьи в сессии
    request.session["judge_id"] = judge.id
    request.session["judge_name"] = f"{judge.first_name} {judge.last_name}"
    request.session["user_role"] = "judge"

    add_message(request, f"Добро пожаловать, {judge.first_name}!", "is-success")
    return RedirectResponse(url='/judge-dashboard', status_code=303)

@app.get("/judge-logout")
def judge_logout(request: Request):
    """Выход судьи"""
    # Удаляем ключи безопасно
    request.session.pop("judge_id", None)
    request.session.pop("judge_name", None)
    request.session.pop("user_role", None)

    add_message(request, "Вы вышли из системы", "is-info")
    return RedirectResponse(url='/', status_code=303)

@app.get("/judge-dashboard", response_class=HTMLResponse)
def judge_dashboard(request: Request, db: Session = Depends(get_db)):
    """Панель судьи"""
    judge_id = request.session.get("judge_id")
    if not judge_id:
        add_message(request, "Сначала войдите в систему как судья", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    # Получаем курсы судьи
    courses = db.execute(
        select(Course)
        .where(Course.judge_id == judge_id)
        .join(Course.subject)
        .join(Course.department, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    return templates.TemplateResponse(request, "judge_dashboard.html", {
        "courses": courses
    })

@app.get("/judge-test-results", response_class=HTMLResponse)
def judge_test_results(request: Request, db: Session = Depends(get_db)):
    """Просмотр результатов тестов судьей"""
    judge_id = request.session.get("judge_id")
    if not judge_id:
        add_message(request, "Сначала войдите в систему как судья", "is-danger")
        return RedirectResponse(url='/judge-login', status_code=303)

    # Получаем курсы судьи
    judge_courses = db.execute(
        select(Course)
        .where(Course.judge_id == judge_id)
        .join(Course.subject)
        .join(Course.department, isouter=True)
        .order_by(Course.semester, Course.id)
    ).scalars().all()

    # Получаем результаты тестов по курсам судьи
    test_results = db.execute(
        select(TestResult)
        .join(TestResult.test)
        .join(Test.course)
        .where(Course.judge_id == judge_id)
        .join(TestResult.employee)
        .order_by(TestResult.completed_at.desc())
        .limit(50)
    ).scalars().all()

    # Считаем статистику
    total_tests = len([t for t in judge_courses for _ in t.tests])
    completed_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r.passed)
    failed_tests = completed_tests - passed_tests

    return templates.TemplateResponse(request, "judge_test_results.html", {
        "courses": judge_courses,
        "test_results": test_results,
        "total_tests": total_tests,
        "completed_tests": completed_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests
    })

def require_judge(request: Request):
    """Декоратор для проверки роли судьи"""
    if request.session.get("user_role") != "judge":
        raise HTTPException(status_code=403, detail="Access denied - judge required")

def require_employee(request: Request):
    """Декоратор для проверки роли сотрудника"""
    if not request.session.get("employee_id"):
        raise HTTPException(status_code=403, detail="Access denied - employee required")


def require_roles(request: Request, allowed: List[str]):
    role = request.session.get("user_role")
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Access denied - insufficient role")


@app.get("/judicial/login", response_class=HTMLResponse)
def judicial_login_page(request: Request):
    """Show role selection/login page for judicial system."""
    return templates.TemplateResponse(request, "login.html")


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
        <title>Судебный законодатель</title>
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

    # Require authenticated user (employee or judge)
    if not (request.session.get("employee_id") or request.session.get("judge_id")):
        raise HTTPException(status_code=403, detail="Authentication required to use AI chat")

    # Read configuration from environment
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
    site_url = os.environ.get("SITE_URL", "http://localhost:8000")
    site_name = os.environ.get("SITE_NAME", "Судебный законодатель")

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
        judges = db.execute(select(Judge)).scalars().all()
    finally:
        if db is not None:
            db.close()

    return templates.TemplateResponse(request, "judge_dashboard.html", {"current_hearings": hearings, "assigned_cases": assigned, "judges": judges})


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

    return templates.TemplateResponse(request, "case_card.html", {"case": case, "case_id": case_id})


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


@app.get("/api/judges")
def api_judges(db: Session = Depends(get_db)):
    judges = db.execute(select(Judge)).scalars().all()
    return {"judges": [{"id": j.id, "name": f"{j.first_name} {j.last_name}"} for j in judges]}



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
        # Создаем отдел
        dept = Department(name="Судебный департамент")
        db.add(dept)
        db.flush()

        # Создаем судей
        judge1 = Judge(
            first_name="Иван",
            last_name="Петров",
            department_id=dept.id,
            email="ivan.petrov@example.org"
        )
        judge2 = Judge(
            first_name="Мария",
            last_name="Сидорова",
            department_id=dept.id,
            email="maria.sidorova@example.org"
        )
        db.add_all([judge1, judge2])
        db.flush()

        # Создаем отделы
        dept1 = Department(
            name="Гражданский отдел"
        )
        dept2 = Department(
            name="Уголовный отдел"
        )
        db.add_all([dept1, dept2])
        db.flush()

        # Создаем предметы
        subjects = [
            Subject(
                code="LAW101",
                title="Гражданское право",
                description="Основы гражданского права"
            ),
            Subject(
                code="LAW102",
                title="Уголовное право",
                description="Изучение уголовного права"
            ),
            Subject(
                code="LAW103",
                title="Конституционное право",
                description="Основы конституционного права"
            )
        ]
        db.add_all(subjects)
        db.flush()

        # Создаем курсы
        courses = [
            Course(
                subject_id=subjects[0].id,
                judge_id=judge1.id,
                department_id=dept1.id,
                semester="Осень 2024",
                credits=3
            ),
            Course(
                subject_id=subjects[1].id,
                judge_id=judge2.id,
                department_id=dept2.id,
                semester="Весна 2025",
                credits=4
            ),
            Course(
                subject_id=subjects[2].id,
                judge_id=judge1.id,
                department_id=dept1.id,
                semester="Осень 2024",
                credits=3
            )
        ]
        db.add_all(courses)
        db.flush()

        # Создаем сотрудников
        employees = [
            Employee(
                first_name="Алексей",
                last_name="Иванов",
                email="alexey.ivanov@example.org",
                department_id=dept1.id,
                hire_date=datetime.now() - timedelta(days=365)
            ),
            Employee(
                first_name="Екатерина",
                last_name="Смирнова",
                email="ekaterina.smirnova@example.org",
                department_id=dept1.id,
                hire_date=datetime.now() - timedelta(days=360)
            ),
            Employee(
                first_name="Дмитрий",
                last_name="Кузнецов",
                email="dmitry.kuznetsov@example.org",
                department_id=dept2.id,
                hire_date=datetime.now() - timedelta(days=355)
            ),
            Employee(
                first_name="Ольга",
                last_name="Попова",
                email="olga.popova@example.org",
                department_id=dept2.id,
                hire_date=datetime.now() - timedelta(days=730)
            ),
            Employee(
                first_name="Сергей",
                last_name="Васильев",
                email="sergey.vasiliev@example.org",
                department_id=dept1.id,
                hire_date=datetime.now() - timedelta(days=725)
            )
        ]
        db.add_all(employees)
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
            Enrollment(employee_id=employees[0].id, course_id=courses[0].id),
            Enrollment(employee_id=employees[0].id, course_id=courses[1].id),
            Enrollment(employee_id=employees[1].id, course_id=courses[0].id),
            Enrollment(employee_id=employees[1].id, course_id=courses[1].id),
            Enrollment(employee_id=employees[2].id, course_id=courses[0].id),
            Enrollment(employee_id=employees[3].id, course_id=courses[2].id),
            Enrollment(employee_id=employees[4].id, course_id=courses[2].id)
        ]
        db.add_all(enrollments)
        db.flush()

        # Создаем оценки
        grades = [
            Grade(exam_id=exams[0].id, employee_id=employees[0].id, score=88),
            Grade(exam_id=exams[0].id, employee_id=employees[1].id, score=92),
            Grade(exam_id=exams[0].id, employee_id=employees[2].id, score=76),
            Grade(exam_id=exams[1].id, employee_id=employees[0].id, score=45),
            Grade(exam_id=exams[1].id, employee_id=employees[1].id, score=48),
            Grade(exam_id=exams[2].id, employee_id=employees[3].id, score=68),
            Grade(exam_id=exams[2].id, employee_id=employees[4].id, score=72)
        ]
        db.add_all(grades)

        db.commit()
        
        # Подготавливаем информацию для вывода
        test_data = {
            "message": "Тестовые данные созданы успешно!",
            "employees": [
                {"name": f"{e.first_name} {e.last_name}", "email": e.email}
                for e in employees
            ],
            "judges": [
                {"name": f"{j.first_name} {j.last_name}", "email": j.email}
                for j in [judge1, judge2]
            ],
            "judge_access_code": "judge123"
        }
        return test_data

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/law-tests", response_class=HTMLResponse)
def law_tests():
    return RedirectResponse(url="/take-test/1", status_code=303)

# ==========================================
# Маршруты для работы с файлами
# ==========================================

def format_file_size(size_bytes: int) -> str:
    """Форматирование размера файла"""
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} КБ"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} МБ"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} ГБ"

@app.post("/upload-file")
async def upload_file(
    request: Request,
    file: UploadFile = FastAPIFile(...),
    entity_type: str = Form(...),  # course, case, test
    entity_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Загрузка файла"""
    # Проверка авторизации
    employee_id = request.session.get("employee_id")
    judge_id = request.session.get("judge_id")
    
    if not employee_id and not judge_id:
        add_message(request, "Необходимо войти в систему", "is-danger")
        return RedirectResponse(url='/login', status_code=303)

    # Проверка имени файла
    if not file.filename or not file.filename.strip():
        add_message(request, "Неверное имя файла", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Проверка расширения
    if not allowed_file(file.filename):
        add_message(request, f"Неподдерживаемый тип файла. Разрешенные: {', '.join(sorted(ALLOWED_EXTENSIONS))}", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Проверка сущности
    if entity_type == "course":
        entity = db.get(Course, entity_id)
        redirect_url = f"/course/{entity_id}"
    elif entity_type == "case":
        entity = db.get(Case, entity_id)
        redirect_url = f"/cases/{entity_id}"
    elif entity_type == "test":
        entity = db.get(Test, entity_id)
        redirect_url = f"/tests/{entity_id}/edit"
    else:
        add_message(request, "Неверный тип сущности", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    if not entity:
        add_message(request, "Сущность не найдена", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Чтение файла и проверка размера
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        add_message(request, f"Файл слишком большой. Максимальный размер: {format_file_size(MAX_FILE_SIZE)}", "is-danger")
        return RedirectResponse(url=redirect_url, status_code=303)

    # Генерация уникального имени файла
    ext = get_file_extension(file.filename)
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    # Сохранение файла
    with open(file_path, "wb") as f:
        f.write(content)

    # Получение имени загрузившего
    uploaded_by = None
    if judge_id:
        judge = db.get(Judge, judge_id)
        uploaded_by = f"{judge.first_name} {judge.last_name}" if judge else None
    elif employee_id:
        employee = db.get(Employee, employee_id)
        uploaded_by = f"{employee.first_name} {employee.last_name}" if employee else None

    # Создание записи в БД
    attachment = FileAttachment(
        filename=file.filename,
        stored_filename=stored_filename,
        file_type=ext,
        file_size=len(content),
        course_id=entity_id if entity_type == "course" else None,
        case_id=entity_id if entity_type == "case" else None,
        test_id=entity_id if entity_type == "test" else None,
        uploaded_by=uploaded_by
    )
    db.add(attachment)
    db.commit()

    add_message(request, f"Файл '{file.filename}' успешно загружен", "is-success")
    return RedirectResponse(url=redirect_url, status_code=303)

@app.get("/download-file/{file_id}")
def download_file(file_id: int, db: Session = Depends(get_db)):
    """Скачивание файла"""
    attachment = db.get(FileAttachment, file_id)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Файл не найден")

    file_path = os.path.join(UPLOAD_DIR, attachment.stored_filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")

    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type="application/octet-stream"
    )

@app.post("/delete-file/{file_id}")
def delete_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db)
):
    """Удаление файла"""
    # Проверка авторизации
    employee_id = request.session.get("employee_id")
    judge_id = request.session.get("judge_id")
    
    if not employee_id and not judge_id:
        add_message(request, "Необходимо войти в систему", "is-danger")
        return RedirectResponse(url='/login', status_code=303)

    attachment = db.get(FileAttachment, file_id)
    
    if not attachment:
        add_message(request, "Файл не найден", "is-danger")
        return RedirectResponse(url='/', status_code=303)

    # Определение URL для редиректа
    if attachment.course_id:
        redirect_url = f"/course/{attachment.course_id}"
    elif attachment.case_id:
        redirect_url = f"/cases/{attachment.case_id}"
    elif attachment.test_id:
        redirect_url = f"/tests/{attachment.test_id}/edit"
    else:
        redirect_url = '/'

    # Удаление файла с диска
    file_path = os.path.join(UPLOAD_DIR, attachment.stored_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Удаление записи из БД
    db.delete(attachment)
    db.commit()

    add_message(request, f"Файл '{attachment.filename}' удален", "is-info")
    return RedirectResponse(url=redirect_url, status_code=303)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
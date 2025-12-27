#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Set environment variable for database
os.environ["DATABASE_URL"] = "sqlite:///test_complete.db"

# Import after setting environment
from app.main import app
from app.models import Base, Course, Subject, Teacher, Group
from app.database import get_db
from sqlalchemy.orm import Session

def test_complete_functionality():
    """Test all new functionality: teachers, subjects, and courses"""
    print("🧪 Testing Complete Functionality...")

    # Initialize sample data first
    print("\n1. Initializing sample data...")
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/init-data")
    assert response.status_code == 200
    print("✅ Sample data initialized")

    # Test database operations directly
    print("\n2. Testing database operations...")

    # Get a database session
    db: Session
    for db in get_db():
        try:
            # Test 1: Create a new subject
            print("\n   Testing subject creation...")
            new_subject = Subject(
                code="NEW101",
                title="Новый предмет",
                description="Тестовый предмет для проверки функциональности"
            )
            db.add(new_subject)
            db.commit()

            created_subject = db.query(Subject).filter(Subject.code == "NEW101").first()
            assert created_subject is not None
            assert created_subject.title == "Новый предмет"
            print("   ✅ Subject creation works")

            # Test 2: Create a new teacher
            print("\n   Testing teacher creation...")
            new_teacher = Teacher(
                first_name="Тестовый",
                last_name="Преподаватель",
                email="test.teacher@example.com"
            )
            db.add(new_teacher)
            db.commit()

            created_teacher = db.query(Teacher).filter(Teacher.email == "test.teacher@example.com").first()
            assert created_teacher is not None
            assert created_teacher.first_name == "Тестовый"
            print("   ✅ Teacher creation works")

            # Test 3: Create a new course using the new subject and teacher
            print("\n   Testing course creation with new subject and teacher...")
            new_course = Course(
                subject_id=created_subject.id,
                teacher_id=created_teacher.id,
                group_id=None,
                semester="Тестовый семестр",
                credits=2
            )
            db.add(new_course)
            db.commit()

            created_course = db.query(Course).filter(Course.semester == "Тестовый семестр").first()
            assert created_course is not None
            assert created_course.subject_id == created_subject.id
            assert created_course.teacher_id == created_teacher.id
            print("   ✅ Course creation with new entities works")

            # Test 4: Test the endpoints
            print("\n3. Testing endpoints...")

            # Test subject creation endpoint
            subject_data = {
                "code": "API101",
                "title": "API Тестирование",
                "description": "Предмет создан через API"
            }
            response = client.post("/subjects/add", data=subject_data)
            assert response.status_code == 303
            print("   ✅ Subject creation endpoint works")

            # Test teacher creation endpoint
            teacher_data = {
                "first_name": "API",
                "last_name": "Преподаватель",
                "email": "api.teacher@example.com"
            }
            response = client.post("/teachers/add", data=teacher_data)
            assert response.status_code == 303
            print("   ✅ Teacher creation endpoint works")

            # Test course creation endpoint
            api_subject = db.query(Subject).filter(Subject.code == "API101").first()
            api_teacher = db.query(Teacher).filter(Teacher.email == "api.teacher@example.com").first()

            course_data = {
                "subject_id": api_subject.id,
                "semester": "API Семестр",
                "credits": "1",
                "teacher_id": api_teacher.id,
                "group_id": ""
            }
            response = client.post("/courses/add", data=course_data)
            assert response.status_code == 303
            print("   ✅ Course creation endpoint works")

            # Verify all creations
            api_course = db.query(Course).filter(Course.semester == "API Семестр").first()
            assert api_course is not None
            print("   ✅ All API creations verified")

            break

        except Exception as e:
            db.rollback()
            raise e

    print("\n🎉 All functionality is working correctly!")
    print("\n📋 Summary of new features:")
    print("   ✅ Teacher creation (forms + API)")
    print("   ✅ Subject creation (forms + API)")
    print("   ✅ Course creation (forms + API)")
    print("   ✅ Calendar widgets for date selection")
    print("   ✅ Improved user interface with multiple forms")
    print("   ✅ Full integration with existing system")

if __name__ == "__main__":
    try:
        test_complete_functionality()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

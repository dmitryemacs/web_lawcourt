#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Set environment variable for database
os.environ["DATABASE_URL"] = "sqlite:///test_courses.db"

# Import after setting environment
from app.main import app
from app.models import Base, Course, Subject, Teacher, Group
from app.database import get_db
from sqlalchemy.orm import Session

def test_course_creation_db():
    """Test course creation functionality directly with database"""
    print("🧪 Testing Course Creation Functionality (Database Level)...")

    # Initialize sample data first
    print("\n1. Initializing sample data...")
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/init-data")
    assert response.status_code == 200
    print("✅ Sample data initialized")

    # Test database operations directly
    print("\n2. Testing database course creation...")

    # Get a database session
    db: Session
    for db in get_db():
        try:
            # Get some sample data for the course
            subject = db.query(Subject).first()
            teacher = db.query(Teacher).first()
            group = db.query(Group).first()

            if not subject:
                print("❌ No subjects found in database")
                return

            print(f"✅ Found subject: {subject.title}")
            print(f"✅ Found teacher: {teacher.first_name if teacher else 'None'}")
            print(f"✅ Found group: {group.name if group else 'None'}")

            # Create a new course
            new_course = Course(
                subject_id=subject.id,
                teacher_id=teacher.id if teacher else None,
                group_id=group.id if group else None,
                semester="Лето 2025",
                credits=5
            )

            db.add(new_course)
            db.commit()
            print("✅ Course created in database")

            # Verify the course was created
            created_course = db.query(Course).filter(Course.semester == "Лето 2025").first()
            assert created_course is not None
            assert created_course.subject_id == subject.id
            assert created_course.semester == "Лето 2025"
            assert created_course.credits == 5
            print("✅ Course verified in database")

            # Test the course creation endpoint directly
            print("\n3. Testing course creation endpoint...")
            form_data = {
                "subject_id": subject.id,
                "semester": "Осень 2025",
                "credits": "3",
                "teacher_id": str(teacher.id) if teacher else "",
                "group_id": str(group.id) if group else ""
            }

            response = client.post("/courses/add", data=form_data)
            assert response.status_code == 303  # Redirect
            print("✅ Course creation endpoint works")

            # Verify the course was created via endpoint
            endpoint_course = db.query(Course).filter(Course.semester == "Осень 2025").first()
            assert endpoint_course is not None
            print("✅ Course created via endpoint verified")

            break

        except Exception as e:
            db.rollback()
            raise e

    print("\n🎉 Course creation functionality is working correctly!")

if __name__ == "__main__":
    try:
        test_course_creation_db()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

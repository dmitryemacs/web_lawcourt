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
from app.models import Base
from fastapi.testclient import TestClient

def test_course_creation():
    """Test course creation functionality"""
    print("🧪 Testing Course Creation Functionality...")

    # Create test client
    client = TestClient(app)

    # Initialize sample data first
    print("\n1. Initializing sample data...")
    response = client.get("/init-data")
    assert response.status_code == 200
    print("✅ Sample data initialized")

    # Test 1: Get courses page to see the form
    print("\n2. Testing courses page with form...")
    response = client.get("/courses")
    assert response.status_code == 200
    assert "Добавить курс" in response.text
    assert "subject_id" in response.text  # Form field
    print("✅ Courses page with form loads successfully")

    # Test 2: Create a new course
    print("\n3. Testing course creation...")
    # First, get the page to see what subjects/teachers/groups are available
    response = client.get("/courses")
    html_content = response.text

    # Extract subject, teacher, and group IDs from the form
    import re
    subject_ids = re.findall(r'<option value="(\d+)">.*?</option>', html_content)
    if subject_ids:
        subject_id = subject_ids[0]
        teacher_id = subject_ids[1] if len(subject_ids) > 1 else ""
        group_id = subject_ids[2] if len(subject_ids) > 2 else ""

        # Create course form data
        form_data = {
            "subject_id": subject_id,
            "semester": "Весна 2025",
            "credits": "4",
            "teacher_id": teacher_id,
            "group_id": group_id
        }

        response = client.post("/courses/add", data=form_data)
        assert response.status_code == 303  # Redirect
        print("✅ Course creation form submitted successfully")

        # Check if course was created
        response = client.get("/courses")
        assert response.status_code == 200
        assert "Весна 2025" in response.text
        print("✅ New course appears in the courses list")

    print("\n🎉 Course creation functionality is working correctly!")

if __name__ == "__main__":
    try:
        test_course_creation()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

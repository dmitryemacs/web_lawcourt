#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Set environment variable for database
os.environ["DATABASE_URL"] = "sqlite:///test.db"

# Import after setting environment
from app.main import app
from app.models import Base
from fastapi.testclient import TestClient

def test_basic_functionality():
    """Test basic application functionality"""
    print("🧪 Testing University Application...")

    # Create test client
    client = TestClient(app)

    # Test 1: Health check
    print("\n1. Testing health check endpoint...")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✅ Health check passed")

    # Test 2: Initialize sample data
    print("\n2. Testing sample data initialization...")
    response = client.get("/init-data")
    assert response.status_code == 200
    data = response.json()
    print(f"✅ Sample data initialization: {data['message']}")

    # Test 3: Test database connectivity
    print("\n3. Testing database connectivity...")
    from app.database import get_db
    from sqlalchemy.orm import Session

    # Create a test database session
    db: Session
    for db in get_db():
        # Test if we can query students
        from app.models import Student
        students = db.query(Student).all()
        print(f"✅ Found {len(students)} students in database")
        break

    print("\n🎉 Basic tests passed! The application core is working correctly.")

if __name__ == "__main__":
    try:
        test_basic_functionality()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

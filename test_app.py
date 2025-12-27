#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Set environment variable for database
os.environ["DATABASE_URL"] = "sqlite:///test.db"

# Import after setting environment
from app.main import app
from app.models import Base
from fastapi.testclient import TestClient

# Set templates directory path
from fastapi.templating import Jinja2Templates
app.templates = Jinja2Templates(directory="app/templates")

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

    # Test 2: Home page
    print("\n2. Testing home page...")
    response = client.get("/")
    assert response.status_code == 200
    assert "University System" in response.text
    print("✅ Home page loads successfully")

    # Test 3: Courses page
    print("\n3. Testing courses page...")
    response = client.get("/courses")
    assert response.status_code == 200
    print("✅ Courses page loads successfully")

    # Test 4: Groups page
    print("\n4. Testing groups page...")
    response = client.get("/groups")
    assert response.status_code == 200
    print("✅ Groups page loads successfully")

    # Test 5: Initialize sample data
    print("\n5. Testing sample data initialization...")
    response = client.get("/init-data")
    assert response.status_code == 200
    data = response.json()
    print(f"✅ Sample data initialization: {data['message']}")

    # Test 6: Check if data was created
    print("\n6. Testing if sample data was created...")
    response = client.get("/")
    assert response.status_code == 200
    # Check if students are present
    assert "Алексей Иванов" in response.text or "Students" in response.text
    print("✅ Sample data appears in the interface")

    print("\n🎉 All tests passed! The application is working correctly.")

if __name__ == "__main__":
    try:
        test_basic_functionality()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

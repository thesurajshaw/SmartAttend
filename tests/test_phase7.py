"""Tests for Phase 7: Analytics, Notifications, Exports."""
import pytest
from app import create_app
from app.extensions import db
from app.models import (
    User, Department, Student, Faculty, Subject, ClassSection,
    Enrollment, AttendanceSession, AttendanceRecord, Setting, Notification
)
from app.services.attendance_service import get_attendance_metrics, get_student_statuses, get_weekly_percentages
from app.services.prediction_service import get_status, get_classes_needed, get_classes_can_miss, detect_declining_trend
from werkzeug.security import generate_password_hash
from datetime import date, time, datetime


@pytest.fixture
def app():
    """Create a test app with an in-memory SQLite database."""
    class TestConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
        SECRET_KEY = 'test-secret'
        WTF_CSRF_ENABLED = False

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded_app(app):
    """Seed minimal data for integration tests."""
    with app.app_context():
        # Settings
        db.session.add(Setting(key='required_attendance_percent', value='0.75'))
        db.session.add(Setting(key='warning_band_percent', value='0.05'))
        db.session.add(Setting(key='session_lock_hours', value='24'))

        # Department
        dept = Department(name='CS', code='CSE')
        db.session.add(dept)
        db.session.flush()

        # Subject
        subj = Subject(code='CS101', name='Data Structures', department_id=dept.id,
                        semester=3, credits=4, subject_type='theory')
        db.session.add(subj)
        db.session.flush()

        # Faculty
        fac_user = User(email='fac@test.edu', password_hash=generate_password_hash('pass'),
                         full_name='Test Faculty', role='faculty', must_change_password=False)
        db.session.add(fac_user)
        db.session.flush()
        fac = Faculty(user_id=fac_user.id, employee_id='F001', department_id=dept.id,
                       designation='AP', joining_date=date(2020, 1, 1))
        db.session.add(fac)
        db.session.flush()

        # Class Section
        cs = ClassSection(subject_id=subj.id, faculty_id=fac.id,
                           section='A', semester=3, academic_year='2026-2027')
        db.session.add(cs)
        db.session.flush()

        # Student
        stu_user = User(email='stu@test.edu', password_hash=generate_password_hash('pass'),
                         full_name='Test Student', role='student', must_change_password=False)
        db.session.add(stu_user)
        db.session.flush()
        stu = Student(user_id=stu_user.id, roll_no='R001', department_id=dept.id,
                       semester=3, section='A', admission_year=2025)
        db.session.add(stu)
        db.session.flush()

        # Enrollment
        db.session.add(Enrollment(student_id=stu.id, class_section_id=cs.id))
        db.session.flush()

        # Create 10 sessions: 7 present, 3 absent => 70% => Critical
        for i in range(10):
            sess = AttendanceSession(
                class_section_id=cs.id,
                session_date=date(2026, 8, 1 + i),
                start_time=time(10, 0),
                end_time=time(11, 0),
                status='locked',
                created_by=fac_user.id
            )
            db.session.add(sess)
            db.session.flush()

            status = 'present' if i < 7 else 'absent'
            db.session.add(AttendanceRecord(
                session_id=sess.id,
                student_id=stu.id,
                status=status,
                marked_by=fac_user.id
            ))

        db.session.commit()
        yield app


def test_get_attendance_metrics_unchanged():
    """Ensure Phase 2 function is intact."""
    records = ['present', 'present', 'absent', 'late', 'excused', 'absent']
    A, C = get_attendance_metrics(records)
    assert A == 3
    assert C == 5


def test_get_student_statuses_from_db(seeded_app):
    """Test that DB queries return correct status list."""
    with seeded_app.app_context():
        stu = Student.query.first()
        cs = ClassSection.query.first()
        statuses = get_student_statuses(stu.id, cs.id)
        assert len(statuses) == 10
        assert statuses.count('present') == 7
        assert statuses.count('absent') == 3


def test_metrics_from_db_feed_prediction(seeded_app):
    """Test full pipeline: DB -> attendance_service -> prediction_service."""
    with seeded_app.app_context():
        stu = Student.query.first()
        cs = ClassSection.query.first()

        statuses = get_student_statuses(stu.id, cs.id)
        A, C = get_attendance_metrics(statuses)
        assert A == 7
        assert C == 10

        status = get_status(A, C, 0.75, 0.05)
        assert status == 'Critical'

        needed = get_classes_needed(A, C, 0.75)
        assert needed == 2  # (7+2)/(10+2) = 9/12 = 0.75

        can_miss = get_classes_can_miss(A, C, 0.75)
        assert can_miss == 0


def test_zero_attendance_edge_case(seeded_app):
    """Test student with no attendance records."""
    with seeded_app.app_context():
        # Create a second student with no records
        dept = Department.query.first()
        cs = ClassSection.query.first()

        u2 = User(email='empty@test.edu', password_hash=generate_password_hash('pass'),
                    full_name='Empty Student', role='student', must_change_password=False)
        db.session.add(u2)
        db.session.flush()
        s2 = Student(user_id=u2.id, roll_no='R999', department_id=dept.id,
                      semester=3, section='A', admission_year=2025)
        db.session.add(s2)
        db.session.flush()
        db.session.add(Enrollment(student_id=s2.id, class_section_id=cs.id))
        db.session.commit()

        statuses = get_student_statuses(s2.id, cs.id)
        assert statuses == []

        A, C = get_attendance_metrics(statuses)
        assert A == 0
        assert C == 0

        status = get_status(A, C, 0.75, 0.05)
        assert status == 'Safe'  # C=0 returns Safe

        needed = get_classes_needed(A, C, 0.75)
        assert needed == 0


def test_notification_creation(seeded_app):
    """Test that alert notifications are created for critical students."""
    with seeded_app.app_context():
        stu = Student.query.first()
        user = stu.user

        # Before: no notifications
        assert Notification.query.filter_by(user_id=user.id).count() == 0

        # Import and call the alert logic
        from app.blueprints.student.routes import _check_alerts
        subjects_data = [{
            'subject_code': 'CS101',
            'subject_name': 'Data Structures',
            'percentage': 70.0,
            'status': 'Critical',
            'needed': 2,
            'declining': False,
        }]
        _check_alerts(stu, subjects_data, 0.75)

        # After: one critical notification created
        notes = Notification.query.filter_by(user_id=user.id).all()
        assert len(notes) == 1
        assert notes[0].type == 'critical'
        assert 'CS101' in notes[0].title

        # Calling again should NOT create a duplicate (idempotent)
        _check_alerts(stu, subjects_data, 0.75)
        assert Notification.query.filter_by(user_id=user.id).count() == 1


def test_notification_idempotent_after_read(seeded_app):
    """After marking as read, a new notification CAN be created."""
    with seeded_app.app_context():
        stu = Student.query.first()
        from app.blueprints.student.routes import _check_alerts

        subjects_data = [{
            'subject_code': 'CS101',
            'subject_name': 'Data Structures',
            'percentage': 70.0,
            'status': 'Critical',
            'needed': 2,
            'declining': False,
        }]
        _check_alerts(stu, subjects_data, 0.75)
        assert Notification.query.filter_by(user_id=stu.user_id).count() == 1

        # Mark as read
        n = Notification.query.first()
        n.is_read = True
        db.session.commit()

        # Now a new one should be created
        _check_alerts(stu, subjects_data, 0.75)
        assert Notification.query.filter_by(user_id=stu.user_id).count() == 2


def test_csv_export_student(seeded_app, client):
    """Test student CSV export endpoint."""
    with seeded_app.app_context():
        # Login as student
        client.post('/login', data={'email': 'stu@test.edu', 'password': 'pass'})
        response = client.get('/student/export')
        assert response.status_code == 200
        assert response.content_type == 'text/csv; charset=utf-8'
        csv_data = response.data.decode()
        assert 'CS101' in csv_data
        assert 'Data Structures' in csv_data
        assert '70.0' in csv_data  # 7/10 = 70%


def test_csv_export_faculty(seeded_app, client):
    """Test faculty CSV export endpoint."""
    with seeded_app.app_context():
        cs = ClassSection.query.first()
        # Login as faculty
        client.post('/login', data={'email': 'fac@test.edu', 'password': 'pass'})
        response = client.get(f'/faculty/sections/{cs.id}/export')
        assert response.status_code == 200
        assert response.content_type == 'text/csv; charset=utf-8'
        csv_data = response.data.decode()
        assert 'R001' in csv_data
        assert 'Test Student' in csv_data


def test_weekly_percentages_empty(seeded_app):
    """Test weekly percentages with no data."""
    with seeded_app.app_context():
        dept = Department.query.first()
        cs = ClassSection.query.first()

        u = User(email='new@test.edu', password_hash=generate_password_hash('pass'),
                  full_name='New', role='student', must_change_password=False)
        db.session.add(u)
        db.session.flush()
        s = Student(user_id=u.id, roll_no='R888', department_id=dept.id,
                     semester=3, section='A', admission_year=2025)
        db.session.add(s)
        db.session.flush()
        db.session.add(Enrollment(student_id=s.id, class_section_id=cs.id))
        db.session.commit()

        weekly = get_weekly_percentages(s.id, cs.id)
        assert weekly == []
        assert detect_declining_trend(weekly) is False

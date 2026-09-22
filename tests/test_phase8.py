"""Tests for Phase 8: Correction Request Workflow and Audit Logs."""
import pytest
from app import create_app
from app.extensions import db
from app.models import (
    User, Department, Student, Faculty, Subject, ClassSection,
    Enrollment, AttendanceSession, AttendanceRecord, Setting,
    CorrectionRequest, AuditLog
)
from werkzeug.security import generate_password_hash
from datetime import date, time, datetime


@pytest.fixture
def app():
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
    with app.app_context():
        # Settings
        db.session.add(Setting(key='session_lock_hours', value='24'))

        # Admin
        admin_user = User(email='admin@test.edu', password_hash=generate_password_hash('pass'),
                          full_name='Test Admin', role='admin', must_change_password=False)
        db.session.add(admin_user)
        db.session.flush()

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

        db.session.add(Enrollment(student_id=stu.id, class_section_id=cs.id))
        db.session.flush()

        # Create a locked session
        sess = AttendanceSession(
            class_section_id=cs.id,
            session_date=date(2026, 8, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            status='locked',
            created_by=fac_user.id
        )
        db.session.add(sess)
        db.session.flush()

        record = AttendanceRecord(
            session_id=sess.id,
            student_id=stu.id,
            status='absent',
            marked_by=fac_user.id
        )
        db.session.add(record)
        db.session.flush()

        # Add a correction request (absent -> present)
        req = CorrectionRequest(
            attendance_record_id=record.id,
            requested_by=fac_user.id,
            old_status='absent',
            new_status='present',
            reason='Marked absent by mistake.'
        )
        db.session.add(req)
        
        # Add a dummy audit log for the original mark
        log = AuditLog(
            actor_user_id=fac_user.id,
            action='INSERT_ATTENDANCE',
            entity_type='AttendanceRecord',
            entity_id=record.id,
            old_value=None,
            new_value={'status': 'absent'},
            ip_address='127.0.0.1'
        )
        db.session.add(log)
        
        db.session.commit()
        yield app


def test_admin_corrections_view(seeded_app, client):
    """Test the admin corrections list page."""
    with seeded_app.app_context():
        client.post('/login', data={'email': 'admin@test.edu', 'password': 'pass'})
        response = client.get('/admin/corrections')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'Correction Requests' in html
        assert 'Marked absent by mistake.' in html
        assert 'Approve' in html
        assert 'Reject' in html


def test_admin_approve_correction(seeded_app, client):
    """Test approving a correction request."""
    with seeded_app.app_context():
        req = CorrectionRequest.query.first()
        record_id = req.attendance_record_id
        
        client.post('/login', data={'email': 'admin@test.edu', 'password': 'pass'})
        response = client.post(f'/admin/corrections/{req.id}/approve', data={'review_note': 'Looks good'})
        assert response.status_code == 302
        
        # Verify changes
        req = CorrectionRequest.query.get(req.id)
        assert req.status == 'approved'
        assert req.review_note == 'Looks good'
        
        record = AttendanceRecord.query.get(record_id)
        assert record.status == 'present'
        
        # Verify audit log was created
        log = AuditLog.query.filter_by(action='APPROVE_CORRECTION').first()
        assert log is not None
        assert log.entity_id == record.id
        assert log.old_value['status'] == 'absent'
        assert log.new_value['status'] == 'present'


def test_admin_reject_correction(seeded_app, client):
    """Test rejecting a correction request."""
    with seeded_app.app_context():
        req = CorrectionRequest.query.first()
        record_id = req.attendance_record_id
        
        client.post('/login', data={'email': 'admin@test.edu', 'password': 'pass'})
        response = client.post(f'/admin/corrections/{req.id}/reject', data={'review_note': 'No proof'})
        assert response.status_code == 302
        
        # Verify changes
        req = CorrectionRequest.query.get(req.id)
        assert req.status == 'rejected'
        assert req.review_note == 'No proof'
        
        record = AttendanceRecord.query.get(record_id)
        assert record.status == 'absent'  # Unchanged
        
        # No new audit log for approval
        log = AuditLog.query.filter_by(action='APPROVE_CORRECTION').first()
        assert log is None


def test_admin_audit_logs_view(seeded_app, client):
    """Test the admin audit logs page."""
    with seeded_app.app_context():
        client.post('/login', data={'email': 'admin@test.edu', 'password': 'pass'})
        response = client.get('/admin/audit-logs')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'Audit Logs' in html
        assert 'INSERT_ATTENDANCE' in html
        assert 'Test Faculty' in html

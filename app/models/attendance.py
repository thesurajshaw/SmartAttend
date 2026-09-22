from datetime import datetime
from ..extensions import db


class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'
    __table_args__ = (db.UniqueConstraint('class_section_id', 'session_date', 'start_time', name='uix_section_date_time'),)

    id = db.Column(db.Integer, primary_key=True)
    class_section_id = db.Column(db.Integer, db.ForeignKey('class_sections.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    topic = db.Column(db.String(255), nullable=True)
    status = db.Column(db.Enum('open', 'locked', 'cancelled', name='session_statuses'), default='open', nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    records = db.relationship('AttendanceRecord', backref='session', lazy=True)


class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    __table_args__ = (db.UniqueConstraint('session_id', 'student_id', name='uix_session_student'),)

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    status = db.Column(db.Enum('present', 'absent', 'late', 'excused', name='attendance_statuses'), nullable=False)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    remarks = db.Column(db.String(255), nullable=True)

    student = db.relationship('Student', backref='attendance_records', lazy=True)


class CorrectionRequest(db.Model):
    __tablename__ = 'correction_requests'

    id = db.Column(db.Integer, primary_key=True)
    attendance_record_id = db.Column(db.Integer, db.ForeignKey('attendance_records.id'), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    old_status = db.Column(db.String(10), nullable=False)
    new_status = db.Column(db.String(10), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum('pending', 'approved', 'rejected', name='correction_statuses'), default='pending', nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.String(255), nullable=True)

    record = db.relationship('AttendanceRecord', backref='correction_requests', lazy=True)
    requester = db.relationship('User', foreign_keys=[requested_by], backref='correction_requests_made', lazy=True)
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], backref='corrections_reviewed', lazy=True)

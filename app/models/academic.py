from datetime import datetime
from ..extensions import db


class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    students = db.relationship('Student', backref='department', lazy=True)
    faculty_members = db.relationship('Faculty', backref='department', lazy=True)
    subjects = db.relationship('Subject', backref='department', lazy=True)


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    batch = db.Column(db.String(10), nullable=True)
    admission_year = db.Column(db.Integer, nullable=False)
    guardian_phone = db.Column(db.String(20), nullable=True)
    guardian_email = db.Column(db.String(120), nullable=True)

    user = db.relationship('User', back_populates='student_profile', lazy=True)
    enrollments = db.relationship('Enrollment', backref='student', lazy=True)


class Faculty(db.Model):
    __tablename__ = 'faculty'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    joining_date = db.Column(db.Date, nullable=False)

    user = db.relationship('User', back_populates='faculty_profile', lazy=True)
    class_sections = db.relationship('ClassSection', backref='faculty', lazy=True)


class Subject(db.Model):
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    subject_type = db.Column(db.Enum('theory', 'lab', name='subject_types'), nullable=False)

    class_sections = db.relationship('ClassSection', backref='subject', lazy=True)


class ClassSection(db.Model):
    __tablename__ = 'class_sections'
    __table_args__ = (db.UniqueConstraint('subject_id', 'section', 'academic_year', name='uix_subject_section_year'),)

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)

    enrollments = db.relationship('Enrollment', backref='class_section', lazy=True)
    timetables = db.relationship('Timetable', backref='class_section', lazy=True)
    sessions = db.relationship('AttendanceSession', backref='class_section', lazy=True)


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    __table_args__ = (db.UniqueConstraint('student_id', 'class_section_id', name='uix_student_class_section'),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_section_id = db.Column(db.Integer, db.ForeignKey('class_sections.id'), nullable=False)


class Timetable(db.Model):
    __tablename__ = 'timetable'

    id = db.Column(db.Integer, primary_key=True)
    class_section_id = db.Column(db.Integer, db.ForeignKey('class_sections.id'), nullable=False)
    day_of_week = db.Column(db.SmallInteger, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(50), nullable=False)

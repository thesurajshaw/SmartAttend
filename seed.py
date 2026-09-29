import random
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import (
    User, Department, Student, Faculty, Subject, ClassSection,
    Enrollment, Timetable, AttendanceSession, AttendanceRecord, Setting
)


def seed_data():
    app = create_app()
    with app.app_context():
        # Clear and recreate all tables
        db.drop_all()
        db.create_all()

        print("Seeding Settings...")
        settings = [
            Setting(key='required_attendance_percent', value='0.75'),
            Setting(key='warning_band_percent', value='0.05'),
            Setting(key='session_lock_hours', value='24'),
            Setting(key='institution_name', value='Smart College of Engineering'),
        ]
        db.session.add_all(settings)

        print("Seeding Departments...")
        dept_cs = Department(name='Computer Science', code='CSE')
        dept_ee = Department(name='Electronics', code='ECE')
        db.session.add_all([dept_cs, dept_ee])
        db.session.commit()

        print("Seeding Subjects...")
        subjs = [
            Subject(code='CS101', name='Data Structures', department_id=dept_cs.id, semester=3, credits=4, subject_type='theory'),
            Subject(code='CS102', name='Discrete Mathematics', department_id=dept_cs.id, semester=3, credits=3, subject_type='theory'),
            Subject(code='CS103', name='Algorithms Lab', department_id=dept_cs.id, semester=3, credits=2, subject_type='lab'),
            Subject(code='EE101', name='Signals & Systems', department_id=dept_ee.id, semester=3, credits=4, subject_type='theory'),
            Subject(code='EE102', name='Analog Circuits', department_id=dept_ee.id, semester=3, credits=4, subject_type='theory'),
            Subject(code='EE103', name='Circuits Lab', department_id=dept_ee.id, semester=3, credits=2, subject_type='lab'),
        ]
        db.session.add_all(subjs)
        db.session.commit()

        print("Seeding Users & Faculty...")
        admin_user = User(email='admin@smart.edu', password_hash=generate_password_hash('password'),
                          full_name='System Admin', role='admin', must_change_password=False)
        db.session.add(admin_user)

        faculties = []
        for i in range(1, 6):
            dept_id = dept_cs.id if i <= 3 else dept_ee.id
            u = User(email=f'faculty{i}@smart.edu', password_hash=generate_password_hash('password'),
                     full_name=f'Faculty {i}', role='faculty', must_change_password=False)
            db.session.add(u)
            db.session.flush()
            f = Faculty(user_id=u.id, employee_id=f'F{100 + i}', department_id=dept_id,
                        designation='Assistant Professor', joining_date=date(2020, 8, 1))
            faculties.append(f)
            db.session.add(f)

        db.session.commit()

        print("Seeding Users & Students...")
        students = []
        for i in range(1, 41):
            dept_id = dept_cs.id if i <= 25 else dept_ee.id
            u = User(email=f'student{i}@smart.edu', password_hash=generate_password_hash('password'),
                     full_name=f'Student {i}', role='student', must_change_password=False)
            db.session.add(u)
            db.session.flush()
            s = Student(user_id=u.id, roll_no=f'R{1000 + i}', department_id=dept_id,
                        semester=3, section='A', admission_year=2025)
            students.append(s)
            db.session.add(s)

        db.session.commit()

        print("Seeding Class Sections & Enrollments...")
        cs_sec_a = ClassSection(subject_id=subjs[0].id, faculty_id=faculties[0].id,
                                section='A', semester=3, academic_year='2026-2027')
        cs_sec_b = ClassSection(subject_id=subjs[1].id, faculty_id=faculties[1].id,
                                section='A', semester=3, academic_year='2026-2027')
        ee_sec_a = ClassSection(subject_id=subjs[3].id, faculty_id=faculties[3].id,
                                section='A', semester=3, academic_year='2026-2027')
        db.session.add_all([cs_sec_a, cs_sec_b, ee_sec_a])
        db.session.commit()

        # Enroll first 25 students in both CS sections, rest in EE
        for s in students[:25]:
            db.session.add(Enrollment(student_id=s.id, class_section_id=cs_sec_a.id))
            db.session.add(Enrollment(student_id=s.id, class_section_id=cs_sec_b.id))

        for s in students[25:]:
            db.session.add(Enrollment(student_id=s.id, class_section_id=ee_sec_a.id))

        db.session.commit()

        print("Seeding 8 Weeks of Attendance...")
        start_date = date.today() - timedelta(weeks=8)

        # 3 sessions per week for 8 weeks = 24 sessions per class section.
        #
        # The first four students are hand-made so every zone and every alert
        # can be demonstrated. Weekly figures are shown because the declining
        # -trend rule reads them, and with 3 sessions a week the only possible
        # weekly values are 0%, 33%, 67% and 100%.
        #
        #   students[0]  24/24 = 100%    Safe
        #   students[1]  18/24 = 75%     Warning  (exactly on the pass mark)
        #   students[2]  15/24 = 62.5%   Critical
        #   students[3]  18/24 = 75%     Warning + declining trend
        #                weekly: 100 100 100 100 100 67 33 0
        #                The last four weeks fall every week, which is what
        #                detect_declining_trend looks for. A run that merely
        #                trends downwards is not enough: the rule needs each
        #                week strictly below the one before.

        for week in range(8):
            for day_offset in [0, 2, 4]:  # Mon, Wed, Fri
                session_date = start_date + timedelta(weeks=week, days=day_offset)

                # Create sessions for cs_sec_a (Data Structures)
                sess = AttendanceSession(
                    class_section_id=cs_sec_a.id,
                    session_date=session_date,
                    start_time=datetime.strptime('10:00', '%H:%M').time(),
                    end_time=datetime.strptime('11:00', '%H:%M').time(),
                    topic=f'Topic W{week + 1} D{day_offset + 1}',
                    status='locked',
                    created_by=faculties[0].user.id,
                )
                db.session.add(sess)
                db.session.flush()

                for s in students[:25]:
                    if s.id == students[0].id:
                        # Always present.
                        status = 'present'
                    elif s.id == students[1].id:
                        # Present for the first 6 weeks, then away: 18/24.
                        status = 'present' if week < 6 else 'absent'
                    elif s.id == students[2].id:
                        # Present for the first 5 weeks, then away: 15/24.
                        status = 'present' if week < 5 else 'absent'
                    elif s.id == students[3].id:
                        # Slides one session further each of the last three
                        # weeks, giving 100, 67, 33, 0 over the final four.
                        if week < 5:
                            status = 'present'                              # 100%
                        elif week == 5:
                            status = 'absent' if day_offset == 4 else 'present'   # 67%
                        elif week == 6:
                            status = 'present' if day_offset == 0 else 'absent'   # 33%
                        else:
                            status = 'absent'                               # 0%
                    else:
                        status = random.choices(
                            ['present', 'absent', 'late', 'excused'],
                            weights=[0.8, 0.1, 0.05, 0.05]
                        )[0]

                    record = AttendanceRecord(
                        session_id=sess.id,
                        student_id=s.id,
                        status=status,
                        marked_by=faculties[0].user.id,
                    )
                    db.session.add(record)

        db.session.commit()
        print("Database seeded successfully!")
        print()
        print("=== Seeded Credentials ===")
        print("Admin:    admin@smart.edu / password")
        print("Faculty:  faculty1@smart.edu / password")
        print("Student:  student1@smart.edu / password")


if __name__ == '__main__':
    seed_data()

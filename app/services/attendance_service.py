from datetime import timedelta
from app.extensions import db
from app.models import AttendanceRecord, AttendanceSession, Enrollment, ClassSection


def get_attendance_metrics(records):
    """
    Computes A (attended) and C (conducted) from a list of record statuses.
    Rule:
    - present, late -> count toward numerator and denominator (+1 A, +1 C)
    - absent -> count toward denominator only (+0 A, +1 C)
    - excused -> excluded entirely (+0 A, +0 C)
    """
    A = 0
    C = 0
    for status in records:
        if status in ('present', 'late'):
            A += 1
            C += 1
        elif status == 'absent':
            C += 1

    return A, C


def get_student_statuses(student_id, class_section_id):
    """
    Queries the DB for all attendance record statuses for a student
    in a given class section. Returns a plain list of status strings
    that can be fed directly to get_attendance_metrics().
    """
    rows = (
        db.session.query(AttendanceRecord.status)
        .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id)
        .filter(
            AttendanceRecord.student_id == student_id,
            AttendanceSession.class_section_id == class_section_id,
            AttendanceSession.status != 'cancelled'
        )
        .order_by(AttendanceSession.session_date)
        .all()
    )
    return [r.status for r in rows]


def get_weekly_percentages(student_id, class_section_id):
    """
    Computes weekly attendance percentages for trend detection.
    Returns a list of floats, one per week, ordered chronologically.
    Weeks with no non-excused records are omitted.
    """
    rows = (
        db.session.query(AttendanceSession.session_date, AttendanceRecord.status)
        .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
        .filter(
            AttendanceRecord.student_id == student_id,
            AttendanceSession.class_section_id == class_section_id,
            AttendanceSession.status != 'cancelled'
        )
        .order_by(AttendanceSession.session_date)
        .all()
    )

    if not rows:
        return []

    # Group by ISO week
    weeks = {}
    for session_date, status in rows:
        # isocalendar returns (year, week_number, weekday)
        year, week_num, _ = session_date.isocalendar()
        key = (year, week_num)
        if key not in weeks:
            weeks[key] = []
        weeks[key].append(status)

    # Compute percentage per week, skip weeks with only excused records
    percentages = []
    for key in sorted(weeks.keys()):
        statuses = weeks[key]
        A, C = get_attendance_metrics(statuses)
        if C > 0:
            percentages.append(A / C)

    return percentages


def get_student_history(student_id, class_section_id):
    """
    Returns a list of dicts with session details and this student's record
    for the attendance history view. Ordered by date descending.
    """
    rows = (
        db.session.query(AttendanceSession, AttendanceRecord)
        .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
        .filter(
            AttendanceRecord.student_id == student_id,
            AttendanceSession.class_section_id == class_section_id,
            AttendanceSession.status != 'cancelled'
        )
        .order_by(AttendanceSession.session_date.desc())
        .all()
    )

    history = []
    for session, record in rows:
        history.append({
            'date': session.session_date,
            'start_time': session.start_time,
            'end_time': session.end_time,
            'topic': session.topic,
            'status': record.status,
            'remarks': record.remarks,
        })

    return history

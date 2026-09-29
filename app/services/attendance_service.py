"""
Reads attendance out of the database and turns it into the numbers the
pages display. The arithmetic itself lives in prediction_service.py.
"""

from app.extensions import db
from app.models import AttendanceRecord, AttendanceSession
from app.services import prediction_service as predict

# How each mark affects the two running totals:
#   attended -- the numerator, classes the student was there for
#   conducted -- the denominator, classes that count against them
# An excused absence appears in neither, so it never hurts the percentage.
COUNTS_AS = {
    'present': (1, 1),
    'late': (1, 1),
    'absent': (0, 1),
    'excused': (0, 0),
}


def get_attendance_metrics(statuses):
    """Adds up a list of marks into (attended, conducted)."""
    attended = 0
    conducted = 0
    for status in statuses:
        a, c = COUNTS_AS.get(status, (0, 0))
        attended += a
        conducted += c
    return attended, conducted


def _session_records(student_id, class_section_id):
    """
    Base query: one row per attendance record for this student in this
    class section, oldest first. Cancelled sessions never count.
    """
    return (
        db.session.query(AttendanceSession, AttendanceRecord)
        .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
        .filter(
            AttendanceRecord.student_id == student_id,
            AttendanceSession.class_section_id == class_section_id,
            AttendanceSession.status != 'cancelled',
        )
        .order_by(AttendanceSession.session_date)
    )


def get_student_statuses(student_id, class_section_id):
    """Just the marks ('present', 'absent', ...), ready for get_attendance_metrics."""
    return [record.status for _, record in _session_records(student_id, class_section_id).all()]


def get_weekly_percentages(student_id, class_section_id):
    """
    One percentage per calendar week, oldest first, for trend detection.
    Weeks containing only excused absences are skipped (nothing to measure).
    """
    weeks = {}
    for session, record in _session_records(student_id, class_section_id).all():
        year, week_number, _ = session.session_date.isocalendar()
        weeks.setdefault((year, week_number), []).append(record.status)

    percentages = []
    for week in sorted(weeks):
        attended, conducted = get_attendance_metrics(weeks[week])
        if conducted > 0:
            percentages.append(attended / conducted)
    return percentages


def get_student_history(student_id, class_section_id):
    """Day-by-day rows for the history tables, newest first."""
    rows = _session_records(student_id, class_section_id).all()
    return [
        {
            'date': session.session_date,
            'start_time': session.start_time,
            'end_time': session.end_time,
            'topic': session.topic,
            'status': record.status,
            'remarks': record.remarks,
        }
        for session, record in reversed(rows)
    ]


def get_subject_summary(student_id, class_section_id, required, warning_band):
    """
    Everything one student's card, table row, or CSV line needs for one
    subject. This is the single place those numbers are worked out, so the
    dashboard, the analytics pages and the exports can never disagree.
    """
    attended, conducted = get_attendance_metrics(
        get_student_statuses(student_id, class_section_id)
    )
    status = predict.get_status(attended, conducted, required, warning_band)
    needed = predict.get_classes_needed(attended, conducted, required)
    can_miss = predict.get_classes_can_miss(attended, conducted, required)
    weekly = get_weekly_percentages(student_id, class_section_id)

    return {
        'attended': attended,
        'conducted': conducted,
        'percentage': predict.percentage(attended, conducted),
        'status': status,
        'needed': needed,
        'can_miss': can_miss,
        'weekly_pcts': weekly,
        'declining': predict.detect_declining_trend(weekly),
        'guidance': predict.guidance_message(status, needed, can_miss, required),
    }

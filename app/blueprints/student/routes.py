import csv
import io

from flask import Blueprint, render_template, request, Response
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Enrollment, Notification
from app.utils import role_required
from app.services.attendance_service import get_subject_summary, get_student_history
from app.services.prediction_service import calculate_what_if
from app.services.settings_service import get_rules

student_bp = Blueprint('student', __name__, url_prefix='/student',
                       template_folder='../../templates/student')


def _my_subjects():
    """
    One summary per subject the logged-in student is enrolled in.
    Everything the dashboard, exports and alerts need comes from here.
    """
    student = current_user.student_profile
    required, warning_band = get_rules()

    subjects = []
    for enrollment in student.enrollments:
        section = enrollment.class_section
        summary = get_subject_summary(student.id, section.id, required, warning_band)
        summary.update(
            class_section_id=section.id,
            subject_code=section.subject.code,
            subject_name=section.subject.name,
            faculty_name=section.faculty.user.full_name,
        )
        subjects.append(summary)

    return subjects, required


def _check_alerts(student, subjects, required):
    """
    Turns the current numbers into notifications for this student. Each alert
    is raised only once: if an unread one with the same title already exists,
    we skip it, so refreshing the dashboard does not spam the bell icon.
    """
    mark = f"{required * 100:.0f}%"

    for subject in subjects:
        if subject['status'] == 'Critical':
            _alert(student, f"Shortage Alert: {subject['subject_code']}",
                   f"Your attendance in {subject['subject_name']} is "
                   f"{subject['percentage']:.1f}%, below the required {mark}. "
                   f"You need to attend {subject['needed']} consecutive classes to recover.",
                   'critical')
        elif subject['status'] == 'Warning':
            _alert(student, f"Warning: {subject['subject_code']}",
                   f"Your attendance in {subject['subject_name']} is "
                   f"{subject['percentage']:.1f}%, near the minimum {mark}. "
                   f"Do not miss any classes.",
                   'warning')

        if subject['declining']:
            _alert(student, f"Declining Trend: {subject['subject_code']}",
                   f"Your weekly attendance in {subject['subject_name']} has been "
                   f"declining for the last 4 weeks. Please take action before it "
                   f"becomes critical.",
                   'warning')


def _alert(student, title, message, alert_type):
    """Adds a notification unless an unread one with this title is already there."""
    already_sent = Notification.query.filter_by(
        user_id=student.user_id, title=title, is_read=False
    ).first()
    if already_sent:
        return

    db.session.add(Notification(user_id=student.user_id, title=title,
                                message=message, type=alert_type))
    db.session.commit()


@student_bp.route('/dashboard')
@login_required
@role_required('student')
def dashboard():
    subjects, required = _my_subjects()
    _check_alerts(current_user.student_profile, subjects, required)

    unread_count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    return render_template('student/dashboard.html', subjects=subjects,
                           required_pct=required * 100, unread_count=unread_count)


@student_bp.route('/subject/<int:section_id>')
@login_required
@role_required('student')
def subject_detail(section_id):
    student = current_user.student_profile
    required, warning_band = get_rules()

    enrollment = Enrollment.query.filter_by(
        student_id=student.id, class_section_id=section_id
    ).first_or_404()
    section = enrollment.class_section

    summary = get_subject_summary(student.id, section.id, required, warning_band)

    # What-if calculator: only runs when the form has been submitted.
    what_if = None
    n = request.args.get('n', type=int)
    action = request.args.get('action')
    if n and n > 0 and action in ('attend', 'miss'):
        projected, status, verdict = calculate_what_if(
            summary['attended'], summary['conducted'], required, n, action, warning_band
        )
        what_if = {'n': n, 'action': action, 'projected': projected * 100,
                   'status': status, 'verdict': verdict}

    return render_template('student/subject_detail.html',
                           cs=section, summary=summary,
                           required_pct=required * 100,
                           what_if_result=what_if,
                           history=get_student_history(student.id, section.id))


@student_bp.route('/history')
@login_required
@role_required('student')
def history():
    student = current_user.student_profile

    subjects = [
        {
            'subject_code': enrollment.class_section.subject.code,
            'subject_name': enrollment.class_section.subject.name,
            'records': get_student_history(student.id, enrollment.class_section_id),
        }
        for enrollment in student.enrollments
    ]

    return render_template('student/history.html', subjects=subjects)


@student_bp.route('/notifications')
@login_required
@role_required('student')
def notifications():
    alerts = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.is_read, Notification.created_at.desc()
    ).all()

    # Visiting the page counts as reading them.
    for alert in alerts:
        alert.is_read = True
    db.session.commit()

    return render_template('student/notifications.html', alerts=alerts)


@student_bp.route('/export')
@login_required
@role_required('student')
def export_csv():
    subjects, _ = _my_subjects()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject Code', 'Subject Name', 'Attended', 'Conducted',
                     'Percentage', 'Status', 'Classes Needed', 'Can Miss'])
    for subject in subjects:
        writer.writerow([subject['subject_code'], subject['subject_name'],
                         subject['attended'], subject['conducted'],
                         f"{subject['percentage']:.1f}", subject['status'],
                         subject['needed'], subject['can_miss']])

    filename = f'{current_user.student_profile.roll_no}_attendance_report.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

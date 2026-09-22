import csv
import io
from flask import Blueprint, render_template, request, Response
from flask_login import login_required, current_user
from app.utils import role_required
from app.extensions import db
from app.models import Enrollment, Setting, Notification
from app.services.attendance_service import (
    get_attendance_metrics, get_student_statuses,
    get_weekly_percentages, get_student_history
)
from app.services.prediction_service import (
    get_status, get_classes_needed, get_classes_can_miss,
    calculate_what_if, detect_declining_trend
)

student_bp = Blueprint('student', __name__, url_prefix='/student', template_folder='../../templates/student')


def _get_settings():
    """Reads R and warning_band from the settings table. On-the-fly, no cache."""
    r_setting = Setting.query.filter_by(key='required_attendance_percent').first()
    w_setting = Setting.query.filter_by(key='warning_band_percent').first()
    R = float(r_setting.value) if r_setting else 0.75
    warning_band = float(w_setting.value) if w_setting else 0.05
    return R, warning_band


def _check_alerts(student, subjects_data, R):
    """
    Generates dashboard-based alert notifications for the student.
    Checks each subject and creates a Notification row if one doesn't
    already exist (unread) for that condition. Simple and idempotent.
    """
    for subj in subjects_data:
        # Critical alert
        if subj['status'] == 'Critical':
            _create_alert_if_new(
                student.user_id,
                f"Shortage Alert: {subj['subject_code']}",
                f"Your attendance in {subj['subject_name']} is {subj['percentage']:.1f}%, "
                f"below the required {R*100:.0f}%. "
                f"You need to attend {subj['needed']} consecutive classes to recover.",
                'critical'
            )
        # Warning alert
        elif subj['status'] == 'Warning':
            _create_alert_if_new(
                student.user_id,
                f"Warning: {subj['subject_code']}",
                f"Your attendance in {subj['subject_name']} is {subj['percentage']:.1f}%, "
                f"near the minimum {R*100:.0f}%. Do not miss any classes.",
                'warning'
            )
        # Declining trend alert
        if subj['declining']:
            _create_alert_if_new(
                student.user_id,
                f"Declining Trend: {subj['subject_code']}",
                f"Your weekly attendance in {subj['subject_name']} has been declining "
                f"for the last 4 weeks. Please take action before it becomes critical.",
                'warning'
            )


def _create_alert_if_new(user_id, title, message, alert_type):
    """Only create a notification if there isn't an unread one with the same title."""
    existing = Notification.query.filter_by(
        user_id=user_id, title=title, is_read=False
    ).first()
    if not existing:
        db.session.add(Notification(
            user_id=user_id, title=title, message=message, type=alert_type
        ))
        db.session.commit()


@student_bp.route('/dashboard')
@login_required
@role_required('student')
def dashboard():
    student = current_user.student_profile
    R, warning_band = _get_settings()

    subjects = []
    for enrollment in student.enrollments:
        cs = enrollment.class_section

        statuses = get_student_statuses(student.id, cs.id)
        A, C = get_attendance_metrics(statuses)
        percentage = (A / C * 100) if C > 0 else 0.0
        status = get_status(A, C, R, warning_band)
        needed = get_classes_needed(A, C, R)
        can_miss = get_classes_can_miss(A, C, R)
        weekly_pcts = get_weekly_percentages(student.id, cs.id)
        declining = detect_declining_trend(weekly_pcts)

        subjects.append({
            'class_section_id': cs.id,
            'subject_code': cs.subject.code,
            'subject_name': cs.subject.name,
            'faculty_name': cs.faculty.user.full_name,
            'attended': A,
            'conducted': C,
            'percentage': percentage,
            'status': status,
            'needed': needed,
            'can_miss': can_miss,
            'declining': declining,
            'weekly_pcts': weekly_pcts,
        })

    # Generate alerts based on current data
    _check_alerts(student, subjects, R)

    # Count unread notifications for badge
    unread_count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    return render_template('student/dashboard.html', subjects=subjects,
                           required_pct=R * 100, unread_count=unread_count)


@student_bp.route('/subject/<int:section_id>')
@login_required
@role_required('student')
def subject_detail(section_id):
    student = current_user.student_profile
    R, warning_band = _get_settings()

    enrollment = Enrollment.query.filter_by(
        student_id=student.id, class_section_id=section_id
    ).first_or_404()
    cs = enrollment.class_section

    statuses = get_student_statuses(student.id, cs.id)
    A, C = get_attendance_metrics(statuses)
    percentage = (A / C * 100) if C > 0 else 0.0
    status = get_status(A, C, R, warning_band)
    needed = get_classes_needed(A, C, R)
    can_miss = get_classes_can_miss(A, C, R)
    weekly_pcts = get_weekly_percentages(student.id, cs.id)
    declining = detect_declining_trend(weekly_pcts)

    # Guidance message
    if status == 'Critical':
        if needed == 'impossible':
            guidance = "Your attendance is too low to recover to the required threshold."
        else:
            guidance = f"You need to attend your next {needed} consecutive classes to reach {R*100:.0f}%."
    elif status == 'Warning':
        guidance = f"You are at the minimum. You cannot miss any more classes right now."
    else:
        if can_miss > 0:
            guidance = f"You can safely miss up to {can_miss} more classes and still stay above {R*100:.0f}%."
        else:
            guidance = f"You are at exactly {R*100:.0f}%. Do not miss any classes."

    # What-if scenarios
    what_if_result = None
    n = request.args.get('n', type=int)
    action = request.args.get('action')
    if n and action in ('attend', 'miss') and n > 0:
        projected, wi_status, verdict = calculate_what_if(A, C, R, n, action, warning_band)
        what_if_result = {
            'n': n,
            'action': action,
            'projected': projected * 100,
            'status': wi_status,
            'verdict': verdict,
        }

    history = get_student_history(student.id, cs.id)

    return render_template('student/subject_detail.html',
                           cs=cs, A=A, C=C, percentage=percentage,
                           status=status, needed=needed, can_miss=can_miss,
                           guidance=guidance, declining=declining,
                           weekly_pcts=weekly_pcts, required_pct=R * 100,
                           what_if_result=what_if_result,
                           history=history)


@student_bp.route('/history')
@login_required
@role_required('student')
def history():
    student = current_user.student_profile
    R, warning_band = _get_settings()

    subjects = []
    for enrollment in student.enrollments:
        cs = enrollment.class_section
        records = get_student_history(student.id, cs.id)
        subjects.append({
            'subject_code': cs.subject.code,
            'subject_name': cs.subject.name,
            'records': records,
        })

    return render_template('student/history.html', subjects=subjects)


# --- Phase 7: Notifications ---
@student_bp.route('/notifications')
@login_required
@role_required('student')
def notifications():
    alerts = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.is_read, Notification.created_at.desc()
    ).all()

    # Mark all as read when the page is visited
    for a in alerts:
        if not a.is_read:
            a.is_read = True
    db.session.commit()

    return render_template('student/notifications.html', alerts=alerts)


# --- Phase 7: CSV Export ---
@student_bp.route('/export')
@login_required
@role_required('student')
def export_csv():
    student = current_user.student_profile
    R, warning_band = _get_settings()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject Code', 'Subject Name', 'Attended', 'Conducted',
                     'Percentage', 'Status', 'Classes Needed', 'Can Miss'])

    for enrollment in student.enrollments:
        cs = enrollment.class_section
        statuses = get_student_statuses(student.id, cs.id)
        A, C = get_attendance_metrics(statuses)
        percentage = (A / C * 100) if C > 0 else 0.0
        status = get_status(A, C, R, warning_band)
        needed = get_classes_needed(A, C, R)
        can_miss = get_classes_can_miss(A, C, R)

        writer.writerow([cs.subject.code, cs.subject.name, A, C,
                         f'{percentage:.1f}', status, needed, can_miss])

    filename = f'{student.roll_no}_attendance_report.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

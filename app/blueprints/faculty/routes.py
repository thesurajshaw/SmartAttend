import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import login_required, current_user
from app.utils import role_required
from app.extensions import db
from app.models import (
    ClassSection, AttendanceSession, AttendanceRecord, Enrollment,
    Setting, AuditLog, CorrectionRequest, Student, Notification
)
from app.services.attendance_service import (
    get_attendance_metrics, get_student_statuses, get_weekly_percentages
)
from app.services.prediction_service import (
    get_status, get_classes_needed, get_classes_can_miss, detect_declining_trend
)

faculty_bp = Blueprint('faculty', __name__, url_prefix='/faculty', template_folder='../../templates/faculty')


def _get_settings():
    """Reads R and warning_band from the settings table."""
    r_setting = Setting.query.filter_by(key='required_attendance_percent').first()
    w_setting = Setting.query.filter_by(key='warning_band_percent').first()
    R = float(r_setting.value) if r_setting else 0.75
    warning_band = float(w_setting.value) if w_setting else 0.05
    return R, warning_band


@faculty_bp.route('/dashboard')
@login_required
@role_required('faculty')
def dashboard():
    sections = current_user.faculty_profile.class_sections
    return render_template('faculty/dashboard.html', sections=sections)


@faculty_bp.route('/sections')
@login_required
@role_required('faculty')
def my_sections():
    sections = current_user.faculty_profile.class_sections
    return render_template('faculty/dashboard.html', sections=sections)


@faculty_bp.route('/sections/<int:section_id>/sessions', methods=['GET', 'POST'])
@login_required
@role_required('faculty')
def section_sessions(section_id):
    section = ClassSection.query.get_or_404(section_id)
    if section.faculty_id != current_user.faculty_profile.id:
        abort(403)

    if request.method == 'POST':
        date_str = request.form.get('session_date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        topic = request.form.get('topic')

        sess = AttendanceSession(
            class_section_id=section.id,
            session_date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            start_time=datetime.strptime(start_time_str, '%H:%M').time(),
            end_time=datetime.strptime(end_time_str, '%H:%M').time(),
            topic=topic,
            created_by=current_user.id
        )
        db.session.add(sess)
        db.session.commit()
        flash('Session created successfully.', 'success')
        return redirect(url_for('faculty.marking_grid', session_id=sess.id))

    # Auto-lock expired sessions
    lock_hours_setting = Setting.query.filter_by(key='session_lock_hours').first()
    lock_hours = int(lock_hours_setting.value) if lock_hours_setting else 24

    sessions = AttendanceSession.query.filter_by(class_section_id=section.id).order_by(AttendanceSession.session_date.desc()).all()
    for s in sessions:
        if s.status == 'open':
            hours_elapsed = (datetime.utcnow() - s.created_at).total_seconds() / 3600
            if hours_elapsed > lock_hours:
                s.status = 'locked'
                db.session.add(s)
    db.session.commit()

    return render_template('faculty/session_list.html', section=section, sessions=sessions)


@faculty_bp.route('/session/<int:session_id>/mark', methods=['GET', 'POST'])
@login_required
@role_required('faculty')
def marking_grid(session_id):
    session = AttendanceSession.query.get_or_404(session_id)
    if session.class_section.faculty_id != current_user.faculty_profile.id:
        abort(403)

    # Check lock status
    lock_hours_setting = Setting.query.filter_by(key='session_lock_hours').first()
    lock_hours = int(lock_hours_setting.value) if lock_hours_setting else 24
    hours_elapsed = (datetime.utcnow() - session.created_at).total_seconds() / 3600

    if session.status == 'open' and hours_elapsed > lock_hours:
        session.status = 'locked'
        db.session.commit()

    is_locked = session.status == 'locked'

    enrollments = Enrollment.query.filter_by(class_section_id=session.class_section_id).join(Enrollment.student).all()
    enrollments.sort(key=lambda e: e.student.roll_no)

    records = {r.student_id: r for r in session.records}

    if request.method == 'POST':
        if is_locked:
            flash('Session is locked. Cannot save marks directly.', 'error')
            return redirect(url_for('faculty.marking_grid', session_id=session.id))

        try:
            for enrollment in enrollments:
                student_id = enrollment.student_id
                status = request.form.get(f'status_{student_id}')
                remarks = request.form.get(f'remarks_{student_id}', '')

                if not status:
                    continue

                existing = records.get(student_id)
                if existing:
                    if existing.status != status or existing.remarks != remarks:
                        log = AuditLog(
                            actor_user_id=current_user.id,
                            action='UPDATE_ATTENDANCE',
                            entity_type='AttendanceRecord',
                            entity_id=existing.id,
                            old_value={'status': existing.status, 'remarks': existing.remarks},
                            new_value={'status': status, 'remarks': remarks},
                            ip_address=request.remote_addr
                        )
                        db.session.add(log)
                        existing.status = status
                        existing.remarks = remarks
                else:
                    new_record = AttendanceRecord(
                        session_id=session.id,
                        student_id=student_id,
                        status=status,
                        marked_by=current_user.id,
                        remarks=remarks
                    )
                    db.session.add(new_record)
                    db.session.flush()

                    log = AuditLog(
                        actor_user_id=current_user.id,
                        action='INSERT_ATTENDANCE',
                        entity_type='AttendanceRecord',
                        entity_id=new_record.id,
                        old_value=None,
                        new_value={'status': status, 'remarks': remarks},
                        ip_address=request.remote_addr
                    )
                    db.session.add(log)

            if request.form.get('action') == 'save_and_lock':
                session.status = 'locked'

            db.session.commit()
            flash('Attendance saved successfully.', 'success')
            return redirect(url_for('faculty.marking_grid', session_id=session.id))

        except Exception as e:
            db.session.rollback()
            flash('Database error occurred. Entire transaction was rolled back.', 'error')

    return render_template('faculty/marking_grid.html', session=session, enrollments=enrollments, records=records, is_locked=is_locked)


@faculty_bp.route('/record/<int:record_id>/correction', methods=['POST'])
@login_required
@role_required('faculty')
def request_correction(record_id):
    record = AttendanceRecord.query.get_or_404(record_id)
    if record.session.class_section.faculty_id != current_user.faculty_profile.id:
        abort(403)

    new_status = request.form.get('new_status')
    reason = request.form.get('reason')

    if not new_status or not reason:
        flash('Missing status or reason for correction.', 'error')
        return redirect(url_for('faculty.marking_grid', session_id=record.session_id))

    req = CorrectionRequest(
        attendance_record_id=record.id,
        requested_by=current_user.id,
        old_status=record.status,
        new_status=new_status,
        reason=reason
    )
    db.session.add(req)
    db.session.commit()

    flash('Correction request submitted to admin.', 'success')
    return redirect(url_for('faculty.marking_grid', session_id=record.session_id))


# --- Phase 7: Analytics ---
@faculty_bp.route('/sections/<int:section_id>/analytics')
@login_required
@role_required('faculty')
def section_analytics(section_id):
    section = ClassSection.query.get_or_404(section_id)
    if section.faculty_id != current_user.faculty_profile.id:
        abort(403)

    R, warning_band = _get_settings()
    enrollments = Enrollment.query.filter_by(class_section_id=section.id).all()

    students_data = []
    status_counts = {'Safe': 0, 'Warning': 0, 'Critical': 0}

    for enrollment in enrollments:
        s = enrollment.student
        statuses = get_student_statuses(s.id, section.id)
        A, C = get_attendance_metrics(statuses)
        percentage = (A / C * 100) if C > 0 else 0.0
        status = get_status(A, C, R, warning_band)
        needed = get_classes_needed(A, C, R)
        can_miss = get_classes_can_miss(A, C, R)
        weekly_pcts = get_weekly_percentages(s.id, section.id)
        declining = detect_declining_trend(weekly_pcts)

        status_counts[status] += 1

        students_data.append({
            'roll_no': s.roll_no,
            'name': s.user.full_name,
            'attended': A,
            'conducted': C,
            'percentage': percentage,
            'status': status,
            'needed': needed,
            'can_miss': can_miss,
            'declining': declining,
        })

    students_data.sort(key=lambda x: x['roll_no'])
    total = len(students_data)
    session_count = AttendanceSession.query.filter_by(
        class_section_id=section.id
    ).filter(AttendanceSession.status != 'cancelled').count()

    return render_template('faculty/section_analytics.html',
                           section=section, students=students_data,
                           status_counts=status_counts, total=total,
                           session_count=session_count, required_pct=R * 100)


# --- Phase 7: CSV Export ---
@faculty_bp.route('/sections/<int:section_id>/export')
@login_required
@role_required('faculty')
def export_section_csv(section_id):
    section = ClassSection.query.get_or_404(section_id)
    if section.faculty_id != current_user.faculty_profile.id:
        abort(403)

    R, warning_band = _get_settings()
    enrollments = Enrollment.query.filter_by(class_section_id=section.id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll No', 'Student Name', 'Attended', 'Conducted', 'Percentage', 'Status', 'Classes Needed', 'Can Miss'])

    for enrollment in enrollments:
        s = enrollment.student
        statuses = get_student_statuses(s.id, section.id)
        A, C = get_attendance_metrics(statuses)
        percentage = (A / C * 100) if C > 0 else 0.0
        status = get_status(A, C, R, warning_band)
        needed = get_classes_needed(A, C, R)
        can_miss = get_classes_can_miss(A, C, R)

        writer.writerow([s.roll_no, s.user.full_name, A, C, f'{percentage:.1f}', status, needed, can_miss])

    filename = f'{section.subject.code}_Section{section.section}_attendance.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

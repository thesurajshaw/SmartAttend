import csv
import io
from datetime import datetime

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, Response)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (ClassSection, AttendanceSession, AttendanceRecord,
                        Enrollment, AuditLog, CorrectionRequest)
from app.utils import role_required
from app.services.attendance_service import get_subject_summary
from app.services.settings_service import get_rules, get_lock_hours

faculty_bp = Blueprint('faculty', __name__, url_prefix='/faculty',
                       template_folder='../../templates/faculty')


def _my_section(section_id):
    """The class section, but only if it belongs to the logged-in teacher."""
    section = ClassSection.query.get_or_404(section_id)
    if section.faculty_id != current_user.faculty_profile.id:
        abort(403)
    return section


def _lock_if_expired(session):
    """
    Sessions can only be edited for a while after they are created (the
    admin sets how long). Past that, they lock and any change has to go
    through a correction request. Returns True if the session is locked.
    """
    if session.status == 'open':
        hours_open = (datetime.utcnow() - session.created_at).total_seconds() / 3600
        if hours_open > get_lock_hours():
            session.status = 'locked'
    return session.status == 'locked'


def _log_change(action, record_id, old_value, new_value):
    """Writes one tamper-evident audit row: who changed what, when, from where."""
    db.session.add(AuditLog(
        actor_user_id=current_user.id,
        action=action,
        entity_type='AttendanceRecord',
        entity_id=record_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=request.remote_addr,
    ))


def _section_students(section, required, warning_band):
    """Every enrolled student's summary for this section, sorted by roll number."""
    enrollments = Enrollment.query.filter_by(class_section_id=section.id).all()

    students = []
    for enrollment in enrollments:
        student = enrollment.student
        summary = get_subject_summary(student.id, section.id, required, warning_band)
        summary.update(roll_no=student.roll_no, name=student.user.full_name)
        students.append(summary)

    students.sort(key=lambda s: s['roll_no'])
    return students


@faculty_bp.route('/dashboard')
@login_required
@role_required('faculty')
def dashboard():
    return render_template('faculty/dashboard.html',
                           sections=current_user.faculty_profile.class_sections)


@faculty_bp.route('/sections')
@login_required
@role_required('faculty')
def my_sections():
    """'My Sections' in the sidebar: the same list as the dashboard."""
    return dashboard()


@faculty_bp.route('/sections/<int:section_id>/sessions', methods=['GET', 'POST'])
@login_required
@role_required('faculty')
def section_sessions(section_id):
    section = _my_section(section_id)

    if request.method == 'POST':
        session = AttendanceSession(
            class_section_id=section.id,
            session_date=datetime.strptime(request.form['session_date'], '%Y-%m-%d').date(),
            start_time=datetime.strptime(request.form['start_time'], '%H:%M').time(),
            end_time=datetime.strptime(request.form['end_time'], '%H:%M').time(),
            topic=request.form.get('topic'),
            created_by=current_user.id,
        )
        db.session.add(session)
        db.session.commit()
        flash('Session created successfully.', 'success')
        return redirect(url_for('faculty.marking_grid', session_id=session.id))

    sessions = (AttendanceSession.query
                .filter_by(class_section_id=section.id)
                .order_by(AttendanceSession.session_date.desc())
                .all())
    for session in sessions:
        _lock_if_expired(session)
    db.session.commit()

    return render_template('faculty/session_list.html', section=section, sessions=sessions)


@faculty_bp.route('/session/<int:session_id>/mark', methods=['GET', 'POST'])
@login_required
@role_required('faculty')
def marking_grid(session_id):
    session = AttendanceSession.query.get_or_404(session_id)
    _my_section(session.class_section_id)

    is_locked = _lock_if_expired(session)
    db.session.commit()

    enrollments = Enrollment.query.filter_by(class_section_id=session.class_section_id).all()
    enrollments.sort(key=lambda e: e.student.roll_no)
    records = {r.student_id: r for r in session.records}

    if request.method == 'POST':
        if is_locked:
            flash('Session is locked. Cannot save marks directly.', 'error')
            return redirect(url_for('faculty.marking_grid', session_id=session.id))

        try:
            for enrollment in enrollments:
                _save_mark(session, enrollment.student_id, records)

            if request.form.get('action') == 'save_and_lock':
                session.status = 'locked'

            db.session.commit()
            flash('Attendance saved successfully.', 'success')
            return redirect(url_for('faculty.marking_grid', session_id=session.id))

        except Exception:
            # All-or-nothing: a half-saved grid would corrupt every percentage.
            db.session.rollback()
            flash('Database error occurred. Entire transaction was rolled back.', 'error')

    return render_template('faculty/marking_grid.html', session=session,
                           enrollments=enrollments, records=records, is_locked=is_locked)


def _save_mark(session, student_id, records):
    """Creates or updates one student's mark, recording the change in the audit log."""
    status = request.form.get(f'status_{student_id}')
    if not status:
        return

    remarks = request.form.get(f'remarks_{student_id}', '')
    existing = records.get(student_id)

    if existing is None:
        record = AttendanceRecord(session_id=session.id, student_id=student_id,
                                  status=status, marked_by=current_user.id,
                                  remarks=remarks)
        db.session.add(record)
        db.session.flush()  # assigns record.id so the log can point at it
        _log_change('INSERT_ATTENDANCE', record.id, None,
                    {'status': status, 'remarks': remarks})

    elif existing.status != status or existing.remarks != remarks:
        _log_change('UPDATE_ATTENDANCE', existing.id,
                    {'status': existing.status, 'remarks': existing.remarks},
                    {'status': status, 'remarks': remarks})
        existing.status = status
        existing.remarks = remarks


@faculty_bp.route('/record/<int:record_id>/correction', methods=['POST'])
@login_required
@role_required('faculty')
def request_correction(record_id):
    record = AttendanceRecord.query.get_or_404(record_id)
    _my_section(record.session.class_section_id)

    new_status = request.form.get('new_status')
    reason = request.form.get('reason')

    if not new_status or not reason:
        flash('Missing status or reason for correction.', 'error')
    else:
        db.session.add(CorrectionRequest(
            attendance_record_id=record.id,
            requested_by=current_user.id,
            old_status=record.status,
            new_status=new_status,
            reason=reason,
        ))
        db.session.commit()
        flash('Correction request submitted to admin.', 'success')

    return redirect(url_for('faculty.marking_grid', session_id=record.session_id))


@faculty_bp.route('/sections/<int:section_id>/analytics')
@login_required
@role_required('faculty')
def section_analytics(section_id):
    section = _my_section(section_id)
    required, warning_band = get_rules()
    students = _section_students(section, required, warning_band)

    status_counts = {'Safe': 0, 'Warning': 0, 'Critical': 0}
    for student in students:
        status_counts[student['status']] += 1

    session_count = (AttendanceSession.query
                     .filter_by(class_section_id=section.id)
                     .filter(AttendanceSession.status != 'cancelled')
                     .count())

    return render_template('faculty/section_analytics.html',
                           section=section, students=students,
                           status_counts=status_counts, total=len(students),
                           session_count=session_count, required_pct=required * 100)


@faculty_bp.route('/sections/<int:section_id>/export')
@login_required
@role_required('faculty')
def export_section_csv(section_id):
    section = _my_section(section_id)
    required, warning_band = get_rules()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll No', 'Student Name', 'Attended', 'Conducted',
                     'Percentage', 'Status', 'Classes Needed', 'Can Miss'])
    for student in _section_students(section, required, warning_band):
        writer.writerow([student['roll_no'], student['name'],
                         student['attended'], student['conducted'],
                         f"{student['percentage']:.1f}", student['status'],
                         student['needed'], student['can_miss']])

    filename = f'{section.subject.code}_Section{section.section}_attendance.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

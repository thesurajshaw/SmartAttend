import csv
import io
from datetime import datetime

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, Response)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (User, Department, Subject, Faculty, Student,
                        ClassSection, Setting, Enrollment, CorrectionRequest,
                        AuditLog)
from app.utils import role_required
from app.services.attendance_service import get_subject_summary
from app.services.settings_service import get_rules

admin_bp = Blueprint('admin', __name__, url_prefix='/admin',
                     template_folder='../../templates/admin')

DEFAULT_PASSWORD = 'password'


def _save(record, message):
    """Adds a row, saves, and tells the user. Used by every 'add' form."""
    db.session.add(record)
    db.session.commit()
    flash(message, 'success')


def _create_login(role):
    """
    Builds the User row that a new student or teacher signs in with.
    They get a known starter password and must change it on first login.
    """
    user = User(
        email=request.form.get('email'),
        full_name=request.form.get('full_name'),
        password_hash=generate_password_hash(DEFAULT_PASSWORD),
        role=role,
        must_change_password=True,
    )
    db.session.add(user)
    db.session.flush()  # assigns user.id for the profile row below
    return user


def _delete(model, record_id, message, with_user=False):
    """Deletes a row (and its login, for students and faculty)."""
    record = model.query.get_or_404(record_id)
    if with_user:
        db.session.delete(record.user)
    db.session.delete(record)
    db.session.commit()
    flash(message, 'success')


def _all_students_summaries():
    """
    Walks every class section and yields one summary per enrolled student.
    Shared by the analytics page and the full CSV export.
    """
    required, warning_band = get_rules()

    for section in ClassSection.query.all():
        enrollments = Enrollment.query.filter_by(class_section_id=section.id).all()
        for enrollment in enrollments:
            student = enrollment.student
            summary = get_subject_summary(student.id, section.id, required, warning_band)
            summary.update(
                roll_no=student.roll_no,
                name=student.user.full_name,
                subject_code=section.subject.code,
                subject_name=section.subject.name,
                section=section.section,
            )
            yield section, summary


@admin_bp.route('/dashboard')
@login_required
@role_required('admin')
def dashboard():
    stats = {
        'students': Student.query.count(),
        'faculty': Faculty.query.count(),
        'departments': Department.query.count(),
        'subjects': Subject.query.count(),
        'sections': ClassSection.query.count(),
    }
    return render_template('admin/dashboard.html', stats=stats)


# --- Departments ---
@admin_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def departments():
    if request.method == 'POST':
        name, code = request.form.get('name'), request.form.get('code')
        if name and code:
            _save(Department(name=name, code=code), 'Department added successfully.')
        return redirect(url_for('admin.departments'))

    return render_template('admin/departments.html', departments=Department.query.all())


@admin_bp.route('/departments/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_department(id):
    _delete(Department, id, 'Department deleted.')
    return redirect(url_for('admin.departments'))


# --- Subjects ---
@admin_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def subjects():
    if request.method == 'POST':
        _save(Subject(
            code=request.form.get('code'),
            name=request.form.get('name'),
            department_id=request.form.get('department_id'),
            semester=request.form.get('semester'),
            credits=request.form.get('credits'),
            subject_type=request.form.get('subject_type'),
        ), 'Subject added successfully.')
        return redirect(url_for('admin.subjects'))

    return render_template('admin/subjects.html', subjects=Subject.query.all(),
                           departments=Department.query.all())


@admin_bp.route('/subjects/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_subject(id):
    _delete(Subject, id, 'Subject deleted.')
    return redirect(url_for('admin.subjects'))


# --- Faculty ---
@admin_bp.route('/faculty', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def faculty_list():
    if request.method == 'POST':
        user = _create_login('faculty')
        _save(Faculty(
            user_id=user.id,
            employee_id=request.form.get('employee_id'),
            department_id=request.form.get('department_id'),
            designation=request.form.get('designation'),
            joining_date=datetime.strptime(request.form['joining_date'], '%Y-%m-%d').date(),
        ), f'Faculty added successfully. Default password is "{DEFAULT_PASSWORD}".')
        return redirect(url_for('admin.faculty_list'))

    return render_template('admin/faculty.html', faculty=Faculty.query.all(),
                           departments=Department.query.all())


@admin_bp.route('/faculty/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_faculty(id):
    _delete(Faculty, id, 'Faculty deleted.', with_user=True)
    return redirect(url_for('admin.faculty_list'))


# --- Students ---
@admin_bp.route('/students', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def students():
    if request.method == 'POST':
        user = _create_login('student')
        _save(Student(
            user_id=user.id,
            roll_no=request.form.get('roll_no'),
            department_id=request.form.get('department_id'),
            semester=request.form.get('semester'),
            section=request.form.get('section'),
            admission_year=request.form.get('admission_year'),
        ), f'Student added successfully. Default password is "{DEFAULT_PASSWORD}".')
        return redirect(url_for('admin.students'))

    page = request.args.get('page', 1, type=int)
    return render_template('admin/students.html',
                           pagination=Student.query.paginate(page=page, per_page=20),
                           departments=Department.query.all())


@admin_bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_student(id):
    _delete(Student, id, 'Student deleted.', with_user=True)
    return redirect(url_for('admin.students'))


# --- Class Sections ---
@admin_bp.route('/class-sections', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def class_sections():
    if request.method == 'POST':
        _save(ClassSection(
            subject_id=request.form.get('subject_id'),
            faculty_id=request.form.get('faculty_id'),
            section=request.form.get('section'),
            semester=request.form.get('semester'),
            academic_year=request.form.get('academic_year'),
        ), 'Class section created.')
        return redirect(url_for('admin.class_sections'))

    return render_template('admin/class_sections.html',
                           sections=ClassSection.query.all(),
                           subjects=Subject.query.all(),
                           faculty=Faculty.query.all())


# --- Settings ---
EDITABLE_SETTINGS = ['required_attendance_percent', 'warning_band_percent',
                     'session_lock_hours', 'institution_name']


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def settings():
    if request.method == 'POST':
        for key in EDITABLE_SETTINGS:
            value = request.form.get(key)
            if not value:
                continue
            row = Setting.query.filter_by(key=key).first()
            if row:
                row.value = value
            else:
                db.session.add(Setting(key=key, value=value))
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html',
                           settings={s.key: s.value for s in Setting.query.all()})


# --- System-wide analytics ---
@admin_bp.route('/analytics')
@login_required
@role_required('admin')
def analytics():
    required, _ = get_rules()

    per_section = {}     # section id -> the row shown in the sections table
    overall = {'Safe': 0, 'Warning': 0, 'Critical': 0}
    at_risk = []

    for section in ClassSection.query.all():
        per_section[section.id] = {
            'subject_code': section.subject.code,
            'subject_name': section.subject.name,
            'section': section.section,
            'faculty_name': section.faculty.user.full_name,
            'total': 0, 'safe': 0, 'warning': 0, 'critical': 0,
        }

    for section, summary in _all_students_summaries():
        row = per_section[section.id]
        row['total'] += 1
        row[summary['status'].lower()] += 1
        overall[summary['status']] += 1

        if summary['status'] in ('Warning', 'Critical'):
            at_risk.append(summary)

    at_risk.sort(key=lambda s: s['percentage'])  # worst first

    return render_template('admin/analytics.html',
                           section_stats=list(per_section.values()),
                           overall=overall, at_risk=at_risk,
                           required_pct=required * 100)


# --- Full CSV export (every student, every section) ---
@admin_bp.route('/export')
@login_required
@role_required('admin')
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject Code', 'Subject Name', 'Section', 'Roll No',
                     'Student Name', 'Attended', 'Conducted', 'Percentage',
                     'Status', 'Classes Needed', 'Can Miss'])

    for _, s in _all_students_summaries():
        writer.writerow([s['subject_code'], s['subject_name'], s['section'],
                         s['roll_no'], s['name'], s['attended'], s['conducted'],
                         f"{s['percentage']:.1f}", s['status'],
                         s['needed'], s['can_miss']])

    filename = f'smartattend_full_report_{datetime.now():%Y%m%d}.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


# --- Correction requests ---
@admin_bp.route('/corrections')
@login_required
@role_required('admin')
def corrections():
    requests = CorrectionRequest.query.order_by(
        db.case((CorrectionRequest.status == 'pending', 1), else_=2),  # pending first
        CorrectionRequest.id.desc()
    ).all()
    return render_template('admin/corrections.html', requests=requests)


@admin_bp.route('/corrections/<int:id>/<action>', methods=['POST'])
@login_required
@role_required('admin')
def process_correction(id, action):
    if action not in ('approve', 'reject'):
        abort(400)

    correction = CorrectionRequest.query.get_or_404(id)
    if correction.status != 'pending':
        flash('This request has already been processed.', 'error')
        return redirect(url_for('admin.corrections'))

    if action == 'approve':
        # Approving is the only way a locked record ever changes, so log it.
        record = correction.record
        db.session.add(AuditLog(
            actor_user_id=current_user.id,
            action='APPROVE_CORRECTION',
            entity_type='AttendanceRecord',
            entity_id=record.id,
            old_value={'status': record.status},
            new_value={'status': correction.new_status},
            ip_address=request.remote_addr,
        ))
        record.status = correction.new_status
        correction.status = 'approved'
        flash('Correction request approved.', 'success')
    else:
        correction.status = 'rejected'
        flash('Correction request rejected.', 'success')

    correction.reviewed_by = current_user.id
    correction.reviewed_at = datetime.utcnow()
    correction.review_note = request.form.get('review_note', '')
    db.session.commit()

    return redirect(url_for('admin.corrections'))


# --- Audit log viewer ---
@admin_bp.route('/audit-logs')
@login_required
@role_required('admin')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    pagination = AuditLog.query.order_by(
        AuditLog.created_at.desc()
    ).paginate(page=page, per_page=50)

    # Look up the names behind the actor ids on this page, in one query.
    actor_ids = {log.actor_user_id for log in pagination.items if log.actor_user_id}
    actors = {u.id: u.full_name
              for u in User.query.filter(User.id.in_(actor_ids)).all()} if actor_ids else {}

    return render_template('admin/audit_logs.html', pagination=pagination, actors=actors)

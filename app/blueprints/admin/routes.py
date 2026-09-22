import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.utils import role_required
from app.extensions import db
from app.models import User, Department, Subject, Faculty, Student, ClassSection, Setting, Enrollment, CorrectionRequest, AuditLog
from app.services.attendance_service import get_attendance_metrics, get_student_statuses
from app.services.prediction_service import get_status, get_classes_needed, get_classes_can_miss
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../../templates/admin')


def _get_settings():
    r_setting = Setting.query.filter_by(key='required_attendance_percent').first()
    w_setting = Setting.query.filter_by(key='warning_band_percent').first()
    R = float(r_setting.value) if r_setting else 0.75
    warning_band = float(w_setting.value) if w_setting else 0.05
    return R, warning_band


@admin_bp.route('/dashboard')
@login_required
@role_required('admin')
def dashboard():
    stats = {
        'students': Student.query.count(),
        'faculty': Faculty.query.count(),
        'departments': Department.query.count(),
        'subjects': Subject.query.count(),
        'sections': ClassSection.query.count()
    }
    return render_template('admin/dashboard.html', stats=stats)


# --- Departments ---
@admin_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def departments():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        if name and code:
            db.session.add(Department(name=name, code=code))
            db.session.commit()
            flash('Department added successfully.', 'success')
        return redirect(url_for('admin.departments'))

    depts = Department.query.all()
    return render_template('admin/departments.html', departments=depts)

@admin_bp.route('/departments/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_department(id):
    dept = Department.query.get_or_404(id)
    db.session.delete(dept)
    db.session.commit()
    flash('Department deleted.', 'success')
    return redirect(url_for('admin.departments'))


# --- Subjects ---
@admin_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def subjects():
    if request.method == 'POST':
        db.session.add(Subject(
            code=request.form.get('code'),
            name=request.form.get('name'),
            department_id=request.form.get('department_id'),
            semester=request.form.get('semester'),
            credits=request.form.get('credits'),
            subject_type=request.form.get('subject_type')
        ))
        db.session.commit()
        flash('Subject added successfully.', 'success')
        return redirect(url_for('admin.subjects'))

    subs = Subject.query.all()
    depts = Department.query.all()
    return render_template('admin/subjects.html', subjects=subs, departments=depts)

@admin_bp.route('/subjects/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_subject(id):
    subj = Subject.query.get_or_404(id)
    db.session.delete(subj)
    db.session.commit()
    flash('Subject deleted.', 'success')
    return redirect(url_for('admin.subjects'))


# --- Faculty ---
@admin_bp.route('/faculty', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def faculty_list():
    if request.method == 'POST':
        email = request.form.get('email')
        u = User(email=email, password_hash=generate_password_hash('password'),
                 full_name=request.form.get('full_name'), role='faculty', must_change_password=True)
        db.session.add(u)
        db.session.flush()

        db.session.add(Faculty(
            user_id=u.id,
            employee_id=request.form.get('employee_id'),
            department_id=request.form.get('department_id'),
            designation=request.form.get('designation'),
            joining_date=datetime.strptime(request.form.get('joining_date'), '%Y-%m-%d').date()
        ))
        db.session.commit()
        flash('Faculty added successfully. Default password is "password".', 'success')
        return redirect(url_for('admin.faculty_list'))

    facs = Faculty.query.all()
    depts = Department.query.all()
    return render_template('admin/faculty.html', faculty=facs, departments=depts)

@admin_bp.route('/faculty/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_faculty(id):
    fac = Faculty.query.get_or_404(id)
    u = fac.user
    db.session.delete(fac)
    db.session.delete(u)
    db.session.commit()
    flash('Faculty deleted.', 'success')
    return redirect(url_for('admin.faculty_list'))


# --- Students ---
@admin_bp.route('/students', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def students():
    if request.method == 'POST':
        email = request.form.get('email')
        u = User(email=email, password_hash=generate_password_hash('password'),
                 full_name=request.form.get('full_name'), role='student', must_change_password=True)
        db.session.add(u)
        db.session.flush()

        db.session.add(Student(
            user_id=u.id,
            roll_no=request.form.get('roll_no'),
            department_id=request.form.get('department_id'),
            semester=request.form.get('semester'),
            section=request.form.get('section'),
            admission_year=request.form.get('admission_year')
        ))
        db.session.commit()
        flash('Student added successfully. Default password is "password".', 'success')
        return redirect(url_for('admin.students'))

    page = request.args.get('page', 1, type=int)
    pagination = Student.query.paginate(page=page, per_page=20)
    depts = Department.query.all()
    return render_template('admin/students.html', pagination=pagination, departments=depts)

@admin_bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_student(id):
    stu = Student.query.get_or_404(id)
    u = stu.user
    db.session.delete(stu)
    db.session.delete(u)
    db.session.commit()
    flash('Student deleted.', 'success')
    return redirect(url_for('admin.students'))


# --- Class Sections ---
@admin_bp.route('/class-sections', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def class_sections():
    if request.method == 'POST':
        db.session.add(ClassSection(
            subject_id=request.form.get('subject_id'),
            faculty_id=request.form.get('faculty_id'),
            section=request.form.get('section'),
            semester=request.form.get('semester'),
            academic_year=request.form.get('academic_year')
        ))
        db.session.commit()
        flash('Class section created.', 'success')
        return redirect(url_for('admin.class_sections'))

    sections = ClassSection.query.all()
    subs = Subject.query.all()
    facs = Faculty.query.all()
    return render_template('admin/class_sections.html', sections=sections, subjects=subs, faculty=facs)


# --- Settings ---
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def settings():
    if request.method == 'POST':
        for key in ['required_attendance_percent', 'warning_band_percent', 'session_lock_hours', 'institution_name']:
            val = request.form.get(key)
            if val:
                s = Setting.query.filter_by(key=key).first()
                if s:
                    s.value = val
                else:
                    db.session.add(Setting(key=key, value=val))
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('admin.settings'))

    all_settings = {s.key: s.value for s in Setting.query.all()}
    return render_template('admin/settings.html', settings=all_settings)


# --- Phase 7: System-wide Analytics ---
@admin_bp.route('/analytics')
@login_required
@role_required('admin')
def analytics():
    R, warning_band = _get_settings()
    sections = ClassSection.query.all()

    section_stats = []
    overall_status_counts = {'Safe': 0, 'Warning': 0, 'Critical': 0}
    at_risk_students = []

    for cs in sections:
        enrollments = Enrollment.query.filter_by(class_section_id=cs.id).all()
        sec_counts = {'Safe': 0, 'Warning': 0, 'Critical': 0}

        for enrollment in enrollments:
            s = enrollment.student
            statuses = get_student_statuses(s.id, cs.id)
            A, C = get_attendance_metrics(statuses)
            percentage = (A / C * 100) if C > 0 else 0.0
            status = get_status(A, C, R, warning_band)
            needed = get_classes_needed(A, C, R)

            sec_counts[status] += 1
            overall_status_counts[status] += 1

            if status in ('Warning', 'Critical'):
                at_risk_students.append({
                    'roll_no': s.roll_no,
                    'name': s.user.full_name,
                    'subject_code': cs.subject.code,
                    'percentage': percentage,
                    'status': status,
                    'needed': needed,
                })

        total = len(enrollments)
        section_stats.append({
            'subject_code': cs.subject.code,
            'subject_name': cs.subject.name,
            'section': cs.section,
            'faculty_name': cs.faculty.user.full_name,
            'total': total,
            'safe': sec_counts['Safe'],
            'warning': sec_counts['Warning'],
            'critical': sec_counts['Critical'],
        })

    # Sort at-risk students by percentage ascending (worst first)
    at_risk_students.sort(key=lambda x: x['percentage'])

    return render_template('admin/analytics.html',
                           section_stats=section_stats,
                           overall=overall_status_counts,
                           at_risk=at_risk_students,
                           required_pct=R * 100)


# --- Phase 7: Admin CSV Export (all students across all sections) ---
@admin_bp.route('/export')
@login_required
@role_required('admin')
def export_csv():
    R, warning_band = _get_settings()
    sections = ClassSection.query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Subject Code', 'Subject Name', 'Section', 'Roll No',
                     'Student Name', 'Attended', 'Conducted', 'Percentage',
                     'Status', 'Classes Needed', 'Can Miss'])

    for cs in sections:
        enrollments = Enrollment.query.filter_by(class_section_id=cs.id).all()
        for enrollment in enrollments:
            s = enrollment.student
            statuses = get_student_statuses(s.id, cs.id)
            A, C = get_attendance_metrics(statuses)
            percentage = (A / C * 100) if C > 0 else 0.0
            status = get_status(A, C, R, warning_band)
            needed = get_classes_needed(A, C, R)
            can_miss = get_classes_can_miss(A, C, R)

            writer.writerow([cs.subject.code, cs.subject.name, cs.section,
                             s.roll_no, s.user.full_name, A, C,
                             f'{percentage:.1f}', status, needed, can_miss])

    filename = f'smartattend_full_report_{datetime.now().strftime("%Y%m%d")}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# --- Phase 8: Correction Requests ---
@admin_bp.route("/corrections")
@login_required
@role_required("admin")
def corrections():
    # Show pending first, then ordered by date
    requests = CorrectionRequest.query.order_by(
        db.case((CorrectionRequest.status == "pending", 1), else_=2),
        CorrectionRequest.id.desc()
    ).all()
    return render_template("admin/corrections.html", requests=requests)

@admin_bp.route("/corrections/<int:id>/<action>", methods=["POST"])
@login_required
@role_required("admin")
def process_correction(id, action):
    req = CorrectionRequest.query.get_or_404(id)
    review_note = request.form.get("review_note", "")

    if req.status != "pending":
        flash("This request has already been processed.", "error")
        return redirect(url_for("admin.corrections"))

    if action == "approve":
        req.status = "approved"
        
        # Update actual attendance record
        record = req.record
        old_status = record.status
        record.status = req.new_status
        
        # Log the change
        log = AuditLog(
            actor_user_id=current_user.id,
            action="APPROVE_CORRECTION",
            entity_type="AttendanceRecord",
            entity_id=record.id,
            old_value={"status": old_status},
            new_value={"status": req.new_status},
            ip_address=request.remote_addr
        )
        db.session.add(log)
        flash("Correction request approved.", "success")
        
    elif action == "reject":
        req.status = "rejected"
        flash("Correction request rejected.", "success")
    else:
        abort(400)

    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.review_note = review_note
    
    db.session.commit()
    return redirect(url_for("admin.corrections"))


# --- Phase 8: Audit Logs ---
@admin_bp.route("/audit-logs")
@login_required
@role_required("admin")
def audit_logs():
    page = request.args.get("page", 1, type=int)
    # Simple pagination for audit logs, ordered chronologically descending
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50)
    
    # We might need to display actor names, let us fetch users for the displayed logs
    actor_ids = {log.actor_user_id for log in pagination.items if log.actor_user_id}
    actors = {u.id: u.full_name for u in User.query.filter(User.id.in_(actor_ids)).all()} if actor_ids else {}
    
    return render_template("admin/audit_logs.html", pagination=pagination, actors=actors)


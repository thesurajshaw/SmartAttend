# SmartAttend 🎓

A Student-Centric Attendance Tracking & Shortage Prediction System. 

SmartAttend is not just an attendance register. It answers the questions students actually ask:
* "What is my attendance in each subject right now?"
* "Am I safe, or am I heading toward a shortage?"
* "How many classes do I need to attend consecutively to reach 75%?"
* "How many classes can I afford to miss before I drop below 75%?"

**Philosophy**: `RECORD → ANALYZE → PREDICT → GUIDE`

## 🌟 Features by Role

### 👩‍💻 Admin
* **Dashboard & Analytics**: View system-wide status counts, section-wise breakdown, and a combined list of "At-Risk" students.
* **System Settings**: Configure global rules like `required_attendance_percent` (e.g., 75%), `warning_band_percent` (e.g., 5%), and `session_lock_hours`.
* **Data Management**: CRUD operations for Departments, Subjects, Faculty, Students, and Class Sections.
* **Correction Workflow**: Approve or reject faculty requests to modify locked attendance records.
* **Audit Logs**: Tamper-proof log viewer showing exactly who changed what, when, and from what IP address.
* **Export**: Download full system CSV reports.

### 👨‍🏫 Faculty
* **Dashboard**: See assigned sections and enrollment counts.
* **Session Management**: Create sessions (topic, date, time). Sessions auto-lock after the admin-configured time window (e.g., 24 hours).
* **Atomic Marking Grid**: Mark Present, Absent, Late, or Excused cleanly.
* **Correction Requests**: If a session is locked, submit a formal request to the Admin to change a record.
* **Section Analytics**: View status distribution (Safe/Warning/Critical) and detailed breakdown of their students. Export CSVs.

### 🧑‍🎓 Student
* **Dashboard & Prediction Engine**: See real-time metrics per subject.
  * **Safe** (Green): Attendance is strictly >= (Required + Warning Band). Shows "Classes you can safely miss".
  * **Warning** (Amber): Attendance is between Required and Safe threshold. Shows "Attend next N classes to reach Safe zone".
  * **Critical** (Red): Attendance is strictly < Required. Shows "Attend next N classes to reach threshold".
* **What-If Calculator**: Input hypothetical "Present" and "Absent" futures to see the predicted percentage.
* **Alerts & Notifications**: Receive warnings for Critical/Warning thresholds and continuous declining trends (e.g., 3 weeks of dropping attendance).
* **History**: View detailed day-by-day attendance history.

## 🗺️ How the Code Is Organised

The project separates *calculating* from *storing* from *displaying*, so each
piece can be read on its own.

```
app/
├── models/             The database tables (users, subjects, attendance, ...)
├── services/           All the thinking happens here
│   ├── prediction_service.py   Pure maths. No database. The heart of the project.
│   ├── attendance_service.py   Reads attendance from the DB and totals it up.
│   └── settings_service.py     Reads the admin's rules (pass mark, lock window).
├── blueprints/         One folder per role — each route just fetches and renders
│   ├── auth/  admin/  faculty/  student/
├── templates/          The HTML pages
└── static/             CSS and a little JavaScript
```

**Where to start reading:** `app/services/prediction_service.py`. Every rule the
system enforces is one short function there, with the algebra written out in the
docstring, and none of it touches the database — so each rule can be checked by
hand and is unit-tested in `tests/test_prediction_service.py`.

The three numbers those functions pass around are:

| Name | Meaning |
|------|---------|
| `attended` | classes the student was present for (present and late both count) |
| `conducted` | classes that count against them (excused absences are excluded) |
| `required` | the pass mark as a fraction, e.g. `0.75` for 75% |

Each student's figures are worked out in exactly one place —
`attendance_service.get_subject_summary()` — which the dashboards, the analytics
pages and the CSV exports all call. That is why a student, their teacher and the
admin can never be shown different numbers for the same subject.

## 🛠️ Tech Stack
* **Backend**: Python, Flask, Flask-Login, Flask-WTF
* **Database**: SQLite (via SQLAlchemy & Flask-Migrate) - *Easily swappable to PostgreSQL/MySQL.*
* **Frontend**: Vanilla HTML, custom CSS with CSS Variables, native JS (No bloated frameworks). Native Dark Mode toggle using `localStorage`.

---

## 🚀 Setup Instructions

1. **Clone the repository and enter the directory**:
   ```bash
   cd SmartAttend
   ```

2. **Create and activate a virtual environment**:
   *Windows:*
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   *Mac/Linux:*
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the Database & Seed Data**:
   This step creates the SQLite database and populates it with departments, subjects, students, faculty, and historical attendance data for prediction testing.
   ```bash
   python seed.py
   ```

5. **Run the Application**:
   ```bash
   python run.py
   ```
   The app will start on `http://127.0.0.1:5000`.

---

## 🔑 Demo Credentials

> **⚠️ WARNING**: These credentials are automatically generated by `seed.py` for **development and demonstration purposes only**. They are not suitable for production use.

**Admin**
* Email: `admin@smart.edu`
* Password: `password`

**Faculty**
* Email: `faculty1@smart.edu` (up to `faculty5@smart.edu`)
* Password: `password`

**Students**
* Email: `student1@smart.edu` (up to `student40@smart.edu`)
* Password: `password`
* *Note: Student 1 has perfect attendance, Student 2 is in "Warning", Student 3 is in "Critical", and Student 4 exhibits a declining trend.*

---

**Strict Data Freshness Guarantee**
SmartAttend calculates all percentages, predictions, and guidance on-the-fly directly from raw database records during the HTTP request-response cycle. There is no caching layer—ensuring the guidance a student sees is mathematically guaranteed to match their raw record at that exact millisecond.

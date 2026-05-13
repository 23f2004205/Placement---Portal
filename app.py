from flask import Flask, render_template, request, redirect, session, flash, url_for, send_from_directory
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import re

# Upload folder settings
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

# Create the Flask application
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database file name
DATABASE = 'placement_portal.db'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_notification(user_id, message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, message)
    )
    conn.commit()
    conn.close()


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            degree TEXT,
            branch TEXT,
            cgpa REAL,
            resume TEXT,
            profile_picture TEXT,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Add profile_picture column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN profile_picture TEXT")
    except Exception:
        pass  # Column already exists, ignore

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_name TEXT NOT NULL,
            hr_name TEXT,
            hr_contact TEXT,
            website TEXT,
            approval_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS placement_drives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            job_title TEXT NOT NULL,
            job_description TEXT,
            eligibility_criteria TEXT,
            salary TEXT,
            location TEXT,
            application_deadline DATE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            drive_id INTEGER NOT NULL,
            application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'applied',
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (drive_id) REFERENCES placement_drives(id),
            UNIQUE(student_id, drive_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute("SELECT * FROM users WHERE role = 'admin'")
    admin = cursor.fetchone()

    if not admin:
        admin_password = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
            ('admin@placement.com', admin_password, 'admin')
        )
        print("✅ Default Admin Created!")
        print("   Email: admin@placement.com")
        print("   Password: admin123")

    conn.commit()
    conn.close()
    print("✅ All database tables created!")


def calculate_job_match(student, drive):
    score = 0

    # 1. CGPA Check (40 points)
    cgpa_match = re.search(r'cgpa\s*[>≥]\s*(\d+\.?\d*)', drive['eligibility_criteria'].lower())
    if cgpa_match:
        required_cgpa = float(cgpa_match.group(1))
        if student['cgpa'] >= required_cgpa:
            score += 40
        elif student['cgpa'] >= required_cgpa - 0.5:
            score += 20
    else:
        score += 40

    # 2. Branch Matching (30 points)
    student_branch_lower = student['branch'].lower()
    eligibility_lower = drive['eligibility_criteria'].lower()

    branch_keywords = {
        'cse': ['cse', 'computer science', 'cs', 'computer'],
        'ece': ['ece', 'electronics', 'electrical'],
        'it': ['it', 'information technology'],
        'mechanical': ['mechanical', 'mech'],
        'civil': ['civil']
    }

    for key, keywords in branch_keywords.items():
        if any(kw in student_branch_lower for kw in keywords):
            if any(kw in eligibility_lower for kw in keywords):
                score += 30
                break

    if 'all' in eligibility_lower or len(eligibility_lower) < 20:
        score += 30

    # 3. Degree Matching (30 points)
    student_degree_lower = student['degree'].lower()
    if student_degree_lower in eligibility_lower:
        score += 30
    elif 'btech' in eligibility_lower and student_degree_lower in ['btech', 'b.tech']:
        score += 30
    elif 'all' in eligibility_lower:
        score += 30
    else:
        score += 15

    return min(score, 100)


# =====================
# GENERAL ROUTES
# =====================

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/test-db')
def test_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    cursor.execute("SELECT * FROM users WHERE role='admin'")
    admin = cursor.fetchone()
    conn.close()
    result = "<h2>Database Status</h2>"
    result += f"<p>Tables created: {len(tables)}</p>"
    result += f"<p>Table names: {[t['name'] for t in tables]}</p>"
    if admin:
        result += f"<p>✅ Admin exists: {admin['email']}</p>"
    else:
        result += "<p>❌ No admin found</p>"
    return result


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        conn = get_db()
        cursor = conn.cursor()

        if role == 'admin':
            if email == 'admin@placement.com' and password == 'admin123':
                session['user_id'] = 0
                session['role'] = 'admin'
                flash('Login successful!', 'success')
                conn.close()
                return redirect('/admin/dashboard')
            else:
                flash('Invalid admin credentials!', 'danger')
                conn.close()
                return redirect('/login')

        elif role == 'student':
            # FIX: email is in users table, not students
            cursor.execute('''
                SELECT students.*, users.password AS user_password
                FROM students
                JOIN users ON students.user_id = users.id
                WHERE users.email = ?
            ''', (email,))
            student = cursor.fetchone()

            if student and check_password_hash(student['user_password'], password):
                if student['status'] == 'blacklisted':
                    flash('Your account has been blacklisted!', 'danger')
                    conn.close()
                    return redirect('/login')

                session['user_id'] = student['user_id']  # store user_id
                session['role'] = 'student'
                session.permanent = True
                flash('Login successful!', 'success')
                conn.close()
                return redirect('/student/dashboard')
            else:
                flash('Invalid student credentials!', 'danger')
                conn.close()
                return redirect('/login')

        elif role == 'company':
            # FIX: email is in users table, not companies
            cursor.execute('''
                SELECT companies.*, users.password AS user_password
                FROM companies
                JOIN users ON companies.user_id = users.id
                WHERE users.email = ?
            ''', (email,))
            company = cursor.fetchone()

            if company and check_password_hash(company['user_password'], password):
                if company['approval_status'] == 'pending':
                    flash('Your account is pending approval!', 'warning')
                    conn.close()
                    return redirect('/login')
                elif company['approval_status'] in ['rejected', 'blacklisted']:
                    flash('Your account has been rejected/blacklisted!', 'danger')
                    conn.close()
                    return redirect('/login')

                session['user_id'] = company['user_id']
                session['role'] = 'company'
                session.permanent = True
                flash('Login successful!', 'success')
                conn.close()
                return redirect('/company/dashboard')
            else:
                flash('Invalid company credentials!', 'danger')
                conn.close()
                return redirect('/login')

        conn.close()

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out!', 'info')
    return redirect(url_for('login'))


# =====================
# TEST DATA ROUTE
# =====================

@app.route('/add-test-data')
def add_test_data():
    conn = get_db()
    cursor = conn.cursor()

    students_data = [
        ('student1@test.com', 'Raj Kumar', '9876543210', 'BTech', 'Computer Science', 8.5),
        ('student2@test.com', 'Priya Singh', '9876543211', 'BTech', 'Electronics', 8.8),
        ('student3@test.com', 'Amit Sharma', '9876543212', 'MTech', 'Data Science', 9.1),
        ('student4@test.com', 'Neha Patel', '9876543213', 'BTech', 'Mechanical', 7.9),
        ('student5@test.com', 'Arjun Reddy', '9876543214', 'BTech', 'Civil', 8.2),
    ]

    for email, name, phone, degree, branch, cgpa in students_data:
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        if not cursor.fetchone():
            password = generate_password_hash('student123')
            cursor.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
                           (email, password, 'student'))
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO students (user_id, name, phone, degree, branch, cgpa) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, phone, degree, branch, cgpa))

    companies_data = [
        ('google@company.com', 'Google Inc', 'Sarah Johnson', '1234567890', 'https://google.com', 'approved'),
        ('microsoft@company.com', 'Microsoft Corp', 'John Smith', '1234567891', 'https://microsoft.com', 'pending'),
        ('amazon@company.com', 'Amazon', 'Emily Davis', '1234567892', 'https://amazon.com', 'approved'),
    ]

    for email, company_name, hr_name, hr_contact, website, status in companies_data:
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        if not cursor.fetchone():
            password = generate_password_hash('company123')
            cursor.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
                           (email, password, 'company'))
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO companies (user_id, company_name, hr_name, hr_contact, website, approval_status) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, company_name, hr_name, hr_contact, website, status))

    cursor.execute("SELECT id FROM companies WHERE approval_status = 'approved' LIMIT 1")
    company = cursor.fetchone()

    if company:
        drives_data = [
            (company['id'], 'Software Engineer', 'Develop web applications', 'BTech CSE, CGPA > 7.0', '15 LPA',
             'Bangalore', '2026-03-30', 'approved'),
            (company['id'], 'Data Analyst', 'Analyze business data', 'BTech/MTech, CGPA > 7.5', '12 LPA',
             'Hyderabad', '2026-04-15', 'pending'),
        ]
        for company_id, job_title, job_desc, criteria, salary, location, deadline, status in drives_data:
            cursor.execute(
                "INSERT INTO placement_drives (company_id, job_title, job_description, eligibility_criteria, salary, location, application_deadline, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (company_id, job_title, job_desc, criteria, salary, location, deadline, status))

    conn.commit()
    conn.close()
    return '<h2>Test Data Added Successfully!</h2><a href="/admin/dashboard">Go to Dashboard</a>'


# =====================
# ADMIN ROUTES
# =====================

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
 
    conn = get_db()
    cursor = conn.cursor()
 
    # --- Original counts ---
    cursor.execute("SELECT COUNT(*) as count FROM students")
    total_students = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM companies")
    total_companies = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM placement_drives")
    total_drives = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM applications")
    total_applications = cursor.fetchone()['count']
 
    # --- Analytics KPIs ---
    cursor.execute("SELECT COUNT(*) as count FROM students WHERE status = 'active'")
    active_students = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM companies WHERE approval_status = 'approved'")
    active_companies = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM applications WHERE status = 'selected'")
    total_placed = cursor.fetchone()['count']
 
    placement_rate = round((total_placed / total_students * 100), 1) if total_students > 0 else 0
 
    cursor.execute("SELECT COUNT(*) as count FROM placement_drives WHERE status = 'approved'")
    active_drives = cursor.fetchone()['count']
 
    # --- Monthly trend ---
    cursor.execute('''
        SELECT strftime('%Y-%m', application_date) as month, COUNT(*) as count
        FROM applications
        GROUP BY month ORDER BY month ASC LIMIT 6
    ''')
    monthly_rows = cursor.fetchall()
    monthly_labels = [r['month'] for r in monthly_rows]
    monthly_counts = [r['count'] for r in monthly_rows]
 
    # --- Status breakdown ---
    cursor.execute("SELECT status, COUNT(*) as count FROM applications GROUP BY status")
    status_rows = cursor.fetchall()
    status_labels = [r['status'].capitalize() for r in status_rows]
    status_counts = [r['count'] for r in status_rows]
 
    # --- Branch stats ---
    cursor.execute('''
        SELECT students.branch,
               COUNT(DISTINCT students.id) as total,
               COUNT(DISTINCT CASE WHEN applications.status='selected' THEN students.id END) as placed
        FROM students
        LEFT JOIN applications ON students.id = applications.student_id
        WHERE students.branch IS NOT NULL AND students.branch != ''
        GROUP BY students.branch
    ''')
    branch_rows = cursor.fetchall()
    branch_labels = [r['branch'] for r in branch_rows]
    branch_totals = [r['total'] for r in branch_rows]
    branch_placed = [r['placed'] for r in branch_rows]
 
    # --- Top companies ---
    cursor.execute('''
        SELECT companies.company_name, COUNT(applications.id) as count
        FROM applications
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        JOIN companies ON placement_drives.company_id = companies.id
        GROUP BY companies.id ORDER BY count DESC LIMIT 5
    ''')
    company_rows = cursor.fetchall()
    company_labels = [r['company_name'] for r in company_rows]
    company_counts = [r['count'] for r in company_rows]
 
    # --- Recent activity ---
    cursor.execute('''
        SELECT students.name as actor, companies.company_name as target,
               applications.application_date as ts, applications.status
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        JOIN companies ON placement_drives.company_id = companies.id
        ORDER BY applications.application_date DESC LIMIT 8
    ''')
    recent_activity = cursor.fetchall()
 
    conn.close()
 
    return render_template('admin_dashboard.html',
        # original
        students=total_students,
        companies=total_companies,
        drives=total_drives,
        applications=total_applications,
        # analytics
        total_placed=total_placed,
        placement_rate=placement_rate,
        active_drives=active_drives,
        monthly_labels=monthly_labels,
        monthly_counts=monthly_counts,
        status_labels=status_labels,
        status_counts=status_counts,
        branch_labels=branch_labels,
        branch_totals=branch_totals,
        branch_placed=branch_placed,
        company_labels=company_labels,
        company_counts=company_counts,
        recent_activity=recent_activity,
    )
@app.route('/admin/students')
def admin_students():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')
    conn = get_db()
    cursor = conn.cursor()

    if search_query:
        cursor.execute('''
            SELECT students.id, students.name, students.phone, students.degree,
                   students.branch, students.cgpa, students.status, users.email
            FROM students
            JOIN users ON students.user_id = users.id
            WHERE students.name LIKE ? OR students.phone LIKE ? OR users.email LIKE ?
            ORDER BY students.id
        ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('''
            SELECT students.id, students.name, students.phone, students.degree,
                   students.branch, students.cgpa, students.status, users.email
            FROM students
            JOIN users ON students.user_id = users.id
            ORDER BY students.id
        ''')

    students = cursor.fetchall()
    conn.close()
    return render_template('admin_students.html', students=students, search_query=search_query)


@app.route('/admin/companies')
def admin_companies():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')
    conn = get_db()
    cursor = conn.cursor()

    if search_query:
        cursor.execute('''
            SELECT companies.id, companies.company_name, companies.hr_name,
                   companies.hr_contact, companies.website, companies.approval_status,
                   users.email
            FROM companies
            JOIN users ON companies.user_id = users.id
            WHERE companies.company_name LIKE ? OR users.email LIKE ?
            ORDER BY companies.id
        ''', (f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('''
            SELECT companies.id, companies.company_name, companies.hr_name,
                   companies.hr_contact, companies.website, companies.approval_status,
                   users.email
            FROM companies
            JOIN users ON companies.user_id = users.id
            ORDER BY companies.id
        ''')

    companies = cursor.fetchall()
    conn.close()
    return render_template('admin_companies.html', companies=companies, search_query=search_query)


@app.route('/admin/approve-company/<int:company_id>')
def approve_company(company_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE companies SET approval_status = 'approved' WHERE id = ?", (company_id,))
    conn.commit()
    conn.close()
    flash('Company approved successfully!', 'success')
    return redirect(url_for('admin_companies'))


@app.route('/admin/reject-company/<int:company_id>')
def reject_company(company_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE companies SET approval_status = 'rejected' WHERE id = ?", (company_id,))
    conn.commit()
    conn.close()
    flash('Company rejected!', 'warning')
    return redirect(url_for('admin_companies'))


@app.route('/admin/blacklist-company/<int:company_id>')
def blacklist_company(company_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT approval_status FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()
    if company:
        if company['approval_status'] != 'blacklisted':
            cursor.execute("UPDATE companies SET approval_status = 'blacklisted' WHERE id = ?", (company_id,))
            flash('Company blacklisted successfully!', 'warning')
        else:
            cursor.execute("UPDATE companies SET approval_status = 'approved' WHERE id = ?", (company_id,))
            flash('Company activated successfully!', 'success')
        conn.commit()
    else:
        flash('Company not found!', 'danger')
    conn.close()
    return redirect(url_for('admin_companies'))


@app.route('/admin/drives')
def admin_drives():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT placement_drives.id, placement_drives.job_title,
               placement_drives.job_description, placement_drives.eligibility_criteria,
               placement_drives.salary, placement_drives.location,
               placement_drives.application_deadline, placement_drives.status,
               companies.company_name
        FROM placement_drives
        JOIN companies ON placement_drives.company_id = companies.id
        ORDER BY placement_drives.id DESC
    ''')
    drives = cursor.fetchall()
    conn.close()
    return render_template('admin_drives.html', drives=drives)


@app.route('/admin/approve-drive/<int:drive_id>')
def approve_drive(drive_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE placement_drives SET status = 'approved' WHERE id = ?", (drive_id,))
    conn.commit()
    conn.close()
    flash('Placement drive approved successfully!', 'success')
    return redirect(url_for('admin_drives'))


@app.route('/admin/reject-drive/<int:drive_id>')
def reject_drive(drive_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE placement_drives SET status = 'rejected' WHERE id = ?", (drive_id,))
    conn.commit()
    conn.close()
    flash('Placement drive rejected!', 'warning')
    return redirect(url_for('admin_drives'))


@app.route('/admin/delete-student/<int:student_id>')
def delete_student(student_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    if student:
        user_id = student['user_id']
        cursor.execute("DELETE FROM applications WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash('Student deleted successfully!', 'success')
    else:
        flash('Student not found!', 'danger')
    conn.close()
    return redirect(url_for('admin_students'))


@app.route('/admin/delete-company/<int:company_id>')
def delete_company(company_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()
    if company:
        user_id = company['user_id']
        cursor.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash('Company deleted successfully!', 'success')
    else:
        flash('Company not found!', 'danger')
    conn.close()
    return redirect(url_for('admin_companies'))


@app.route('/admin/blacklist-student/<int:student_id>')
def blacklist_student(student_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    if student:
        if student['status'] == 'active':
            cursor.execute("UPDATE students SET status = 'blacklisted' WHERE id = ?", (student_id,))
            flash('Student blacklisted successfully!', 'warning')
        else:
            cursor.execute("UPDATE students SET status = 'active' WHERE id = ?", (student_id,))
            flash('Student activated successfully!', 'success')
        conn.commit()
    else:
        flash('Student not found!', 'danger')
    conn.close()
    return redirect(url_for('admin_students'))


@app.route('/admin/applications')
def admin_applications():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT applications.id, applications.application_date, applications.status,
               students.name as student_name, students.cgpa,
               placement_drives.job_title,
               companies.company_name
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        JOIN companies ON placement_drives.company_id = companies.id
        ORDER BY applications.application_date DESC
    ''')
    applications = cursor.fetchall()
    conn.close()
    return render_template('admin_applications.html', applications=applications)


# =====================
# STUDENT ROUTES
# =====================

@app.route('/student-register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        degree = request.form.get('degree')
        branch = request.form.get('branch')
        cgpa = request.form.get('cgpa')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Email already registered! Please login.', 'danger')
            conn.close()
            return redirect(url_for('student_register'))

        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
            (email, hashed_password, 'student')
        )
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO students (user_id, name, phone, degree, branch, cgpa, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, degree, branch, cgpa, 'active')
        )
        conn.commit()
        conn.close()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('student_register.html')


@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT students.*, users.email
        FROM students
        JOIN users ON students.user_id = users.id
        WHERE students.user_id = ?
    ''', (session['user_id'],))
    student = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as count FROM placement_drives WHERE status = 'approved'")
    total_drives = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM applications WHERE student_id = ?", (student['id'],))
    my_applications = cursor.fetchone()['count']
    conn.close()

    return render_template('student_dashboard.html',
                           student=student,
                           total_drives=total_drives,
                           my_applications=my_applications)


@app.route('/student/drives')
def student_drives():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    # FIX: Join with users to get email, query by user_id
    cursor.execute('''
        SELECT students.*, users.email
        FROM students
        JOIN users ON students.user_id = users.id
        WHERE students.user_id = ?
    ''', (session['user_id'],))
    student = cursor.fetchone()

    if not student:
        flash('Student not found!', 'danger')
        conn.close()
        return redirect('/logout')

    student_dict = {
        'id': student['id'],
        'name': student['name'],
        'cgpa': student['cgpa'],
        'branch': student['branch'],
        'degree': student['degree']
    }

    # FIX: correct table name is placement_drives
    cursor.execute('''
        SELECT placement_drives.*, companies.company_name
        FROM placement_drives
        JOIN companies ON placement_drives.company_id = companies.id
        WHERE placement_drives.status = "approved"
        ORDER BY placement_drives.created_at DESC
    ''')

    drives_raw = cursor.fetchall()

    drives = []
    for drive in drives_raw:
        drive_dict = {
            'id': drive['id'],
            'company_id': drive['company_id'],
            'job_title': drive['job_title'],
            'job_description': drive['job_description'],
            'eligibility_criteria': drive['eligibility_criteria'],
            'salary': drive['salary'],
            'location': drive['location'],
            'application_deadline': drive['application_deadline'],
            'status': drive['status'],
            'created_at': drive['created_at'],
            'company_name': drive['company_name'],
            'match_percentage': calculate_job_match(student_dict, {
                'eligibility_criteria': drive['eligibility_criteria'],
                'job_description': drive['job_description']
            })
        }
        drives.append(drive_dict)

    drives.sort(key=lambda x: x['match_percentage'], reverse=True)

    conn.close()
    return render_template('student_drives.html', drives=drives)


@app.route('/student/apply/<int:drive_id>', methods=['POST'])
def student_apply(drive_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM students WHERE user_id = ?", (session['user_id'],))
    student = cursor.fetchone()

    if not student:
        flash('Student not found!', 'danger')
        conn.close()
        return redirect(url_for('student_drives'))

    try:
        cursor.execute(
            "INSERT INTO applications (student_id, drive_id, status) VALUES (?, ?, ?)",
            (student['id'], drive_id, 'applied')
        )
        conn.commit()
        flash('Application submitted successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('You have already applied for this drive!', 'warning')

    conn.close()
    return redirect(url_for('student_drives'))


@app.route('/student/my-applications')
def student_applications():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE user_id = ?", (session['user_id'],))
    student = cursor.fetchone()

    cursor.execute('''
        SELECT applications.id, applications.application_date, applications.status,
               placement_drives.job_title, placement_drives.salary,
               placement_drives.location, placement_drives.application_deadline,
               companies.company_name
        FROM applications
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        JOIN companies ON placement_drives.company_id = companies.id
        WHERE applications.student_id = ?
        ORDER BY applications.application_date DESC
    ''', (student['id'],))

    applications = cursor.fetchall()
    conn.close()

    return render_template('student_applications.html',
                           applications=applications,
                           student=student)


@app.route('/student/profile', methods=['GET', 'POST'])
def student_profile():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))


    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT students.*, users.email
        FROM students
        JOIN users ON students.user_id = users.id
        WHERE students.user_id = ?
    ''', (session['user_id'],))
    student = cursor.fetchone()

    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        degree = request.form.get('degree')
        branch = request.form.get('branch')
        cgpa = request.form.get('cgpa')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        resume = student['resume']
        profile_picture = student['profile_picture']

        # Handle resume upload
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"resume_{session['user_id']}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                resume = filename

        # Handle profile picture upload
        if 'profile_picture' in request.files:
            pic = request.files['profile_picture']
            if pic and pic.filename != '' and allowed_image(pic.filename):
                pic_filename = secure_filename(pic.filename)
                ext = pic_filename.rsplit('.', 1)[1].lower()
                pic_filename = f"profile_{session['user_id']}.{ext}"
                pic.save(os.path.join(app.config['UPLOAD_FOLDER'], pic_filename))
                profile_picture = pic_filename

        cursor.execute('''
            UPDATE students
            SET name = ?, phone = ?, degree = ?, branch = ?, cgpa = ?, resume = ?, profile_picture = ?
            WHERE user_id = ?
        ''', (name, phone, degree, branch, cgpa, resume, profile_picture, session['user_id']))

        if new_password:
            if new_password == confirm_password:
                hashed_password = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password = ? WHERE id = ?",
                               (hashed_password, session['user_id']))
                flash('Password updated successfully!', 'success')
            else:
                flash('Passwords do not match!', 'danger')
                conn.close()
                return redirect(url_for('student_profile'))

        conn.commit()
        conn.close()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('student_profile'))

    conn.close()
    return render_template('student_profile.html', student=student)


# =====================
# COMPANY ROUTES
# =====================

@app.route('/company-register', methods=['GET', 'POST'])
def company_register():
    if request.method == 'POST':
        company_name = request.form.get('company_name')
        email = request.form.get('email')
        password = request.form.get('password')
        hr_name = request.form.get('hr_name')
        hr_contact = request.form.get('hr_contact')
        website = request.form.get('website')

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Email already registered!', 'danger')
            conn.close()
            return redirect(url_for('company_register'))

        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
            (email, hashed_password, 'company')
        )
        user_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO companies (user_id, company_name, hr_name, hr_contact, website, approval_status) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, company_name, hr_name, hr_contact, website, 'pending')
        )

        conn.commit()
        conn.close()

        flash('Registration successful! Please wait for admin approval before logging in.', 'success')
        return redirect(url_for('login'))

    return render_template('company_register.html')


@app.route('/company/dashboard')
def company_dashboard():
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT companies.*, users.email
        FROM companies
        JOIN users ON companies.user_id = users.id
        WHERE companies.user_id = ?
    ''', (session['user_id'],))
    company = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as count FROM placement_drives WHERE company_id = ?", (company['id'],))
    total_drives = cursor.fetchone()['count']

    cursor.execute('''
        SELECT COUNT(*) as count FROM applications
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        WHERE placement_drives.company_id = ?
    ''', (company['id'],))
    total_applications = cursor.fetchone()['count']

    cursor.execute('''
        SELECT COUNT(*) as count FROM applications
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        WHERE placement_drives.company_id = ? AND applications.status = 'selected'
    ''', (company['id'],))
    total_selected = cursor.fetchone()['count']

    conn.close()

    return render_template('company_dashboard.html',
                           company=company,
                           total_drives=total_drives,
                           total_applications=total_applications,
                           total_selected=total_selected)


@app.route('/company/drives')
def company_drives():
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM companies WHERE user_id = ?", (session['user_id'],))
    company = cursor.fetchone()

    cursor.execute('''
        SELECT * FROM placement_drives
        WHERE company_id = ?
        ORDER BY created_at DESC
    ''', (company['id'],))

    drives = cursor.fetchall()
    conn.close()

    return render_template('company_drives.html', drives=drives, company=company)


@app.route('/company/create-drive', methods=['GET', 'POST'])
def create_drive():
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM companies WHERE user_id = ?", (session['user_id'],))
    company = cursor.fetchone()

    if request.method == 'POST':
        job_title = request.form.get('job_title')
        job_description = request.form.get('job_description')
        eligibility_criteria = request.form.get('eligibility_criteria')
        salary = request.form.get('salary')
        location = request.form.get('location')
        application_deadline = request.form.get('application_deadline')

        cursor.execute('''
            INSERT INTO placement_drives
            (company_id, job_title, job_description, eligibility_criteria,
             salary, location, application_deadline, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (company['id'], job_title, job_description, eligibility_criteria,
              salary, location, application_deadline, 'pending'))

        conn.commit()
        conn.close()

        flash('Placement drive created! Waiting for admin approval.', 'success')
        return redirect(url_for('company_dashboard'))

    conn.close()
    return render_template('company_create_drive.html', company=company)


@app.route('/company/drive-applications/<int:drive_id>')
def drive_applications(drive_id):
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM companies WHERE user_id = ?", (session['user_id'],))
    company = cursor.fetchone()

    cursor.execute("SELECT * FROM placement_drives WHERE id = ? AND company_id = ?",
                   (drive_id, company['id']))
    drive = cursor.fetchone()

    if not drive:
        flash('Drive not found!', 'danger')
        conn.close()
        return redirect(url_for('company_drives'))

    cursor.execute('''
        SELECT applications.*, students.name, students.phone,
               students.degree, students.branch, students.cgpa, students.resume,
               users.email
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN users ON students.user_id = users.id
        WHERE applications.drive_id = ?
        ORDER BY applications.application_date DESC
    ''', (drive_id,))

    applications = cursor.fetchall()
    conn.close()

    return render_template('company_drive_applications.html',
                           applications=applications,
                           drive=drive,
                           company=company)


@app.route('/company/shortlist-application/<int:application_id>')
def shortlist_application(application_id):
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status = 'shortlisted' WHERE id = ?", (application_id,))
    conn.commit()

    cursor.execute("SELECT drive_id FROM applications WHERE id = ?", (application_id,))
    app_row = cursor.fetchone()
    conn.close()

    flash('Student shortlisted!', 'success')
    return redirect(url_for('drive_applications', drive_id=app_row['drive_id']))


@app.route('/company/select-application/<int:application_id>')
def select_application(application_id):
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status = 'selected' WHERE id = ?", (application_id,))
    conn.commit()

    cursor.execute("SELECT drive_id FROM applications WHERE id = ?", (application_id,))
    app_row = cursor.fetchone()
    conn.close()

    flash('Student selected!', 'success')
    return redirect(url_for('drive_applications', drive_id=app_row['drive_id']))


@app.route('/company/reject-application/<int:application_id>')
def reject_application(application_id):
    if 'user_id' not in session or session.get('role') != 'company':
        flash('Please login as company first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status = 'rejected' WHERE id = ?", (application_id,))
    conn.commit()

    cursor.execute("SELECT drive_id FROM applications WHERE id = ?", (application_id,))
    app_row = cursor.fetchone()
    conn.close()

    flash('Student rejected!', 'warning')
    return redirect(url_for('drive_applications', drive_id=app_row['drive_id']))


# =====================
# DEBUG ROUTES
# =====================

@app.route('/debug-login')
def debug_login():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, role FROM users")
    users = cursor.fetchall()
    conn.close()
    result = "<h2>All Users in Database:</h2>"
    for user in users:
        result += f"<p>ID: {user['id']} | Email: {user['email']} | Role: {user['role']}</p>"
    return result


@app.route('/debug/check-student')
def debug_check_student():
    if 'user_id' not in session:
        return "No user_id in session - You're not logged in!"

    if session.get('role') != 'student':
        return f"Role is: {session.get('role')} (not student)"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM students WHERE user_id = ?', (session['user_id'],))
    student = cursor.fetchone()
    conn.close()

    if not student:
        return f"Student with user_id {session['user_id']} NOT FOUND in database!"

    return f"Student found: {student['name']} (ID: {student['id']})"


@app.route('/admin/password-reset-tool')
def password_reset_tool():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT companies.id, companies.company_name, companies.approval_status, users.email
        FROM companies
        JOIN users ON companies.user_id = users.id
    ''')
    companies = cursor.fetchall()
    conn.close()

    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Password Reset Tool</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container mt-5">
            <h2>Company Password Reset Tool</h2>
            <div class="card mt-4">
                <div class="card-body">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>ID</th><th>Company Name</th><th>Email</th><th>Status</th><th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
    '''

    for company in companies:
        html += f'''
            <tr>
                <td>{company['id']}</td>
                <td>{company['company_name']}</td>
                <td>{company['email']}</td>
                <td>{company['approval_status']}</td>
                <td>
                    <a href="/admin/do-reset/{company['id']}" class="btn btn-sm btn-warning">
                        Reset to "company123"
                    </a>
                </td>
            </tr>
        '''

    html += '</tbody></table></div></div></div></body></html>'
    return html


@app.route('/admin/do-reset/<int:company_id>')
def do_reset(company_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()
    if company:
        new_password = generate_password_hash('company123')
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, company['user_id']))
        conn.commit()
    conn.close()
    flash('Password reset to company123!', 'success')
    return redirect(url_for('password_reset_tool'))

@app.route('/admin/analytics')
def admin_analytics():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Please login as admin first!', 'danger')
        return redirect(url_for('login'))
 
    conn = get_db()
    cursor = conn.cursor()
 
    # --- Summary KPIs ---
    cursor.execute("SELECT COUNT(*) as count FROM students WHERE status = 'active'")
    active_students = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM companies WHERE approval_status = 'approved'")
    active_companies = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM applications WHERE status = 'selected'")
    total_placed = cursor.fetchone()['count']
 
    cursor.execute("SELECT COUNT(*) as count FROM students")
    total_students = cursor.fetchone()['count']
 
    placement_rate = round((total_placed / total_students * 100), 1) if total_students > 0 else 0
 
    cursor.execute("SELECT COUNT(*) as count FROM placement_drives WHERE status = 'approved'")
    active_drives = cursor.fetchone()['count']
 
    # --- Applications by status (pie/doughnut chart) ---
    cursor.execute('''
        SELECT status, COUNT(*) as count
        FROM applications
        GROUP BY status
        ORDER BY count DESC
    ''')
    status_rows = cursor.fetchall()
    status_labels = [r['status'].capitalize() for r in status_rows]
    status_counts = [r['count'] for r in status_rows]
 
    # --- Monthly applications trend (last 6 months) ---
    cursor.execute('''
        SELECT strftime('%Y-%m', application_date) as month, COUNT(*) as count
        FROM applications
        GROUP BY month
        ORDER BY month ASC
        LIMIT 6
    ''')
    monthly_rows = cursor.fetchall()
    monthly_labels = [r['month'] for r in monthly_rows]
    monthly_counts = [r['count'] for r in monthly_rows]
 
    # --- Branch-wise placement stats ---
    cursor.execute('''
        SELECT
            students.branch,
            COUNT(DISTINCT students.id) as total,
            COUNT(DISTINCT CASE WHEN applications.status = 'selected' THEN students.id END) as placed
        FROM students
        LEFT JOIN applications ON students.id = applications.student_id
        WHERE students.branch IS NOT NULL AND students.branch != ''
        GROUP BY students.branch
        ORDER BY total DESC
    ''')
    branch_rows = cursor.fetchall()
    branch_labels = [r['branch'] for r in branch_rows]
    branch_totals = [r['total'] for r in branch_rows]
    branch_placed = [r['placed'] for r in branch_rows]
 
    # --- Top 5 companies by applications received ---
    cursor.execute('''
        SELECT companies.company_name, COUNT(applications.id) as count
        FROM applications
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        JOIN companies ON placement_drives.company_id = companies.id
        GROUP BY companies.id
        ORDER BY count DESC
        LIMIT 5
    ''')
    company_rows = cursor.fetchall()
    company_labels = [r['company_name'] for r in company_rows]
    company_counts = [r['count'] for r in company_rows]
 
    # --- Degree distribution ---
    cursor.execute('''
        SELECT degree, COUNT(*) as count
        FROM students
        WHERE degree IS NOT NULL AND degree != ''
        GROUP BY degree
        ORDER BY count DESC
    ''')
    degree_rows = cursor.fetchall()
    degree_labels = [r['degree'] for r in degree_rows]
    degree_counts = [r['count'] for r in degree_rows]
 
    # --- Recent activity feed ---
    cursor.execute('''
        SELECT
            'application' as type,
            students.name as actor,
            companies.company_name as target,
            applications.application_date as ts,
            applications.status as status
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN placement_drives ON applications.drive_id = placement_drives.id
        JOIN companies ON placement_drives.company_id = companies.id
        ORDER BY applications.application_date DESC
        LIMIT 8
    ''')
    recent_activity = cursor.fetchall()
 
    conn.close()
 
    return render_template('admin_analytics.html',
        # KPIs
        active_students=active_students,
        active_companies=active_companies,
        total_placed=total_placed,
        placement_rate=placement_rate,
        active_drives=active_drives,
        # Charts
        status_labels=status_labels,
        status_counts=status_counts,
        monthly_labels=monthly_labels,
        monthly_counts=monthly_counts,
        branch_labels=branch_labels,
        branch_totals=branch_totals,
        branch_placed=branch_placed,
        company_labels=company_labels,
        company_counts=company_counts,
        degree_labels=degree_labels,
        degree_counts=degree_counts,
        # Feed
        recent_activity=recent_activity,
    )
 

# =====================
# MOCK INTERVIEW ROUTES
# =====================

@app.route('/student/interview')
def student_interview():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT students.*, users.email
        FROM students JOIN users ON students.user_id = users.id
        WHERE students.user_id = ?
    ''', (session['user_id'],))
    student = cursor.fetchone()
    conn.close()

    return render_template('student_interview.html', student=student)


@app.route('/student/interview/chat', methods=['POST'])
def interview_chat():
    if 'user_id' not in session or session.get('role') != 'student':
        return {'error': 'Unauthorized'}, 401

    data = request.get_json()
    messages = data.get('messages', [])
    student_name = data.get('student_name', 'Student')
    student_branch = data.get('student_branch', '')
    student_degree = data.get('student_degree', '')
    interview_type = data.get('interview_type', 'technical')

    import requests as req

    system_prompt = f"""You are a strict, experienced technical interviewer conducting a mock placement interview for {student_name}, a {student_degree} student from {student_branch}.

Interview type: {interview_type}

Your behavior:
- Ask ONE question at a time. Wait for their answer before proceeding.
- Start with an introduction and then ask your first question.
- Be realistic — not too easy, not impossible. Match difficulty to their level ({student_degree}, {student_branch}).
- After each answer, give BRIEF feedback (1-2 lines): what was good, what was missing.
- Keep a mental score. After 6-8 questions, wrap up with a FINAL EVALUATION in this exact format:

---FINAL EVALUATION---
Overall Score: X/10
Strengths: [list 2-3]
Weaknesses: [list 2-3]
Verdict: [Ready for placement / Needs more preparation / Strong candidate]
Top Tip: [one actionable advice]
---END EVALUATION---

Interview types and focus:
- technical: DSA, OS, DBMS, CN, OOP concepts
- hr: behavioral, communication, situational questions
- aptitude: logical reasoning, quant, verbal

Rules:
- Never break character as an interviewer
- Be encouraging but honest
- If answer is wrong, gently correct after acknowledging their attempt
- Track question count internally; end the interview after 6-8 questions with the final evaluation"""

    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

    try:
        response = req.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GROQ_API_KEY}'
            },
            json={
                'model': 'llama-3.1-8b-instant',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    *messages
                ],
                'max_tokens': 1000,
                'temperature': 0.7
            },
            timeout=30
        )

        print("Groq status:", response.status_code)
        print("Groq response:", response.text[:300])

        result = response.json()

        if 'choices' in result:
            reply = result['choices'][0]['message']['content']
        elif 'error' in result:
            print("Groq error:", result['error'])
            reply = f"API Error: {result['error'].get('message', 'Unknown error')}"
        else:
            reply = 'Sorry, something went wrong. Please try again.'

    except Exception as e:
        print("Exception in interview_chat:", str(e))
        reply = f'Connection error: {str(e)}'

    return {'reply': reply}
# =====================
# RUN APPLICATION
# =====================

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
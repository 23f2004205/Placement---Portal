from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime
import os

# Upload folder settings
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

# Create the Flask application
app = Flask(__name__)

# Secret key for security
app.secret_key = 'my-secret-key-2024'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database file name
DATABASE = 'placement_portal.db'

# Function to connect to database
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

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
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
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
    result = f"<h2>Database Status</h2>"
    result += f"<p>Tables created: {len(tables)}</p>"
    result += f"<p>Table names: {[t['name'] for t in tables]}</p>"
    if admin:
        result += f"<p>✅ Admin exists: {admin['email']}</p>"
    else:
        result += f"<p>❌ No admin found</p>"
    return result

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ? AND role = ?", (email, role))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            
            # Special check for company - must be approved first!
            if role == 'company':
                conn2 = get_db()
                cursor2 = conn2.cursor()
                cursor2.execute("SELECT approval_status FROM companies WHERE user_id = ?", (user['id'],))
                company = cursor2.fetchone()
                conn2.close()
                
                if company and company['approval_status'] == 'pending':
                    flash('Your company registration is pending admin approval!', 'warning')
                    return redirect(url_for('login'))
                elif company and company['approval_status'] == 'rejected':
                    flash('Your company registration has been rejected!', 'danger')
                    return redirect(url_for('login'))
                elif company and company['approval_status'] == 'blacklisted':
                    flash('Your company account has been blacklisted!', 'danger')
                    return redirect(url_for('login'))
            
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            
            flash('Login successful!', 'success')
            
            if role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif role == 'company':
                return redirect(url_for('company_dashboard'))
            elif role == 'student':
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid email, password, or role!', 'danger')
    
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
            cursor.execute("INSERT INTO students (user_id, name, phone, degree, branch, cgpa) VALUES (?, ?, ?, ?, ?, ?)",
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
            cursor.execute("INSERT INTO companies (user_id, company_name, hr_name, hr_contact, website, approval_status) VALUES (?, ?, ?, ?, ?, ?)",
                          (user_id, company_name, hr_name, hr_contact, website, status))
    
    cursor.execute("SELECT id FROM companies WHERE approval_status = 'approved' LIMIT 1")
    company = cursor.fetchone()
    
    if company:
        drives_data = [
            (company['id'], 'Software Engineer', 'Develop web applications', 'BTech CSE, CGPA > 7.0', '15 LPA', 'Bangalore', '2026-03-30', 'approved'),
            (company['id'], 'Data Analyst', 'Analyze business data', 'BTech/MTech, CGPA > 7.5', '12 LPA', 'Hyderabad', '2026-04-15', 'pending'),
        ]
        for company_id, job_title, job_desc, criteria, salary, location, deadline, status in drives_data:
            cursor.execute("INSERT INTO placement_drives (company_id, job_title, job_description, eligibility_criteria, salary, location, application_deadline, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
    cursor.execute("SELECT COUNT(*) as count FROM students")
    total_students = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM companies")
    total_companies = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM placement_drives")
    total_drives = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM applications")
    total_applications = cursor.fetchone()['count']
    conn.close()
    
    return render_template('admin_dashboard.html',
                         students=total_students,
                         companies=total_companies,
                         drives=total_drives,
                         applications=total_applications)

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

@app.route('/student/drives')
def student_drives():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM students WHERE user_id = ?", (session['user_id'],))
    student = cursor.fetchone()
    
    cursor.execute('''
        SELECT placement_drives.*, companies.company_name
        FROM placement_drives
        JOIN companies ON placement_drives.company_id = companies.id
        WHERE placement_drives.status = 'approved'
        ORDER BY placement_drives.application_deadline ASC
    ''')
    
    drives = cursor.fetchall()
    conn.close()
    
    return render_template('student_drives.html', drives=drives, student=student)

@app.route('/student/apply/<int:drive_id>')
def apply_drive(drive_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as student first!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM students WHERE user_id = ?", (session['user_id'],))
    student = cursor.fetchone()
    
    cursor.execute("SELECT * FROM applications WHERE student_id = ? AND drive_id = ?", 
                  (student['id'], drive_id))
    existing = cursor.fetchone()
    
    if existing:
        flash('You have already applied for this drive!', 'warning')
        conn.close()
        return redirect(url_for('student_drives'))
    
    if student['status'] == 'blacklisted':
        flash('Your account is blacklisted. You cannot apply!', 'danger')
        conn.close()
        return redirect(url_for('student_drives'))
    
    cursor.execute(
        "INSERT INTO applications (student_id, drive_id, status) VALUES (?, ?, ?)",
        (student['id'], drive_id, 'applied')
    )
    
    conn.commit()
    conn.close()
    
    flash('Application submitted successfully!', 'success')
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
        
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                filename = f"resume_{session['user_id']}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                resume = filename
        
        cursor.execute('''
            UPDATE students 
            SET name = ?, phone = ?, degree = ?, branch = ?, cgpa = ?, resume = ?
            WHERE user_id = ?
        ''', (name, phone, degree, branch, cgpa, resume, session['user_id']))
        
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
    app = cursor.fetchone()
    conn.close()
    
    flash('Student shortlisted!', 'success')
    return redirect(url_for('drive_applications', drive_id=app['drive_id']))

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
    app = cursor.fetchone()
    conn.close()
    
    flash('Student selected!', 'success')
    return redirect(url_for('drive_applications', drive_id=app['drive_id']))

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
    app = cursor.fetchone()
    conn.close()
    
    flash('Student rejected!', 'warning')
    return redirect(url_for('drive_applications', drive_id=app['drive_id']))


@app.route('/admin/password-reset-tool')
def password_reset_tool():
    from werkzeug.security import generate_password_hash
    
    conn = sqlite3.connect('placement_portal.db')
    cursor = conn.cursor()
    
    # Get all companies
    cursor.execute('SELECT id, company_name, email, approval_status FROM companies')
    companies = cursor.fetchall()
    
    # Build HTML page
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
                                <th>ID</th>
                                <th>Company Name</th>
                                <th>Email</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
    '''
    
    for company in companies:
        html += f'''
            <tr>
                <td>{company[0]}</td>
                <td>{company[1]}</td>
                <td>{company[2]}</td>
                <td>{company[3]}</td>
                <td>
                    <a href="/admin/do-reset/{company[0]}" class="btn btn-sm btn-warning">
                        Reset to "company123"
                    </a>
                </td>
            </tr>
        '''
    
    html += '''
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    
    conn.close()
    return html



# =====================
# RUN APPLICATION
# =====================

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True, port=5000)











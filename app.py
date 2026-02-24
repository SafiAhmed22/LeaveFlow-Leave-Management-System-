from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from typing import Optional, Dict, Any
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

# NOTE: For production, set this via environment variable.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'leave_management_system.db')

def get_db_connection():
    """Create and return a database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn


def _token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="leaveflow-auth")


def create_auth_token(payload: dict) -> str:
    return _token_serializer().dumps(payload)


def verify_auth_token(token: str, max_age_seconds: int = 60 * 60 * 24) -> Optional[Dict[str, Any]]:
    try:
        return _token_serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


@app.route("/api/auth/login", methods=["POST"])
def login():
    """
    Login for Admin or Employee.
    - Admin credentials are stored in `admin_users` (username='admin', hashed password).
    - Employee credentials are stored in `employee_users` (hashed password).
    Returns a signed token to store on frontend.
    """
    try:
        data = request.get_json() or {}
        role = (data.get("role") or "").strip().lower()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        remember = bool(data.get("remember", False))

        if role not in {"admin", "employee"}:
            return jsonify({"error": "Invalid role", "message": "Role must be admin or employee"}), 400
        if not username or not password:
            return jsonify({"error": "Missing credentials", "message": "Username and password are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        if role == "admin":
            cursor.execute(
                "SELECT id, username, password, full_name, role FROM admin_users WHERE username = ? LIMIT 1",
                (username,),
            )
            row = cursor.fetchone()
            if not row or not check_password_hash(row["password"], password):
                conn.close()
                return jsonify({"error": "Unauthorized", "message": "Invalid username or password"}), 401

            token = create_auth_token(
                {"role": "admin", "adminId": row["id"], "username": row["username"]}
            )
            conn.close()
            return jsonify(
                {
                    "success": True,
                    "role": "admin",
                    "token": token,
                    "redirect": "dashboard.html",
                    "admin": {"id": row["id"], "username": row["username"], "fullName": row["full_name"]},
                    "expiresInSeconds": 60 * 60 * 24 * (30 if remember else 1),
                }
            ), 200

        # role == "employee"
        cursor.execute(
            "SELECT employee_id, username, password FROM employee_users WHERE username = ? LIMIT 1",
            (username,),
        )
        row = cursor.fetchone()
        if not row or not check_password_hash(row["password"], password):
            conn.close()
            return jsonify({"error": "Unauthorized", "message": "Invalid username or password"}), 401

        employee_id = int(row["employee_id"])
        token = create_auth_token({"role": "employee", "employeeId": employee_id, "username": row["username"]})
        conn.close()
        return jsonify(
            {
                "success": True,
                "role": "employee",
                "token": token,
                "redirect": "employee-profile.html",
                "employee": {"id": employee_id, "username": row["username"]},
                "expiresInSeconds": 60 * 60 * 24 * (30 if remember else 1),
            }
        ), 200

    except Exception as e:
        return jsonify({"error": "Login failed", "message": str(e)}), 500


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    """Optional helper: validate token and return identity."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized", "message": "Missing Bearer token"}), 401
    token = auth.removeprefix("Bearer ").strip()
    payload = verify_auth_token(token, max_age_seconds=60 * 60 * 24 * 30)
    if not payload:
        return jsonify({"error": "Unauthorized", "message": "Invalid or expired token"}), 401
    return jsonify({"success": True, "user": payload}), 200

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics: total, active, on leave, and overdue employees"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        today = datetime.today().date()
        
        # 1️⃣ Total Employees
        cursor.execute("SELECT COUNT(*) FROM employees")
        total_employees = cursor.fetchone()[0]
        
        # 2️⃣ Employees Currently On Leave
        cursor.execute("""
            SELECT COUNT(DISTINCT employee_id)
            FROM leaves
            WHERE status = 'Approved'
            AND returned = 'No'
            AND start_date <= ?
            AND end_date >= ?
        """, (today, today))
        on_leave = cursor.fetchone()[0]
        
        # 3️⃣ Active Employees (present)
        active = total_employees - on_leave
        
        conn.close()
        
        return jsonify({
            'total': total_employees,
            'active': active,
            'onLeave': on_leave
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch dashboard stats',
            'message': str(e)
        }), 500

@app.route('/api/employees/all', methods=['GET'])
def get_all_employees():
    """Get all employees"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, position, department, phone, email FROM employees ORDER BY name")
        employees = cursor.fetchall()
        
        conn.close()
        
        return jsonify([{
            'id': emp['id'],
            'name': emp['name'],
            'position': emp['position'],
            'department': emp['department'],
            'phone': emp['phone'],
            'email': emp['email'],
            'status': 'active'
        } for emp in employees]), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch employees',
            'message': str(e)
        }), 500

@app.route('/api/employees/leave', methods=['GET'])
def get_employees_on_leave():
    """Get employees currently on leave"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        today = datetime.today().date()
        
        query = """
            SELECT e.id, e.name, e.position, e.department, l.start_date, l.end_date, l.applied_on, l.reason
            FROM employees e
            JOIN leaves l ON e.id = l.employee_id
            WHERE l.status = 'Approved' AND l.returned = 'No'
            AND l.start_date <= ? AND l.end_date >= ?
            ORDER BY l.start_date
        """
        cursor.execute(query, (today, today))
        employees = cursor.fetchall()
        
        conn.close()
        
        return jsonify([{
            'id': emp['id'],
            'name': emp['name'],
            'position': emp['position'],
            'department': emp['department'],
            'startDate': emp['start_date'],
            'endDate': emp['end_date'],
            'appliedOn': emp['applied_on'],
            'reason': emp['reason'],
            'status': 'on_leave'
        } for emp in employees]), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch employees on leave',
            'message': str(e)
        }), 500

@app.route('/api/employees/present', methods=['GET'])
def get_present_employees():
    """Get employees currently present (not on leave)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        today = datetime.today().date()
        
        query = """
            SELECT e.id, e.name, e.position, e.department, e.phone, e.email
            FROM employees e
            LEFT JOIN leaves l ON e.id = l.employee_id
            AND l.status = 'Approved' AND l.returned = 'No'
            AND l.start_date <= ? AND l.end_date >= ?
            WHERE l.employee_id IS NULL
            GROUP BY e.id
            ORDER BY e.name
        """
        cursor.execute(query, (today, today))
        employees = cursor.fetchall()
        
        conn.close()
        
        return jsonify([{
            'id': emp['id'],
            'name': emp['name'],
            'position': emp['position'],
            'department': emp['department'],
            'phone': emp['phone'],
            'email': emp['email'],
            'status': 'present'
        } for emp in employees]), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch present employees',
            'message': str(e)
        }), 500

@app.route('/api/dashboard/positions', methods=['GET'])
def get_position_counts():
    """Get employee counts grouped by position"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count employees by position
        cursor.execute("""
            SELECT position, COUNT(*) as count
            FROM employees
            GROUP BY position
            ORDER BY count DESC
        """)
        results = cursor.fetchall()
        
        conn.close()
        
        # Extract positions and counts into separate lists
        positions = [row['position'] for row in results]
        counts = [int(row['count']) for row in results]
        
        return jsonify({
            'positions': positions,
            'counts': counts
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch position counts',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>', methods=['GET'])
def get_employee(employee_id):
    """Get employee details by ID (search employee)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch employee details
        cursor.execute("""
            SELECT id, name, gender, age, position, department, phone, email, status
            FROM employees
            WHERE id = ?
        """, (employee_id,))
        
        employee = cursor.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'No employee found with ID: {employee_id}'
            }), 404
        
        # Fetch leave history
        cursor.execute("""
            SELECT start_date, end_date, leave_days, remaining_days, reason, status, returned, actual_return_date
            FROM leaves
            WHERE employee_id = ?
            ORDER BY start_date DESC
        """, (employee_id,))
        
        leaves = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'id': employee['id'],
            'name': employee['name'],
            'gender': employee['gender'],
            'age': employee['age'],
            'position': employee['position'],
            'department': employee['department'],
            'phone': employee['phone'],
            'email': employee['email'],
            'status': employee['status'],
            'leaveHistory': [{
                'startDate': leave['start_date'],
                'endDate': leave['end_date'],
                'leaveDays': leave['leave_days'],
                'remainingDays': leave['remaining_days'],
                'reason': leave['reason'],
                'status': leave['status'],
                'returned': leave['returned'],
                'actualReturnDate': leave['actual_return_date']
            } for leave in leaves]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch employee',
            'message': str(e)
        }), 500

@app.route('/api/employees', methods=['POST'])
def add_employee():
    """Add a new employee"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'gender', 'age', 'position', 'department', 'phone', 'email', 'status']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'error': 'Missing required field',
                    'message': f'{field} is required'
                }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert into employees table
        cursor.execute("""
            INSERT INTO employees (name, gender, age, position, department, phone, email, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['name'],
            data['gender'],
            int(data['age']),
            data['position'],
            data['department'],
            data['phone'],
            data['email'],
            data['status']
        ))
        conn.commit()
        
        # Get the new employee ID
        employee_id = cursor.lastrowid
        
        # Create employee login credentials
        username = f"user{employee_id}"
        password_plain = f"pass{employee_id}"
        password_hashed = generate_password_hash(password_plain)
        
        cursor.execute("""
            INSERT INTO employee_users (employee_id, username, password)
            VALUES (?, ?, ?)
        """, (employee_id, username, password_hashed))
        conn.commit()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Employee added successfully',
            'employee': {
                'id': employee_id,
                'name': data['name'],
                'username': username,
                'password': password_plain
            }
        }), 201
        
    except ValueError as e:
        return jsonify({
            'error': 'Invalid input',
            'message': f'Age must be a number: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'error': 'Failed to add employee',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>', methods=['PUT'])
def update_employee(employee_id):
    """Update employee details"""
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if employee exists
        cursor.execute("SELECT name FROM employees WHERE id = ?", (employee_id,))
        employee = cursor.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'No employee found with ID: {employee_id}'
            }), 404
        
        # Fetch current details
        cursor.execute("""
            SELECT name, gender, age, position, department, phone, email, status
            FROM employees
            WHERE id = ?
        """, (employee_id,))
        current = cursor.fetchone()
        
        # Update only provided fields (leave blank fields unchanged)
        name = data.get('name', current['name'])
        gender = data.get('gender', current['gender'])
        age = data.get('age', current['age'])
        position = data.get('position', current['position'])
        department = data.get('department', current['department'])
        phone = data.get('phone', current['phone'])
        email = data.get('email', current['email'])
        status = data.get('status', current['status'])
        
        # Update in database
        cursor.execute("""
            UPDATE employees
            SET name = ?, gender = ?, age = ?, position = ?, department = ?, phone = ?, email = ?, status = ?
            WHERE id = ?
        """, (name, gender, int(age), position, department, phone, email, status, employee_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Employee updated successfully',
            'employee': {
                'id': employee_id,
                'name': name,
                'gender': gender,
                'age': age,
                'position': position,
                'department': department,
                'phone': phone,
                'email': email,
                'status': status
            }
        }), 200
        
    except ValueError as e:
        return jsonify({
            'error': 'Invalid input',
            'message': f'Age must be a number: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'error': 'Failed to update employee',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>', methods=['DELETE'])
def delete_employee(employee_id):
    """Delete an employee"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if employee exists
        cursor.execute("SELECT name FROM employees WHERE id = ?", (employee_id,))
        employee = cursor.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'No employee found with ID: {employee_id}'
            }), 404
        
        employee_name = employee['name']
        
        # Delete from leaves first (foreign key constraint)
        cursor.execute("DELETE FROM leaves WHERE employee_id = ?", (employee_id,))
        
        # Delete from employee_users table
        cursor.execute("DELETE FROM employee_users WHERE employee_id = ?", (employee_id,))
        
        # Delete from employees
        cursor.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Employee {employee_name} (ID: {employee_id}) has been deleted successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to delete employee',
            'message': str(e)
        }), 500

@app.route('/api/leave-requests', methods=['GET'])
def get_leave_requests():
    """Get leave requests filtered by status"""
    try:
        status_filter = request.args.get('status', 'all')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query based on status filter
        if status_filter == 'pending':
            query = """
                SELECT l.leave_id, e.id as employee_id, e.name, e.position, e.department, 
                       l.start_date, l.end_date, l.leave_days, l.reason, l.status, l.applied_on
                FROM employees e
                JOIN leaves l ON e.id = l.employee_id
                WHERE l.status = 'Pending'
                ORDER BY l.applied_on DESC
            """
            cursor.execute(query)
        elif status_filter == 'approved':
            query = """
                SELECT l.leave_id, e.id as employee_id, e.name, e.position, e.department, 
                       l.start_date, l.end_date, l.leave_days, l.reason, l.status, l.applied_on
                FROM employees e
                JOIN leaves l ON e.id = l.employee_id
                WHERE l.status = 'Approved'
                ORDER BY l.applied_on DESC
            """
            cursor.execute(query)
        elif status_filter == 'rejected':
            query = """
                SELECT l.leave_id, e.id as employee_id, e.name, e.position, e.department, 
                       l.start_date, l.end_date, l.leave_days, l.reason, l.status, l.applied_on
                FROM employees e
                JOIN leaves l ON e.id = l.employee_id
                WHERE l.status = 'Rejected'
                ORDER BY l.applied_on DESC
            """
            cursor.execute(query)
        else:  # all
            query = """
                SELECT l.leave_id, e.id as employee_id, e.name, e.position, e.department, 
                       l.start_date, l.end_date, l.leave_days, l.reason, l.status, l.applied_on
                FROM employees e
                JOIN leaves l ON e.id = l.employee_id
                ORDER BY l.applied_on DESC
            """
            cursor.execute(query)
        
        leaves = cursor.fetchall()
        conn.close()
        
        return jsonify([{
            'leaveId': leave['leave_id'],
            'employeeId': leave['employee_id'],
            'name': leave['name'],
            'position': leave['position'],
            'department': leave['department'],
            'startDate': leave['start_date'],
            'endDate': leave['end_date'],
            'leaveDays': leave['leave_days'],
            'reason': leave['reason'],
            'status': leave['status'].lower(),  # Convert to lowercase for frontend
            'appliedOn': leave['applied_on']
        } for leave in leaves]), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch leave requests',
            'message': str(e)
        }), 500

@app.route('/api/leave-requests/<int:leave_id>/approve', methods=['PATCH'])
def approve_leave_request(leave_id):
    """Approve a leave request by leave_id"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if leave exists
        cursor.execute("SELECT employee_id, status FROM leaves WHERE leave_id = ?", (leave_id,))
        leave = cursor.fetchone()
        
        if not leave:
            conn.close()
            return jsonify({
                'error': 'Leave request not found',
                'message': f'No leave request found with ID: {leave_id}'
            }), 404
        
        if leave['status'] != 'Pending':
            conn.close()
            return jsonify({
                'error': 'Invalid status',
                'message': f'Leave request is already {leave["status"]}'
            }), 400
        
        # Update leave status
        cursor.execute("""
            UPDATE leaves
            SET status = ?, returned = ?
            WHERE leave_id = ?
        """, ('Approved', 'No', leave_id))
        
        conn.commit()
        
        # Get employee name for response
        cursor.execute("SELECT name FROM employees WHERE id = ?", (leave['employee_id'],))
        employee = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Leave for {employee["name"]} has been APPROVED',
            'leaveId': leave_id
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to approve leave request',
            'message': str(e)
        }), 500

@app.route('/api/leave-requests/<int:leave_id>/reject', methods=['PATCH'])
def reject_leave_request(leave_id):
    """Reject a leave request by leave_id"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if leave exists
        cursor.execute("SELECT employee_id, status FROM leaves WHERE leave_id = ?", (leave_id,))
        leave = cursor.fetchone()
        
        if not leave:
            conn.close()
            return jsonify({
                'error': 'Leave request not found',
                'message': f'No leave request found with ID: {leave_id}'
            }), 404
        
        if leave['status'] != 'Pending':
            conn.close()
            return jsonify({
                'error': 'Invalid status',
                'message': f'Leave request is already {leave["status"]}'
            }), 400
        
        # Update leave status
        cursor.execute("""
            UPDATE leaves
            SET status = ?, returned = ?
            WHERE leave_id = ?
        """, ('Rejected', 'Yes', leave_id))
        
        conn.commit()
        
        # Get employee name for response
        cursor.execute("SELECT name FROM employees WHERE id = ?", (leave['employee_id'],))
        employee = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Leave for {employee["name"]} has been REJECTED',
            'leaveId': leave_id
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to reject leave request',
            'message': str(e)
        }), 500

@app.route('/api/leave-requests/by-employee/<int:employee_id>/approve', methods=['POST'])
def approve_leave_by_employee(employee_id):
    """Approve pending leave request by employee ID (quick action)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch pending leave for this employee
        cursor.execute("""
            SELECT l.leave_id, e.name
            FROM employees e
            JOIN leaves l ON e.id = l.employee_id
            WHERE e.id = ? AND l.status = 'Pending'
            ORDER BY l.applied_on DESC
            LIMIT 1
        """, (employee_id,))
        
        leave_record = cursor.fetchone()
        
        if not leave_record:
            conn.close()
            return jsonify({
                'error': 'No pending leave found',
                'message': f'No pending leave found for Employee ID: {employee_id}'
            }), 404
        
        leave_id = leave_record['leave_id']
        employee_name = leave_record['name']
        
        # Update leave status
        cursor.execute("""
            UPDATE leaves
            SET status = ?, returned = ?
            WHERE leave_id = ?
        """, ('Approved', 'No', leave_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Leave for {employee_name} has been APPROVED',
            'leaveId': leave_id
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to approve leave',
            'message': str(e)
        }), 500

@app.route('/api/leave-requests/by-employee/<int:employee_id>/reject', methods=['POST'])
def reject_leave_by_employee(employee_id):
    """Reject pending leave request by employee ID (quick action)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch pending leave for this employee
        cursor.execute("""
            SELECT l.leave_id, e.name
            FROM employees e
            JOIN leaves l ON e.id = l.employee_id
            WHERE e.id = ? AND l.status = 'Pending'
            ORDER BY l.applied_on DESC
            LIMIT 1
        """, (employee_id,))
        
        leave_record = cursor.fetchone()
        
        if not leave_record:
            conn.close()
            return jsonify({
                'error': 'No pending leave found',
                'message': f'No pending leave found for Employee ID: {employee_id}'
            }), 404
        
        leave_id = leave_record['leave_id']
        employee_name = leave_record['name']
        
        # Update leave status
        cursor.execute("""
            UPDATE leaves
            SET status = ?, returned = ?
            WHERE leave_id = ?
        """, ('Rejected', 'Yes', leave_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Leave for {employee_name} has been REJECTED',
            'leaveId': leave_id
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to reject leave',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>/profile', methods=['GET'])
def get_employee_profile(employee_id):
    """Get employee profile with biodata and leave history"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch employee biodata
        cursor.execute("""
            SELECT id, name, gender, age, position, department, phone, email, status
            FROM employees
            WHERE id = ?
        """, (employee_id,))
        
        employee = cursor.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'No employee found with ID: {employee_id}'
            }), 404
        
        # Get username from employee_users table
        cursor.execute("SELECT username FROM employee_users WHERE employee_id = ?", (employee_id,))
        user_row = cursor.fetchone()
        username = user_row['username'] if user_row else None
        
        # Fetch leave history
        cursor.execute("""
            SELECT start_date, end_date, leave_days, remaining_days, reason, status, returned, actual_return_date, applied_on
            FROM leaves
            WHERE employee_id = ?
            ORDER BY leave_id DESC
        """, (employee_id,))
        
        leaves = cursor.fetchall()
        
        # Determine remaining days from latest leave (or default to 20)
        remaining_days = 20  # Default
        if leaves:
            remaining_days = leaves[0]['remaining_days']
        
        conn.close()
        
        return jsonify({
            'employeeId': employee['id'],
            'username': username,
            'name': employee['name'],
            'gender': employee['gender'],
            'age': employee['age'],
            'position': employee['position'],
            'department': employee['department'],
            'phone': employee['phone'],
            'email': employee['email'],
            'status': employee['status'],
            'remainingLeaveBalance': remaining_days,
            'leaveHistory': [{
                'startDate': leave['start_date'],
                'endDate': leave['end_date'],
                'leaveDays': leave['leave_days'],
                'remainingDays': leave['remaining_days'],
                'reason': leave['reason'],
                'status': leave['status'],
                'returned': leave['returned'],
                'actualReturnDate': leave['actual_return_date'],
                'appliedOn': leave['applied_on']
            } for leave in leaves]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch employee profile',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>/leave-balance', methods=['GET'])
def get_employee_leave_balance(employee_id):
    """Get employee leave balance information"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify employee exists
        cursor.execute("SELECT username FROM employee_users WHERE employee_id = ?", (employee_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'Employee ID {employee_id} not found'
            }), 404
        
        # Get latest remaining balance
        cursor.execute("SELECT remaining_days FROM leaves WHERE employee_id = ? ORDER BY leave_id DESC LIMIT 1", (employee_id,))
        last_leave = cursor.fetchone()
        remaining_days = last_leave['remaining_days'] if last_leave else 60  # Default to 60 as user specified
        
        # Calculate total used (60 - remaining)
        total_leave = 60
        used_days = total_leave - remaining_days
        
        # Count pending leave requests
        cursor.execute("SELECT COUNT(*) FROM leaves WHERE employee_id = ? AND status = 'Pending'", (employee_id,))
        pending_count = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'total': total_leave,
            'used': used_days,
            'remaining': remaining_days,
            'pending': pending_count
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch leave balance',
            'message': str(e)
        }), 500

@app.route('/api/leave-requests/apply', methods=['POST'])
def apply_for_leave():
    """Submit a leave application"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['employeeId', 'startDate', 'endDate', 'reason']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'error': 'Missing required field',
                    'message': f'{field} is required'
                }), 400
        
        employee_id = int(data['employeeId'])
        start_date_str = data['startDate']
        end_date_str = data['endDate']
        reason = data['reason']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify Employee Exists
        cursor.execute("SELECT username FROM employee_users WHERE employee_id = ?", (employee_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'Employee ID {employee_id} not found'
            }), 404
        
        # Validate Dates
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            leave_days = (end_date - start_date).days + 1
            
            if leave_days <= 0:
                conn.close()
                return jsonify({
                    'error': 'Invalid dates',
                    'message': 'End date must be after start date'
                }), 400
        except ValueError:
            conn.close()
            return jsonify({
                'error': 'Invalid date format',
                'message': 'Please use YYYY-MM-DD format'
            }), 400
        
        # Check Balance
        cursor.execute("SELECT remaining_days FROM leaves WHERE employee_id = ? ORDER BY leave_id DESC LIMIT 1", (employee_id,))
        last_leave = cursor.fetchone()
        current_balance = last_leave['remaining_days'] if last_leave else 60  # Default to 60
        
        if leave_days > current_balance:
            conn.close()
            return jsonify({
                'error': 'Insufficient balance',
                'message': f'Insufficient leave balance. You have {current_balance} days, requested {leave_days}.'
            }), 400
        
        new_balance = current_balance - leave_days
        applied_on = datetime.now().strftime('%Y-%m-%d')
        
        # Insert Leave
        cursor.execute('''
            INSERT INTO leaves (employee_id, start_date, end_date, leave_days, remaining_days, reason, status, returned, applied_on)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (employee_id, start_date_str, end_date_str, leave_days, new_balance, reason, 'Pending', 'No', applied_on))
        
        conn.commit()
        leave_id = cursor.lastrowid
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Leave application submitted successfully!',
            'leaveId': leave_id,
            'newBalance': new_balance,
            'leaveDays': leave_days
        }), 201
        
    except ValueError as e:
        return jsonify({
            'error': 'Invalid input',
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'error': 'Failed to submit leave application',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>/leave-status', methods=['GET'])
def get_employee_leave_status(employee_id):
    """Get all leave applications status for an employee"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify employee exists
        cursor.execute("SELECT username FROM employee_users WHERE employee_id = ?", (employee_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'Employee ID {employee_id} not found'
            }), 404
        
        # Get all leave applications ordered by leave_id DESC (most recent first)
        cursor.execute("""
            SELECT leave_id, start_date, end_date, leave_days, remaining_days, reason, status, applied_on
            FROM leaves
            WHERE employee_id = ?
            ORDER BY leave_id DESC
        """, (employee_id,))
        
        leaves = cursor.fetchall()
        
        # Get latest leave for remaining balance
        latest_leave = leaves[0] if leaves else None
        remaining_days = latest_leave['remaining_days'] if latest_leave else 60
        
        conn.close()
        
        return jsonify({
            'remainingDays': remaining_days,
            'applications': [{
                'leaveId': leave['leave_id'],
                'startDate': leave['start_date'],
                'endDate': leave['end_date'],
                'leaveDays': leave['leave_days'],
                'remainingDays': leave['remaining_days'],
                'reason': leave['reason'],
                'status': leave['status'],
                'appliedOn': leave['applied_on']
            } for leave in leaves]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch leave status',
            'message': str(e)
        }), 500

@app.route('/api/employees/<int:employee_id>/notifications', methods=['GET'])
def get_employee_notifications(employee_id):
    """Get notifications for an employee based on latest leave status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify employee exists
        cursor.execute("SELECT username FROM employee_users WHERE employee_id = ?", (employee_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'error': 'Employee not found',
                'message': f'Employee ID {employee_id} not found'
            }), 404
        
        # Get latest leave
        cursor.execute("""
            SELECT leave_id, start_date, end_date, leave_days, remaining_days, reason, status, applied_on
            FROM leaves
            WHERE employee_id = ?
            ORDER BY leave_id DESC
            LIMIT 1
        """, (employee_id,))
        
        latest_leave = cursor.fetchone()
        
        notifications = []
        
        if not latest_leave:
            # No leave records
            notifications.append({
                'type': 'info',
                'title': 'No Leave Records',
                'message': 'You have no leave applications yet. Current Balance: 60 days',
                'timestamp': datetime.now().strftime('%Y-%m-%d')
            })
        else:
            status = latest_leave['status']
            end_date_str = latest_leave['end_date']
            
            if status == 'Approved':
                # Calculate return date (end_date + 1 day)
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    return_date = end_date + timedelta(days=1)
                    notifications.append({
                        'type': 'success',
                        'title': 'Leave Application Approved',
                        'message': f'Your leave application has been approved. Please return to work on {return_date.strftime("%Y-%m-%d")}',
                        'timestamp': latest_leave['applied_on']
                    })
                except ValueError:
                    notifications.append({
                        'type': 'success',
                        'title': 'Leave Application Approved',
                        'message': f'Your leave application has been approved. Please return after {end_date_str}',
                        'timestamp': latest_leave['applied_on']
                    })
            
            elif status == 'Rejected':
                notifications.append({
                    'type': 'error',
                    'title': 'Leave Application Rejected',
                    'message': 'Your leave application was rejected. Please contact HR for more information.',
                    'timestamp': latest_leave['applied_on']
                })
            
            elif status == 'Pending':
                notifications.append({
                    'type': 'warning',
                    'title': 'Leave Application Pending',
                    'message': 'Your leave application is currently pending approval. You will be notified once a decision is made.',
                    'timestamp': latest_leave['applied_on']
                })
        
        conn.close()
        
        return jsonify({
            'notifications': notifications
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch notifications',
            'message': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'Flask backend is running'}), 200

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database not found at {DB_PATH}")
    
    app.run(debug=True, port=5000)

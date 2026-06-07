from flask import Flask, render_template, request, session, redirect, url_for, make_response
from config import config
from models import db
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config.from_object(config['default'])
app.secret_key = app.config['SECRET_KEY']

app.config['SESSION_PERMANENT'] = False
app.config['SESSION_COOKIE_NAME'] = 'library_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ========== 登录检查装饰器 ==========
def login_required_student(f):
    def wrapper(*args, **kwargs):
        if 'sno' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def login_required_admin(f):
    def wrapper(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def login_required_any(f):
    def wrapper(*args, **kwargs):
        if 'sno' not in session and 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ========== 辅助函数 ==========
def get_current_borrow_count(sno):
    """获取学生当前借阅数量"""
    result = db.query_one("SELECT GetCurrentBorrowCount(%s) as cnt", (sno,))
    return result['cnt'] if result else 0

def get_student_borrows(sno):
    """获取学生的所有借阅记录（动态计算应还日期和状态）"""
    return db.query("""
        SELECT b.*, bk.bname, bk.author,
               DATE_ADD(b.borrow_date, INTERVAL 30 DAY) as due_date,
               CASE 
                   WHEN b.return_date IS NOT NULL THEN '已归还'
                   WHEN DATE_ADD(b.borrow_date, INTERVAL 30 DAY) < CURDATE() THEN '逾期'
                   ELSE '借阅中'
               END as status
        FROM Borrow b, Book bk
        WHERE b.bid = bk.bid AND b.sno = %s
        ORDER BY b.borrow_date DESC
    """, (sno,))

def get_student_current_borrows(sno):
    """获取学生当前借阅（未还的图书）"""
    return db.query("""
        SELECT b.*, bk.bname, bk.author,
               DATE_ADD(b.borrow_date, INTERVAL 30 DAY) as due_date,
               CASE 
                   WHEN DATE_ADD(b.borrow_date, INTERVAL 30 DAY) < CURDATE() THEN '逾期'
                   ELSE '借阅中'
               END as status,
               GREATEST(DATEDIFF(CURDATE(), DATE_ADD(b.borrow_date, INTERVAL 30 DAY)), 0) as overdue_days
        FROM Borrow b, Book bk
        WHERE b.bid = bk.bid 
          AND b.sno = %s 
          AND b.return_date IS NULL
        ORDER BY b.borrow_date DESC
    """, (sno,))

def get_student_reserves(sno):
    """获取学生的有效预约（在SQL中计算状态）"""
    return db.query("""
        SELECT r.reserve_id, r.sno, r.bid, r.reserve_date, r.take_date,
               bk.bname, bk.author,
               CASE 
                   WHEN r.take_date IS NOT NULL THEN '已取书'
                   WHEN DATE_ADD(r.reserve_date, INTERVAL 7 DAY) < CURDATE() THEN '已过期'
                   ELSE '有效'
               END as status
        FROM Reserve r, Book bk
        WHERE r.bid = bk.bid 
          AND r.sno = %s 
          AND r.take_date IS NULL
          AND DATE_ADD(r.reserve_date, INTERVAL 7 DAY) >= CURDATE()
        ORDER BY r.reserve_date DESC
    """, (sno,))

def get_student_overdues(sno):
    """获取学生的所有逾期记录（动态计算逾期天数和罚款金额）"""
    return db.query("""
        SELECT o.*, bk.bname, bk.author, b.borrow_date, b.bid, b.sno,
               DATE_ADD(b.borrow_date, INTERVAL 30 DAY) as due_date,
               CASE 
                   WHEN b.return_date IS NOT NULL THEN '已归还'
                   WHEN DATE_ADD(b.borrow_date, INTERVAL 30 DAY) < CURDATE() THEN '逾期'
                   ELSE '借阅中'
               END as borrow_status,
               GREATEST(DATEDIFF(COALESCE(b.return_date, CURDATE()), DATE_ADD(b.borrow_date, INTERVAL 30 DAY)), 0) as overdue_days,
               GREATEST(DATEDIFF(COALESCE(b.return_date, CURDATE()), DATE_ADD(b.borrow_date, INTERVAL 30 DAY)), 0) * 0.5 as fine_amount
        FROM Overdue o, Borrow b, Book bk
        WHERE o.borrow_id = b.borrow_id 
          AND b.bid = bk.bid 
          AND b.sno = %s
        ORDER BY o.is_paid ASC
    """, (sno,))

def get_all_books():
    return db.query("SELECT * FROM Book")

def get_all_students():
    return db.query("SELECT * FROM Student")

def get_all_admins():
    return db.query("SELECT ano, aname, aphone FROM Admin")

def get_all_borrows():
    """获取所有借阅记录（动态计算应还日期和状态）"""
    return db.query("""
        SELECT b.*, bk.bname, bk.author, s.sname,
               DATE_ADD(b.borrow_date, INTERVAL 30 DAY) as due_date,
               CASE 
                   WHEN b.return_date IS NOT NULL THEN '已归还'
                   WHEN DATE_ADD(b.borrow_date, INTERVAL 30 DAY) < CURDATE() THEN '逾期'
                   ELSE '借阅中'
               END as status
        FROM Borrow b, Book bk, Student s
        WHERE b.bid = bk.bid AND b.sno = s.sno
        ORDER BY b.borrow_date DESC
    """)

def get_all_overdues():
    """获取所有逾期记录（动态计算逾期天数和罚款金额）"""
    return db.query("""
        SELECT o.*, bk.bname, bk.author, s.sname, b.borrow_date, b.sno, b.bid,
               DATE_ADD(b.borrow_date, INTERVAL 30 DAY) as due_date,
               CASE 
                   WHEN b.return_date IS NOT NULL THEN '已归还'
                   WHEN DATE_ADD(b.borrow_date, INTERVAL 30 DAY) < CURDATE() THEN '逾期'
                   ELSE '借阅中'
               END as borrow_status,
               GREATEST(DATEDIFF(COALESCE(b.return_date, CURDATE()), DATE_ADD(b.borrow_date, INTERVAL 30 DAY)), 0) as overdue_days,
               GREATEST(DATEDIFF(COALESCE(b.return_date, CURDATE()), DATE_ADD(b.borrow_date, INTERVAL 30 DAY)), 0) * 0.5 as fine_amount
        FROM Overdue o, Borrow b, Book bk, Student s
        WHERE o.borrow_id = b.borrow_id 
          AND b.bid = bk.bid 
          AND b.sno = s.sno
        ORDER BY o.is_paid ASC
    """)

def get_all_reserves():
    """获取所有有效预约记录（在SQL中计算状态）"""
    return db.query("""
        SELECT r.reserve_id, r.sno, r.bid, r.reserve_date, r.take_date,
               bk.bname, bk.author, s.sname,
               CASE 
                   WHEN r.take_date IS NOT NULL THEN '已取书'
                   WHEN DATE_ADD(r.reserve_date, INTERVAL 7 DAY) < CURDATE() THEN '已过期'
                   ELSE '有效'
               END as status
        FROM Reserve r, Book bk, Student s
        WHERE r.bid = bk.bid 
          AND r.sno = s.sno
          AND r.take_date IS NULL
          AND DATE_ADD(r.reserve_date, INTERVAL 7 DAY) >= CURDATE()
        ORDER BY r.reserve_date DESC
    """)

# ========== 登录/退出 ==========
@app.route('/')
def index():
    if 'sno' in session:
        return redirect(url_for('student_index'))
    if 'admin_id' in session:
        return redirect(url_for('admin_index'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'sno' in session:
        return redirect(url_for('student_index'))
    if 'admin_id' in session:
        return redirect(url_for('admin_index'))
    
    if request.method == 'POST':
        user_type = request.form.get('user_type')
        
        if user_type == 'student':
            sno = request.form.get('sno')
            password = request.form.get('password')
            student = db.query_one(
                "SELECT * FROM Student WHERE sno = %s AND spassword = MD5(%s)",
                (sno, password)
            )
            if student:
                session['sno'] = sno
                session['sname'] = student['sname']
                session['user_type'] = 'student'
                return redirect(url_for('student_index'))
            else:
                return render_template('login.html', error='学号或密码错误')
        
        elif user_type == 'admin':
            ano = request.form.get('ano')
            password = request.form.get('password')
            admin = db.query_one(
                "SELECT * FROM Admin WHERE ano = %s AND apassword = MD5(%s)",
                (ano, password)
            )
            if admin:
                session['admin_id'] = ano
                session['admin_name'] = admin['aname']
                session['user_type'] = 'admin'
                return redirect(url_for('admin_index'))
            else:
                return render_template('login.html', error='工号或密码错误')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    resp = make_response(redirect(url_for('login')))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

# ========== 图书信息 ==========
@app.route('/books')
@login_required_any
def books():
    books = get_all_books()
    return render_template('books.html', books=books)

# ========== 学生功能 ==========
@app.route('/student')
def student_index():
    if 'sno' not in session:
        return redirect(url_for('login'))
    
    borrow_count = get_current_borrow_count(session['sno'])
    overdues = get_student_overdues(session['sno'])
    overdue_count = len([o for o in overdues if not o['is_paid']])
    
    student = db.query_one("SELECT photo FROM Student WHERE sno = %s", (session['sno'],))
    student_photo = student['photo'] if student else None
    
    return render_template('student_index.html', 
                          borrow_count=borrow_count,
                          overdue_count=overdue_count,
                          student_photo=student_photo)

@app.route('/borrow', methods=['GET', 'POST'])
@login_required_student
def borrow():
    # 获取搜索关键词
    search_keyword = request.args.get('search', '').strip()
    borrow_count = get_current_borrow_count(session['sno'])
    
    # 根据是否有搜索关键词查询不同的图书列表
    if search_keyword:
        books = db.query("""
            SELECT * FROM Book 
            WHERE bname LIKE %s 
            ORDER BY bname
        """, (f'%{search_keyword}%',))
    else:
        books = get_all_books()
    
    if request.method == 'POST':
        bid = request.form.get('bid')
        if not bid:
            return render_template('borrow.html', books=books,borrow_count=borrow_count,
                                  msg="请选择图书",success=False)
        try:
            result = db.call_procedure('BorrowBook', (session['sno'], bid, '', 0))
            if result:
                msg = result.get('@_BorrowBook_2', '')
                code = result.get('@_BorrowBook_3', 1)
                success = (code == 0)
            else:
                success = False
                msg = "借书失败：未知错误"
            # 刷新数据（保持搜索状态）
            if search_keyword:
                books = db.query("SELECT * FROM Book WHERE bname LIKE %s ORDER BY bname", (f'%{search_keyword}%',))
            else:
                books = get_all_books()
        
            borrow_count = get_current_borrow_count(session['sno'])
            return render_template('borrow.html',books=books, borrow_count=borrow_count,
                                  msg=msg, success=success)
        except Exception as e:
            return render_template('borrow.html',books=books, borrow_count=borrow_count,
                                  msg=f"借书失败：{str(e)}",success=False)
    return render_template('borrow.html', books=books, borrow_count=borrow_count)

@app.route('/return', methods=['GET', 'POST'])
@login_required_student
def return_book():
    current_borrows = get_student_current_borrows(session['sno'])
    
    if request.method == 'POST':
        bid = request.form.get('bid')
        if not bid:
            return render_template('return.html', borrows=current_borrows,
                                  msg="请选择图书", success=False)
        
        try:
            result = db.call_procedure('ReturnBook', (session['sno'], bid, '', 0))  
            if result:
                msg = result.get('@_ReturnBook_2', '')
                code = result.get('@_ReturnBook_3', 1)
                success = (code == 0)
            else:
                success = False
                msg = "还书失败：未知错误"
            current_borrows = get_student_current_borrows(session['sno'])
            return render_template('return.html', borrows=current_borrows,
                                  msg=msg, success=success)
        except Exception as e:
            return render_template('return.html', borrows=current_borrows,
                                  msg=f"还书失败：{str(e)}", success=False)
    
    return render_template('return.html', borrows=current_borrows)

@app.route('/reserve', methods=['GET', 'POST'])
@login_required_student
def reserve():
    search = request.args.get('search', '')
    books = db.query("SELECT * FROM Book WHERE bname LIKE %s ORDER BY bname", (f'%{search}%',)) if search else get_all_books()
    if request.method == 'POST':
        bid = request.form.get('bid')
        if not bid:
            return render_template('reserve.html', reserves=get_student_reserves(session['sno']), 
                                  books=books, msg="请选择图书", success=False)
        try:
            # 检查是否已预约
            if db.query_one("SELECT * FROM Reserve WHERE sno=%s AND bid=%s AND take_date IS NULL AND DATE_ADD(reserve_date, INTERVAL 7 DAY)>=CURDATE()", 
                           (session['sno'], bid)):
                return render_template('reserve.html', reserves=get_student_reserves(session['sno']), 
                                      books=books, msg="预约失败：您已预约过该书", success=False)
            
            db.execute("INSERT INTO Reserve(sno,bid,reserve_date,take_date) VALUES(%s,%s,CURDATE(),NULL)", 
                      (session['sno'], bid))
            
            # 刷新图书列表（保持搜索状态）
            books = db.query("SELECT * FROM Book WHERE bname LIKE %s ORDER BY bname", (f'%{search}%',)) if search else get_all_books()
            return render_template('reserve.html', reserves=get_student_reserves(session['sno']), 
                                  books=books, msg="预约成功", success=True)
        except Exception as e:
            return render_template('reserve.html', reserves=get_student_reserves(session['sno']), 
                                  books=books, msg=f"预约失败：{str(e)}", success=False)
    return render_template('reserve.html', reserves=get_student_reserves(session['sno']), 
                          books=books)

@app.route('/reserve/cancel/<int:reserve_id>')
@login_required_student
def cancel_reserve(reserve_id):
    try:
        reserve = db.query_one("SELECT * FROM Reserve WHERE reserve_id = %s", (reserve_id,))
        if reserve and reserve['take_date'] is None:
            db.execute("DELETE FROM Reserve WHERE reserve_id = %s", (reserve_id,))
        return redirect(url_for('reserve'))
    except Exception as e:
        return redirect(url_for('reserve'))

@app.route('/student_overdue')
@login_required_student
def student_overdue():
    overdues = get_student_overdues(session['sno'])
    return render_template('student_overdue.html', overdues=overdues)

@app.route('/student_records')
@login_required_student
def student_records():
    borrows = get_student_borrows(session['sno'])
    return render_template('student_records.html', borrows=borrows)

# 修改密码 
@app.route('/student/change_password', methods=['POST'])
@login_required_student
def change_password():
    sno = session['sno']
    old, new, confirm = request.form.get('old_password'), request.form.get('new_password'), request.form.get('confirm_password')
    
    if new != confirm:
        msg, success = "两次输入的新密码不一致", False
    elif not db.query_one("SELECT * FROM Student WHERE sno=%s AND spassword=MD5(%s)", (sno, old)):
        msg, success = "原密码错误", False
    else:
        db.execute("UPDATE Student SET spassword=MD5(%s) WHERE sno=%s", (new, sno))
        msg, success = "密码修改成功", True
    
    return render_template('student_index.html', 
                          borrow_count=get_current_borrow_count(sno),
                          overdue_count=len([o for o in get_student_overdues(sno) if not o['is_paid']]),
                          student_photo=(db.query_one("SELECT photo FROM Student WHERE sno=%s", (sno,)) or {}).get('photo'),
                          msg=msg, success=success)

# 图片上传 
@app.route('/student/upload_photo', methods=['POST'])
@login_required_student
def upload_student_photo():
    file = request.files.get('photo')
    if file and file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext in ['png', 'jpg', 'jpeg', 'gif']:
            path = f"static/student_{session['sno']}_{int(datetime.now().timestamp())}.{ext}"
            file.save(path)
            db.execute("UPDATE Student SET photo = %s WHERE sno = %s", (path, session['sno']))
    return redirect(url_for('student_index'))

# 图片删除 
@app.route('/student/delete_photo', methods=['GET', 'POST'])
@login_required_student
def delete_student_photo():
    student = db.query_one("SELECT photo FROM Student WHERE sno = %s", (session['sno'],))
    if student and student['photo']:
        try:
            os.remove(student['photo'])
        except:
            pass
    db.execute("UPDATE Student SET photo = NULL WHERE sno = %s", (session['sno'],))
    return redirect(url_for('student_index'))

@app.route('/overdue/pay/<int:overdue_id>')
@login_required_any
def pay_overdue(overdue_id):
    try:
        if session.get('user_type') == 'student':
            overdue = db.query_one("""
                SELECT o.* FROM Overdue o, Borrow b
                WHERE o.borrow_id = b.borrow_id 
                  AND o.overdue_id = %s 
                  AND b.sno = %s 
                  AND o.is_paid = FALSE
            """, (overdue_id, session['sno']))
        else:
            overdue = db.query_one(
                "SELECT * FROM Overdue WHERE overdue_id = %s AND is_paid = FALSE",
                (overdue_id,)
            )
        
        if overdue:
            db.execute("UPDATE Overdue SET is_paid = TRUE, paid_date = CURDATE() WHERE overdue_id = %s", (overdue_id,))
        
        if session.get('user_type') == 'student':
            return redirect(url_for('student_overdue'))
        else:
            return redirect(url_for('overdue'))
    except Exception as e:
        if session.get('user_type') == 'student':
            return redirect(url_for('student_overdue'))
        else:
            return redirect(url_for('overdue'))
# ========== 管理员功能 ==========
@app.route('/admin')
def admin_index():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    
    stats = {
        'student_count': db.query_one("SELECT COUNT(*) as cnt FROM Student")['cnt'],
        'book_count': db.query_one("SELECT COUNT(*) as cnt FROM Book")['cnt'],
        'borrow_count': db.query_one("""
            SELECT COUNT(*) as cnt FROM Borrow WHERE return_date IS NULL
        """)['cnt'],
        'overdue_borrow_count': db.query_one("""
            SELECT COUNT(*) as cnt FROM Borrow 
            WHERE DATE_ADD(borrow_date, INTERVAL 30 DAY) < CURDATE() AND return_date IS NULL
        """)['cnt'],
        'overdue_count': db.query_one("SELECT COUNT(*) as cnt FROM Overdue WHERE is_paid = FALSE")['cnt'],
        'reserve_count': db.query_one("""
            SELECT COUNT(*) as cnt FROM Reserve 
            WHERE take_date IS NULL 
              AND DATE_ADD(reserve_date, INTERVAL 7 DAY) >= CURDATE()
        """)['cnt'],
    }
    return render_template('admin_index.html', stats=stats)

@app.route('/students')
@login_required_admin
def students():
    students = get_all_students()
    return render_template('students.html', students=students)

@app.route('/admins')
@login_required_admin
def admins():
    admins = get_all_admins()
    return render_template('admins.html', admins=admins)

@app.route('/records')
@login_required_admin
def records():
    borrows = get_all_borrows()
    return render_template('records.html', borrows=borrows)

@app.route('/admin_reserves')
@login_required_admin
def admin_reserves():
    reserves = get_all_reserves()
    return render_template('admin_reserves.html', reserves=reserves)

@app.route('/overdue')
@login_required_admin
def overdue():
    overdues = get_all_overdues()
    return render_template('overdue.html', overdues=overdues)

@app.route('/overdue/delete/<int:overdue_id>')
@login_required_admin
def delete_overdue(overdue_id):
    try:
        db.execute("DELETE FROM Overdue WHERE overdue_id = %s", (overdue_id,))
        return redirect(url_for('overdue'))
    except Exception as e:
        return redirect(url_for('overdue'))

@app.route('/admin/reserve/delete/<int:reserve_id>')
@login_required_admin
def admin_delete_reserve(reserve_id):
    try:
        reserve = db.query_one("SELECT * FROM Reserve WHERE reserve_id = %s", (reserve_id,))
        if reserve:
            db.execute("DELETE FROM Reserve WHERE reserve_id = %s", (reserve_id,))
            return redirect(url_for('admin_reserves'))
    except Exception as e:
        return redirect(url_for('admin_reserves'))

@app.route('/student/edit/<sno>', methods=['GET', 'POST'])
@login_required_admin
def edit_student(sno):
    if request.method == 'POST':
        sname = request.form.get('sname')
        sclass = request.form.get('sclass')
        sphone = request.form.get('sphone')
        semail = request.form.get('semail')
        new_password = request.form.get('new_password')
        
        try:
            if new_password and new_password.strip():
                db.execute("""
                    UPDATE Student 
                    SET sname = %s, sclass = %s, sphone = %s, semail = %s, spassword = MD5(%s)
                    WHERE sno = %s
                """, (sname, sclass, sphone, semail, new_password, sno))
            else:
                db.execute("""
                    UPDATE Student 
                    SET sname = %s, sclass = %s, sphone = %s, semail = %s
                    WHERE sno = %s
                """, (sname, sclass, sphone, semail, sno))
            
            return redirect(url_for('students'))
        except Exception as e:
            return redirect(url_for('students'))
    
    return redirect(url_for('students'))

@app.route('/student/delete/<sno>')
@login_required_admin
def delete_student(sno):
    try:
        if get_student_current_borrows(sno):
            msg,success = '删除失败，该学生仍有未归还的图书', False
            return render_template('students.html',students = get_all_students(), msg=msg, success=success)
        
        db.execute("DELETE FROM Student WHERE sno = %s", (sno,))
        msg,success = '删除成功', True
        return render_template('students.html',students = get_all_students(), msg=msg, success=success)
    except Exception as e:
        msg,success = '删除失败，未知错误', False
        return render_template('students.html', students = get_all_students(),msg=msg, success=success)
    

@app.route('/student/add', methods=['GET', 'POST'])
@login_required_admin
def add_student():
    if request.method == 'POST':
        sno = request.form.get('sno') 
        sname = request.form.get('sname')
        sclass = request.form.get('sclass')
        sphone = request.form.get('sphone')
        semail = request.form.get('semail')
        spassword = request.form.get('new_password')
        photo = request.form.get('photo', None)
        
        if not sno or not sname or not spassword:
            msg = '添加失败，学号、姓名和密码不能为空'
            success = False
            return render_template('students.html',students = get_all_students() , msg=msg, success=success)
        
        elif db.query_one("SELECT * FROM Student WHERE sno = %s", (sno,)):
            msg = '添加失败，学号已存在'
            success = False 
            return render_template('students.html',students = get_all_students() , msg=msg, success=success)
        
        else:  
            try:
                db.execute("""
                    INSERT INTO Student (sno, sname, spassword, sclass, sphone, semail, photo)
                    VALUES (%s, %s, MD5(%s), %s, %s, %s, %s)
                """, (sno, sname, spassword, sclass, sphone, semail, photo))
                
                msg = '添加成功'
                success = True
                return render_template('students.html', students = get_all_students() , msg=msg, success=success)
            except Exception as e:
                print(f"添加学生错误: {e}")
                msg = '添加失败：未知错误'
                success = False
                return render_template('students.html', students = get_all_students() , msg=msg, success=success)
    
    return redirect(url_for('students'))
    
if __name__ == '__main__':
    app.run(debug=True)
from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import os
import ssl  # 必须引入 ssl 模块以支持 TiDB Cloud

# ================= 1. 配置路径与应用 =================
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, '../templates')
static_dir = os.path.join(base_dir, '../static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get('SECRET_KEY', 'mygo_is_eternal_deployment_key')

# ================= 2. 数据库连接 (强制 SSL 修复版) =================
def get_db_connection():
    """
    建立数据库连接。
    修复了 Error 1105: 强制使用 SSL 上下文，无论环境变量如何设置。
    """
    # 1. 构建 SSL 配置
    ssl_ca_path = "/etc/ssl/certs/ca-certificates.crt"
    ssl_config = None

    if os.path.exists(ssl_ca_path):
        ssl_config = {"ca": ssl_ca_path}
    else:
        # 本地/无证书环境：创建忽略验证的 SSL 上下文
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssl_config = ctx

    # 2. 建立连接
    try:
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST'),
            port=int(os.environ.get('DB_PORT', 4000)),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            database=os.environ.get('DB_NAME', 'mygo_db'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            ssl=ssl_config,  # [关键] 强制传入 SSL
            autocommit=False # 关闭自动提交
        )
        
        # 3. 关闭安全模式
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET SQL_SAFE_UPDATES = 0")
        except Exception:
            pass 
            
        return conn

    except Exception as e:
        print(f"❌ Database Connection Failed: {e}")
        return None

# ================= 3. 登录与注销 =================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        if not conn:
            flash('无法连接到数据库 (Error 500)', 'danger')
            return render_template('login.html')

        try:
            with conn.cursor() as cursor:
                # --- A. 管理员 ---
                if role == 'admin':
                    admin_pwd = os.environ.get('ADMIN_PASSWORD', 'admin')
                    if username == 'admin' and password == admin_pwd:
                        session['role'] = 'admin'
                        session['user_name'] = 'Administrator'
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('管理员密码错误', 'danger')

                # --- B. 乐队 ---
                elif role == 'band':
                    cursor.execute("SELECT band_id, name FROM Band WHERE name=%s AND password=%s", (username, password))
                    band = cursor.fetchone()
                    if band:
                        session['role'] = 'band'
                        session['band_id'] = band['band_id']
                        session['band_name'] = band['name']
                        return redirect(url_for('band_dashboard'))
                    else:
                        flash('乐队不存在或密码错误', 'danger')

                # --- C. 歌迷 ---
                elif role == 'fan':
                    cursor.execute("SELECT fan_id, name FROM Fan WHERE name=%s AND password=%s", (username, password))
                    user = cursor.fetchone()
                    if user:
                        session['role'] = 'fan'
                        session['fan_id'] = user['fan_id']
                        session['fan_name'] = user['name']
                        return redirect(url_for('fan_dashboard'))
                    else:
                        flash('账号不存在或密码错误', 'danger')
        except Exception as e:
            flash(f"登录错误: {e}", 'danger')
        finally:
            conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ================= 4. 管理员功能模块 =================
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            with conn.cursor() as cursor:
                if action == 'add_band':
                    cursor.execute("INSERT INTO Band (name, leader_name, founding_date, password, intro) VALUES (%s, %s, %s, %s, %s)",
                                   (request.form.get('name'), request.form.get('leader'), request.form.get('date'), request.form.get('password'), request.form.get('intro')))
                    flash('乐队创建成功', 'success')
                elif action == 'add_fan':
                    cursor.execute("INSERT INTO Fan (name, password, age) VALUES (%s, %s, %s)", 
                                   (request.form.get('name'), request.form.get('password'), request.form.get('age')))
                    flash('歌迷添加成功', 'success')
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f'操作失败: {e}', 'danger')

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM Band")
            bands = cursor.fetchall()
            cursor.execute("SELECT * FROM Fan")
            fans = cursor.fetchall()
    finally:
        conn.close()
    return render_template('admin.html', bands=bands, fans=fans)

@app.route('/admin/band_detail/<int:band_id>', methods=['GET', 'POST'])
def admin_band_detail(band_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        try:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO Member (name, role, gender, join_date, band_id) VALUES (%s, %s, %s, %s, %s)",
                               (request.form.get('name'), request.form.get('role'), request.form.get('gender'), request.form.get('join_date'), band_id))
            conn.commit()
            flash('成员添加成功', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'添加失败: {e}', 'danger')

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM Band WHERE band_id=%s", (band_id,))
            band = cursor.fetchone()
            cursor.execute("SELECT * FROM Member WHERE band_id=%s", (band_id,))
            members = cursor.fetchall()
    finally:
        conn.close()
    return render_template('admin_band_members.html', band=band, members=members)

@app.route('/admin/delete_band/<int:band_id>')
def admin_delete_band(band_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Band WHERE band_id=%s", (band_id,))
        conn.commit()
        flash('乐队已删除', 'warning')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_fan/<int:fan_id>')
def admin_delete_fan(fan_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Fan WHERE fan_id=%s", (fan_id,))
        conn.commit()
        flash('歌迷已注销', 'warning')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_member/<int:member_id>/<int:band_id>')
def admin_delete_member(member_id, band_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Member WHERE member_id=%s", (member_id,))
        conn.commit()
        flash('成员已移除', 'success')
    finally:
        conn.close()
    return redirect(url_for('admin_band_detail', band_id=band_id))

# ================= 5. 乐队功能模块 =================
@app.route('/band', methods=['GET', 'POST'])
def band_dashboard():
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    band_id = session['band_id']
    band_name = session['band_name']

    # 视图映射
    view_map = {
        'MyGO!!!!!': ("view_mygo_info", "view_mygo_fan_stats", "view_mygo_song_stats", "view_mygo_concert_stats"),
        'Ave Mujica': ("view_avemujica_info", "view_avemujica_fan_stats", "view_avemujica_song_stats", "view_avemujica_concert_stats")
    }
    has_views = band_name in view_map

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            with conn.cursor() as cursor:
                if action == 'update_intro':
                    cursor.execute("UPDATE Band SET intro=%s WHERE band_id=%s", (request.form.get('intro'), band_id))
                    flash('简介更新成功', 'success')
                elif action == 'add_album':
                    cursor.execute("INSERT INTO Album (title, release_date, album_intro, band_id) VALUES (%s, %s, %s, %s)",
                                   (request.form.get('title'), request.form.get('release_date'), request.form.get('intro'), band_id))
                    flash('新专辑发布成功', 'success')
                elif action == 'add_song':
                    cursor.execute("INSERT INTO Song (title, authors, album_id) VALUES (%s, %s, %s)",
                                   (request.form.get('title'), request.form.get('authors'), request.form.get('album_id')))
                    flash('新歌录入成功', 'success')
                elif action == 'add_concert': 
                    cursor.execute("INSERT INTO Concert (name, hold_time, location, band_id) VALUES (%s, %s, %s, %s)",
                                   (request.form.get('name'), request.form.get('hold_time'), request.form.get('location'), band_id))
                    flash('演唱会发布成功', 'success')
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f'操作失败: {e}', 'danger')

    try:
        with conn.cursor() as cursor:
            # 统计数据
            if has_views:
                v_info, v_stats, v_song, v_concert = view_map[band_name]
                cursor.execute(f"SELECT * FROM {v_info}")
                members = cursor.fetchall()
                cursor.execute(f"SELECT * FROM {v_stats}")
                stats = cursor.fetchone()
                cursor.execute(f"SELECT * FROM {v_song}")
                song_stats = cursor.fetchall()
                cursor.execute(f"SELECT * FROM {v_concert}")
                concert_stats = cursor.fetchall()
            else:
                cursor.execute("SELECT name, role, gender, join_date FROM Member WHERE band_id=%s", (band_id,))
                members = cursor.fetchall()
                stats, song_stats, concert_stats = None, [], []

            cursor.execute("SELECT intro FROM Band WHERE band_id=%s", (band_id,))
            current_intro = cursor.fetchone()['intro']
            
            cursor.execute("SELECT * FROM Album WHERE band_id=%s", (band_id,))
            my_albums = cursor.fetchall()
            
            cursor.execute("SELECT s.song_id, s.title, s.authors, a.title as album_title FROM Song s JOIN Album a ON s.album_id = a.album_id WHERE a.band_id = %s", (band_id,))
            my_songs = cursor.fetchall()
            
            cursor.execute("SELECT r.score, r.comment, r.review_time, a.title as album_title, f.name as fan_name FROM Review r JOIN Album a ON r.album_id = a.album_id JOIN Fan f ON r.fan_id = f.fan_id WHERE a.band_id = %s ORDER BY r.review_time DESC", (band_id,))
            reviews = cursor.fetchall()

            cursor.execute("SELECT * FROM Concert WHERE band_id=%s ORDER BY hold_time DESC", (band_id,))
            my_concerts = cursor.fetchall()
    finally:
        conn.close()

    return render_template('band.html', band_name=band_name, members=members, stats=stats, 
                           intro=current_intro, my_albums=my_albums, my_songs=my_songs, 
                           reviews=reviews, my_concerts=my_concerts, 
                           song_stats=song_stats, concert_stats=concert_stats)

# 乐队删除接口
@app.route('/band/delete_album/<int:album_id>')
def delete_album(album_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Album WHERE album_id=%s AND band_id=%s", (album_id, session['band_id']))
        conn.commit()
    finally: conn.close()
    return redirect(url_for('band_dashboard'))

@app.route('/band/delete_song/<int:song_id>')
def delete_song(song_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Song WHERE song_id=%s AND album_id IN (SELECT album_id FROM Album WHERE band_id=%s)", (song_id, session['band_id']))
        conn.commit()
    finally: conn.close()
    return redirect(url_for('band_dashboard'))

@app.route('/band/delete_concert/<int:concert_id>')
def delete_concert(concert_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Concert WHERE concert_id=%s AND band_id=%s", (concert_id, session['band_id']))
        conn.commit()
    finally: conn.close()
    return redirect(url_for('band_dashboard'))

@app.route('/band/delete_member/<int:member_id>')
def delete_member(member_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Member WHERE member_id=%s AND band_id=%s", (member_id, session['band_id']))
        conn.commit()
    finally: conn.close()
    return redirect(url_for('band_dashboard'))

# ================= 6. 歌迷功能模块 (含 Python 版自动算分) =================
@app.route('/fan', methods=['GET', 'POST'])
def fan_dashboard():
    if session.get('role') != 'fan': return redirect(url_for('login'))
    conn = get_db_connection()
    fan_id = session['fan_id']

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            with conn.cursor() as cursor:
                if action == 'rate':
                    album_id = request.form.get('album_id')
                    score = request.form.get('score')
                    comment = request.form.get('comment')
                    
                    # 1. 插入或更新评论
                    sql = """
                        INSERT INTO Review (fan_id, album_id, score, comment, review_time) 
                        VALUES (%s, %s, %s, %s, NOW()) 
                        ON DUPLICATE KEY UPDATE 
                        score = VALUES(score), comment = VALUES(comment), review_time = NOW()
                    """
                    cursor.execute(sql, (fan_id, album_id, score, comment))

                    # 2. [新增] 纯 Python 实现的“触发器”逻辑：更新平均分
                    update_avg_sql = """
                        UPDATE Album 
                        SET avg_score = (SELECT AVG(score) FROM Review WHERE album_id = %s) 
                        WHERE album_id = %s
                    """
                    cursor.execute(update_avg_sql, (album_id, album_id))
                    
                    flash('评价已提交，专辑分数已更新！', 'success')
                
                elif action == 'update_profile':
                    cursor.execute("UPDATE Fan SET occupation=%s, education=%s, age=%s WHERE fan_id=%s",
                                   (request.form.get('occupation'), request.form.get('education'), request.form.get('age'), fan_id))
                    flash('资料已更新', 'success')
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f'操作失败: {e}', 'danger')

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM Fan WHERE fan_id=%s", (fan_id,))
            my_profile = cursor.fetchone()
            
            # 排行榜直接查 Album 表（因为我们已经把分算进去了）
            cursor.execute("SELECT * FROM Album ORDER BY avg_score DESC LIMIT 10")
            ranks = cursor.fetchall()
            
            cursor.execute("SELECT * FROM Album")
            albums = cursor.fetchall()
            
            cursor.execute("SELECT b.name, b.band_id FROM Band b JOIN Fan_Like_Band f ON b.band_id=f.band_id WHERE f.fan_id=%s", (fan_id,))
            like_bands = cursor.fetchall()
            cursor.execute("SELECT s.title, s.song_id FROM Song s JOIN Fan_Like_Song f ON s.song_id=f.song_id WHERE f.fan_id=%s", (fan_id,))
            like_songs = cursor.fetchall()
            
            cursor.execute("SELECT s.song_id, s.title, s.authors, a.title as album_title FROM Song s JOIN Album a ON s.album_id = a.album_id")
            all_songs = cursor.fetchall()
    finally:
        conn.close()

    return render_template('fan.html', user_name=session['fan_name'], my_profile=my_profile, 
                           ranks=ranks, albums=albums, 
                           like_bands=like_bands, like_songs=like_songs, 
                           all_songs=all_songs)

@app.route('/fan/toggle_like/<type>/<int:id>')
def toggle_like(type, id):
    if session.get('role') != 'fan': return redirect(url_for('login'))
    conn = get_db_connection()
    fan_id = session['fan_id']
    
    config = {
        'band': ('Fan_Like_Band', 'band_id'),
        'album': ('Fan_Like_Album', 'album_id'),
        'song': ('Fan_Like_Song', 'song_id'),
        'concert': ('Fan_Attend_Concert', 'concert_id')
    }
    
    if type in config:
        table, col = config[type]
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {table} WHERE fan_id=%s AND {col}=%s", (fan_id, id))
                if cursor.fetchone():
                    cursor.execute(f"DELETE FROM {table} WHERE fan_id=%s AND {col}=%s", (fan_id, id))
                    flash('已取消关注', 'warning')
                else:
                    cursor.execute(f"INSERT INTO {table} (fan_id, {col}) VALUES (%s, %s)", (fan_id, id))
                    flash('关注成功', 'success')
            conn.commit()
        finally:
            conn.close()
            
    return redirect(url_for('fan_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
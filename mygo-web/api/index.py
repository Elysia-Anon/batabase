from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import os
import ssl  # 必须引入 ssl 模块以支持 TiDB Cloud

# ================= 1. 配置路径与应用 =================
# 获取当前文件 (api/index.py) 的目录
base_dir = os.path.dirname(os.path.abspath(__file__))
# 模板目录在上一级的 templates 文件夹
template_dir = os.path.join(base_dir, '../templates')
# 静态文件目录 (存放吉他图标)
static_dir = os.path.join(base_dir, '../static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# 从环境变量获取密钥，如果没有则使用默认值
app.secret_key = os.environ.get('SECRET_KEY', 'mygo_is_eternal_deployment_key')

# ================= 2. 数据库连接 (强制 SSL 修复版) =================
def get_db_connection():
    """
    建立数据库连接。
    修复了 Error 1105: 强制使用 SSL 上下文，无论环境变量如何设置。
    """
    
    # --- 1. 构建 SSL 配置 ---
    # 尝试寻找系统默认的 CA 证书 (Linux/Vercel 环境通常在这里)
    ssl_ca_path = "/etc/ssl/certs/ca-certificates.crt"
    ssl_config = None

    if os.path.exists(ssl_ca_path):
        # 如果能在系统里找到证书，使用系统证书 (最安全)
        ssl_config = {"ca": ssl_ca_path}
    else:
        # 如果找不到证书 (如本地 Windows 或某些容器)，创建一个忽略主机名验证的 SSL 上下文
        # 这样既能满足 TiDB 的 SSL 强制要求，又不会因为缺文件而报错
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssl_config = ctx

    # --- 2. 建立连接 ---
    try:
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST'),
            port=int(os.environ.get('DB_PORT', 4000)), # 默认为 4000
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            database=os.environ.get('DB_NAME', 'mygo_db'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            ssl=ssl_config,  # [关键修复] 强制传入 SSL 配置
            autocommit=False # 关闭自动提交，手动管理事务
        )
        
        # --- 3. 环境设置 ---
        # 关闭安全更新模式，防止 UPDATE/DELETE 报错
        # 同时也为了让触发器能顺利执行
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET SQL_SAFE_UPDATES = 0")
        except Exception:
            pass # 如果这步出错（极少见），不影响主连接
            
        return conn

    except Exception as e:
        print(f"❌ Database Connection Failed: {e}")
        # 在控制台打印详细错误，方便 Vercel Logs 查看
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
            flash('无法连接到数据库，请检查网络或配置 (Error 500)', 'danger')
            return render_template('login.html')

        try:
            with conn.cursor() as cursor:
                # --- A. 管理员登录 ---
                if role == 'admin':
                    # 默认密码 'admin'，生产环境建议配置环境变量
                    admin_pwd = os.environ.get('ADMIN_PASSWORD', 'admin')
                    if username == 'admin' and password == admin_pwd:
                        session['role'] = 'admin'
                        session['user_name'] = 'Administrator'
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('管理员密码错误', 'danger')

                # --- B. 乐队登录 ---
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

                # --- C. 歌迷登录 ---
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
            flash(f"登录过程发生错误: {e}", 'danger')
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
    if not conn: return "DB Connection Error", 500
    
    # POST: 添加乐队或歌迷
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            with conn.cursor() as cursor:
                if action == 'add_band':
                    name = request.form.get('name')
                    leader = request.form.get('leader')
                    date = request.form.get('date')
                    pwd = request.form.get('password')
                    intro = request.form.get('intro')
                    cursor.execute("INSERT INTO Band (name, leader_name, founding_date, password, intro) VALUES (%s, %s, %s, %s, %s)",
                                   (name, leader, date, pwd, intro))
                    flash(f'乐队 {name} 创建成功！', 'success')
                
                elif action == 'add_fan':
                    name = request.form.get('name')
                    pwd = request.form.get('password')
                    age = request.form.get('age')
                    cursor.execute("INSERT INTO Fan (name, password, age) VALUES (%s, %s, %s)", (name, pwd, age))
                    flash(f'歌迷 {name} 添加成功！', 'success')
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f'操作失败: {e}', 'danger')

    # GET: 获取列表
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
            name = request.form.get('name')
            role = request.form.get('role')
            gender = request.form.get('gender')
            join_date = request.form.get('join_date')
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO Member (name, role, gender, join_date, band_id) VALUES (%s, %s, %s, %s, %s)",
                               (name, role, gender, join_date, band_id))
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

# 管理员删除操作路由
@app.route('/admin/delete_band/<int:band_id>')
def admin_delete_band(band_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Band WHERE band_id=%s", (band_id,))
        conn.commit()
        flash('乐队数据已删除', 'warning')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {e}', 'danger')
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
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {e}', 'danger')
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
    except Exception as e:
        conn.rollback()
        flash(f'移除失败: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin_band_detail', band_id=band_id))

# ================= 5. 乐队功能模块 =================
@app.route('/band', methods=['GET', 'POST'])
def band_dashboard():
    if session.get('role') != 'band': return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn: return "DB Connection Error", 500

    band_name = session['band_name']
    band_id = session['band_id']
    
    # 视图判断逻辑：兼容新乐队
    # 如果乐队名是这两者之一，尝试读取视图；否则直接读 Member 表
    if band_name == 'MyGO!!!!!':
        view_info, view_stats = "view_mygo_info", "view_mygo_fan_stats"
        view_song_stats, view_concert_stats = "view_mygo_song_stats", "view_mygo_concert_stats"
        has_views = True
    elif band_name == 'Ave Mujica':
        view_info, view_stats = "view_avemujica_info", "view_avemujica_fan_stats"
        view_song_stats, view_concert_stats = "view_avemujica_song_stats", "view_avemujica_concert_stats"
        has_views = True
    else:
        has_views = False 

    # POST: 乐队管理操作
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            with conn.cursor() as cursor:
                if action == 'update_intro':
                    new_intro = request.form.get('intro')
                    cursor.execute("UPDATE Band SET intro=%s WHERE band_id=%s", (new_intro, band_id))
                    flash('简介更新成功', 'success')
                
                elif action == 'add_album':
                    title = request.form.get('title')
                    date = request.form.get('release_date')
                    intro = request.form.get('intro')
                    cursor.execute("INSERT INTO Album (title, release_date, album_intro, band_id) VALUES (%s, %s, %s, %s)",
                                   (title, date, intro, band_id))
                    flash('新专辑发布成功', 'success')

                elif action == 'add_song':
                    title = request.form.get('title')
                    authors = request.form.get('authors')
                    album_id = request.form.get('album_id')
                    cursor.execute("INSERT INTO Song (title, authors, album_id) VALUES (%s, %s, %s)",
                                   (title, authors, album_id))
                    flash('新歌录入成功', 'success')
                
                elif action == 'add_concert': 
                    name = request.form.get('name')
                    hold_time = request.form.get('hold_time')
                    location = request.form.get('location')
                    cursor.execute("INSERT INTO Concert (name, hold_time, location, band_id) VALUES (%s, %s, %s, %s)",
                                   (name, hold_time, location, band_id))
                    flash('演唱会预告发布成功', 'success')
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f'操作失败: {e}', 'danger')

    # GET: 页面数据渲染
    try:
        with conn.cursor() as cursor:
            # 1. 成员与统计
            if has_views:
                cursor.execute(f"SELECT * FROM {view_info}")
                members = cursor.fetchall()
                cursor.execute(f"SELECT * FROM {view_stats}")
                stats = cursor.fetchone()
                cursor.execute(f"SELECT * FROM {view_song_stats}")
                song_stats = cursor.fetchall()
                cursor.execute(f"SELECT * FROM {view_concert_stats}")
                concert_stats = cursor.fetchall()
            else:
                cursor.execute("SELECT name, role, gender, join_date FROM Member WHERE band_id=%s", (band_id,))
                members = cursor.fetchall()
                stats = None
                song_stats = []
                concert_stats = []

            # 2. 简介
            cursor.execute("SELECT intro FROM Band WHERE band_id=%s", (band_id,))
            res = cursor.fetchone()
            current_intro = res['intro'] if res else ""
            
            # 3. 专辑与歌曲
            cursor.execute("SELECT * FROM Album WHERE band_id=%s", (band_id,))
            my_albums = cursor.fetchall()
            
            cursor.execute("""
                SELECT s.song_id, s.title, s.authors, a.title as album_title 
                FROM Song s JOIN Album a ON s.album_id = a.album_id 
                WHERE a.band_id = %s
            """, (band_id,))
            my_songs = cursor.fetchall()
            
            # 4. 乐评
            cursor.execute("""
                SELECT r.score, r.comment, r.review_time, a.title as album_title, f.name as fan_name 
                FROM Review r 
                JOIN Album a ON r.album_id = a.album_id 
                JOIN Fan f ON r.fan_id = f.fan_id
                WHERE a.band_id = %s ORDER BY r.review_time DESC
            """, (band_id,))
            reviews = cursor.fetchall()

            # 5. 演唱会
            cursor.execute("SELECT * FROM Concert WHERE band_id=%s ORDER BY hold_time DESC", (band_id,))
            my_concerts = cursor.fetchall()
    finally:
        conn.close()

    return render_template('band.html', band_name=band_name, members=members, stats=stats, 
                           intro=current_intro, my_albums=my_albums, my_songs=my_songs, 
                           reviews=reviews, my_concerts=my_concerts, 
                           song_stats=song_stats, concert_stats=concert_stats)

# 乐队删除资源接口
@app.route('/band/delete_album/<int:album_id>')
def delete_album(album_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Album WHERE album_id=%s AND band_id=%s", (album_id, session['band_id']))
        conn.commit()
        flash('专辑已删除', 'warning')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('band_dashboard'))

@app.route('/band/delete_song/<int:song_id>')
def delete_song(song_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM Song WHERE song_id=%s 
                AND album_id IN (SELECT album_id FROM Album WHERE band_id=%s)
            """, (song_id, session['band_id']))
        conn.commit()
        flash('歌曲已删除', 'warning')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('band_dashboard'))

@app.route('/band/delete_concert/<int:concert_id>')
def delete_concert(concert_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Concert WHERE concert_id=%s AND band_id=%s", (concert_id, session['band_id']))
        conn.commit()
        flash('演唱会已取消', 'warning')
    except Exception as e:
        conn.rollback()
        flash(f'操作失败: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('band_dashboard'))

@app.route('/band/delete_member/<int:member_id>')
def delete_member(member_id):
    if session.get('role') != 'band': return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Member WHERE member_id=%s AND band_id=%s", (member_id, session['band_id']))
        conn.commit()
        flash('成员已移除', 'warning')
    except Exception as e:
        conn.rollback()
        flash(f'操作失败: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('band_dashboard'))

# ================= 6. 歌迷功能模块 =================
@app.route('/fan', methods=['GET', 'POST'])
def fan_dashboard():
    if session.get('role') != 'fan': return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn: return "DB Connection Error", 500
    fan_id = session['fan_id']

    # POST: 歌迷操作 (打分/改资料)
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            with conn.cursor() as cursor:
                if action == 'rate':
                    album_id = request.form.get('album_id')
                    score = request.form.get('score')
                    comment = request.form.get('comment')
                    
                    # 使用 ON DUPLICATE KEY UPDATE 解决重复评论问题
                    # 并更新评论时间为最新
                    sql = """
                        INSERT INTO Review (fan_id, album_id, score, comment, review_time) 
                        VALUES (%s, %s, %s, %s, NOW()) 
                        ON DUPLICATE KEY UPDATE 
                        score = VALUES(score), 
                        comment = VALUES(comment), 
                        review_time = NOW()
                    """
                    cursor.execute(sql, (fan_id, album_id, score, comment))
                    flash('评价已提交/更新！', 'success')
                
                elif action == 'update_profile':
                    new_occ = request.form.get('occupation')
                    new_edu = request.form.get('education')
                    new_age = request.form.get('age')
                    cursor.execute("UPDATE Fan SET occupation=%s, education=%s, age=%s WHERE fan_id=%s",
                                   (new_occ, new_edu, new_age, fan_id))
                    flash('个人资料已更新', 'success')
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f'操作失败: {e}', 'danger')

    # GET: 歌迷首页数据
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM Fan WHERE fan_id=%s", (fan_id,))
            my_profile = cursor.fetchone()
            
            cursor.execute("SELECT * FROM AlbumRank ORDER BY score DESC")
            ranks = cursor.fetchall()
            
            cursor.execute("SELECT * FROM Album")
            albums = cursor.fetchall()
            
            # 收藏数据
            cursor.execute("SELECT b.name, b.band_id FROM Band b JOIN Fan_Like_Band f ON b.band_id=f.band_id WHERE f.fan_id=%s", (fan_id,))
            like_bands = cursor.fetchall()
            cursor.execute("SELECT s.title, s.song_id FROM Song s JOIN Fan_Like_Song f ON s.song_id=f.song_id WHERE f.fan_id=%s", (fan_id,))
            like_songs = cursor.fetchall()
            
            # 发现数据
            cursor.execute("""
                SELECT s.song_id, s.title, s.authors, a.title as album_title 
                FROM Song s JOIN Album a ON s.album_id = a.album_id
            """)
            all_songs = cursor.fetchall()
    finally:
        conn.close()

    return render_template('fan.html', user_name=session['fan_name'], my_profile=my_profile, 
                           ranks=ranks, albums=albums, 
                           like_bands=like_bands, like_songs=like_songs, 
                           all_songs=all_songs)

# 歌迷关注/取消关注接口
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
    
    if type not in config: return redirect(url_for('fan_dashboard'))
    
    table, col = config[type]
    
    try:
        with conn.cursor() as cursor:
            # 检查是否已关注
            cursor.execute(f"SELECT * FROM {table} WHERE fan_id=%s AND {col}=%s", (fan_id, id))
            if cursor.fetchone():
                cursor.execute(f"DELETE FROM {table} WHERE fan_id=%s AND {col}=%s", (fan_id, id))
                flash('已取消关注', 'warning')
            else:
                cursor.execute(f"INSERT INTO {table} (fan_id, {col}) VALUES (%s, %s)", (fan_id, id))
                flash('关注成功！', 'success')
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'操作失败: {e}', 'danger')
    finally:
        conn.close()
        
    return redirect(url_for('fan_dashboard'))

# Vercel 需要这个入口，本地运行也需要
if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
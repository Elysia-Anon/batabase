from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import os


base_dir = os.path.dirname(os.path.abspath(__file__)) 
template_dir = os.path.join(base_dir, '../templates') 

app = Flask(__name__, template_folder=template_dir)

app.secret_key = os.environ.get('SECRET_KEY', 'bangdream')


def get_db_connection():
   
    return pymysql.connect(
        host=os.environ.get('DB_HOST'),
        port=4000,
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        database='mygo_db',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
      
        ssl={
            "ca": "/etc/ssl/certs/ca-certificates.crt"
        }
    )


@app.route('/')
def index():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM Band")
            bands = cursor.fetchall()
    finally:
        conn.close()
    

    user = session.get('user')
    return render_template('index.html', bands=bands, user=user)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
      
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM Fan WHERE name = %s AND password = %s"
                cursor.execute(sql, (username, password))
                fan = cursor.fetchone()
        finally:
            conn.close()

        if fan:
        
            session['user'] = {'type': 'fan', 'id': fan['fan_id'], 'name': fan['name']}
            return redirect(url_for('index'))
        
        elif username == 'MyGO!!!!!' and password == '123456':
             session['user'] = {'type': 'band', 'name': 'MyGO!!!!!'}
             return redirect(url_for('band_detail', band_id=1))
        elif username == 'Ave Mujica' and password == '123456':
             session['user'] = {'type': 'band', 'name': 'Ave Mujica'}
             return redirect(url_for('band_detail', band_id=2))
        
        else:
            flash('登录失败：用户名或密码错误')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/band/<int:band_id>')
def band_detail(band_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
          
            cursor.execute("SELECT * FROM Band WHERE band_id = %s", (band_id,))
            band = cursor.fetchone()
            
            
            cursor.execute("SELECT * FROM Member WHERE band_id = %s", (band_id,))
            members = cursor.fetchall()

          
            cursor.execute("SELECT * FROM Concert WHERE band_id = %s ORDER BY concert_date DESC", (band_id,))
            concerts = cursor.fetchall()

           
            cursor.execute("SELECT * FROM Album WHERE band_id = %s", (band_id,))
            albums = cursor.fetchall()
            
           
            for album in albums:
                cursor.execute("SELECT * FROM Song WHERE album_id = %s", (album['album_id'],))
                
                album['songs'] = cursor.fetchall()

           
            stats = None
            if band and band['name'] == 'MyGO!!!!!':
                cursor.execute("SELECT * FROM view_mygo_fan_stats")
                stats = cursor.fetchone()
            elif band and band['name'] == 'Ave Mujica':
                cursor.execute("SELECT * FROM view_avemujica_fan_stats")
                stats = cursor.fetchone()

         
            sql_reviews = """
                SELECT r.score, r.comment, f.name as fan_name, a.title as album_title
                FROM Review r
                JOIN Fan f ON r.fan_id = f.fan_id
                JOIN Album a ON r.album_id = a.album_id
                WHERE a.band_id = %s
                ORDER BY r.review_id DESC
                LIMIT 10
            """
            cursor.execute(sql_reviews, (band_id,))
            reviews = cursor.fetchall()

    finally:
        conn.close()
        
    return render_template('detail.html', 
                           band=band, 
                           members=members, 
                           stats=stats, 
                           user=session.get('user'),
                           albums=albums,     
                           concerts=concerts, 
                           reviews=reviews    
                           )



@app.route('/add_review', methods=['POST'])
def add_review():

    if not session.get('user') or session['user']['type'] != 'fan':
        return "请先登录歌迷账号！", 403

    fan_id = session['user']['id'] 
    album_id = request.form['album_id']
    score = request.form['score']
    comment = request.form['comment']

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            
            cursor.execute(
                "INSERT INTO Review (fan_id, album_id, score, comment) VALUES (%s, %s, %s, %s)", 
                (fan_id, album_id, score, comment)
            )
            
        
            cursor.execute("""
                UPDATE Album a 
                SET avg_score = (SELECT AVG(score) FROM Review WHERE album_id = %s) 
                WHERE album_id = %s
            """, (album_id, album_id))
            
            
            cursor.execute("DELETE FROM AlbumRank")
            cursor.execute("""
                INSERT INTO AlbumRank (album_id, title, score)
                SELECT album_id, title, avg_score 
                FROM Album 
                ORDER BY avg_score DESC 
                LIMIT 10
            """)
            
        conn.commit() 
    except Exception as e:
        conn.rollback() 
        return f"打分失败: {str(e)}"
    finally:
        conn.close()
        
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)


@app.route('/add_review', methods=['POST'])
def add_review():
    
    user = session.get('user')
    if not user:
        return redirect('/login')
    
   
    fan_id = user['id']  
    album_id = request.form.get('album_id') 
    score = request.form.get('score')
    comment = request.form.get('comment')
    
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO Review (fan_id, album_id, score, comment) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (fan_id, album_id, score, comment))
        conn.commit()
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()
        
   
    return redirect(request.referrer or '/')

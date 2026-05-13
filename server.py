import sqlite3
import os
import uuid
import requests
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from datetime import datetime, timedelta
from constants import APP_SECRET_KEY
from utils.get_points import get_points
from utils.post_points import post_points
from utils.login import login as API_login

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'db', 'rebus.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def get_themes():
    db = get_db()
    themes = db.execute('SELECT id, name FROM themes').fetchall()
    db.close()
    return themes


def get_rebuses_by_theme(theme_id):
    db = get_db()
    rebuses = db.execute('SELECT id, final_word, folder_name FROM rebuses WHERE theme_id = ?', (theme_id,)).fetchall()
    db.close()
    return rebuses


def get_rebus_data(rebus_id):
    db = get_db()
    rebus = db.execute('SELECT id, final_word, ru_word, folder_name, theme_id FROM rebuses WHERE id = ?',
                       (rebus_id,)).fetchone()
    if not rebus:
        db.close()
        return None
    rows = db.execute(
        'SELECT position, letter, image_filename, word_disc, word_disc_ru FROM letters WHERE rebus_id = ? ORDER BY position',
        (rebus_id,)).fetchall()
    db.close()
    return {
        'id': rebus['id'],
        'final_word': rebus['final_word'].upper(),
        'ru_word': rebus['ru_word'],
        'folder_name': rebus['folder_name'],
        'theme_id': rebus['theme_id'],
        'letters': [dict(row) for row in rows],
        'total_letters': len(rows)
    }


def get_or_create_user(email, is_guest=False):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if not user:
        join_date = datetime.now().strftime('%d.%m.%Y')
        db.execute(
            'INSERT INTO users (email, rebuses_solved, words_solved, join_date, is_guest) VALUES (?, 0, 0, ?, ?)',
            (email, join_date, int(is_guest)))
        db.commit()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    db.close()
    return dict(user)


def load_user_to_session(user):
    session['user_id'] = user['email']
    session['is_guest'] = bool(user['is_guest'])
    session['join_date'] = user['join_date']
    if not bool(user['is_guest']):
        session['nickname'] = user['email'].split('@')[0]
    else:
        session['nickname'] = f"Гость_{uuid.uuid4().hex[:4]}"
    session['user_stats'] = {
        'rebuses_solved': user['rebuses_solved'],
        'words_solved': user['words_solved'],
        'points': 0.0
    }


def update_user_stats(email, rebuses_delta=0, words_delta=0):
    db = get_db()
    db.execute(
        'UPDATE users SET rebuses_solved = rebuses_solved + ?, words_solved = words_solved + ? WHERE email = ?',
        (rebuses_delta, words_delta, email))
    db.commit()
    db.close()


def require_login():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return None


def calculate_score(used_hints):
    if used_hints >= 5:
        return 0.0
    return max(0.1, round(1.0 - 0.15 * used_hints, 2))


def ensure_stats():
    stats_key = 'user_stats'
    if stats_key not in session:
        session[stats_key] = {'rebuses_solved': 0, 'words_solved': 0, 'points': 0.0}
    if 'points' not in session[stats_key]:
        session[stats_key]['points'] = 0.0


@app.route('/')
def index():
    redirect_result = require_login()
    if redirect_result:
        return redirect_result
    return render_template('index.html',
                           themes=get_themes(),
                           active_page='index',
                           user_id=session.get('user_id'),
                           points=session.get('user_points'),
                           error=session.pop('error', None))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if session.get('user_id') and not session.get('is_guest'):
            return redirect(url_for('index'))
        if session.get('is_guest'):
            session.clear()
        return render_template('login.html')

    email = request.form.get('email')
    password = request.form.get('password')
    if not (email and password):
        return render_template('login.html', error={'message': 'Заполните все поля'})

    try:
        api_user_id = API_login(email, password)
        session.clear()
        session['api_user_id'] = api_user_id

        user = get_or_create_user(email)
        load_user_to_session(user)

        try:
            points = get_points(api_user_id)
            session['user_points'] = points if points is not None else 0
        except Exception:
            session['user_points'] = 0

        session['nickname'] = email.split('@')[0]

    except Exception:
        return render_template('login.html', error={'message': 'Неверная почта или пароль'})

    return redirect(url_for('index'))


@app.route('/guest-login', methods=['POST'])
def guest_login():
    guest_id = f"guest_{uuid.uuid4().hex[:8]}"
    session.clear()
    user = get_or_create_user(guest_id, is_guest=True)
    load_user_to_session(user)
    session['user_points'] = 0
    session.permanent = False
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/points', methods=['GET', 'POST'])
def points():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Необходимо войти'})
    if session.get('is_guest'):
        if request.method == 'POST':
            return jsonify({'success': False, 'message': 'Гости не могут сохранять прогресс'})
        return jsonify({'success': True, 'points': 0})
    if request.method == 'GET':
        try:
            session['user_points'] = get_points()
        except Exception:
            session['user_points'] = 0
    elif request.method == 'POST':
        try:
            session['user_points'] = post_points(int(request.form.get('points', 0)))
        except Exception as e:
            session['error'] = str(e)
    return redirect(url_for('index'))


@app.route('/theme/<int:theme_id>')
def theme_page(theme_id):
    redirect_result = require_login()
    if redirect_result:
        return redirect_result
    themes = get_themes()
    current_theme = next((t for t in themes if t['id'] == theme_id), None)
    if not current_theme:
        return redirect(url_for('index'))
    return render_template('theme.html', themes=themes, current_theme=current_theme,
                           rebuses=get_rebuses_by_theme(theme_id), active_page='themes',
                           user_id=session.get('user_id'), points=session.get('user_points'))


@app.route('/rebus/<int:rebus_id>')
def rebus_page(rebus_id):
    redirect_result = require_login()
    if redirect_result:
        return redirect_result
    data = get_rebus_data(rebus_id)
    if not data:
        return redirect(url_for('index'))

    filled = session.get(f'rebus_{rebus_id}_filled', {})
    cells = []
    for letter in data['letters']:
        pos = str(letter['position'])
        cells.append({
            'position': letter['position'],
            'image': letter['image_filename'],
            'filled': pos in filled,
            'display_letter': filled.get(pos, ''),
            'word_disc': letter['word_disc'],
            'word_disc_ru': letter.get('word_disc_ru', '')
        })

    filled_count = sum(1 for c in cells if c['filled'])
    return render_template('rebus_page.html',
                           rebus_id=rebus_id,
                           rebus_theme_id=data['theme_id'],
                           final_word=data['final_word'],
                           ru_word=data['ru_word'],
                           cells=cells,
                           folder_name=data['folder_name'],
                           all_filled=filled_count == len(cells),
                           filled_count=filled_count,
                           total_count=len(cells),
                           user_id=session.get('user_id'),
                           points=session.get('user_points'))


@app.route('/cell/<int:rebus_id>/<int:position>')
def cell_page(rebus_id, position):
    redirect_result = require_login()
    if redirect_result:
        return redirect_result

    db = get_db()
    letter = db.execute(
        'SELECT letter, image_filename, word_disc, word_disc_ru FROM letters WHERE rebus_id = ? AND position = ?',
        (rebus_id, position)).fetchone()
    folder = db.execute('SELECT folder_name FROM rebuses WHERE id = ?', (rebus_id,)).fetchone()
    db.close()

    if not letter:
        return redirect(url_for('rebus_page', rebus_id=rebus_id))

    already_filled = str(position) in session.get(f'rebus_{rebus_id}_filled', {})
    old_score = None
    if already_filled:
        scores = session.get(f'rebus_{rebus_id}_scores', {})
        old_score = scores.get(str(position))

    return render_template('cell_page.html', rebus_id=rebus_id, position=position,
                           letter=letter['letter'].upper(), image_filename=letter['image_filename'],
                           word_disc=letter['word_disc'], word_disc_ru=letter['word_disc_ru'],
                           folder_name=folder['folder_name'], already_filled=already_filled, old_score=old_score,
                           user_id=session.get('user_id'), points=session.get('user_points'))


@app.route('/check_letter', methods=['POST'])
def check_letter():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Необходимо войти в систему'})

    data = request.json
    rebus_id = data['rebus_id']
    position = data['position']
    answer = data['answer'].strip().upper()
    used_hints = data.get('used_hints', 0)

    db = get_db()
    correct = db.execute('SELECT word_disc, letter FROM letters WHERE rebus_id = ? AND position = ?',
                         (rebus_id, position)).fetchone()
    db.close()

    if not correct or answer != correct['word_disc'].upper():
        return jsonify({'success': False, 'message': 'Неправильно'})

    score = calculate_score(used_hints)

    filled_key = f'rebus_{rebus_id}_filled'
    scores_key = f'rebus_{rebus_id}_scores'
    pos_str = str(position)

    session.setdefault(filled_key, {})
    session.setdefault(scores_key, {})

    old_score = session[scores_key].get(pos_str)
    session[filled_key][pos_str] = correct['letter'].upper()

    points_to_add = 0.0
    if old_score is None:
        points_to_add = score
        session[scores_key][pos_str] = score
    elif score > old_score:
        points_to_add = round(score - old_score, 2)
        session[scores_key][pos_str] = score

    ensure_stats()
    if points_to_add > 0:
        session['user_stats']['points'] = round(session['user_stats']['points'] + points_to_add, 2)
    session.modified = True

    return jsonify({
        'success': True,
        'letter': correct['letter'].upper(),
        'score': points_to_add,
        'total_score': score,
        'old_score': old_score,
        'total_points': session['user_stats']['points']
    })


@app.route('/check_final_word', methods=['POST'])
def check_final_word():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Необходимо войти в систему'})

    data = request.json
    rebus_id = data['rebus_id']
    user_russian = data['ru_word'].strip().lower()

    db = get_db()
    correct = db.execute('SELECT ru_word FROM rebuses WHERE id = ?', (rebus_id,)).fetchone()
    db.close()

    if not correct:
        return jsonify({'success': False, 'message': 'Ребус не найден'})
    if user_russian != correct['ru_word'].lower():
        return jsonify({'success': False, 'message': 'Неправильно! Попробуйте ещё раз.'})

    ensure_stats()
    completed_key = f'rebus_{rebus_id}_completed'
    if not session.get(completed_key):
        db = get_db()
        letters_count = db.execute('SELECT COUNT(*) as cnt FROM letters WHERE rebus_id = ?', (rebus_id,)).fetchone()['cnt']
        db.close()
        session['user_stats']['rebuses_solved'] += 1
        session['user_stats']['words_solved'] += letters_count
        session[completed_key] = True

        update_user_stats(session['user_id'], rebuses_delta=1, words_delta=letters_count)
        session.modified = True

    return jsonify({
        'success': True,
        'message': 'Поздравляем! Ребус решён!',
        'rebuses': session['user_stats']['rebuses_solved'],
        'words': session['user_stats']['words_solved'],
        'points': session['user_stats']['points']
    })


@app.route('/profile')
def profile():
    redirect_result = require_login()
    if redirect_result:
        return redirect_result
    ensure_stats()
    stats = session['user_stats']
    stats['points'] = round(stats.get('points', 0.0), 1)
    return render_template('profile.html', stats=stats,
                           user={
                               'nickname': session.get('nickname', 'Игрок'),
                               'join_date': session.get('join_date', ''),
                               'email': session.get('user_id')
                           },
                           active_page='profile',
                           user_id=session.get('user_id'),
                           points=session.get('user_points'))


@app.route('/update_nickname', methods=['POST'])
def update_nickname():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Необходимо войти в систему'})
    new_nick = request.json.get('nickname', '').strip()
    if new_nick:
        session['nickname'] = new_nick
        session.modified = True
        return jsonify({'success': True})
    return jsonify({'success': False})


@app.route('/get_points', methods=['GET'])
def get_points_route():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Необходимо войти в систему'})
    ensure_stats()
    return jsonify({'points': session['user_stats']['points']})


@app.route('/leaderboard')
def leaderboard():
    redirect_result = require_login()
    if redirect_result:
        return redirect_result
    db = get_db()
    top = db.execute('SELECT email, rebuses_solved, words_solved FROM users WHERE is_guest = 0 ORDER BY rebuses_solved DESC LIMIT 20').fetchall()
    db.close()
    leaderboard = []
    for row in top:
        leaderboard.append({
            'nickname': row['email'].split('@')[0],
            'rebuses_solved': row['rebuses_solved'],
            'words_solved': row['words_solved']
        })
    return render_template('leaderboard.html',
                           leaderboard=leaderboard,
                           active_page='leaderboard',
                           user_id=session.get('user_id'),
                           points=session.get('user_points'))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
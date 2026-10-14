import sqlite3
import os
import uuid
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from datetime import datetime
from constants import APP_SECRET_KEY
from utils import api

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY
path_base = os.environ.get('GAME_PATH_BASE', '').rstrip('/')
app.config['APPLICATION_ROOT'] = path_base or '/'
app.config['SESSION_COOKIE_PATH'] = path_base or '/'
app.config['SESSION_COOKIE_NAME'] = os.environ.get(
    'GAME_COOKIE_NAME', 'lingvogameos_rebusi_session'
)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

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


def init_session():
    if 'user_id' not in session:
        guest_id = f"guest_{uuid.uuid4().hex[:8]}"
        session['user_id'] = guest_id
        session['nickname'] = f"Гость_{uuid.uuid4().hex[:4]}"
        session['join_date'] = datetime.now().strftime('%d.%m.%Y')
        session['user_stats'] = {'rebuses_solved': 0, 'words_solved': 0, 'points': 0.0}


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
@app.route('/start')
def index():
    # Портал открывает игру как /start?session=<id>&token=<hmac>.
    api.get_game_session_id()
    init_session()
    return render_template('index.html',
                           themes=get_themes(),
                           active_page='index',
                           user_id=session.get('user_id'),
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/theme/<int:theme_id>')
def theme_page(theme_id):
    init_session()
    themes = get_themes()
    current_theme = next((t for t in themes if t['id'] == theme_id), None)
    if not current_theme:
        return redirect(url_for('index'))
    return render_template('theme.html', themes=themes, current_theme=current_theme,
                           rebuses=get_rebuses_by_theme(theme_id), active_page='themes',
                           user_id=session.get('user_id'),
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/rebus/<int:rebus_id>')
def rebus_page(rebus_id):
    init_session()
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
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/cell/<int:rebus_id>/<int:position>')
def cell_page(rebus_id, position):
    init_session()

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
                           user_id=session.get('user_id'),
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/check_letter', methods=['POST'])
def check_letter():
    init_session()

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
    init_session()

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
        session.modified = True

        # По контракту портала игровая сессия одноразовая. Ребус начисляет
        # один балл только при первом полном решении.
        if session.get('game_session_id'):
            try:
                api.add_points(1)
            except api.ApiError as exc:
                app.logger.warning("Не удалось начислить баллы портала: %s", exc)

    return jsonify({
        'success': True,
        'message': 'Поздравляем! Ребус решён!',
        'rebuses': session['user_stats']['rebuses_solved'],
        'words': session['user_stats']['words_solved'],
        'points': session['user_stats']['points']
    })


@app.route('/profile')
def profile():
    init_session()
    ensure_stats()
    stats = session['user_stats']
    stats['points'] = round(stats.get('points', 0.0), 1)
    return render_template('profile.html', stats=stats,
                           user={
                               'nickname': session.get('nickname', 'Игрок'),
                               'join_date': session.get('join_date', '')
                           },
                           active_page='profile',
                           user_id=session.get('user_id'),
                           points=stats['points'])


@app.route('/update_nickname', methods=['POST'])
def update_nickname():
    init_session()
    new_nick = request.json.get('nickname', '').strip()
    if new_nick:
        session['nickname'] = new_nick
        session.modified = True
        return jsonify({'success': True})
    return jsonify({'success': False})


@app.route('/get_points', methods=['GET'])
def get_points_route():
    init_session()
    ensure_stats()
    return jsonify({'points': session['user_stats']['points']})


@app.route('/leaderboard')
def leaderboard():
    init_session()
    return render_template('leaderboard.html',
                           leaderboard=[],
                           active_page='leaderboard',
                           user_id=session.get('user_id'),
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/how-to-play')
def how_to_play():
    init_session()
    return render_template('how_to_play.html',
                           user_id=session.get('user_id'),
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/create-rebus')
def create_rebus_page():
    init_session()
    return render_template('create_rebus.html',
                           themes=get_themes(),
                           user_id=session.get('user_id'),
                           points=session.get('user_stats', {}).get('points', 0))


@app.route('/create_rebus', methods=['POST'])
def create_rebus():
    init_session()

    theme_id = request.form.get('theme_id')
    theme_name = request.form.get('theme_name')
    final_word = request.form.get('final_word', '').strip().lower()
    ru_word = request.form.get('ru_word', '').strip().lower()

    if not final_word:
        return jsonify({'success': False, 'message': 'Введите итоговое слово'})

    db = get_db()

    if theme_name:
        folder_path = theme_name.lower().replace(' ', '_')
        db.execute('INSERT INTO themes (name, folder_path) VALUES (?, ?)', (theme_name, folder_path))
        db.commit()
        theme_id = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']
    elif theme_id:
        theme_id = int(theme_id)
    else:
        db.close()
        return jsonify({'success': False, 'message': 'Выберите тему'})

    folder_name = final_word.replace('ӕ', 'ae').replace('ӕ', 'ae')

    folder_path = os.path.join(BASE_DIR, 'static', 'images', 'rebus', folder_name)
    os.makedirs(folder_path, exist_ok=True)

    db.execute('INSERT INTO rebuses (final_word, ru_word, folder_name, theme_id) VALUES (?, ?, ?, ?)',
               (final_word, ru_word, folder_name, theme_id))
    db.commit()
    rebus_id = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']

    positions = set()
    for key in request.form:
        if key.startswith('pos_'):
            positions.add(key.split('_')[1])

    for pos in sorted(positions, key=int):
        word_disc = request.form.get(f'word_{pos}', '')
        word_disc_ru = request.form.get(f'word_ru_{pos}', '')
        image_file = request.files.get(f'image_{pos}')

        if image_file and image_file.filename:
            ext = os.path.splitext(image_file.filename)[1]
            filename = f"{pos}_{secure_filename(word_disc)}{ext}"
            image_file.save(os.path.join(folder_path, filename))
        else:
            filename = ''

        db.execute(
            'INSERT INTO letters (rebus_id, position, letter, image_filename, word_disc, word_disc_ru) VALUES (?, ?, ?, ?, ?, ?)',
            (rebus_id, int(pos), final_word[int(pos) - 1] if int(pos) <= len(final_word) else '',
             filename, word_disc, word_disc_ru))

    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'rebus_id': rebus_id,
        'rebus_url': url_for('rebus_page', rebus_id=rebus_id)
    })


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=6013, debug=True)

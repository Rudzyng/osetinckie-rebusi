import sqlite3
import os
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'

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
        'SELECT position, letter, image_filename, word_disc FROM letters WHERE rebus_id = ? ORDER BY position',
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


@app.route('/')
def index():
    return render_template('index.html', themes=get_themes(), active_page='index')


@app.route('/theme/<int:theme_id>')
def theme_page(theme_id):
    themes = get_themes()
    current_theme = next((t for t in themes if t['id'] == theme_id), None)
    if not current_theme:
        return redirect(url_for('index'))
    return render_template('theme.html', themes=themes, current_theme=current_theme,
                           rebuses=get_rebuses_by_theme(theme_id), active_page='themes')


@app.route('/rebus/<int:rebus_id>')
def rebus_page(rebus_id):
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
            'word_disc': letter['word_disc']
        })

    filled_count = sum(1 for c in cells if c['filled'])
    return render_template('rebus_page.html',
                           rebus_id=rebus_id,
                           rebus_theme_id=data['theme_id'],  # Добавлено!
                           final_word=data['final_word'],
                           ru_word=data['ru_word'],
                           cells=cells,
                           folder_name=data['folder_name'],
                           all_filled=filled_count == len(cells),
                           filled_count=filled_count,
                           total_count=len(cells))


@app.route('/cell/<int:rebus_id>/<int:position>')
def cell_page(rebus_id, position):
    letter = get_db().execute(
        'SELECT letter, image_filename, word_disc FROM letters WHERE rebus_id = ? AND position = ?',
        (rebus_id, position)).fetchone()
    if not letter:
        return redirect(url_for('rebus_page', rebus_id=rebus_id))

    if str(position) in session.get(f'rebus_{rebus_id}_filled', {}):
        return redirect(url_for('rebus_page', rebus_id=rebus_id))

    folder = get_db().execute('SELECT folder_name FROM rebuses WHERE id = ?', (rebus_id,)).fetchone()['folder_name']
    return render_template('cell_page.html', rebus_id=rebus_id, position=position,
                           letter=letter['letter'].upper(), image_filename=letter['image_filename'],
                           word_disc=letter['word_disc'], folder_name=folder)


@app.route('/check_letter', methods=['POST'])
def check_letter():
    data = request.json
    rebus_id, position, answer = data['rebus_id'], data['position'], data['answer'].strip().upper()

    db = get_db()
    correct = db.execute('SELECT word_disc, letter FROM letters WHERE rebus_id = ? AND position = ?',
                         (rebus_id, position)).fetchone()
    db.close()

    if not correct or answer != correct['word_disc'].upper():
        return jsonify({'success': False, 'message': 'Неправильно'})

    key = f'rebus_{rebus_id}_filled'
    session[key] = session.get(key, {})
    session[key][str(position)] = correct['letter'].upper()
    session.modified = True
    return jsonify({'success': True, 'letter': correct['letter'].upper()})


@app.route('/check_final_word', methods=['POST'])
def check_final_word():
    data = request.json
    rebus_id = data['rebus_id']
    user_russian = data['ru_word'].strip().lower()

    db = get_db()
    correct = db.execute('SELECT ru_word FROM rebuses WHERE id = ?', (rebus_id,)).fetchone()
    db.close()

    if not correct:
        return jsonify({'success': False, 'message': 'Ребус не найден'})

    if user_russian != correct['ru_word'].lower():
        return jsonify({'success': False, 'message': f'Неправильно! Попробуйте ещё раз.'})

    stats_key = 'user_stats'
    if stats_key not in session:
        session[stats_key] = {'rebuses_solved': 0, 'words_solved': 0}

    letters_count = get_db().execute('SELECT COUNT(*) as cnt FROM letters WHERE rebus_id = ?', (rebus_id,)).fetchone()[
        'cnt']

    completed_key = f'rebus_{rebus_id}_completed'
    if not session.get(completed_key):
        session[stats_key]['rebuses_solved'] += 1
        session[stats_key]['words_solved'] += letters_count
        session[completed_key] = True
        session.modified = True

    return jsonify({'success': True, 'message': 'Поздравляем! Ребус решён!',
                    'rebuses': session[stats_key]['rebuses_solved'],
                    'words': session[stats_key]['words_solved']})

@app.route('/profile')
def profile():
    stats = session.get('user_stats', {'rebuses_solved': 0, 'words_solved': 0})
    nickname = session.get('nickname', 'Игрок')
    join_date = session.get('join_date')
    if not join_date:
        join_date = datetime.now().strftime('%d.%m.%Y')
        session['join_date'] = join_date
    return render_template('profile.html', stats=stats, user={'nickname': nickname, 'join_date': join_date},
                           active_page='profile')


@app.route('/update_nickname', methods=['POST'])
def update_nickname():
    new_nick = request.json.get('nickname', '').strip()
    if new_nick:
        session['nickname'] = new_nick
        session.modified = True
        return jsonify({'success': True})
    return jsonify({'success': False})


if __name__ == '__main__':
    app.run(debug=True)
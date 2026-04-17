from flask import Flask, render_template, session, redirect, url_for
from datetime import datetime

from data.db_session import global_init

app = Flask(__name__)
app.secret_key = 'supersecretkey'

@app.context_processor
def inject_current_time():
    return {'current_time': datetime.now().strftime('%H:%M:%S')}


@app.route('/')
def index():
    return render_template('index.html', active_page='index')


@app.route('/rebus/<theme_id>')
def rebus_page(theme_id):
    if theme_id not in THEMES:
        return redirect(url_for('index'))

    theme = THEMES[theme_id]
    filled_key = f'filled_cells_{theme_id}'
    if filled_key not in session:
        session[filled_key] = {}

    filled_cells = session[filled_key]

    cells = []
    for i, cell in enumerate(theme['cells']):
        cells.append({
            'image': cell['image'],
            'correct_word': cell['correct_word'],
            'filled': str(i) in filled_cells,
            'letter': filled_cells.get(str(i), '')
        })

    filled_count = sum(1 for c in cells if c['filled'])
    all_filled = filled_count == len(cells)

    return render_template('rebus_page.html',
                           active_page='rebus',
                           theme_id=theme_id,
                           theme_name=theme['name'],
                           cells=cells,
                           filled_count=filled_count,
                           total_cells=len(cells),
                           all_filled=all_filled,
                           final_answer=theme['final_answer'])


@app.route('/cell/<theme_id>/<int:cell_id>')
def cell_page(theme_id, cell_id):
    if theme_id not in THEMES:
        return redirect(url_for('index'))

    theme = THEMES[theme_id]
    if cell_id >= len(theme['cells']):
        return redirect(url_for('rebus_page', theme_id=theme_id))

    return render_template('cell_page.html',
                           theme_id=theme_id,
                           cell=theme['cells'][cell_id],
                           cell_id=cell_id)


@app.route('/fill_cell', methods=['POST'])
def fill_cell():
    from flask import request
    data = request.json
    theme_id = data.get('theme_id')
    cell_id = str(data.get('cell_id'))
    letter = data.get('letter')

    if theme_id in THEMES:
        filled_key = f'filled_cells_{theme_id}'
        if filled_key not in session:
            session[filled_key] = {}
        session[filled_key][cell_id] = letter
        session.modified = True
        return {'success': True}
    return {'success': False}, 400


@app.route('/profile')
def profile():
    user_data = {
        'nickname': 'Игрок',
        'join_date': datetime.now().strftime('%d.%m.%Y')
    }
    return render_template('profile.html', active_page='profile', user=user_data)

def main():
    global_init("db/database.db")
    app.run()


if __name__ == '__main__':
    main()
    app.run(debug=True)
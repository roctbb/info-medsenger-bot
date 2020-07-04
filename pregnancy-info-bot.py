from datetime import datetime, timedelta
import time
from threading import Thread
from flask import Flask, request, render_template
import sqlite3
import requests
import hashlib, uuid
from config import *
import threading
import json

app = Flask(__name__)

contracts = {}
available_modes = ['daily', 'weekly', 'none']


def delayed(delay, f, args):
    timer = threading.Timer(delay, f, args=args)
    timer.start()


def validate_date(date):
    try:
        datetime.strptime(date, '%Y-%m-%d')
        return True
    except:
        return False


def check_digit(number):
    try:
        int(number)
        return True
    except:
        return False


def get_connection():
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    return conn, cursor


def add_contract(connection, id):
    conn, cursor = connection
    cursor.execute('INSERT INTO contracts (contract_id) VALUES (?)', (id,))
    conn.commit()


def set_date(connection, id, date):
    conn, cursor = connection
    cursor.execute('UPDATE contracts SET pregnancy_start = ? WHERE contract_id = ?', (date, id))
    conn.commit()


def delete_contract(connection, id):
    conn, cursor = connection
    cursor.execute('DELETE FROM contracts WHERE contract_id = ?', (id,))
    conn.commit()


def get_notifications(connection):
    conn, cursor = connection
    cursor.execute('SELECT * FROM notifications')
    return cursor.fetchall()


def get_contracts(connection):
    conn, cursor = connection
    cursor.execute('SELECT * FROM contracts')
    return cursor.fetchall()


def get_sent_notifications(connection):
    conn, cursor = connection
    cursor.execute('SELECT * FROM sent_notifications')
    return cursor.fetchall()


def make_sent(connection, notification_id, contract_id):
    conn, cursor = connection
    cursor.execute('INSERT INTO sent_notifications (notification_id, contract_id) VALUES (?, ?)',
                   (notification_id, contract_id))
    conn.commit()


@app.route('/status', methods=['POST'])
def status():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    connection = get_connection()

    answer = {
        "is_tracking_data": True,
        "supported_scenarios": [],
        "tracked_contracts": [int(contract[0]) for contract in get_contracts(connection)]
    }

    connection[0].close()

    return json.dumps(answer)


@app.route('/init', methods=['POST'])
def init():
    data = request.json

    if data['api_key'] != APP_KEY:
        if DEBUG:
            print('invalid key')
        return 'invalid key'
    if not check_digit(data['contract_id']):
        if DEBUG:
            print('invalid id')
        return 'invalid id'

    contract_id = int(data['contract_id'])

    connection = get_connection()
    add_contract(connection, contract_id)
    connection[0].close()

    return 'ok'


@app.route('/remove', methods=['POST'])
def remove():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'
    if not check_digit(data['contract_id']):
        return 'invalid id'

    contract_id = int(data['contract_id'])

    connection = get_connection()
    delete_contract(connection, contract_id)
    connection[0].close()

    return 'ok'


@app.route('/settings', methods=['GET'])
def settings():
    key = request.args.get('api_key', '')
    contract_id = request.args.get('contract_id', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    connection = get_connection()
    contracts = get_contracts(connection)
    connection[0].close()

    if not check_digit(contract_id) or len(list(filter(lambda x: x[0] == int(contract_id), contracts))) == 0:
        return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

    return render_template('settings.html', contract=list(filter(lambda x: x[0] == int(contract_id), contracts))[0])


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


@app.route('/settings', methods=['POST'])
def setting_save():
    key = request.args.get('api_key', '')
    contract_id = request.args.get('contract_id', '')

    connection = get_connection()
    contracts = get_contracts(connection)
    connection[0].close()

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."
    if not check_digit(contract_id) or len(list(filter(lambda x: x[0] == int(contract_id), contracts))) == 0:
        return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

    contract_id = int(contract_id)
    date = request.form.get('date', '')

    if not validate_date(date):
        return "<strong>Ошибки при заполнении формы.</strong> Пожалуйста, что все поля заполнены.<br><a onclick='history.go(-1);'>Назад</a>"

    connection = get_connection()
    set_date(connection, contract_id, date)
    connection[0].close()

    return """
            <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
            """


def send(contract_id, message):
    data = {
        "contract_id": contract_id,
        "api_key": APP_KEY,
        "message": {
            "text": message,
            "only_doctor": False,
            "only_patient": True,
        }
    }
    try:
        result = requests.post(MAIN_HOST + '/api/agents/message', json=data)
        print('sent to', contract_id)
    except Exception as e:
        print('connection error', e)


def get_week(start, now):
    monday1 = (now - timedelta(days=now.weekday()))
    monday2 = (start - timedelta(days=start.weekday()))

    return (monday1 - monday2).days // 7


def sender():
    while True:
        today = datetime.today()
        connection = get_connection()

        contracts = get_contracts(connection)
        sent_notifications = get_sent_notifications(connection)
        notifications = get_notifications(connection)
        for event in notifications:
            for contract in contracts:
                if not validate_date(contract[1]):
                    continue
                start = datetime.strptime(contract[1], '%Y-%m-%d')

                if (event[0], contract[0]) not in sent_notifications and get_week(start, today) >= event[2]:
                    send(contract[0], event[1])
                    make_sent(connection, event[0], contract[0])

        connection[0].close()
        time.sleep(60)


@app.route('/message', methods=['POST'])
def message():
    return "ok"


t = Thread(target=sender)
t.start()

app.run(port='9999')

from datetime import datetime, timedelta
import time
from threading import Thread
from flask import Flask, request, render_template
import sqlite3
import requests
import hashlib, uuid
from config import *
from flask_sqlalchemy import SQLAlchemy
from medsenger_api import AgentApiClient
import threading
import json

medsenger_api = AgentApiClient(APP_KEY, MAIN_HOST, AGENT_ID, API_DEBUG)

app = Flask(__name__)

available_modes = ['daily', 'weekly', 'none']
presets = ['pregnancy', 'stenocardia', 'heartfailure', 'fibrillation', 'hypertensia']

db_string = "postgres://{}:{}@{}:{}/{}".format(DB_LOGIN, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE)
app.config['SQLALCHEMY_DATABASE_URI'] = db_string
db = SQLAlchemy(app)


class SentNotifications(db.Model):
    notification_id = db.Column(db.Integer, db.ForeignKey('notification.id', ondelete="CASCADE"), primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id', ondelete="CASCADE"), primary_key=True)


class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start = db.Column(db.Date, nullable=True)
    preset = db.Column(db.String, default='pregnancy', nullable=True)

    sent_notifications = db.relationship('Notification', secondary='sent_notifications',
                                         backref=db.backref("notification"))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=True)
    week = db.Column(db.Integer, default=0)
    preset = db.Column(db.String, default='pregnancy', nullable=True)
    info_materials = db.Column(db.Text, nullable=True)

    sent_to = db.relationship('Contract', secondary='sent_notifications', backref=db.backref("contract"))


try:
    db.create_all()
except:
    print('cant create structure')


def gts():
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


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


def delete_contract(contract_id):
    SentNotifications.query.filter_by(contract_id=contract_id).delete()
    Contract.query.filter_by(id=contract_id).delete()
    db.session.commit()


def add_contract(contract_id, preset):
    try:
        query = Contract.query.filter_by(id=contract_id)

        if query.count() != 0:
            contract = query.first()
            contract.preset = preset
            contract.last_push = 0

            print("{}: Reactivate contract {}".format(gts(), contract.id))
        else:
            contract = Contract(id=contract_id, preset=preset)
            db.session.add(contract)

            print("{}: Add contract {}".format(gts(), contract.id))

        db.session.commit()

        return contract

    except Exception as e:
        print(e)
        return None


@app.route('/status', methods=['POST'])
def status():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    contract_ids = [l[0] for l in db.session.query(Contract.id).all()]

    answer = {
        "is_tracking_data": True,
        "supported_scenarios": presets,
        "tracked_contracts": contract_ids
    }

    return json.dumps(answer)


@app.route('/init', methods=['POST'])
def init():
    data = request.json
    print(data)
    if data['api_key'] != APP_KEY:
        print('invalid key')
        return 'invalid key'

    if not check_digit(data['contract_id']):
        print('invalid id')
        return 'invalid id'

    contract_id = int(data['contract_id'])

    preset = data.get('preset')
    params = data.get('params')

    if params:
        preset = [data.get('preset')]
        for key, value in params.items():
            if "info_" in key and value:
                preset.append(key.replace('info_', ''))
        preset = '|'.join(preset)


    contract = add_contract(contract_id, preset)

    if params and validate_date(params.get('start_date')):
        start_date = params.get('start_date')
        contract.start = start_date

    if params and check_digit(params.get('week')):
        week = int(params.get('week'))
        if week > 0 and week < 40:
            contract.start = datetime.today() - timedelta(weeks=week)

    db.session.commit()

    tasks()

    return 'ok'


@app.route('/remove', methods=['POST'])
def remove():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    if not check_digit(data['contract_id']):
        return 'invalid id'

    contract_id = int(data['contract_id'])

    delete_contract(contract_id)

    return 'ok'


@app.route('/settings', methods=['GET'])
def settings():
    key = request.args.get('api_key', '')
    contract_id = request.args.get('contract_id', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    contract = Contract.query.filter_by(id=contract_id).first()

    if not check_digit(contract_id) or not contract:
        return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

    return render_template('settings.html', contract=contract)


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


@app.route('/settings', methods=['POST'])
def setting_save():
    key = request.args.get('api_key', '')
    contract_id = request.args.get('contract_id', '')

    contract = Contract.query.filter_by(id=contract_id).first()

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."
    if not check_digit(contract_id) or not contract \
            :
        return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

    date = request.form.get('date', '')
    preset = request.form.get('preset', '')

    if not validate_date(date) or (preset not in presets and preset != 'other'):
        return "<strong>Ошибки при заполнении формы.</strong> Пожалуйста, что все поля заполнены.<br><a onclick='history.go(-1);'>Назад</a>"

    contract.start = date
    if preset != 'other':
        contract.preset = preset
    db.session.commit()

    return """
            <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
            """


def get_week(start, now):
    monday1 = (now - timedelta(days=now.weekday()))
    monday2 = (start - timedelta(days=start.weekday()))

    return (monday1 - monday2).days // 7


def tasks():
    today = datetime.today().date()
    contracts = Contract.query.filter(Contract.start != None).all()
    notifications = Notification.query.all()

    for contract in contracts:
        for notification in notifications:

            if notification.preset in contract.preset.split('|'):
                if notification not in contract.sent_notifications and get_week(contract.start, today) >= notification.week:
                    medsenger_api.send_message(contract.id, notification.text, only_doctor=False, only_patient=True)

                    if notification.info_materials:
                        medsenger_api.set_info_materials(contract.id, notification.info_materials)

                    contract.sent_notifications.append(notification)

    db.session.commit()

def sender():
    while True:
        tasks()
        time.sleep(60 * 5)


@app.route('/message', methods=['POST'])
def message():
    return "ok"

if __name__ == "__main__":
    t = Thread(target=sender)
    t.start()

    app.run(host=HOST, port=PORT)

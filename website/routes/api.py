import os
import json
import datetime as dt

from werkzeug.utils import secure_filename

from flask import (Flask, render_template, request, url_for, redirect, jsonify, flash, Blueprint)
from flask_login import login_required, current_user, login_user

from core import config
from functions import *
from database import DatabaseManager


api = Blueprint('api', __name__)
logger = Logger(config)
database_manager = DatabaseManager(config.DATABASE)


# start: CHAT
@api.route('/submit-chat-message/<string:room_id>', methods=['POST'])
@login_required
def submit_chat_message(room_id):
    message_text = request.form.get('message')
    file = request.files.get('file')

    if not message_text and not file:
        return redirect(url_for('chat.room', room_id=room_id))

    try:
        with database_manager as session:
            meta_data = {'is_file': False}

            if file and allowed_file(file.filename, config.ALLOWED_EXTENSIONS):
                filename = secure_filename(file.filename)
                file.save(os.path.join(config.FILE_UPLOAD_DIR, filename))
                meta_data = {
                    'is_file': True,
                    'filename': filename
                }

            message = database_manager.ChatMessage(
                id=generate_id('uuid'),
                datetime=dt.datetime.now(),
                message=message_text if message_text else '',
                sender_id=current_user.id,
                room_id=room_id,
                meta_data=json.dumps(meta_data)
            )
            
            session.add(message)
            session.commit()

        return redirect(url_for('chat.room', room_id=room_id))

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('chat.index'), code=302)

@api.route('/create-chat-room', methods=['POST'])
@login_required
def create_room():
    try:

        room_name = request.form['room_name']
        if room_name:
            with database_manager as session:
                room = database_manager.ChatRoom(
                    id=generate_id('uuid'),
                    name=room_name,
                    creation_date=dt.datetime.now(),
                    room_creator_id=current_user.id
                )
                
                session.add(room)
                session.commit()
        
        return redirect(url_for('chat.home'), code=302)

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('chat.home'), code=302)

@api.route('/delete-chat-room/<string:room_id>', methods=['POST'])
@login_required
def delete_room(room_id):
    try:
        if room_id:
            with database_manager as session:
                room = session.query(database_manager.ChatRoom).filter_by(id=room_id).first()
                room_messages = session.query(database_manager.ChatMessage).filter_by(room_id=room_id).all()

                session.delete(room)
                for message in room_messages:
                    session.delete(message)
                
                session.commit()
        return redirect(url_for('admin.index'), code=302)

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('admin.index'), code=302)
# end: CHAT


# start: USER
@api.route('alter-user-information/<string:user_id>', methods=['POST'])
def alter_user_information(user_id):
    username = request.form['username']
    email = request.form['email']
    is_admin = request.form.get('is_admin')
 
    try:
        with database_manager as session:
            user = session.query(database_manager.User).filter_by(id=user_id).first()
            user.username = username
            user.meta_data = json.loads(user.meta_data)
            user.meta_data['is_admin'] = 'True' if is_admin else "False"
            user.meta_data = json.dumps(user.meta_data)
            session.commit()

        return redirect(url_for('chat.index'), code=302)

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('chat.index'), code=302)


@api.route('/alter-user-profile-picture/<string:user_id>', methods=['POST'])
@login_required
def alter_user_profile_picture(user_id):
    try:

        file = request.files['file']
        if not allowed_file(file.filename, config.ALLOWED_EXTENSIONS):
            flash('File type not allowed.', 'error')
            return redirect(url_for('user.profile'), code=302)
        else:
            filename = secure_filename(file.filename)
            file.save(os.path.join(config.FILE_UPLOAD_DIR, filename))

            with database_manager as session:
                user = session.query(database_manager.User).filter_by(id=user_id).first()

                user.meta_data = json.loads(user.meta_data)
                user.meta_data['profile_picture'] = filename
                user.meta_data = json.dumps(user.meta_data)
                session.commit()

            return redirect(url_for('user.profile'), code=302)

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('chat.index'), code=302)
# end: USER

# start: AUTH
@api.route('/login-user', methods=['POST'])
def login_user_profile():
    try:
        with database_manager as session:
            user = session.query(database_manager.User).filter_by(username=request.form.get("username")).first()

            if user and user.password == request.form.get("password"):
                login_user(user, remember=bool(request.form.get('remember')))

                user.meta_data = json.loads(user.meta_data)
                user.meta_data.update({
                    'last_login_datetime': str(dt.datetime.now()),
                    'last_login_user_info': {
                        'remote_addr': request.remote_addr,
                        'x_forwarded_for': request.headers.get('X-Forwarded-For')
                    }
                })
                user.meta_data = json.dumps(user.meta_data)
                session.commit()

                flash('You were successfully logged in')
                return redirect(url_for('chat.index'))
            else:
                flash('Wrong username or password.', 'error')
                return redirect(url_for('auth.login'))
    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('admin.index'), code=302)

@api.route('/signup-user', methods=['POST'])
def signup_user():
    try:
        with database_manager as session:
            user = session.query(database_manager.User).filter_by(username=request.form.get('username')).first()

        if user:
            flash('username taken.', 'error')
            return redirect(url_for('auth.signup'))
        else:
            with database_manager as session:
                new_user = database_manager.User(
                    id=generate_id('uuid'),
                    username=request.form.get('username'),
                    password=request.form.get('password'),
                    meta_data=json.dumps({'email': request.form.get('email'), "is_admin": "False"}))

                session.add(new_user)
                session.commit()

            return redirect(url_for('auth.login'))

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('admin.index'), code=302)

@api.route('alter-user-password/<string:user_id>', methods=['POST'])
def alter_user_password(user_id):
    try:
        with database_manager as session:
            user = session.query(database_manager.User).filter_by(id=user_id).first()

            current_password = request.form['current_password']
            new_password = request.form['new_password']
            new_password_2 = request.form['new_password_2']

            if current_password != user.password:
                flash('Incorrect password', 'error')
            elif new_password != new_password_2:
                flash('New passwords don\'t match', 'error')
            elif len(new_password) <= 4:
                flash('Password length has to be greater than 4.', 'error')
            elif current_password == new_password:
                flash('New password cannot be the same as the current one.', 'error')
            else:
                user.password = new_password
                session.commit()
                flash('Password has successfully been changed')
                return redirect(url_for('user.profile'), code=302)

            return redirect(url_for('auth.reset_password'), code=302)

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('user.profile'), code=302)
# end: AUTH

# start: SERVER
@api.route('/delete-file/<string:file_name>', methods=['POST'])
@login_required
def delete_file(file_name):
    try:
        os.remove(os.path.join(config.FILE_UPLOAD_DIR, file_name))
        flash(f'{file_name} deleted successfully')
        return redirect(url_for('admin.index'), code=302)

    except Exception as exc:
        log_api_error(logger, exc, request)
        return redirect(url_for('admin.index'), code=302)
# end: SERVER
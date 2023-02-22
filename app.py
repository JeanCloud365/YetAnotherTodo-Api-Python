import sqlite3
import json
import os
import typing as t
from dataclasses import dataclass
from apiflask import APIFlask, Schema, abort, HTTPTokenAuth
from flask import jsonify,render_template, request,Response
from authlib.integrations.flask_oauth2 import current_token
from apiflask.fields import Integer, String
from apiflask.validators import Length, OneOf
from flask_azure_oauth import FlaskAzureOauth
from apiflask import Schema
from apiflask.fields import Integer, String, List, Nested, Boolean
from apiflask.validators import Length, OneOf
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests
import jsonpickle
DB_FILE="todo.db"
load_dotenv()  # take environment variables from .env.
app = APIFlask(__name__,title='Yet Another Todo',version='beta')
app.config['AZURE_OAUTH_TENANCY'] = '21bd23b0-751d-4a22-8367-6a57ecd77b49'
#app.config['AZURE_OAUTH_APPLICATION_ID'] = ['709a97a6-fffc-43f5-8020-64925fc69760','api://yata']
app.config['AZURE_OAUTH_APPLICATION_ID'] = '709a97a6-fffc-43f5-8020-64925fc69760'
auth = FlaskAzureOauth()
auth.init_app(app)

app.security_schemes = {  # equals to use config SECURITY_SCHEMES
    'OAuth2': {
      'type': 'oauth2',
      'flows':{
        'implicit':{
            'authorizationUrl':'https://login.microsoftonline.com/21bd23b0-751d-4a22-8367-6a57ecd77b49/oauth2/v2.0/authorize',
            'scopes':{'api://709a97a6-fffc-43f5-8020-64925fc69760/impersonate':'user scope'}
        }
      }
    }
}
app.servers = [
    {
        'description': 'Production Server',
        'url': f"{os.environ.get('base_url')}"
    }
]
app.config['SWAGGER_UI_OAUTH_CONFIG'] = {
    'clientId': '4b2b7ae1-da3d-40c5-888e-b4d2eefc1604'
}
app.config['SWAGGER_UI_CONFIG'] = {
    'oauth2RedirectUrl' : os.environ.get('base_url') +'/docs/oauth2-redirect'
}

auth_legacy = HTTPBasicAuth()
users = {
    "admin": generate_password_hash("admin"),
}

@auth_legacy.verify_password
def verify_password(username, password):
    if username in users and \
            check_password_hash(users.get(username), password):
        return username



class WebhookIn(Schema):
    type = String(required=True,validate=OneOf(['created','completed']))
    url = String(required=True)
class TaskIn(Schema):
    description = String(required=True)
class TaskOut(Schema):
    id= Integer()
    description = String()
    user = Integer()
    done = Boolean()
class UserOut(Schema):
    id=Integer()
    external_id=String()
    email=String()


class UserQuery(Schema):
    value=List(Nested(UserOut))

class TaskQuery(Schema):
    value=List(Nested(TaskOut))


@dataclass
class User:
    def __init__(self,id=None,external_id=None,email=None) -> None:
        self.id = id
        self.external_id = external_id
        self.email = email
    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, 
            sort_keys=True, indent=4)
    id:int = 0
    external_id:str = ""
    email:str = ""

@dataclass
class Webhook:
    def __init__(self,id=None,user=None,url=None,type=None)  -> None:
        self.id = id
        self.url = url
        self.user = user
        self.type = type
    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, 
            sort_keys=True, indent=4)
    id:int = None
    url:str = None
    user:int = None
    type:str = None

@dataclass
class Task:
    def __init__(self,id=None,user=None,description=None,done=None) -> None:
        self.id = id
        self.description = description
        self.done = done
        self.user = user
    
    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, 
            sort_keys=True, indent=4)
    id:int = 0
    description:str = ""
    done:bool = 0
    user:int = ""

def db_get_db():
    conn = sqlite3.connect(DB_FILE)
    return conn

def db_create_db():
   tables = ["""
   create table if not exists user (
    id integer primary key autoincrement,
    external_id string not null,
    email string not null
    
    )
   """,
   """
   create table if not exists task (
    id integer primary key autoincrement,
    user integer not null,
    description string not null,
    done bit default 0
   )
   """,
   """
   create table if not exists webhook (
    id integer primary key autoincrement,
    user integer not null,
    url string not null,
    type string not null
   )
   """
   ]
   db = db_get_db()
   cursor = db.cursor()
   for table in tables:
    cursor.execute(table)

def db_get_external_user(external_id:String):
    db = db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select * from user where external_id = '{external_id}'")
    rows = result.fetchall()
    return [User(*row) for row in rows]

def db_list_all_users():
    db = db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select * from user")
    rows = result.fetchall()
    return [User(*row) for row in rows]

def db_list_legacy():
    db = db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select a.email as email, b.id as id, b.description as description, b.done as completed from user a inner join task b on b.user = a.id")
    rows = result.fetchall()
    return rows

def db_create_user(email:str, external_id:str)->int:
    db = db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"insert into user(external_id,email) values (?,?)",[external_id,email])
    db.commit()
    return result.lastrowid

def db_create_task(user:str,description:str)->int:
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"insert into task(user,description) values (?,?)",[user,description])
    db.commit()
    return result.lastrowid
def db_complete_task(id:int,user:int):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"update task set done = 1 where id = ? and user = ?",[id,user])
    db.commit()
    return True
def db_complete_task_legacy(id:int):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"update task set done = 1 where id = ?",[id])
    db.commit()
    return True
def db_list_all_tasks():
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select * from task")
    rows = result.fetchall()
    return [Task(*row) for row in rows]
def db_list_user_tasks(user:int):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select * from task where user = ?",[user])
    rows = result.fetchall()
    return [Task(*row) for row in rows]
def db_get_user_task(id:int,user:int):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select * from task where user = ? and id = ?",[user,id])
    rows = result.fetchall()
    return [Task(*row) for row in rows]

def db_create_user_webhook(url:int,user:int,type:str):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"insert into webhook(user,url,type) values (?,?,?)",[user,url,type])
    db.commit()
    return result.lastrowid
def db_delete_user_webhook(id:int,user:int):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"delete from webhook where user = ? and id = ?",[user,id])
    db.commit()
    return

def db_get_user_webhook(user:int,type:str):
    db=db_get_db()
    cursor = db.cursor()
    result = cursor.execute(f"select * from webhook where user = ? and type = ?",[user,type])
    rows = result.fetchall()
    return [Webhook(*row) for row in rows]

def get_user_from_token()->User:
    if current_token is None:
        raise "No token present"
    external_id = current_token.claims["oid"]
    email = current_token.claims["unique_name"]
    user = User()
    user.email = email
    user.external_id = external_id
    print(f"current_user: {user.external_id}")
    return user



def get_or_create_user()->User:
    token_user = get_user_from_token()
    db_user = db_get_external_user(token_user.external_id)
    if len(db_user) == 0:
        db_create_user(token_user.email,token_user.external_id)
        db_user = db_get_external_user(token_user.external_id)
    return db_user[0]

def create_task(description:str)->Task:
    user = get_or_create_user()
    id = db_create_task(user=user.id,description=description)
    task = db_get_user_task(id,user.id)
    webhooks = db_get_user_webhook(user.id,'created')
    for webhook in webhooks:
        try:
          data = jsonpickle.encode(task[0],unpicklable=True)
          requests.post(webhook.url,data,headers={'Content-Type':'application/json'})
          print(f"Task Creation Webhook Sent To : {webhook.url}. Payload: {data}")
        except Exception as e:
            print(f"Task Creation Webhook Failed For : {webhook.url}. Error: {e}. Payload: {data}")
            pass
    return task

def complete_task(id:str):
    user = get_or_create_user()
    db_complete_task(id,user.id)
    task = db_get_user_task(id,user.id)
    webhooks = db_get_user_webhook(user.id,'completed')
    for webhook in webhooks:
        try:
          data = jsonpickle.encode(task[0])
          requests.post(webhook.url,data,headers={'Content-Type':'application/json'})
          print(f"Task Completion Webhook Sent To : {webhook.url}. Payload: {data}")
        except Exception as e:
            print(f"Task Completion Webhook Failed For : {webhook.url}. Error: {e}. Payload: {data}")
            pass
    return
def list_user_tasks()->t.List[Task]:
    user = get_or_create_user()
    return db_list_user_tasks(user.id)
def list_admin_tasks()->t.List[Task]:
    user = get_or_create_user()
    return db_list_all_tasks()
def list_admin_users()->t.List[User]:
    user = get_or_create_user()
    return db_list_all_users()
def create_webhook(type:str,url:str):
    user = get_or_create_user()
    return db_create_user_webhook(url=url,user=user.id,type=type)
def delete_webhook(id:int):
    user = get_or_create_user()
    db_delete_user_webhook(id,user.id)

@app.get('/task')
@auth()
@app.doc(security='OAuth2',summary='List Tasks',operation_id='user-task-list',description='List Tasks')
@app.output(TaskQuery)
def api_get_task():
    data = list_user_tasks()
    print(data)
    return {'value': data}

@app.post('/task')
@auth()
@app.input(TaskIn, location='json')  # data
@app.doc(security='OAuth2',summary='Create task',operation_id='user-task-create',description='Create a task')
def api_post_task(data):
    return create_task(data['description']),'201'

@app.post('/task/<int:task>/complete')
@app.doc(security='OAuth2',summary='Complete task',operation_id='user-task-complete',description='Complete a task')
@auth()
def api_complete_task(task):
    complete_task(task)
    return {},'200'

@app.get('/admin/user')
@app.doc(security='OAuth2',summary='List users (admin)',operation_id='admin_user',description='List users as an admin')
@app.output(UserQuery)
@auth()
def api_admin_users():
    data = list_admin_users()
    print(data)
    return {'value':data}

@app.get('/admin/task')
@app.doc(security='OAuth2',summary='List tasks (admin)',operation_id='admin_task',description='List tasks as an admin')
@app.output(TaskQuery)
@auth()
def api_admin_tasks():
    data = list_admin_tasks()
    print(data)
    return {'value': data}

@app.post('/webhook')
@app.doc(security='OAuth2',summary='Create webhook',operation_id='create_webhook',description='Create Webhook')
@app.input(WebhookIn)
@auth()
def api_create_webhook(data):
    id = create_webhook(data['type'],data['url'])
    resp = Response('')
    resp.status_code = 201
    resp.location = os.environ.get('base_url') + "/webhook/" + str(id)  
    return resp

@app.delete('/webhook/<int:webhook>')
@app.doc(security='OAuth2',summary='Delete webhook',operation_id='delete_webhook',description='Delete Webhook')
@auth()
def api_delete_webhook(webhook):
    delete_webhook(webhook)
    return {},'200'


@app.route('/admin/legacy',methods = ['POST', 'GET'])
@app.doc(hide=True,deprecated=True)
@auth_legacy.login_required
def api_admin_legacy():
    if(request.method == "POST"):
        db_complete_task_legacy(request.form.get("id"))
    data = db_list_legacy()
    print(data)
    return render_template('legacy.html',data= data)




if __name__ == "__main__":
    db_create_db()
    """
    Here you can change debug and port
    Remember that, in order to make this API functional, you must set debug in False
    """
    app.run(host='0.0.0.0', port=os.environ.get('PORT'), debug=os.environ.get('DEBUG'))

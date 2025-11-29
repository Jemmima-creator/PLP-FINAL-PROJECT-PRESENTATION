from flask import Flask, render_template, request, abort, session, redirect
from pymongo import MongoClient
import uuid
from groq import Groq
from datetime import datetime, timezone
from typing import Literal
from random import randint
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Environment variables
MONGO_URL = os.getenv("MONGO_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

# Database client
client = MongoClient(MONGO_URL)
db = client["Football_ChatBot"]
chats_collection = db["Chat_ids"]
user_data_collection = db["users"]

# Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Flask app
app = Flask(__name__)
app.secret_key = SECRET_KEY


def talk_to_ai(msgs: list[dict]):
    # Remove Time key for model input
    msgs = [{k: v for k, v in msg.items() if k != "Time"} for msg in msgs]

    completion = groq_client.chat.completions.create(
        model="meta-llama/llama-4-maverick-17b-128e-instruct",
        messages=msgs,
        temperature=1,
        max_completion_tokens=256,
        top_p=1,
        stream=True,
        stop=None
    )

    msg = ""
    for chunk in completion:
        msg += str(chunk.choices[0].delta.content or "")

    assistant_response = {
        "role": "assistant",
        "content": msg,
        "Time": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }
    return assistant_response


@app.route("/")
def landing_page():
    if session.get("user_id"):
        return render_template("chats/index.html", user_id=session.get("user_id"))
    return render_template("chats/login.html")


@app.route("/login", methods=["POST"])
def login():
    login_email = request.form.get("email")
    login_password = request.form.get("password")

    user: dict = user_data_collection.find_one({"email": login_email}) or {}

    if user.get("password") == login_password:
        session["user_id"] = user.get("_id")

    return redirect("/")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        user_data: dict[Literal["_id", "name", "email", "password", "confirm"], str] = request.get_json()
        email = user_data["email"].lower()

        if (password := user_data.get("password")) and password == user_data.get("confirm"):
            email_db = user_data_collection.find_one({"email": email})
            if email_db:
                return abort(409, "email already exists")

            del user_data["confirm"]
            user_data["_id"] = str(uuid.uuid4())
            user_data_collection.insert_one(user_data)

            session["user_id"] = user_data["_id"]
            return "success"

    return render_template("chats/signup.html")


@app.route("/signout")
def signout():
    session.clear()
    return redirect("/")


@app.route("/all_chats_ids", methods=["POST"])
def fetch_history():
    user_id = request.get_json()["user_id"]

    if session.get("user_id") != user_id:
        return abort(401, "RESOURCE UNAUTHORIZED")

    user = user_data_collection.find_one({"_id": user_id})

    if user:
        return user.get("associated_chats") or abort(404, "NO CHATS ON RECORD")

    return abort(404, "NO SUCH USER")


@app.route("/acquire_messages", methods=["POST"])
def acquire_messages():
    if (s_user_id := session.get("user_id")):
        chat_details = request.get_json()
        chat_id = chat_details["chat_id"]

        chat_data = chats_collection.find_one({"_id": chat_id}) or {}

        if chat_data.get("user_id") != s_user_id or chat_details["user_id"] != s_user_id:
            return abort(401, "RESOURCE UNAUTHORIZED")

        if (chat := chat_data.get("chat_progress")):
            chat.pop(0)
            return chat or abort(404, "NO MESSAGES PRESENT")

        return abort(404, "NOT FOUND")

    return redirect("/")


@app.route("/new_chat", methods=["POST"])
def new_chat():
    chat_id = randint(1000000000, 9999999999)

    msgs = [{
        "role": "system",
        "content": "you are a chatbot, you provide brief, structured, evidence-based sports health guidance using HTML tags for formatting."
    }]

    user_id = (request.get_json() or {}).get("user_id")

    chats_collection.insert_one({
        "_id": chat_id,
        "user_id": user_id,
        "title": f"Conversation Id: {chat_id}",
        "chat_progress": msgs
    })

    user_info = user_data_collection.find_one({"_id": user_id}) or {}
    if user_info:
        user_data_collection.update_one({"_id": user_id}, {"$push": {"associated_chats": chat_id}})

    return {"chat_id": chat_id}


@app.route("/chatmessage", methods=["POST"])
def handle_message():
    data = request.get_json() or {}
    req_text = data.get("chat_text")
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")

    if session.get("user_id") != user_id:
        return abort(401, "RESOURCE UNAUTHORIZED")

    user_date = (data.get("date") or "").encode("utf-8", "replace").decode()

    chat_progress = (chats_collection.find_one({"_id": chat_id}) or {}).get("chat_progress") or []

    if chat_progress:
        user_input = {"role": "user", "content": req_text, "Time": user_date}

        chats_collection.update_one({"_id": chat_id}, {"$push": {"chat_progress": user_input}})

        assistant = talk_to_ai(chat_progress + [user_input])

        chats_collection.update_one({"_id": chat_id}, {"$push": {"chat_progress": assistant}})

        return assistant

    return abort(404)


if __name__ == "__main__":
    app.run(debug=True)

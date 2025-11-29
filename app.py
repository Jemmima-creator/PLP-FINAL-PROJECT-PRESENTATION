from groq import Groq
from random import randint
from pathlib import Path
import json
from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Load .env values
load_dotenv()

# Read variables from environment
MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("MONGO_DB")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

chat_id = randint(1000000000,9999999999)

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

chat = collection.find_one({"_id":chat_id}) or {}

if (b := chat.get("chat_progress")):
    msgs: list = b
else:
    msgs: list = [{
        "role": "system",
        "content": "you are a chatbot, you are supposed to provide accessible, personalized and evidence-based sports health guidance to help footballers improve performance while protecting their physical and mental wellbeing"
    }]
    collection.insert_one({
        "_id": chat_id,
        "title": f"Conversation Id: {chat_id}",
        "chat_progress": msgs
    })

client = Groq(api_key=GROQ_API_KEY)

def user_input():
    return input("input user prompt: ")

while True:
    user = {"role": "user", "content": user_input()}

    collection.update_one({"_id": chat_id}, {"$push": {"chat_progress": user}})
    msgs.append(user)

    completion = client.chat.completions.create(
        model="meta-llama/llama-4-maverick-17b-128e-instruct",
        messages=msgs,
        temperature=1,
        max_completion_tokens=1024,
        top_p=1,
        stream=True,
        stop=None
    )
    
    msg = ""
    for chunk in completion:
        msg += str(chunk.choices[0].delta.content or "")

    assistant = {"role": "assistant", "content": msg}
    collection.update_one({"_id": chat_id}, {"$push": {"chat_progress": assistant}})
    msgs.append(assistant)

    print(assistant["content"])

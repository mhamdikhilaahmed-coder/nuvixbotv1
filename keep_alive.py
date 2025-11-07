from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.get("/")
def index():
    return "Nuvix Tickets OK", 200

def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    Thread(target=run, daemon=True).start()

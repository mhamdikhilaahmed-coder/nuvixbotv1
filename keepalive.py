import os
from flask import Flask, jsonify
app = Flask(__name__)
@app.get("/")
def root():
    return jsonify(status="ok", service="Nuvix Tickets", message="connected", since=os.environ.get("CONNECTED_SINCE","unknown"))
def run():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

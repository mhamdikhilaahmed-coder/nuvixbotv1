import os
from flask import Flask, jsonify
app = Flask(__name__)
@app.get("/")
def index():
    return jsonify(ok=True, name="Nuvix Tickets", ts="2025-11-07 20:29:59 UTC")
def run():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
if __name__ == "__main__":
    run()

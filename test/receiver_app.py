from flask import Flask, request, jsonify
from flask_cors import CORS


app = Flask("backend_app")
cors = CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/detection', methods=['POST'])
def update_status():
    objects = request.json
    print(objects)
    return 'k'

if __name__ == "__main__":
    app.run('0.0.0.0', port=5988)
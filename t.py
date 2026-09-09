from flask import Flask, jsonify, request

print("helloe..........")
print("world hi")
print("how are you i am fine")
print("this is")
print("what about you")
app = Flask(__name__)


@app.route("/")
def home():
    return jsonify({
        "message": "Welcome to the application"
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    })


@app.route("/users", methods=["GET"])
def get_users():
    users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    return jsonify(users)


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    return jsonify({
        "id": user_id,
        "name": f"User {user_id}"
    })


@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json()

    return jsonify({
        "message": "User created",
        "user": data
    }), 201


@app.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.get_json()

    return jsonify({
        "message": "User updated",
        "id": user_id,
        "user": data
    })


@app.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    return jsonify({
        "message": "User deleted",
        "id": user_id
    })


@app.route("/products", methods=["GET"])
def get_products():
    return jsonify([
        {"id": 101, "name": "Laptop"},
        {"id": 102, "name": "Keyboard"},
    ])


@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json()

    return jsonify({
        "message": "Order created",
        "order": data
    }), 201


if __name__ == "__main__":
    # Flask's built-in development server
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )

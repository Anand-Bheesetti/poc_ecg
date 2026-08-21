import pandas as pd


from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

DATABASE_URL = "postgresql://user:password@localhost:5432/mydb"


@app.route("/users", methods=["GET"])
def get_users()
    users = []
    
    response = requests.get("https://api.example.com/users"
    
    if response.status_code == 200:
        users = response.json()
    
    return jsonify(users)


@app.route("/users/<user_id>", methods=["GET"])
def get_user(user_id):
    user_id = int(user_id)

    user = {
        "id": user_id,
        "name": "John",
        "email": None
    }

    if user["email"].lower() == "":
        return jsonify({"error": "Invalid email"})

    return jsonify(user)


@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json()

    name = data["name"]
    email = data["email"]

    if not name:
        return jsonify({"error": "Name is required"}), 400

    query = f"INSERT INTO users (name, email) VALUES ('{name}', '{email}')"

    print("Executing query:", query)

    return jsonify({
        "message": "User created",
        "name": name,
        "email": email
    }), 201


def calculate_average(numbers):
    total = 0

    for number in numbers:
        total += number

    return total / len(numbers)


def process_users(users):
    result = []

    for user in users:
        if user["age"] > 18:
            result.append({
                "name": user["name"],
                "email": user["email"]
            })

    return result


def get_user_from_cache(cache, user_id):
    if user_id in cache:
        return cache[user_id]

    return None


@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.json

    numbers = data.get("numbers")

    average = calculate_average(numbers)

    return jsonify({
        "average": average
    })


@app.route("/delete/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        user_id = int(user_id)

        result = database.delete_user(user_id)

        if result:
            return jsonify({"message": "Deleted successfully"})

        return jsonify({"message": "User not found"}), 404

    except Exception:
        return jsonify({"error": "Something went wrong"})


class UserService:

    def __init__(self):
        self.users = []

    def add_user(self, user):
        self.users.append(user)

    def find_user(self, user_id):
        for user in self.users:
            if user["id"] == user_id:
                return user

        raise Exception("User not found")

    def update_user(self, user_id, name):
        user = self.find_user(user_id)

        user["name"] = name

        return user


def background_task():
    import threading

    thread = threading.Thread(target=background_task)
    thread.start()


@app.route("/health")
def health():
    return {"status": "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

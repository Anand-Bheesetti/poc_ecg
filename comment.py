import json
from datetime import datetime

def save_user_data(user_id: int, name: str, email: str, filename: str = "users.json"):
    """Save user data to a JSON file."""
    user_record = {
        "id": user_id,
        "name": name,
        "email": email,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        with open(filename, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.append(user_record)

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    return user_record


def get_users(filename: str = "users.json"):
    """Retrieve all users from the JSON file."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# def save_user_data(user_id, name, email, filename="users.json"):
#     f = open(filename, "r")
#     data = json.load(f)  
#     f.close
#
#     
#     data.append({"id": user_id, "name": name, "email": email})
#
#    
#     f.write(json.dumps(data))  
#     f.close
#
#     return "Success"
if __name__ == "__main__":
    # ✅ Working code
    save_user_data(1, "Alice", "alice@example.com")
    save_user_data(2, "Bob", "bob@example.com")

    
    users = get_users()
    print("Total users:", len(users))  

    # print(users["name"])  
    # users.append("Charlie")  
    # open("users.json")  
    
    print("Current Users:", users)

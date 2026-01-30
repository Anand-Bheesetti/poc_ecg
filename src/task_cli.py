import json
import os
import sys
import argparse

DATA_FILE = "tasks_data.json"
VALID_PRIORITIES = {"low", "medium", "high"}
PRIORITY_ORDER = {"High": 1, "Medium": 2, "Low": 3}


# -----------------------------
# Persistence Layer
# -----------------------------
def load_tasks():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_tasks(tasks):
    with open(DATA_FILE, "w") as f:
        json.dump(tasks, f, indent=4)


# -----------------------------
# Core Logic
# -----------------------------
def create_task():
    print("\n📝 Create New Task")

    title = input("Task title: ").strip()
    if not title:
        print("❌ Title cannot be empty")
        return

    priority = input("Priority (Low / Medium / High): ").strip().lower()
    if priority not in VALID_PRIORITIES:
        print("❌ Invalid priority")
        return

    category = input("Category: ").strip()
    if not category:
        print("❌ Category cannot be empty")
        return

    tasks = load_tasks()
    next_id = max([t["id"] for t in tasks], default=0) + 1

    task = {
        "id": next_id,
        "title": title,
        "priority": priority.capitalize(),
        "category": category
    }

    tasks.append(task)
    save_tasks(tasks)

    print("✅ Task created successfully")


def list_tasks(priority=None, category=None, sort_by_priority=False):
    tasks = load_tasks()

    # -----------------------------
    # Filtering
    # -----------------------------
    if priority:
        tasks = [
            t for t in tasks
            if t["priority"].lower() == priority.lower()
        ]

    if category:
        tasks = [
            t for t in tasks
            if t["category"].lower() == category.lower()
        ]

    # -----------------------------
    # Sorting
    # -----------------------------
    if sort_by_priority:
        tasks.sort(key=lambda t: PRIORITY_ORDER[t["priority"]])

    if not tasks:
        print("\n📭 No tasks match the criteria")
        return

    print("\n📋 Task List")
    print("-" * 70)

    for task in tasks:
        print(
            f"[{task['id']}] "
            f"{task['title']} | "
            f"Priority: {task['priority']} | "
            f"Category: {task['category']}"
        )

    print("-" * 70)


# -----------------------------
# CLI Interface
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Task CLI")

    subparsers = parser.add_subparsers(dest="command")

    # create command
    subparsers.add_parser("create", help="Create a new task")

    # list command with filters
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument(
        "--priority",
        choices=["Low", "Medium", "High"],
        help="Filter tasks by priority"
    )
    list_parser.add_argument(
        "--category",
        help="Filter tasks by category"
    )
    list_parser.add_argument(
        "--sort",
        choices=["priority"],
        help="Sort tasks (priority)"
    )

    args = parser.parse_args()

    if args.command == "create":
        create_task()

    elif args.command == "list":
        list_tasks(
            priority=args.priority,
            category=args.category,
            sort_by_priority=(args.sort == "priority")
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

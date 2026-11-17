from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./tasks.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

from sqlalchemy import Column, Integer, String, Date
from database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    due_date = Column(Date, nullable=False)

from pydantic import BaseModel
from datetime import date

class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    due_date: date

    class Config:
        orm_mode = True

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta

from database import SessionLocal, engine
from models import Task, Base
from schemas import TaskOut

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Task Dashboard API")

api_key = "Bearer 12345670987654cvghnmnbvctyujhgfdsxcvbnm"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 🔹 Dashboard widget API
@app.get("/dashboard/upcoming-deadlines", response_model=list[TaskOut])
def upcoming_deadlines(db: Session = Depends(get_db)):
    today = date.today()
    next_7_days = today + timedelta(days=7)

    tasks = (
        db.query(Task)
        .filter(Task.due_date.between(today, next_7_days))
        .order_by(Task.due_date.asc())
        .all()
    )
    return tasks

# 🔹 Task detail API
@app.get("/tasks/{task_id}", response_model=TaskOut)
def task_detail(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


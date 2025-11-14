import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Literal
from bson import ObjectId
from database import db, create_document, get_documents
from schemas import UserAccount, Department, Employee, LeaveRequest, Notification

app = FastAPI(title="HRMS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

# Simple JWT-like stub (not full auth): token is user_id. In real systems, use proper JWT.
class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    role: str
    full_name: str
    user_id: str

# Utilities

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Very light auth: expects Authorization: Bearer <user_id>. If not provided, treat as guest."""
    if not credentials:
        return None
    user_id = credentials.credentials
    user = db["useraccount"].find_one({"_id": to_object_id(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    user["_id"] = str(user["_id"])
    return user


@app.get("/")
def read_root():
    return {"message": "HRMS Backend Running"}


@app.get("/test")
def test_database():
    info = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            info["database"] = "✅ Available"
            info["connection_status"] = "Connected"
            info["collections"] = db.list_collection_names()
    except Exception as e:
        info["database"] = f"⚠️ Error: {str(e)[:60]}"
    return info


# Authentication (demo-level; stores hashed_password but compares plain for simplicity)
@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    user = db["useraccount"].find_one({"email": payload.email})
    if not user or not user.get("hashed_password"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Demo: compare plain text. In production, verify bcrypt hash.
    if payload.password != user["hashed_password"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(token=str(user["_id"]), role=user.get("role", "Employee"), full_name=user.get("full_name", ""), user_id=str(user["_id"]))


# Seed minimal roles for demo
class SeedUser(BaseModel):
    email: str
    full_name: str
    role: Literal["HR", "Manager", "Employee"]
    password: str

@app.post("/seed/user")
def seed_user(u: SeedUser):
    existing = db["useraccount"].find_one({"email": u.email})
    if existing:
        return {"message": "exists", "id": str(existing["_id"]) }
    uid = create_document("useraccount", {
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "hashed_password": u.password,
        "is_active": True,
    })
    return {"message": "created", "id": uid}


# Departments
class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    manager_id: Optional[str] = None

@app.post("/departments")
def create_department(dep: DepartmentCreate, user=Depends(get_current_user)):
    if not user or user.get("role") != "HR":
        raise HTTPException(status_code=403, detail="HR only")
    dep_id = create_document("department", dep.dict())
    return {"id": dep_id}

@app.get("/departments")
def list_departments(user=Depends(get_current_user)):
    items = get_documents("department")
    for it in items:
        it["_id"] = str(it["_id"])
    return items


# Employees (HR CRUD)
class EmployeeCreate(BaseModel):
    email: str
    full_name: str
    password: str
    joining_date: Optional[str] = None
    department_id: Optional[str] = None
    designation: Optional[str] = None
    manager_user_id: Optional[str] = None

@app.post("/employees")
def create_employee(payload: EmployeeCreate, user=Depends(get_current_user)):
    if not user or user.get("role") != "HR":
        raise HTTPException(status_code=403, detail="HR only")
    # create user account
    existing = db["useraccount"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    user_id = create_document("useraccount", {
        "email": payload.email,
        "full_name": payload.full_name,
        "role": "Employee",
        "hashed_password": payload.password,
        "is_active": True,
    })
    # create employee profile
    emp_id = create_document("employee", {
        "user_id": user_id,
        "joining_date": payload.joining_date,
        "department_id": payload.department_id,
        "designation": payload.designation,
        "manager_user_id": payload.manager_user_id,
    })
    return {"user_id": user_id, "employee_id": emp_id}

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    department_id: Optional[str] = None
    designation: Optional[str] = None
    manager_user_id: Optional[str] = None

@app.put("/employees/{user_id}")
def update_employee(user_id: str, payload: EmployeeUpdate, user=Depends(get_current_user)):
    if not user or user.get("role") not in ["HR", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if "full_name" in updates:
        db["useraccount"].update_one({"_id": to_object_id(user_id)}, {"$set": {"full_name": updates.pop("full_name")}})
    if updates:
        db["employee"].update_one({"user_id": user_id}, {"$set": updates})
    return {"updated": True}

@app.delete("/employees/{user_id}")
def delete_employee(user_id: str, user=Depends(get_current_user)):
    if not user or user.get("role") != "HR":
        raise HTTPException(status_code=403, detail="HR only")
    db["employee"].delete_one({"user_id": user_id})
    db["useraccount"].delete_one({"_id": to_object_id(user_id)})
    return {"deleted": True}

@app.get("/employees")
def list_employees(user=Depends(get_current_user)):
    if not user or user.get("role") not in ["HR", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    # join user info and employee profile (basic)
    employees = []
    for emp in db["employee"].find({}):
        u = db["useraccount"].find_one({"_id": to_object_id(emp.get("user_id"))})
        emp["_id"] = str(emp["_id"]) if emp.get("_id") else None
        employees.append({
            "user_id": emp.get("user_id"),
            "full_name": u.get("full_name") if u else None,
            "email": u.get("email") if u else None,
            "department_id": emp.get("department_id"),
            "designation": emp.get("designation"),
            "manager_user_id": emp.get("manager_user_id"),
        })
    return employees

@app.get("/me")
def my_profile(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    emp = db["employee"].find_one({"user_id": user["_id"]})
    if emp:
        emp["_id"] = str(emp["_id"]) if emp.get("_id") else None
    return {"user": user, "employee": emp}


# Leave Management
class LeaveCreate(BaseModel):
    start_date: str
    end_date: str
    type: Literal["Annual", "Sick", "Casual", "Unpaid", "Other"] = "Annual"
    reason: Optional[str] = None

@app.post("/leaves")
def submit_leave(payload: LeaveCreate, user=Depends(get_current_user)):
    if not user or user.get("role") not in ["Employee", "Manager", "HR"]:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Determine manager: prefer employee profile manager_user_id; fallback to department manager
    emp = db["employee"].find_one({"user_id": user["_id"]})
    manager_user_id = None
    if emp and emp.get("manager_user_id"):
        manager_user_id = emp.get("manager_user_id")
    elif emp and emp.get("department_id"):
        dep = db["department"].find_one({"_id": to_object_id(emp.get("department_id"))}) if emp.get("department_id") else None
        manager_user_id = dep.get("manager_id") if dep else None
    lr_id = create_document("leaverequest", {
        "employee_user_id": user["_id"],
        "manager_user_id": manager_user_id,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "type": payload.type,
        "reason": payload.reason,
        "status": "Pending",
    })
    # Notify HR and manager
    create_document("notification", {"title": "New Leave Request", "message": f"{user.get('full_name')} submitted a leave.", "entity_type": "LeaveRequest", "entity_id": lr_id, "audience": "HR"})
    if manager_user_id:
        create_document("notification", {"title": "Approval Needed", "message": f"Leave request pending approval.", "entity_type": "LeaveRequest", "entity_id": lr_id, "user_id": manager_user_id})
    return {"id": lr_id}

class LeaveAction(BaseModel):
    action: Literal["Approve", "Reject"]
    comment: Optional[str] = None

@app.post("/leaves/{leave_id}/action")
def act_on_leave(leave_id: str, payload: LeaveAction, user=Depends(get_current_user)):
    if not user or user.get("role") not in ["Manager", "HR"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    lr = db["leaverequest"].find_one({"_id": to_object_id(leave_id)})
    if not lr:
        raise HTTPException(status_code=404, detail="Leave not found")
    status = "Approved" if payload.action == "Approve" else "Rejected"
    db["leaverequest"].update_one({"_id": to_object_id(leave_id)}, {"$set": {"status": status, "manager_comment": payload.comment, "updated_at": datetime.utcnow()}})
    # Notify employee and HR
    create_document("notification", {"title": f"Leave {status}", "message": payload.comment or "", "entity_type": "LeaveRequest", "entity_id": leave_id, "user_id": lr.get("employee_user_id")})
    create_document("notification", {"title": f"Leave {status}", "message": f"A leave was {status.lower()}.", "entity_type": "LeaveRequest", "entity_id": leave_id, "audience": "HR"})
    return {"updated": True}

@app.get("/leaves")
def list_leaves(status: Optional[str] = None, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    query = {}
    if user.get("role") == "Employee":
        query["employee_user_id"] = user["_id"]
    elif user.get("role") == "Manager":
        query["manager_user_id"] = user["_id"]
    if status:
        query["status"] = status
    items = list(db["leaverequest"].find(query))
    for it in items:
        it["_id"] = str(it["_id"]) if it.get("_id") else None
    return items


# Notifications
@app.get("/notifications")
def my_notifications(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    role = user.get("role")
    q = {"$or": [{"user_id": user["_id"]}]}
    if role:
        q["$or"].append({"audience": role})
    items = list(db["notification"].find(q).sort("created_at", -1).limit(50))
    for it in items:
        it["_id"] = str(it["_id"]) if it.get("_id") else None
    return items


# Schema endpoint for tooling
@app.get("/schema")
def get_schema_models():
    return {
        "models": [
            "UserAccount", "Department", "Employee", "LeaveRequest", "Notification"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

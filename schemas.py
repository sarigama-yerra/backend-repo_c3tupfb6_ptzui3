"""
Database Schemas for HRMS

Each Pydantic model maps to a MongoDB collection (lowercased class name).
- UserAccount -> "useraccount"
- Department -> "department"
- Employee -> "employee"
- LeaveRequest -> "leaverequest"
- Notification -> "notification"

These schemas are returned by GET /schema for tooling/inspection.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import date, datetime

class UserAccount(BaseModel):
    email: EmailStr = Field(..., description="Unique email used for login")
    full_name: str = Field(..., description="Full name of the user")
    role: Literal["HR", "Manager", "Employee"] = Field("Employee", description="System role")
    hashed_password: str = Field(..., description="BCrypt hashed password")
    is_active: bool = Field(True, description="Whether the user can sign in")

class Department(BaseModel):
    name: str = Field(..., description="Department name")
    description: Optional[str] = Field(None, description="Brief description")
    manager_id: Optional[str] = Field(None, description="UserAccount _id of the department manager")

class Employee(BaseModel):
    user_id: str = Field(..., description="UserAccount _id reference")
    employee_code: Optional[str] = Field(None, description="Internal employee code")
    joining_date: Optional[date] = Field(None, description="Date of joining")
    department_id: Optional[str] = Field(None, description="Department _id reference")
    designation: Optional[str] = Field(None, description="Job title/designation")
    manager_user_id: Optional[str] = Field(None, description="UserAccount _id of direct manager")
    phone: Optional[str] = Field(None, description="Contact number")
    address: Optional[str] = Field(None, description="Address")

class LeaveRequest(BaseModel):
    employee_user_id: str = Field(..., description="UserAccount _id of employee")
    manager_user_id: Optional[str] = Field(None, description="UserAccount _id of manager who will approve")
    start_date: date = Field(..., description="Leave start date")
    end_date: date = Field(..., description="Leave end date")
    type: Literal["Annual", "Sick", "Casual", "Unpaid", "Other"] = Field("Annual", description="Type of leave")
    reason: Optional[str] = Field(None, description="Reason provided by employee")
    status: Literal["Pending", "Approved", "Rejected"] = Field("Pending", description="Approval status")
    manager_comment: Optional[str] = Field(None, description="Comment by manager on approval/rejection")

class Notification(BaseModel):
    user_id: Optional[str] = Field(None, description="UserAccount _id of recipient; null = broadcast to HR")
    audience: Optional[Literal["HR", "Manager", "Employee"]] = Field(None, description="If set, all users with this role are recipients")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification body")
    entity_type: Optional[str] = Field(None, description="Related entity type e.g., LeaveRequest")
    entity_id: Optional[str] = Field(None, description="Related entity id")
    is_read: bool = Field(False, description="Whether user has read the notification")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp (autofilled)")

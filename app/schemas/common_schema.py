from enum import Enum
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class UserRole(str, Enum):
    ADMIN = "admin"
    HR_OWNER = "hr_owner"
    HR_MEMBER = "hr_member"
    APPLICANT = "applicant"

class JobStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"
    EXPIRED = "expired"

class ApplicationStatus(str, Enum):
    NEW = "new"
    REVIEWING = "reviewing"
    INTERVIEW = "interview"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"

class ApplicationSource(str, Enum):
    HR_SOURCED = "hr_sourced"
    APPLICANT_APPLY = "applicant_apply"

class NotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

class NotificationReadStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"

class CompanyStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"

class AuditAction(str, Enum):
    COMPANY_VERIFIED = "company_verified"
    COMPANY_REJECTED = "company_rejected"
    COMPANY_SUSPENDED = "company_suspended"
    COMPANY_UPDATED = "company_updated"
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    APPLICATION_NOTE_ADDED = "application_note_added"
    JOB_CREATED = "job_created"
    JOB_UPDATED = "job_updated"
    JOB_DELETED = "job_deleted"
    HR_MEMBER_INVITED = "hr_member_invited"
    HR_MEMBER_REMOVED = "hr_member_removed"
    USER_ROLE_UPDATED = "user_role_updated"
    USER_STATUS_UPDATED = "user_status_updated"
    USER_ANONYMIZED = "user_anonymized"
    PASSWORD_RESET = "password_reset"
    LOGIN_FAILED = "login_failed"
    PLAN_CREATED = "plan_created"
    PLAN_UPDATED = "plan_updated"
    PLAN_STATUS_TOGGLED = "plan_status_toggled"

class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class AdminLevel(str, Enum):
    PROVINCE = "province"
    DISTRICT = "district"
    WARD = "ward"

class RecommendationEnum(str, Enum):
    HIRE = "hire"
    NO_HIRE = "no_hire"
    MAYBE = "maybe"
    STRONG_HIRE = "strong_hire"

class RemoteFlexibilityEnum(str, Enum):
    REMOTE_ONLY = "remote_only"
    HYBRID = "hybrid"
    ONSITE_ONLY = "onsite_only"
    ANY = "any"

class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"

class NotificationActorType(str, Enum):
    SYSTEM = "system"
    ADMIN = "admin"
    HR_USER = "hr_user"
    APPLICANT = "applicant"

class NotificationActionType(str, Enum):
    KYC_REQUESTED = "kyc_requested"
    KYC_APPROVED = "kyc_approved"
    KYC_REJECTED = "kyc_rejected"
    NEW_CV_RECEIVED = "new_cv_received"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    APPLICATION_UPDATED = "application_updated"
    GENERAL_ALERT = "general_alert"

class CurrencyEnum(str, Enum):
    VND = "VND"
    USD = "USD"

class DiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"

class QuotaActionType(str, Enum):
    AI_INTERVIEW_GEN = "AI_INTERVIEW_GEN"
    REVERSE_MATCHING = "REVERSE_MATCHING"
    HR_PARSE_CV = "HR_PARSE_CV"
    HR_MAP_CV_AI_SCORE = "HR_MAP_CV_AI_SCORE"
    HR_MAP_BATCH_CV_AI_SCORE = "HR_MAP_BATCH_CV_AI_SCORE"
    EXPIRED_CREDIT_RECOVERY = "EXPIRED_CREDIT_RECOVERY"
    APPLICANT_SELF_SCORE = "APPLICANT_SELF_SCORE"
    UPGRADE_FREE = "UPGRADE_FREE"
    UPGRADE_PRO = "UPGRADE_PRO"
    UPGRADE_ENTERPRISE = "UPGRADE_ENTERPRISE"
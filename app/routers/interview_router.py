from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from datetime import datetime, timezone

from app.core.security import CurrentUser, require_hr
from app.schemas.interview_feedback_schema import InterviewCreate, InterviewFeedbackCreate, InterviewStatus
from app.repositories.interview_repository import InterviewRepository
from app.repositories.interview_feedback_repository import InterviewFeedbackRepository
from app.repositories.application_repository import ApplicationRepository
from app.services.email_service import send_interview_email
from app.middleware.rate_limit import limiter
from fastapi import Request, Response

router = APIRouter(prefix="/api/v1/interviews", tags=["Interview Management"])

@router.post("/")
@limiter.limit("30/day")
async def schedule_interview(
    request: Request,
    response: Response,
    payload: InterviewCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_hr)
):
    application = await ApplicationRepository.get_by_id(payload.application_id)
    if not application or application.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển hợp lệ")

    record = payload.model_dump()
    record.update({
        "company_id": current_user.company_id,
        "status": InterviewStatus.SCHEDULED.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    
    interview_id = await InterviewRepository.create(record)

    candidate_email = application.get("cv_snapshot", {}).get("candidate_info", {}).get("email")
    if candidate_email:
        send_interview_email(
            background_tasks=background_tasks,
            to=candidate_email,
            name=application.get("cv_snapshot", {}).get("display_name", "Ứng viên"),
            job_title="Vị trí bạn đã ứng tuyển",
            company_name="Công ty của chúng tôi",
            interview_time=payload.scheduled_time,
            location="Online" if payload.meeting_url else "Offline",
            meeting_link=payload.meeting_url,
            custom_message=f"Thư mời tham dự vòng: {payload.round_name}"
        )

    return {"status": "success", "message": f"Đã lên lịch vòng '{payload.round_name}'", "id": interview_id}

@router.post("/{interview_id}/feedback")
async def submit_interview_feedback(
    interview_id: str,
    payload: InterviewFeedbackCreate,
    current_user: CurrentUser = Depends(require_hr)
):
    interview = await InterviewRepository.get_by_id(interview_id)
    if not interview or interview.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch phỏng vấn")

    if current_user.id not in interview.get("interviewers", []):
        raise HTTPException(status_code=403, detail="Bạn không nằm trong danh sách hội đồng của vòng phỏng vấn này")

    existing_feedback = await InterviewFeedbackRepository.find_one({
        "interview_id": interview_id,
        "interviewer_user_id": current_user.id
    })
    if existing_feedback:
        raise HTTPException(status_code=400, detail="Bạn đã gửi đánh giá cho vòng này rồi")

    record = payload.model_dump()
    record.update({
        "application_id": interview["application_id"],
        "interviewer_user_id": current_user.id,
        "created_at": datetime.now(timezone.utc)
    })
    
    _id = await InterviewFeedbackRepository.create(record)
    return {"status": "success", "message": "Đã nộp đánh giá phỏng vấn", "id": _id}

@router.get("/application/{application_id}")
async def get_interviews_for_application(
    application_id: str,
    current_user: CurrentUser = Depends(require_hr)
):
    application = await ApplicationRepository.get_by_id(application_id)
    if not application or application.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển hợp lệ")

    interviews = await InterviewRepository.get_by_application_id(application_id)
    return {"status": "success", "data": interviews}
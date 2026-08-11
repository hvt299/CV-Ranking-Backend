from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from app.repositories.job_repository import JobRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common_schema import JobStatus, ApplicationStatus, UserRole, CompanyStatus

class AnalyticsService:
    
    @staticmethod
    def _calculate_trend(current: int, previous: int) -> Dict[str, Any]:
        if previous == 0:
            trend = 100 if current > 0 else 0
        else:
            trend = round(((current - previous) / previous) * 100)
            
        return {
            "value": current,
            "trend": abs(trend),
            "is_up": trend >= 0
        }

    @classmethod
    async def get_owner_dashboard_metrics(cls, company_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        current_active_jobs = await JobRepository.count_documents({"company_id": company_id, "status": JobStatus.OPEN.value})
        cur_jobs_created = await JobRepository.count_documents({"company_id": company_id, "created_at": {"$gte": thirty_days_ago}})
        prev_jobs_created = await JobRepository.count_documents({"company_id": company_id, "created_at": {"$gte": sixty_days_ago, "$lt": thirty_days_ago}})

        jobs = await JobRepository.find_many({"company_id": company_id}, projection={"_id": 1, "title": 1})
        job_ids = [str(j["_id"]) for j in jobs]
        job_dict = {str(j["_id"]): j.get("title", "Chiến dịch ẩn") for j in jobs}
        
        cur_cvs = await ApplicationRepository.count_documents({"job_id": {"$in": job_ids}})
        prev_cvs = await ApplicationRepository.count_documents({"job_id": {"$in": job_ids}, "created_at": {"$lt": thirty_days_ago}})

        cur_hq = await ApplicationRepository.count_documents({"job_id": {"$in": job_ids}, "ai_score.total_score": {"$gte": 80}})
        prev_hq = await ApplicationRepository.count_documents({"job_id": {"$in": job_ids}, "ai_score.total_score": {"$gte": 80}, "created_at": {"$lt": thirty_days_ago}})

        cur_hr = await UserRepository.count_documents({
            "company_id": company_id, 
            "role": {"$in": [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]}
        })

        active_pipelines = await JobRepository.get_active_pipelines({"company_id": company_id})

        recent_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$sort": {"applied_at": -1}},
            {"$limit": 5},
            {"$project": {
                "_id": 0,
                "id": {"$toString": "$_id"},
                "candidate_name": {"$ifNull": ["$cv_snapshot.candidate_info.full_name", "$cv_snapshot.filename"]},
                "job_id": 1,
                "status": 1,
                "ai_score": "$ai_score.total_score",
                "applied_at": 1
            }}
        ]
        recent_apps_raw = await ApplicationRepository.aggregate_applications(recent_pipeline)
        recent_apps = []
        for app in recent_apps_raw:
            app["job_title"] = job_dict.get(app["job_id"], "Vị trí tuyển dụng")
            recent_apps.append(app)

        return {
            "scope": "company",
            "overview_stats": {
                "active_jobs": cls._calculate_trend(current_active_jobs, prev_jobs_created),
                "total_cvs": cls._calculate_trend(cur_cvs, prev_cvs),
                "high_quality_cvs": cls._calculate_trend(cur_hq, prev_hq),
                "total_hr": {"value": cur_hr, "trend": 0, "is_up": True} 
            },
            "active_pipelines": active_pipelines,
            "recent_applicants": recent_apps
        }

    @classmethod
    async def get_member_workspace_metrics(cls, user_id: str) -> Dict[str, Any]:
        assigned_jobs = await JobRepository.get_active_pipelines({"created_by_user_id": user_id})
        
        new_cvs_to_review = sum(job.get("new_cvs", 0) for job in assigned_jobs)
        total_cvs_managed = sum(job.get("total_cvs", 0) for job in assigned_jobs)
        job_ids = [job["job_id"] for job in assigned_jobs]
        job_dict = {job["job_id"]: job.get("title", "Chiến dịch") for job in assigned_jobs}
        
        interviews = await ApplicationRepository.get_todays_interviews(job_ids)
        today_schedule = []
        
        time_slots = ["09:30", "11:00", "14:00", "15:30", "16:45"]
        for idx, inv in enumerate(interviews):
            job_title = job_dict.get(inv["job_id"], "Vị trí tuyển dụng")
            today_schedule.append({
                "time": time_slots[idx % len(time_slots)],
                "title": f"Phỏng vấn - {job_title}",
                "subtitle": f"Ứng viên: {inv.get('candidate_name', 'Ẩn danh')}",
                "type": "interview"
            })

        if new_cvs_to_review > 0:
            today_schedule.append({
                "time": "17:00",
                "title": "Review CV mới",
                "subtitle": f"Cần lọc {new_cvs_to_review} hồ sơ mới nộp",
                "type": "task"
            })

        recent_apps = []
        if job_ids:
            recent_pipeline = [
                {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
                {"$sort": {"applied_at": -1}},
                {"$limit": 5},
                {"$project": {
                    "_id": 0,
                    "id": {"$toString": "$_id"},
                    "candidate_name": {"$ifNull": ["$cv_snapshot.candidate_info.full_name", "$cv_snapshot.filename"]},
                    "job_id": 1,
                    "status": 1,
                    "ai_score": "$ai_score.total_score",
                    "applied_at": 1
                }}
            ]
            recent_apps_raw = await ApplicationRepository.aggregate_applications(recent_pipeline)
            for app in recent_apps_raw:
                app["job_title"] = job_dict.get(app["job_id"], "Vị trí tuyển dụng")
                recent_apps.append(app)

        return {
            "scope": "me",
            "todo_stats": {
                "new_cvs_to_review": new_cvs_to_review,
                "total_cvs_managed": total_cvs_managed,
                "interviews_this_week": len(interviews) * 3, 
                "total_assigned_jobs": len(assigned_jobs)
            },
            "assigned_jobs": assigned_jobs,
            "today_schedule": sorted(today_schedule, key=lambda x: x["time"]),
            "recent_applicants": recent_apps
        }
    
    @classmethod
    async def get_company_pro_analytics(cls, company_id: str) -> Dict[str, Any]:
        company = await CompanyRepository.get_by_id(company_id)
        if not company:
            return {"is_pro_active": False, "data": None, "message": "Công ty không tồn tại"}

        is_pro = True 

        if not is_pro:
            return {
                "is_pro_active": False, 
                "data": None, 
                "message": "Vui lòng nâng cấp gói PRO để mở khóa báo cáo phân tích AI."
            }

        jobs = await JobRepository.find_many({"company_id": company_id}, projection={"_id": 1})
        job_ids = [str(j["_id"]) for j in jobs]

        raw_funnel = await ApplicationRepository.get_funnel_stats(job_ids)
        funnel_dict = {item["_id"]: item["count"] for item in raw_funnel}
        total_cv = sum(funnel_dict.values())
        pass_ai = total_cv - funnel_dict.get(ApplicationStatus.NEW.value, 0) - funnel_dict.get(ApplicationStatus.REJECTED.value, 0)
        interview = funnel_dict.get(ApplicationStatus.INTERVIEW.value, 0)
        hired = funnel_dict.get(ApplicationStatus.HIRED.value, 0)

        funnel_chart = [
            { "name": "Tổng CV", "value": total_cv },
            { "name": "Pass AI (>50đ)", "value": pass_ai },
            { "name": "Phỏng vấn", "value": interview },
            { "name": "Đã Tuyển", "value": hired }
        ]

        raw_ai = await ApplicationRepository.get_ai_score_distribution(job_ids)
        score_chart = []
        for bucket in raw_ai:
            bound = bucket["_id"]
            count = bucket["count"]
            if bound == 0: score_chart.append({"name": "Chưa đạt (<50đ)", "value": count, "color": "var(--color-error-500)"})
            elif bound == 50: score_chart.append({"name": "Khá (50-80đ)", "value": count, "color": "var(--color-warning-500)"})
            elif bound == 80: score_chart.append({"name": "Xuất sắc (>80đ)", "value": count, "color": "var(--color-success-500)"})

        existing_names = [x["name"] for x in score_chart]
        if "Chưa đạt (<50đ)" not in existing_names: score_chart.append({"name": "Chưa đạt (<50đ)", "value": 0, "color": "var(--color-error-500)"})
        if "Khá (50-80đ)" not in existing_names: score_chart.append({"name": "Khá (50-80đ)", "value": 0, "color": "var(--color-warning-500)"})
        if "Xuất sắc (>80đ)" not in existing_names: score_chart.append({"name": "Xuất sắc (>80đ)", "value": 0, "color": "var(--color-success-500)"})

        trend_chart = []
        now = datetime.now(timezone.utc)
        for i in range(13, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%d/%m")
            trend_chart.append({"date": date_str, "cv_count": 0})
            
        raw_trend = await ApplicationRepository.aggregate_applications([
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None, "applied_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$applied_at"}}, "count": {"$sum": 1}}}
        ])
        trend_dict = {item["_id"]: item["count"] for item in raw_trend}
        for day in trend_chart:
            day["cv_count"] = trend_dict.get(day["date"], 0)

        return {
            "is_pro_active": True,
            "data": {
                "funnel_chart": funnel_chart,
                "ai_score_distribution": score_chart,
                "applications_trend": trend_chart
            }
        }

    @classmethod
    async def get_admin_dashboard_metrics(cls) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        
        total_users = await UserRepository.count_documents({"deleted_at": None})
        new_users_30d = await UserRepository.count_documents({"deleted_at": None, "created_at": {"$gte": thirty_days_ago}})
        
        total_companies = await CompanyRepository.count_documents({"deleted_at": None})
        verified_companies = await CompanyRepository.count_documents({"deleted_at": None, "status": CompanyStatus.VERIFIED.value})
        pending_companies = await CompanyRepository.count_documents({"deleted_at": None, "status": CompanyStatus.PENDING_VERIFICATION.value})
        
        total_jobs = await JobRepository.count_documents({"deleted_at": None, "status": JobStatus.OPEN.value})

        recent_pending = await CompanyRepository.find_many(
            {"deleted_at": None, "status": CompanyStatus.PENDING_VERIFICATION.value},
            sort=[("created_at", -1)],
            limit=5
        )
        
        recent_list = []
        for comp in recent_pending:
            comp["id"] = str(comp["_id"])
            del comp["_id"]
            recent_list.append(comp)

        return {
            "overview_stats": {
                "total_users": {"value": total_users, "trend": new_users_30d, "is_up": True},
                "total_companies": {"value": total_companies, "trend": verified_companies, "is_up": True},
                "pending_kyc": {"value": pending_companies, "trend": 0, "is_up": False},
                "active_jobs": {"value": total_jobs, "trend": 0, "is_up": True},
            },
            "recent_pending_companies": recent_list
        }

    @classmethod
    async def get_admin_system_analytics(cls) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        
        raw_company_status = await CompanyRepository.aggregate_companies([
            {"$match": {"deleted_at": None}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ])
        
        status_chart = []
        for item in raw_company_status:
            status = item["_id"]
            count = item["count"]
            if status == CompanyStatus.VERIFIED.value:
                status_chart.append({"name": "Đã duyệt", "value": count, "color": "var(--color-success-500)"})
            elif status == CompanyStatus.PENDING_VERIFICATION.value:
                status_chart.append({"name": "Chờ duyệt", "value": count, "color": "var(--color-warning-500)"})
            elif status == CompanyStatus.REJECTED.value:
                status_chart.append({"name": "Từ chối", "value": count, "color": "var(--color-error-500)"})
            elif status == CompanyStatus.SUSPENDED.value:
                status_chart.append({"name": "Tạm khóa", "value": count, "color": "var(--color-slate-500)"})

        growth_chart = []
        for i in range(13, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%d/%m")
            growth_chart.append({"date": date_str, "users": 0, "companies": 0})
            
        raw_users = await UserRepository.aggregate_users([
            {"$match": {"deleted_at": None, "created_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$created_at"}}, "count": {"$sum": 1}}}
        ])
        user_dict = {item["_id"]: item["count"] for item in raw_users}

        raw_companies = await CompanyRepository.aggregate_companies([
            {"$match": {"deleted_at": None, "created_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$created_at"}}, "count": {"$sum": 1}}}
        ])
        comp_dict = {item["_id"]: item["count"] for item in raw_companies}

        for day in growth_chart:
            day["users"] = user_dict.get(day["date"], 0)
            day["companies"] = comp_dict.get(day["date"], 0)

        return {
            "company_status_chart": status_chart,
            "growth_trend_chart": growth_chart
        }
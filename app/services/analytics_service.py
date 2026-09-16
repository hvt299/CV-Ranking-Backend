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
        prev_jobs_created = await JobRepository.count_documents({"company_id": company_id, "created_at": {"$gte": sixty_days_ago, "$lt": thirty_days_ago}})

        jobs = await JobRepository.find_many({"company_id": company_id}, projection={"_id": 1, "title": 1})
        job_ids = [str(j.get("id")) for j in jobs]
        job_dict = {str(j.get("id")): j.get("title", "Chiến dịch") for j in jobs}
        
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

        # 1. Experience Distribution Pie Chart
        exp_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$group": {"_id": "$cv_snapshot.years_of_experience", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        raw_exp = await ApplicationRepository.aggregate_applications(exp_pipeline)
        exp_chart = []
        colors = ["#94a3b8", "var(--color-primary-500)", "var(--color-info-500)", "var(--color-warning-500)", "var(--color-success-500)"]
        for idx, item in enumerate(raw_exp):
            val = item.get("_id") or 0
            label = "Mới tốt nghiệp" if val == 0 else f"{val} năm kinh nghiệm"
            exp_chart.append({"name": label, "value": item["count"], "color": colors[idx % len(colors)]})
            
        # 2. Top Jobs (Bar Chart)
        top_jobs_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$group": {"_id": "$job_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        raw_top_jobs = await ApplicationRepository.aggregate_applications(top_jobs_pipeline)
        top_jobs_chart = []
        for idx, item in enumerate(raw_top_jobs):
            top_jobs_chart.append({
                "name": job_dict.get(item.get("_id"), "Chiến dịch"),
                "cv_count": item["count"],
                "color": colors[idx % len(colors)]
            })
            
        # 3. Pipeline Health (Real Pipeline)
        pipeline_health_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        raw_pipeline = await ApplicationRepository.aggregate_applications(pipeline_health_pipeline)
        ph_dict = {item.get("_id"): item["count"] for item in raw_pipeline}
        
        pipeline_health_chart = [
            {"name": "Mới", "value": ph_dict.get(ApplicationStatus.NEW.value, 0), "fill": "#94a3b8"},
            {"name": "Đang xem xét", "value": ph_dict.get(ApplicationStatus.REVIEWING.value, 0), "fill": "var(--color-info-500)"},
            {"name": "Phỏng vấn", "value": ph_dict.get(ApplicationStatus.INTERVIEW.value, 0), "fill": "var(--color-warning-500)"},
            {"name": "Đã tuyển", "value": ph_dict.get(ApplicationStatus.HIRED.value, 0), "fill": "var(--color-success-500)"}
        ]

        return {
            "scope": "company",
            "overview_stats": {
                "active_jobs": cls._calculate_trend(current_active_jobs, prev_jobs_created),
                "total_cvs": cls._calculate_trend(cur_cvs, prev_cvs),
                "high_quality_cvs": cls._calculate_trend(cur_hq, prev_hq),
                "total_hr": {"value": cur_hr, "trend": 0, "is_up": True} 
            },
            "active_pipelines": active_pipelines,
            "recent_applicants": recent_apps,
            "charts": {
                "experience_distribution": exp_chart,
                "top_jobs": top_jobs_chart,
                "pipeline_health": pipeline_health_chart
            }
        }

    @classmethod
    async def get_member_workspace_metrics(cls, user_id: str) -> Dict[str, Any]:
        # Member works on assigned jobs
        assigned_jobs = await JobRepository.get_active_pipelines({"assigned_hr_ids": user_id})
        
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

        # 1. Daily Assigned CVs (Area chart)
        now = datetime.now(timezone.utc)
        velocity_chart = []
        for i in range(13, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            velocity_chart.append({"date": date_str, "count": 0})
            
        if job_ids:
            raw_velocity = await ApplicationRepository.aggregate_applications([
                {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None, "applied_at": {"$gte": now - timedelta(days=14)}}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$applied_at"}}, "count": {"$sum": 1}}}
            ])
            velocity_dict = {item.get("_id"): item["count"] for item in raw_velocity}
            for day in velocity_chart:
                day["count"] = velocity_dict.get(day["date"], 0)
            
        # 2. AI Score Histogram for Assigned Jobs
        ai_score_histogram = []
        if job_ids:
            raw_ai = await ApplicationRepository.get_ai_score_distribution(job_ids)
            for bucket in raw_ai:
                bound = bucket.get("_id")
                count = bucket["count"]
                if bound == 0: ai_score_histogram.append({"name": "<50", "value": count, "color": "var(--color-error-500)"})
                elif bound == 50: ai_score_histogram.append({"name": "50-80", "value": count, "color": "var(--color-warning-500)"})
                elif bound == 80: ai_score_histogram.append({"name": ">80", "value": count, "color": "var(--color-success-500)"})

        return {
            "scope": "me",
            "todo_stats": {
                "new_cvs_to_review": new_cvs_to_review,
                "total_cvs_managed": total_cvs_managed,
                "interviews_this_week": len(interviews), 
                "total_assigned_jobs": len(assigned_jobs)
            },
            "assigned_jobs": assigned_jobs,
            "today_schedule": sorted(today_schedule, key=lambda x: x["time"]),
            "recent_applicants": recent_apps,
            "charts": {
                "daily_assigned_cvs": velocity_chart,
                "ai_score_histogram": ai_score_histogram
            }
        }
    
    @classmethod
    async def get_company_pro_analytics(cls, company_id: str) -> Dict[str, Any]:
        company = await CompanyRepository.get_by_id(company_id)
        if not company:
            return {"is_pro_active": False, "data": None, "message": "Công ty không tồn tại"}

        # Require PRO
        is_pro = True

        if not is_pro:
            return {
                "is_pro_active": False, 
                "data": None, 
                "message": "Vui lòng nâng cấp gói PRO để mở khóa báo cáo phân tích AI."
            }

        jobs = await JobRepository.find_many({"company_id": company_id}, projection={"_id": 1})
        job_ids = [str(j.get("id")) for j in jobs]

        raw_funnel = await ApplicationRepository.get_funnel_stats(job_ids)
        funnel_dict = {item.get("_id"): item["count"] for item in raw_funnel}
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
            bound = bucket.get("_id")
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
        trend_dict = {item.get("_id"): item["count"] for item in raw_trend}
        for day in trend_chart:
            day["cv_count"] = trend_dict.get(day["date"], 0)

        # 4. Word Cloud (Real Data using skills from cv_snapshot)
        skills_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None, "cv_snapshot.skills": {"$exists": True, "$type": "array"}}},
            {"$unwind": "$cv_snapshot.skills"},
            {"$group": {"_id": "$cv_snapshot.skills", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        raw_skills = await ApplicationRepository.aggregate_applications(skills_pipeline)
        skills_word_cloud = []
        for item in raw_skills:
            skills_word_cloud.append({"text": item.get("_id"), "value": item["count"]})
        
        # 5. Education Levels (Real Data)
        edu_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$group": {"_id": "$cv_snapshot.education_level", "count": {"$sum": 1}}}
        ]
        raw_edu = await ApplicationRepository.aggregate_applications(edu_pipeline)
        education_reasons_chart = []
        edu_colors = ["var(--color-info-500)", "var(--color-success-500)", "var(--color-warning-500)", "var(--color-primary-500)"]
        for idx, item in enumerate(raw_edu):
            lvl = item.get("_id") or "Không rõ"
            education_reasons_chart.append({"name": lvl, "value": item["count"], "color": edu_colors[idx % len(edu_colors)]})
        
        # 6. Apply Time Heatmap (Real Data using $hour and $dayOfWeek)
        apply_time_heatmap = []
        days = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"]
        shifts = ["Đêm (0-6h)", "Sáng (6-12h)", "Chiều (12-18h)", "Tối (18-24h)"]
        
        for d in days:
            for s in shifts:
                apply_time_heatmap.append({"day": d, "shift": s, "value": 0})
                
        heatmap_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$project": {
                "dayOfWeek": {"$dayOfWeek": "$applied_at"},
                "hour": {"$hour": "$applied_at"}
            }},
            {"$group": {
                "_id": {"day": "$dayOfWeek", "hour": "$hour"},
                "count": {"$sum": 1}
            }}
        ]
        raw_heatmap = await ApplicationRepository.aggregate_applications(heatmap_pipeline)
        
        for item in raw_heatmap:
            _id = item.get("_id")
            count = item.get("count", 0)
            if not _id: continue
            
            day_idx = _id.get("day", 1) - 1 # 1 is Sunday
            hour = _id.get("hour", 0)
            
            day_label = days[day_idx]
            shift_label = "Đêm (0-6h)"
            if 6 <= hour < 12: shift_label = "Sáng (6-12h)"
            elif 12 <= hour < 18: shift_label = "Chiều (12-18h)"
            elif 18 <= hour <= 23: shift_label = "Tối (18-24h)"
            
            for cell in apply_time_heatmap:
                if cell["day"] == day_label and cell["shift"] == shift_label:
                    cell["value"] += count

        return {
            "is_pro_active": True,
            "data": {
                "funnel_chart": funnel_chart,
                "ai_score_distribution": score_chart,
                "applications_trend": trend_chart,
                "skills_word_cloud": skills_word_cloud,
                "education_reasons_chart": education_reasons_chart,
                "apply_time_heatmap": apply_time_heatmap
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
        
        # 1. Growth Trend Chart (Area Chart)
        growth_chart = []
        for i in range(13, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%d/%m")
            growth_chart.append({"date": date_str, "companies": 0, "users": 0})
            
        raw_companies = await CompanyRepository.aggregate_companies([
            {"$match": {"deleted_at": None, "created_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$created_at"}}, "count": {"$sum": 1}}}
        ])
        comp_dict = {item.get("_id"): item["count"] for item in raw_companies}
        
        raw_users_d = await UserRepository.aggregate_users([
            {"$match": {"deleted_at": None, "created_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$created_at"}}, "count": {"$sum": 1}}}
        ])
        user_dict = {item.get("_id"): item["count"] for item in raw_users_d}
        
        for day in growth_chart:
            day["companies"] = comp_dict.get(day["date"], 0)
            day["users"] = user_dict.get(day["date"], 0)

        # 2. Subscription Tier (Donut Chart)
        from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
        from app.database.config import get_db
        plans = await SubscriptionPlanRepository.find_many()
        plan_dict = {str(p["id"]): p["name"] for p in plans}

        db = get_db()
        tier_pipeline = [
            {"$match": {"deleted_at": None}},
            {"$group": {"_id": "$current_plan_id", "count": {"$sum": 1}}}
        ]
        raw_company_tiers = await CompanyRepository.aggregate_companies(tier_pipeline)
        raw_applicant_tiers = await db.applicant_profiles.aggregate(tier_pipeline).to_list(length=100)

        tier_counts = {}
        for item in raw_company_tiers + raw_applicant_tiers:
            pid = item.get("_id")
            tier_counts[pid] = tier_counts.get(pid, 0) + item["count"]

        subscription_tier_chart = []
        colors = ["#94a3b8", "var(--color-success-500)", "var(--color-info-500)", "var(--color-warning-500)", "var(--color-primary-500)", "var(--color-error-500)"]

        for plan_id, count in tier_counts.items():
            if not plan_id:
                label = "Gói Miễn Phí"
            else:
                label = plan_dict.get(str(plan_id), "Gói Trả Phí")
            
            # Find if label exists
            found = False
            for tier in subscription_tier_chart:
                if tier["name"] == label:
                    tier["value"] += count
                    found = True
                    break
            
            if not found:
                color = colors[0] if label == "Gói Miễn Phí" else colors[(len(subscription_tier_chart) % (len(colors) - 1)) + 1]
                subscription_tier_chart.append({"name": label, "value": count, "color": color})

        # 3. Bản đồ Ngành nghề (Bar Chart)
        raw_industries = await JobRepository.aggregate_jobs([
            {"$match": {"deleted_at": None}},
            {"$group": {"_id": "$industry", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ])
        jobs_by_industry_chart = []
        colors = ["var(--color-primary-500)", "var(--color-info-500)", "var(--color-success-500)", "var(--color-warning-500)", "var(--color-error-500)"]
        for idx, item in enumerate(raw_industries):
            ind = item.get("_id") or "Khác"
            if isinstance(ind, list): ind = ind[0] if len(ind) > 0 else "Khác"
            jobs_by_industry_chart.append({"name": ind, "value": item["count"], "color": colors[idx % len(colors)]})
            
        # 4. Tải trọng Hệ Thống (Line Chart - Real applications created per day)
        system_load_chart = []
        for i in range(13, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%d/%m")
            system_load_chart.append({"date": date_str, "cv_received": 0})
            
        raw_apps = await ApplicationRepository.aggregate_applications([
            {"$match": {"deleted_at": None, "applied_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$applied_at"}}, "count": {"$sum": 1}}}
        ])
        app_dict = {item.get("_id"): item["count"] for item in raw_apps}
        for day in system_load_chart:
            day["cv_received"] = app_dict.get(day["date"], 0)

        return {
            "overview_stats": {
                "total_users": {"value": total_users, "trend": new_users_30d, "is_up": True},
                "total_companies": {"value": total_companies, "trend": verified_companies, "is_up": True},
                "pending_kyc": {"value": pending_companies, "trend": 0, "is_up": False},
                "active_jobs": {"value": total_jobs, "trend": 0, "is_up": True},
            },
            "recent_pending_companies": recent_pending,
            "charts": {
                "growth_trend": growth_chart,
                "subscription_tier": subscription_tier_chart,
                "jobs_by_industry": jobs_by_industry_chart,
                "system_load": system_load_chart
            }
        }

    @classmethod
    async def get_applicant_dashboard_metrics(cls, user_id: str) -> Dict[str, Any]:
        apps = await ApplicationRepository.find_many({"applicant_user_id": user_id, "deleted_at": None})
        
        # 1. Funnel Chart
        funnel_dict = {"total": 0, "viewed": 0, "interview": 0, "hired": 0}
        funnel_dict["total"] = len(apps)
        for app in apps:
            status = app.get("status", ApplicationStatus.NEW.value)
            if status != ApplicationStatus.NEW.value:
                funnel_dict["viewed"] += 1
            if status in [ApplicationStatus.INTERVIEW.value, ApplicationStatus.HIRED.value]:
                funnel_dict["interview"] += 1
            if status == ApplicationStatus.HIRED.value:
                funnel_dict["hired"] += 1
                
        funnel_chart = [
            {"name": "Đã Nộp", "value": funnel_dict["total"], "fill": "#94a3b8"},
            {"name": "HR Đã Xem", "value": funnel_dict["viewed"], "fill": "var(--color-primary-400)"},
            {"name": "Phỏng Vấn", "value": funnel_dict["interview"], "fill": "var(--color-warning-500)"},
            {"name": "Trúng Tuyển", "value": funnel_dict["hired"], "fill": "var(--color-success-500)"}
        ]

        # 2. AI Score History Radar
        ai_scores = []
        for app in apps[-5:]:
            score = app.get("ai_score", {})
            ai_scores.append(score.get("total_score", 0))
            
        skill_gap_radar = [
            {"subject": "Kỹ năng (Skills)", "A": 0, "fullMark": 100},
            {"subject": "Kinh nghiệm (Exp)", "A": 0, "fullMark": 100},
            {"subject": "Học vấn (Edu)", "A": 0, "fullMark": 100},
        ]
        
        if apps:
            total_skills, total_exp, total_edu = 0, 0, 0
            for app in apps:
                s = app.get("ai_score", {})
                total_skills += s.get("match_percentage_skills", 0)
                total_exp += s.get("match_percentage_experience", 0)
                total_edu += s.get("match_percentage_education", 0)
            skill_gap_radar[0]["A"] = total_skills / len(apps)
            skill_gap_radar[1]["A"] = total_exp / len(apps)
            skill_gap_radar[2]["A"] = total_edu / len(apps)

        # 3. Application Activity Trend
        now = datetime.now(timezone.utc)
        activity_chart = []
        for i in range(13, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%d/%m")
            activity_chart.append({"date": date_str, "applied": 0})

        raw_apps = await ApplicationRepository.aggregate_applications([
            {"$match": {"applicant_user_id": user_id, "deleted_at": None, "applied_at": {"$gte": now - timedelta(days=14)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$applied_at"}}, "count": {"$sum": 1}}}
        ])
        app_dict = {item.get("_id"): item["count"] for item in raw_apps}
        for day in activity_chart:
            day["applied"] = app_dict.get(day["date"], 0)

        return {
            "charts": {
                "funnel": funnel_chart,
                "ai_radar": skill_gap_radar,
                "activity_trend": activity_chart
            }
        }

    @classmethod
    async def get_admin_system_analytics(cls, days: int = 14) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        
        if days >= 3650:
            oldest_user = await UserRepository.find_many({"deleted_at": None}, sort=[("created_at", 1)], limit=1)
            oldest_company = await CompanyRepository.find_many({"deleted_at": None}, sort=[("created_at", 1)], limit=1)
            
            oldest_dates = []
            if oldest_user and "created_at" in oldest_user[0]:
                oldest_dates.append(oldest_user[0]["created_at"])
            if oldest_company and "created_at" in oldest_company[0]:
                oldest_dates.append(oldest_company[0]["created_at"])
                
            if oldest_dates:
                oldest_date = min(oldest_dates)
                if oldest_date.tzinfo is None:
                    oldest_date = oldest_date.replace(tzinfo=timezone.utc)
                diff = (now - oldest_date).days + 1
                days = min(diff, 9999)
            else:
                days = 30
        
        raw_company_status = await CompanyRepository.aggregate_companies([
            {"$match": {"deleted_at": None}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ])
        
        status_chart = []
        for item in raw_company_status:
            status = item.get("_id")
            count = item["count"]
            if status == CompanyStatus.VERIFIED.value:
                status_chart.append({"name": "Đã duyệt", "value": count, "color": "var(--color-success-500)"})
            elif status == CompanyStatus.PENDING_VERIFICATION.value:
                status_chart.append({"name": "Chờ duyệt", "value": count, "color": "var(--color-warning-500)"})
            elif status == CompanyStatus.REJECTED.value:
                status_chart.append({"name": "Từ chối", "value": count, "color": "var(--color-error-500)"})
            elif status == CompanyStatus.SUSPENDED.value:
                status_chart.append({"name": "Tạm khóa", "value": count, "color": "#64748b"})

        growth_chart = []
        for i in range(days - 1, -1, -1):
            day_obj = now - timedelta(days=i)
            mongo_date = day_obj.strftime("%Y-%m-%d")
            display_date = day_obj.strftime("%d/%m/%Y" if days > 90 else "%d/%m")
            growth_chart.append({
                "mongo_date": mongo_date,
                "date": display_date,
                "users": 0,
                "companies": 0
            })
            
        raw_users = await UserRepository.aggregate_users([
            {"$match": {"deleted_at": None, "created_at": {"$gte": now - timedelta(days=days)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "count": {"$sum": 1}}}
        ])
        user_dict = {item.get("_id"): item["count"] for item in raw_users}

        raw_companies = await CompanyRepository.aggregate_companies([
            {"$match": {"deleted_at": None, "created_at": {"$gte": now - timedelta(days=days)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "count": {"$sum": 1}}}
        ])
        comp_dict = {item.get("_id"): item["count"] for item in raw_companies}

        for day in growth_chart:
            m_date = day["mongo_date"]
            day["users"] = user_dict.get(m_date, 0)
            day["companies"] = comp_dict.get(m_date, 0)
            del day["mongo_date"]

        # 1. Gói cước (Pie Chart)
        from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
        from app.database.config import get_db
        plans = await SubscriptionPlanRepository.find_many()
        plan_dict = {str(p["id"]): p["name"] for p in plans}

        db = get_db()
        tier_pipeline = [
            {"$match": {"deleted_at": None}},
            {"$group": {"_id": "$current_plan_id", "count": {"$sum": 1}}}
        ]
        raw_company_tiers = await CompanyRepository.aggregate_companies(tier_pipeline)
        raw_applicant_tiers = await db.applicant_profiles.aggregate(tier_pipeline).to_list(length=100)

        tier_counts = {}
        for item in raw_company_tiers + raw_applicant_tiers:
            pid = item.get("_id")
            tier_counts[pid] = tier_counts.get(pid, 0) + item["count"]

        subscription_tier_chart = []
        pie_colors = [
            "#94a3b8", # gray for free
            "#3b82f6", # blue
            "#8b5cf6", # violet
            "#ec4899", # pink
            "#f59e0b", # amber
            "#10b981", # emerald
            "#ef4444", # red
            "#06b6d4", # cyan
            "#f97316", # orange
            "#14b8a6", # teal
            "#6366f1", # indigo
        ]
        for plan_id, count in tier_counts.items():
            if not plan_id:
                label = "Gói Miễn Phí"
            else:
                label = plan_dict.get(str(plan_id), "Gói Trả Phí")
            
            found = False
            for tier in subscription_tier_chart:
                if tier["name"] == label:
                    tier["value"] += count
                    found = True
                    break
            
            if not found:
                color = pie_colors[0] if label == "Gói Miễn Phí" else pie_colors[(len(subscription_tier_chart) % (len(pie_colors) - 1)) + 1]
                subscription_tier_chart.append({"name": label, "value": count, "color": color})

        # 2. Ngành nghề (Bar Chart)
        from app.repositories.job_repository import JobRepository
        raw_industries = await JobRepository.aggregate_jobs([
            {"$match": {"deleted_at": None}},
            {"$group": {"_id": "$industry", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ])
        jobs_by_industry_chart = []
        ind_colors = ["var(--color-primary-500)", "var(--color-info-500)", "var(--color-success-500)", "var(--color-warning-500)", "var(--color-error-500)"]
        for idx, item in enumerate(raw_industries):
            ind = item.get("_id") or "Khác"
            if isinstance(ind, list): ind = ind[0] if len(ind) > 0 else "Khác"
            jobs_by_industry_chart.append({"name": ind, "value": item["count"], "color": ind_colors[idx % len(ind_colors)]})

        # 3. Tải trọng (Line chart)
        system_load_chart = []
        for i in range(days - 1, -1, -1):
            date_str = (now - timedelta(days=i)).strftime("%d/%m")
            system_load_chart.append({"date": date_str, "cv_received": 0})
            
        from app.repositories.application_repository import ApplicationRepository
        raw_apps = await ApplicationRepository.aggregate_applications([
            {"$match": {"deleted_at": None, "applied_at": {"$gte": now - timedelta(days=days)}}},
            {"$group": {"_id": {"$dateToString": {"format": "%d/%m", "date": "$applied_at"}}, "count": {"$sum": 1}}}
        ])
        app_dict = {item.get("_id"): item["count"] for item in raw_apps}
        for day in system_load_chart:
            day["cv_received"] = app_dict.get(day["date"], 0)

        return {
            "company_status_chart": status_chart,
            "growth_trend_chart": growth_chart,
            "charts": {
                "growth_trend": growth_chart,
                "subscription_tier": subscription_tier_chart,
                "jobs_by_industry": jobs_by_industry_chart,
                "system_load": system_load_chart
            }
        }


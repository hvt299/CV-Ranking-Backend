import os
import httpx
import logging
from fastapi import BackgroundTasks
from typing import Optional

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# =====================================================================
# HTML BASE TEMPLATE (Tránh lặp lại cấu trúc UI)
# =====================================================================
def get_base_html(inner_content: str) -> str:
    return f"""
      <div style="background-color: #f4f7f6; padding: 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
          <div style="background-color: #2563eb; padding: 30px 20px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 26px; letter-spacing: 1px;">🚀 AI CV RANKING</h1>
          </div>
          <div style="padding: 40px 30px; color: #333333; line-height: 1.6;">
            {inner_content}
          </div>
        </div>
      </div>
    """

# =====================================================================
# I18N MESSAGES (Cơ sở dữ liệu đa ngôn ngữ / Message Keys)
# =====================================================================
I18N_MESSAGES = {
    "vi": {
        "verify": {
            "subject": "Kích hoạt tài khoản Hệ thống ATS",
            "content": """
                <p style="font-size: 16px;">Xin chào <strong>{name}</strong>,</p>
                <p>Chào mừng bạn đến với Hệ thống Quản lý Tuyển dụng AI. Vui lòng bấm vào nút bên dưới để xác thực địa chỉ email và kích hoạt tài khoản của bạn:</p>
                <div style="text-align: center; margin: 35px 0;">
                  <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">KÍCH HOẠT TÀI KHOẢN</a>
                </div>
                <p style="font-size: 14px; color: #666;"><em>*Link xác thực này sẽ hết hạn sau 24 giờ.</em></p>
            """
        },
        "reset_password": {
            "subject": "Yêu cầu đặt lại mật khẩu",
            "content": """
                <h2 style="color: #2563eb; text-align: center; margin-top: 0;">Yêu cầu đặt lại mật khẩu 🔑</h2>
                <p style="font-size: 16px;">Xin chào <strong>{name}</strong>,</p> 
                <p>Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. Vui lòng bấm vào nút bên dưới để tiến hành tạo mật khẩu mới:</p>
                <div style="text-align: center; margin: 35px 0;">
                  <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">ĐẶT LẠI MẬT KHẨU</a>
                </div>
                <p style="font-size: 14px; color: #666;"><em>*Link khôi phục này sẽ hết hạn sau 15 phút.</em></p>
            """
        },
        "notification": {
            "subject": "Cập nhật hồ sơ ứng tuyển: {job_title}",
            "content": """
                <p style="font-size: 16px;">Xin chào <strong>{name}</strong>,</p>
                <p>Hồ sơ ứng tuyển của bạn cho vị trí <strong>{job_title}</strong> vừa được cập nhật trạng thái mới.</p>
                <div style="background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af;">Trạng thái mới: {status_label}</h3>
                    <p style="margin-bottom: 0;">{message}</p>
                </div>
                <div style="text-align: center; margin: 30px 0;">
                  <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 15px; display: inline-block;">XEM CHI TIẾT</a>
                </div>
            """
        },
        "invite_hr": {
            "subject": "Thư mời tham gia quản lý tuyển dụng tại {company_name}",
            "content": """
                <p style="font-size: 16px;">Xin chào,</p>
                <p>Bạn vừa nhận được lời mời từ <strong>{inviter_name}</strong> để tham gia quản trị hệ thống tuyển dụng của công ty <strong>{company_name}</strong> trên nền tảng ATS.</p>
                <p>Vui lòng bấm vào nút bên dưới để tạo tài khoản và tham gia không gian làm việc:</p>
                <div style="text-align: center; margin: 35px 0;">
                  <a href="{link}" style="background-color: #10b981; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">CHẤP NHẬN LỜI MỜI</a>
                </div>
                <p style="font-size: 14px; color: #666;"><em>*Lưu ý: Link mời này có thời hạn sử dụng trong 7 ngày. Không chia sẻ link này cho người khác.</em></p>
            """
        },
        "interview_invite": {
            "subject": "Thư mời phỏng vấn - Vị trí {job_title} tại {company_name}",
            "content": """
                <p style="font-size: 16px;">Xin chào <strong>{name}</strong>,</p>
                <p>Cảm ơn bạn đã quan tâm và ứng tuyển vào vị trí <strong>{job_title}</strong> tại <strong>{company_name}</strong>. Hồ sơ của bạn rất phù hợp và chúng tôi muốn mời bạn tham gia một buổi phỏng vấn để trao đổi chi tiết hơn.</p>
                
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 25px 0;">
                    <h3 style="margin-top: 0; color: #1e40af; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;">THÔNG TIN LỊCH HẸN</h3>
                    <ul style="list-style: none; padding: 0; margin: 0; font-size: 15px; color: #334155;">
                        <li style="margin-bottom: 10px;">🕒 <strong>Thời gian:</strong> {interview_time}</li>
                        <li style="margin-bottom: 10px;">📍 <strong>Địa điểm/Hình thức:</strong> {location}</li>
                        {meeting_link_html}
                    </ul>
                </div>
                
                {message_html}
                
                <p>Vui lòng phản hồi lại email này để xác nhận khả năng tham dự của bạn.</p>
                <p>Trân trọng,<br/><strong>Bộ phận Tuyển dụng - {company_name}</strong></p>
            """
        }
    },
    "en": {
        "verify": {
            "subject": "Activate your ATS Account",
            "content": """
                <p style="font-size: 16px;">Hello <strong>{name}</strong>,</p>
                <p>Welcome to our AI Recruitment System. Please click the button below to verify your email and activate your account:</p>
                <div style="text-align: center; margin: 35px 0;">
                  <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">ACTIVATE ACCOUNT</a>
                </div>
                <p style="font-size: 14px; color: #666;"><em>*This link expires in 24 hours.</em></p>
            """
        },
        "reset_password": {
            "subject": "Password Reset Request",
            "content": """
                <h2 style="color: #2563eb; text-align: center; margin-top: 0;">Password Reset Request 🔑</h2>
                <p style="font-size: 16px;">Hello <strong>{name}</strong>,</p> 
                <p>We received a request to reset your password. Click the button below to create a new password:</p>
                <div style="text-align: center; margin: 35px 0;">
                  <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">RESET PASSWORD</a>
                </div>
                <p style="font-size: 14px; color: #666;"><em>*This link expires in 15 minutes.</em></p>
            """
        },
        "notification": {
            "subject": "Application Update: {job_title}",
            "content": """
                <p style="font-size: 16px;">Hello <strong>{name}</strong>,</p>
                <p>Your application for the <strong>{job_title}</strong> position has a new status update.</p>
                <div style="background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af;">New Status: {status_label}</h3>
                    <p style="margin-bottom: 0;">{message}</p>
                </div>
                <div style="text-align: center; margin: 30px 0;">
                  <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 15px; display: inline-block;">VIEW DETAILS</a>
                </div>
            """
        },
        "invite_hr": {
            "subject": "Invitation to join recruitment team at {company_name}",
            "content": """
                <p style="font-size: 16px;">Hello,</p>
                <p>You have been invited by <strong>{inviter_name}</strong> to join the recruitment team for <strong>{company_name}</strong> on our ATS platform.</p>
                <p>Please click the button below to create your account and join the workspace:</p>
                <div style="text-align: center; margin: 35px 0;">
                  <a href="{link}" style="background-color: #10b981; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">ACCEPT INVITATION</a>
                </div>
                <p style="font-size: 14px; color: #666;"><em>*Note: This link expires in 7 days. Do not share this link with others.</em></p>
            """
        }
    }
}

# =====================================================================
# CORE SENDER FUNCTION
# =====================================================================
async def send_email_via_brevo(to_email: str, subject: str, html_content: str):
    if not BREVO_API_KEY or not SENDER_EMAIL:
        logger.warning(f"Cấu hình Email (BREVO_API_KEY hoặc SENDER_EMAIL) bị thiếu. Bỏ qua gửi email cho {to_email}")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "AI CV Ranking", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"📧 Email sent successfully to {to_email}")
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {e}")

# =====================================================================
# EMAIL TRIGGERS
# =====================================================================
def send_verification_email(background_tasks: BackgroundTasks, to: str, name: str, token: str, lang: str = "vi"):
    base_url = FRONTEND_URL.rstrip('/')
    link = f"{base_url}/verify?token={token}"
    
    template = I18N_MESSAGES.get(lang, I18N_MESSAGES["vi"])["verify"]
    
    inner_html = template["content"].format(name=name, link=link)
    html_content = get_base_html(inner_html)
    
    background_tasks.add_task(send_email_via_brevo, to, template["subject"], html_content)

def send_reset_password_email(background_tasks: BackgroundTasks, to: str, name: str, token: str, lang: str = "vi"):
    base_url = FRONTEND_URL.rstrip('/')
    link = f"{base_url}/reset-password?token={token}"
    
    template = I18N_MESSAGES.get(lang, I18N_MESSAGES["vi"])["reset_password"]
    
    inner_html = template["content"].format(name=name, link=link)
    html_content = get_base_html(inner_html)
    
    background_tasks.add_task(send_email_via_brevo, to, template["subject"], html_content)

def send_notification_email(
    background_tasks: BackgroundTasks, 
    to: str, 
    name: str, 
    job_title: str, 
    status_label: str, 
    message: str, 
    application_id: str,
    lang: str = "vi"
):
    base_url = FRONTEND_URL.rstrip('/')
    link = f"{base_url}/applicant/applications/{application_id}"
    
    template = I18N_MESSAGES.get(lang, I18N_MESSAGES["vi"])["notification"]
    subject = template["subject"].format(job_title=job_title)
    
    inner_html = template["content"].format(
        name=name, 
        job_title=job_title, 
        status_label=status_label, 
        message=message, 
        link=link
    )
    
    html_content = get_base_html(inner_html)
    
    background_tasks.add_task(send_email_via_brevo, to, subject, html_content)

def send_hr_invite_email(
    background_tasks: BackgroundTasks, 
    to: str, 
    inviter_name: str, 
    company_name: str, 
    token: str, 
    lang: str = "vi"
):
    base_url = FRONTEND_URL.rstrip('/')
    link = f"{base_url}/register?invite_token={token}"
    
    template = I18N_MESSAGES.get(lang, I18N_MESSAGES["vi"])["invite_hr"]
    subject = template["subject"].format(company_name=company_name)
    
    inner_html = template["content"].format(
        inviter_name=inviter_name, 
        company_name=company_name, 
        link=link
    )
    
    html_content = get_base_html(inner_html)
    
    background_tasks.add_task(send_email_via_brevo, to, subject, html_content)

def send_interview_email(
    background_tasks: BackgroundTasks, 
    to: str, 
    name: str, 
    job_title: str,
    company_name: str,
    interview_time: str,
    location: str,
    meeting_link: Optional[str] = None,
    custom_message: Optional[str] = None,
    lang: str = "vi"
):
    template = I18N_MESSAGES.get(lang, I18N_MESSAGES["vi"])["interview_invite"]
    subject = template["subject"].format(job_title=job_title, company_name=company_name)
    
    meeting_link_html = f'<li style="margin-bottom: 10px;">🔗 <strong>Link tham gia:</strong> <a href="{meeting_link}" style="color: #2563eb;">{meeting_link}</a></li>' if meeting_link else ""
    message_html = f'<div style="background-color: #fffbeb; padding: 15px; border-left: 4px solid #f59e0b; margin-bottom: 20px;"><strong>Ghi chú từ Nhân sự:</strong><br/>{custom_message}</div>' if custom_message else ""
    
    inner_html = template["content"].format(
        name=name, 
        job_title=job_title, 
        company_name=company_name,
        interview_time=interview_time,
        location=location,
        meeting_link_html=meeting_link_html,
        message_html=message_html
    )
    
    html_content = get_base_html(inner_html)
    background_tasks.add_task(send_email_via_brevo, to, subject, html_content)
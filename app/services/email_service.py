import os
import httpx
import logging
from fastapi import BackgroundTasks
from typing import Optional

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

COLOR_PRIMARY_600 = "#2563eb"
COLOR_PRIMARY_700 = "#1d4ed8"
COLOR_PRIMARY_800 = "#1e40af"
COLOR_SUCCESS_500 = "#10b981"
COLOR_SUCCESS_700 = "#047857"
COLOR_WARNING_500 = "#f59e0b"
COLOR_WARNING_50 = "#fffbeb"
COLOR_TEXT = "#0f172a"
COLOR_TEXT_MUTED = "#64748b"
COLOR_TEXT_SUBTLE = "#94a3b8"
COLOR_BORDER = "#e2e8f0"
COLOR_BACKGROUND = "#f8fafc"
COLOR_SURFACE = "#ffffff"
FONT_STACK = "'Be Vietnam Pro', 'Segoe UI', Helvetica, Arial, sans-serif"

LUCIDE_ICONS = {
    "hexagon": {
        "svg": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>',
        "fallback": "⬡",
    },
    "clock": {
        "svg": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
        "fallback": "🕒",
    },
    "map_pin": {
        "svg": '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
        "fallback": "📍",
    },
    "link": {
        "svg": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
        "fallback": "🔗",
    },
    "key_round": {
        "svg": '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/>',
        "fallback": "🔑",
    },
}

def lucide_icon(name: str, size: int = 16, color: str = COLOR_TEXT_MUTED) -> str:
    data = LUCIDE_ICONS[name]
    svg = (
        f'<!--[if !mso]><!-->'
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'style="color: {color}; vertical-align: middle; display: inline-block;">{data["svg"]}</svg>'
        f'<!--<![endif]-->'
    )
    fallback = (
        f'<!--[if mso]>'
        f'<span style="font-family: Arial, sans-serif; font-size: {size}px; line-height: 1; '
        f'color: {color}; vertical-align: middle;">{data["fallback"]}</span>'
        f'<![endif]-->'
    )
    return fallback + svg

def get_base_html(inner_content: str) -> str:
    return f"""
      <div style="background-color: {COLOR_BACKGROUND}; padding: 32px 16px; font-family: {FONT_STACK};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; width: 100%;">
          <tr>
            <td style="background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; border-radius: 20px; overflow: hidden;">

              <!-- ===================== HEADER (đồng bộ PublicHeader.tsx) ===================== -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background: linear-gradient(135deg, {COLOR_PRIMARY_600} 0%, {COLOR_PRIMARY_800} 100%); padding: 32px 30px; text-align: center;">
                    <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 0 auto;">
                      <tr>
                        <td style="vertical-align: middle; padding-right: 10px;">
                          <table role="presentation" width="40" height="40" cellpadding="0" cellspacing="0" style="background-color: rgba(255,255,255,0.15); border-radius: 10px; border: 1px solid rgba(255,255,255,0.3);">
                            <tr>
                              <td align="center" valign="middle" style="width: 40px; height: 40px;">{lucide_icon("hexagon", size=20, color="#ffffff")}</td>
                            </tr>
                          </table>
                        </td>
                        <td style="vertical-align: middle;">
                          <span style="font-size: 22px; font-weight: 900; letter-spacing: -0.02em; color: #ffffff;">ATS<span style="color: #bfdbfe;">SYSTEM</span></span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- ===================== NỘI DUNG CHÍNH ===================== -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding: 40px 32px; color: {COLOR_TEXT}; line-height: 1.65; font-size: 15px;">
                    {inner_content}
                  </td>
                </tr>
              </table>

              <!-- ===================== FOOTER (đồng bộ PublicFooter.tsx) ===================== -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding: 24px 32px 32px; border-top: 1px solid {COLOR_BORDER};">
                    <p style="margin: 0 0 6px; font-size: 12px; color: {COLOR_TEXT_SUBTLE}; text-align: center;">
                      © 2026 ATS System. Bản quyền đã được bảo hộ.
                    </p>
                    <p style="margin: 0; font-size: 12px; color: {COLOR_TEXT_SUBTLE}; text-align: center;">
                      Nền tảng Quản trị Tuyển dụng Ứng dụng Trí tuệ Nhân tạo
                    </p>
                  </td>
                </tr>
              </table>

            </td>
          </tr>
        </table>
      </div>
    """

I18N_MESSAGES = {
    "vi": {
        "verify": {
            "subject": "Kích hoạt tài khoản Hệ thống ATS",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Xin chào <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Chào mừng bạn đến với Hệ thống Quản lý Tuyển dụng AI. Vui lòng bấm vào nút bên dưới để xác thực địa chỉ email và kích hoạt tài khoản của bạn:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="{{link}}" style="background-color: {COLOR_PRIMARY_600}; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 15px; display: inline-block;">KÍCH HOẠT TÀI KHOẢN</a>
                </div>
                <p style="font-size: 13px; color: {COLOR_TEXT_SUBTLE}; margin: 0;"><em>*Link xác thực này sẽ hết hạn sau 24 giờ.</em></p>
            """
        },
        "reset_password": {
            "subject": "Yêu cầu đặt lại mật khẩu",
            "content": f"""
                <h2 style="color: {COLOR_PRIMARY_700}; text-align: center; margin: 0 0 20px; font-size: 20px;">Yêu cầu đặt lại mật khẩu {lucide_icon("key_round", size=18, color=COLOR_PRIMARY_700)}</h2>
                <p style="font-size: 16px; margin: 0 0 16px;">Xin chào <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. Vui lòng bấm vào nút bên dưới để tiến hành tạo mật khẩu mới:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="{{link}}" style="background-color: {COLOR_PRIMARY_600}; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 15px; display: inline-block;">ĐẶT LẠI MẬT KHẨU</a>
                </div>
                <p style="font-size: 13px; color: {COLOR_TEXT_SUBTLE}; margin: 0;"><em>*Link khôi phục này sẽ hết hạn sau 15 phút.</em></p>
            """
        },
        "notification": {
            "subject": "Cập nhật hồ sơ ứng tuyển: {job_title}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Xin chào <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Hồ sơ ứng tuyển của bạn cho vị trí <strong style="color: {COLOR_TEXT};">{{job_title}}</strong> vừa được cập nhật trạng thái mới.</p>
                <div style="background-color: {COLOR_BACKGROUND}; border-left: 4px solid {COLOR_PRIMARY_600}; border-radius: 8px; padding: 16px 18px; margin: 20px 0;">
                    <h3 style="margin: 0 0 6px; color: {COLOR_PRIMARY_800}; font-size: 15px;">Trạng thái mới: {{status_label}}</h3>
                    <p style="margin: 0; color: {COLOR_TEXT_MUTED};">{{message}}</p>
                </div>
                <div style="text-align: center; margin: 28px 0 0;">
                  <a href="{{link}}" style="background-color: {COLOR_PRIMARY_600}; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 14px; display: inline-block;">XEM CHI TIẾT</a>
                </div>
            """
        },
        "invite_hr": {
            "subject": "Thư mời tham gia quản lý tuyển dụng tại {company_name}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Xin chào,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Bạn vừa nhận được lời mời từ <strong style="color: {COLOR_TEXT};">{{inviter_name}}</strong> để tham gia quản trị hệ thống tuyển dụng của công ty <strong style="color: {COLOR_TEXT};">{{company_name}}</strong> trên nền tảng ATS.</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Vui lòng bấm vào nút bên dưới để tạo tài khoản và tham gia không gian làm việc:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="{{link}}" style="background-color: {COLOR_SUCCESS_500}; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 15px; display: inline-block;">CHẤP NHẬN LỜI MỜI</a>
                </div>
                <p style="font-size: 13px; color: {COLOR_TEXT_SUBTLE}; margin: 0;"><em>*Lưu ý: Link mời này có thời hạn sử dụng trong 7 ngày. Không chia sẻ link này cho người khác.</em></p>
            """
        },
        "interview_invite": {
            "subject": "Thư mời phỏng vấn - Vị trí {job_title} tại {company_name}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Xin chào <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Cảm ơn bạn đã quan tâm và ứng tuyển vào vị trí <strong style="color: {COLOR_TEXT};">{{job_title}}</strong> tại <strong style="color: {COLOR_TEXT};">{{company_name}}</strong>. Hồ sơ của bạn rất phù hợp và chúng tôi muốn mời bạn tham gia một buổi phỏng vấn để trao đổi chi tiết hơn.</p>

                <div style="background-color: {COLOR_BACKGROUND}; border: 1px solid {COLOR_BORDER}; border-radius: 12px; padding: 20px; margin: 24px 0;">
                    <h3 style="margin: 0 0 12px; color: {COLOR_PRIMARY_800}; font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid {COLOR_BORDER}; padding-bottom: 10px;">Thông tin lịch hẹn</h3>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size: 14px; color: {COLOR_TEXT};">
                        <tr>
                            <td style="padding-bottom: 10px;">{lucide_icon("clock", size=15, color=COLOR_PRIMARY_600)} <strong>Thời gian:</strong> {{interview_time}}</td>
                        </tr>
                        <tr>
                            <td style="padding-bottom: 10px;">{lucide_icon("map_pin", size=15, color=COLOR_PRIMARY_600)} <strong>Địa điểm/Hình thức:</strong> {{location}}</td>
                        </tr>
                        {{meeting_link_html}}
                    </table>
                </div>

                {{message_html}}

                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Vui lòng phản hồi lại email này để xác nhận khả năng tham dự của bạn.</p>
                <p style="margin: 0;">Trân trọng,<br/><strong>Bộ phận Tuyển dụng - {{company_name}}</strong></p>
            """
        },
        "ticket_reply": {
            "subject": "Phản hồi yêu cầu hỗ trợ: {subject}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Xin chào <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Cảm ơn bạn đã liên hệ với bộ phận hỗ trợ của ATS. Chúng tôi đã xem xét yêu cầu của bạn (Mã: <strong>#{str("{{ticket_id}}")[:8]}</strong>) và xin phản hồi như sau:</p>
                <div style="background-color: {COLOR_BACKGROUND}; border-left: 4px solid {COLOR_PRIMARY_600}; border-radius: 8px; padding: 16px 18px; margin: 20px 0; color: {COLOR_TEXT}; white-space: pre-wrap;">
                    {{reply_message}}
                </div>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Nếu bạn có bất kỳ thắc mắc nào khác, vui lòng phản hồi lại email này.</p>
                <p style="margin: 0;">Trân trọng,<br/><strong>Đội ngũ Hỗ trợ ATS</strong></p>
            """
        }
    },
    "en": {
        "verify": {
            "subject": "Activate your ATS Account",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Hello <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Welcome to our AI Recruitment System. Please click the button below to verify your email and activate your account:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="{{link}}" style="background-color: {COLOR_PRIMARY_600}; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 15px; display: inline-block;">ACTIVATE ACCOUNT</a>
                </div>
                <p style="font-size: 13px; color: {COLOR_TEXT_SUBTLE}; margin: 0;"><em>*This link expires in 24 hours.</em></p>
            """
        },
        "reset_password": {
            "subject": "Password Reset Request",
            "content": f"""
                <h2 style="color: {COLOR_PRIMARY_700}; text-align: center; margin: 0 0 20px; font-size: 20px;">Password Reset Request {lucide_icon("key_round", size=18, color=COLOR_PRIMARY_700)}</h2>
                <p style="font-size: 16px; margin: 0 0 16px;">Hello <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">We received a request to reset your password. Click the button below to create a new password:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="{{link}}" style="background-color: {COLOR_PRIMARY_600}; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 15px; display: inline-block;">RESET PASSWORD</a>
                </div>
                <p style="font-size: 13px; color: {COLOR_TEXT_SUBTLE}; margin: 0;"><em>*This link expires in 15 minutes.</em></p>
            """
        },
        "notification": {
            "subject": "Application Update: {job_title}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Hello <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Your application for the <strong style="color: {COLOR_TEXT};">{{job_title}}</strong> position has a new status update.</p>
                <div style="background-color: {COLOR_BACKGROUND}; border-left: 4px solid {COLOR_PRIMARY_600}; border-radius: 8px; padding: 16px 18px; margin: 20px 0;">
                    <h3 style="margin: 0 0 6px; color: {COLOR_PRIMARY_800}; font-size: 15px;">New Status: {{status_label}}</h3>
                    <p style="margin: 0; color: {COLOR_TEXT_MUTED};">{{message}}</p>
                </div>
                <div style="text-align: center; margin: 28px 0 0;">
                  <a href="{{link}}" style="background-color: {COLOR_PRIMARY_600}; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 14px; display: inline-block;">VIEW DETAILS</a>
                </div>
            """
        },
        "invite_hr": {
            "subject": "Invitation to join recruitment team at {company_name}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Hello,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">You have been invited by <strong style="color: {COLOR_TEXT};">{{inviter_name}}</strong> to join the recruitment team for <strong style="color: {COLOR_TEXT};">{{company_name}}</strong> on our ATS platform.</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Please click the button below to create your account and join the workspace:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="{{link}}" style="background-color: {COLOR_SUCCESS_500}; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 15px; display: inline-block;">ACCEPT INVITATION</a>
                </div>
                <p style="font-size: 13px; color: {COLOR_TEXT_SUBTLE}; margin: 0;"><em>*Note: This link expires in 7 days. Do not share this link with others.</em></p>
            """
        },
        "ticket_reply": {
            "subject": "Support Ticket Reply: {subject}",
            "content": f"""
                <p style="font-size: 16px; margin: 0 0 16px;">Hello <strong>{{name}}</strong>,</p>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">Thank you for contacting ATS Support. We have reviewed your request (Ticket ID: <strong>#{str("{{ticket_id}}")[:8]}</strong>) and here is our response:</p>
                <div style="background-color: {COLOR_BACKGROUND}; border-left: 4px solid {COLOR_PRIMARY_600}; border-radius: 8px; padding: 16px 18px; margin: 20px 0; color: {COLOR_TEXT}; white-space: pre-wrap;">
                    {{reply_message}}
                </div>
                <p style="margin: 0 0 16px; color: {COLOR_TEXT_MUTED};">If you have any further questions, please feel free to reply directly to this email.</p>
                <p style="margin: 0;">Best regards,<br/><strong>ATS Support Team</strong></p>
            """
        }
    }
}

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
        "sender": {"name": "ATSSYSTEM", "email": SENDER_EMAIL},
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

    meeting_link_html = f'<tr><td style="padding-bottom: 10px;">{lucide_icon("link", size=15, color=COLOR_PRIMARY_600)} <strong>Link tham gia:</strong> <a href="{meeting_link}" style="color: {COLOR_PRIMARY_600};">{meeting_link}</a></td></tr>' if meeting_link else ""
    message_html = f'<div style="background-color: {COLOR_WARNING_50}; padding: 16px 18px; border-left: 4px solid {COLOR_WARNING_500}; border-radius: 8px; margin: 0 0 20px;"><strong style="color: {COLOR_TEXT};">Ghi chú từ Nhân sự:</strong><br/><span style="color: {COLOR_TEXT_MUTED};">{custom_message}</span></div>' if custom_message else ""

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

def send_ticket_reply_email(
    background_tasks: BackgroundTasks,
    to: str,
    name: str,
    ticket_subject: str,
    ticket_id: str,
    reply_message: str,
    lang: str = "vi"
):
    template = I18N_MESSAGES.get(lang, I18N_MESSAGES["vi"])["ticket_reply"]
    subject = template["subject"].format(subject=ticket_subject)

    inner_html = template["content"].format(
        name=name,
        ticket_id=ticket_id,
        reply_message=reply_message
    )

    html_content = get_base_html(inner_html)
    background_tasks.add_task(send_email_via_brevo, to, subject, html_content)
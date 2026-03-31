import os
import httpx
import logging
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

async def send_email_via_brevo(to_email: str, subject: str, html_content: str):
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
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"📧 Email sent successfully to {to_email}")
        except Exception as e:
            logger.error(f"Error sending email: {e}")

def send_verification_email(background_tasks: BackgroundTasks, to: str, name: str, token: str):
    url = f"{FRONTEND_URL}/verify?token={token}"
    html_content = f"""
      <div style="background-color: #f4f7f6; padding: 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
          <div style="background-color: #2563eb; padding: 30px 20px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 26px; letter-spacing: 1px;">🚀 AI CV RANKING</h1>
          </div>
          <div style="padding: 40px 30px; color: #333333; line-height: 1.6;">
            <p style="font-size: 16px;">Xin chào <strong>{name}</strong>,</p>
            <p>Chào mừng bạn đến với Hệ thống Quản lý Tuyển dụng AI. Vui lòng bấm vào nút bên dưới để xác thực địa chỉ email và kích hoạt tài khoản của bạn:</p>
            <div style="text-align: center; margin: 35px 0;">
              <a href="{url}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">KÍCH HOẠT TÀI KHOẢN</a>
            </div>
            <p style="font-size: 14px; color: #666;"><em>*Link xác thực này sẽ hết hạn sau 24 giờ.</em></p>
          </div>
        </div>
      </div>
    """
    background_tasks.add_task(send_email_via_brevo, to, "Kích hoạt tài khoản Hệ thống ATS", html_content)

def send_reset_password_email(background_tasks: BackgroundTasks, to: str, name: str, token: str):
    reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
    html_content = f"""
      <div style="background-color: #f4f7f6; padding: 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
          <div style="background-color: #2563eb; padding: 30px 20px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 26px; letter-spacing: 1px;">🚀 AI CV RANKING</h1>
          </div>
          <div style="padding: 40px 30px; color: #333333; line-height: 1.6;">
            <h2 style="color: #2563eb; text-align: center; margin-top: 0;">Yêu cầu đặt lại mật khẩu 🔑</h2>
            <p style="font-size: 16px;">Xin chào <strong>{name}</strong>,</p> 
            <p>Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. Vui lòng bấm vào nút bên dưới để tiến hành tạo mật khẩu mới:</p>
            <div style="text-align: center; margin: 35px 0;">
              <a href="{reset_link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">ĐẶT LẠI MẬT KHẨU</a>
            </div>
            <p style="font-size: 14px; color: #666;"><em>*Link khôi phục này sẽ hết hạn sau 15 phút.</em></p>
          </div>
        </div>
      </div>
    """
    background_tasks.add_task(send_email_via_brevo, to, "Yêu cầu đặt lại mật khẩu", html_content)
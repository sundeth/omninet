"""
Email service for sending verification and notification emails.
"""
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib
from jinja2 import Environment, BaseLoader

from omninet.config import settings


class EmailService:
    """Service for sending emails."""

    # Simple email templates
    VERIFICATION_TEMPLATE = """
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Omnipet Account Verification</h2>
        <p>Hello {{ nickname }},</p>
        <p>Your verification code is:</p>
        <h1 style="color: #4CAF50; letter-spacing: 5px;">{{ code }}</h1>
        <p>This code will expire in {{ expiry_minutes }} minutes.</p>
        <p>If you didn't request this code, please ignore this email.</p>
        <br>
        <p>Best regards,<br>The Omnipet Team</p>
    </body>
    </html>
    """

    PASSWORD_RESET_TEMPLATE = """
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Omnipet Password Reset</h2>
        <p>Hello {{ nickname }},</p>
        <p>Your password reset code is:</p>
        <h1 style="color: #FF5722; letter-spacing: 5px;">{{ code }}</h1>
        <p>This code will expire in {{ expiry_minutes }} minutes.</p>
        <p>If you didn't request a password reset, please ignore this email.</p>
        <br>
        <p>Best regards,<br>The Omnipet Team</p>
    </body>
    </html>
    """

    WELCOME_TEMPLATE = """
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Welcome to Omnipet!</h2>
        <p>Hello {{ nickname }},</p>
        <p>Your account has been successfully verified and is now active.</p>
        <p>You can now:</p>
        <ul>
            <li>Upload and share game modules</li>
            <li>Participate in online battles</li>
            <li>Earn coins and rewards</li>
        </ul>
        <br>
        <p>Happy gaming!<br>The Omnipet Team</p>
    </body>
    </html>
    """

    def __init__(self):
        self.jinja_env = Environment(loader=BaseLoader())

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send an email using SMTP."""
        if not settings.smtp_user or not settings.smtp_password:
            # Log instead of sending in dev mode without SMTP config
            print(f"[EMAIL] To: {to_email}, Subject: {subject}")
            print(f"[EMAIL] Content: {html_content[:200]}...")
            return True

        try:
            message = MIMEMultipart("alternative")
            message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            message["To"] = to_email
            message["Subject"] = subject

            # Add text part if provided
            if text_content:
                message.attach(MIMEText(text_content, "plain"))

            # Add HTML part
            message.attach(MIMEText(html_content, "html"))

            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
            return True
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send email: {e}")
            return False

    def _render_template(self, template: str, **kwargs) -> str:
        """Render a Jinja2 template string."""
        tmpl = self.jinja_env.from_string(template)
        return tmpl.render(**kwargs)

    async def send_verification_email(
        self, to_email: str, nickname: str, code: str
    ) -> bool:
        """Send verification code email."""
        html = self._render_template(
            self.VERIFICATION_TEMPLATE,
            nickname=nickname,
            code=code,
            expiry_minutes=settings.verification_code_expiry_minutes,
        )
        return await self.send_email(
            to_email=to_email,
            subject="Omnipet - Verify Your Account",
            html_content=html,
        )

    async def send_password_reset_email(
        self, to_email: str, nickname: str, code: str
    ) -> bool:
        """Send password reset code email."""
        html = self._render_template(
            self.PASSWORD_RESET_TEMPLATE,
            nickname=nickname,
            code=code,
            expiry_minutes=settings.verification_code_expiry_minutes,
        )
        return await self.send_email(
            to_email=to_email,
            subject="Omnipet - Password Reset",
            html_content=html,
        )

    async def send_welcome_email(self, to_email: str, nickname: str) -> bool:
        """Send welcome email after verification."""
        html = self._render_template(
            self.WELCOME_TEMPLATE,
            nickname=nickname,
        )
        return await self.send_email(
            to_email=to_email,
            subject="Welcome to Omnipet!",
            html_content=html,
        )


# Singleton instance
email_service = EmailService()

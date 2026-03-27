"""
Email Service
Async SMTP delivery via aiosmtplib with exponential-backoff retries.

Usage:
    from app.services.email_service import email_service

    # In a FastAPI route (non-blocking):
    background_tasks.add_task(email_service.send_verification_email, email, nickname, token)

All send_* methods are fire-and-forget coroutines — they never raise; failures
are logged. The underlying send() returns bool for callers that care.
"""

import asyncio
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM
        self.frontend_url = settings.FRONTEND_URL.rstrip("/")

    @property
    def _configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.from_email)

    # =========================================================================
    # CORE SEND
    # =========================================================================

    async def send(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send an HTML email. Retries up to 3 times with 2s/4s/8s backoff.

        Never raises. Returns True on success, False after all retries exhausted.
        """
        if not self._configured:
            logger.warning(
                "SMTP not configured — email not sent: to=%s subject=%r", to_email, subject
            )
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        delays = [2, 4, 8]
        for attempt, delay in enumerate(delays, start=1):
            try:
                await aiosmtplib.send(
                    msg,
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    start_tls=True,
                    timeout=15,
                )
                logger.info(
                    "Email sent [%s]: to=%s subject=%r",
                    datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    to_email,
                    subject,
                )
                return True
            except Exception as exc:
                logger.warning(
                    "Email attempt %d/3 failed: to=%s error=%s", attempt, to_email, exc
                )
                if attempt < 3:
                    await asyncio.sleep(delay)

        logger.error(
            "Email delivery failed after 3 attempts: to=%s subject=%r", to_email, subject
        )
        return False

    # =========================================================================
    # PUBLIC SEND METHODS
    # =========================================================================

    async def send_verification_email(
        self, to_email: str, nickname: str, token: str
    ) -> None:
        verification_url = f"{self.frontend_url}/verify-email?token={token}"
        html = self._render_verification_template(nickname, verification_url)
        await self.send(to_email, "Verify your Trading Forge account", html)

    async def send_password_reset(
        self, to_email: str, nickname: str, token: str
    ) -> None:
        reset_url = f"{self.frontend_url}/reset-password?token={token}"
        html = self._render_reset_template(nickname, reset_url)
        await self.send(to_email, "Reset your Trading Forge password", html)

    async def send_contest_starting(
        self,
        to_email: str,
        nickname: str,
        contest_name: str,
        start_time: datetime,
    ) -> None:
        html = self._render_contest_starting_template(nickname, contest_name, start_time)
        await self.send(to_email, f"Contest starting soon: {contest_name}", html)

    async def send_contest_results(
        self,
        to_email: str,
        nickname: str,
        contest_name: str,
        rank: int,
        pnl_percent: float,
        prize_usd: float,
    ) -> None:
        html = self._render_contest_results_template(
            nickname, contest_name, rank, pnl_percent, prize_usd
        )
        await self.send(to_email, f"Your results: {contest_name}", html)

    async def send_auto_close_alert(
        self,
        to_email: str,
        nickname: str,
        symbol: str,
        reason: str,
        pnl_usd: float,
    ) -> None:
        html = self._render_auto_close_template(nickname, symbol, reason, pnl_usd)
        await self.send(to_email, f"Position closed automatically: {symbol}", html)

    # =========================================================================
    # HTML TEMPLATES
    # All use inline CSS — email clients don't load external stylesheets.
    # =========================================================================

    @staticmethod
    def _base_layout(title: str, content: str) -> str:
        """Wrap content in the shared dark-theme email shell."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#0a0b0f;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#0a0b0f;min-height:100vh;">
    <tr>
      <td align="center" style="padding:40px 16px;">

        <!-- Card -->
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background-color:#111218;
                      border-radius:10px;border:1px solid #1e2030;
                      box-shadow:0 4px 24px rgba(0,0,0,0.5);">

          <!-- Header / Logo -->
          <tr>
            <td style="padding:28px 40px;border-bottom:1px solid #1e2030;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="font-family:'Courier New',Courier,monospace;
                                 font-size:20px;font-weight:700;
                                 color:#3b82f6;letter-spacing:3px;
                                 text-transform:uppercase;">
                      TRADING FORGE
                    </span>
                  </td>
                  <td align="right">
                    <span style="font-family:'Courier New',Courier,monospace;
                                 font-size:11px;color:#4b5563;letter-spacing:1px;">
                      PRO TRADING SIMULATION
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px;">
              {content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;border-top:1px solid #1e2030;
                       background-color:#0d0e14;border-radius:0 0 10px 10px;">
              <p style="margin:0 0 6px 0;font-size:12px;color:#4b5563;
                        text-align:center;line-height:1.6;">
                You received this email because you have a Trading Forge account.
              </p>
              <p style="margin:0;font-size:11px;color:#374151;text-align:center;">
                Trading Forge &mdash; Simulate. Learn. Master.
              </p>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>
</body>
</html>"""

    @staticmethod
    def _cta_button(url: str, label: str, color: str = "#3b82f6") -> str:
        return f"""<table cellpadding="0" cellspacing="0" border="0" style="margin:32px 0;">
  <tr>
    <td align="center"
        style="background-color:{color};border-radius:6px;">
      <a href="{url}"
         style="display:inline-block;padding:14px 36px;
                font-family:Arial,Helvetica,sans-serif;font-size:15px;
                font-weight:700;color:#ffffff;text-decoration:none;
                letter-spacing:0.5px;">
        {label}
      </a>
    </td>
  </tr>
</table>"""

    @staticmethod
    def _fallback_url_line(url: str) -> str:
        return f"""<p style="margin:16px 0 0 0;font-size:12px;color:#6b7280;">
  Or copy this link into your browser:<br>
  <span style="font-family:'Courier New',Courier,monospace;color:#3b82f6;
               word-break:break-all;">{url}</span>
</p>"""

    @staticmethod
    def _greeting(nickname: str) -> str:
        name = nickname if nickname else "Trader"
        return f"""<p style="margin:0 0 20px 0;font-size:22px;font-weight:700;color:#f3f4f6;">
  Hey, {name} 👋
</p>"""

    # ---- Verification -------------------------------------------------------

    def _render_verification_template(
        self, nickname: str, verification_url: str
    ) -> str:
        content = f"""{self._greeting(nickname)}
<p style="margin:0 0 16px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  Welcome to Trading Forge. Before you can start trading, we need to confirm
  your email address.
</p>
<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  Click the button below to verify your account. This link expires in
  <strong style="color:#e5e7eb;">24 hours</strong>.
</p>
{self._cta_button(verification_url, "Verify My Account")}
{self._fallback_url_line(verification_url)}
<div style="margin-top:32px;padding:16px;background-color:#0d0e14;
            border-radius:6px;border-left:3px solid #3b82f6;">
  <p style="margin:0;font-size:13px;color:#6b7280;line-height:1.6;">
    If you didn&rsquo;t create a Trading Forge account, you can safely ignore
    this email.
  </p>
</div>"""
        return self._base_layout("Verify your Trading Forge account", content)

    # ---- Password Reset -----------------------------------------------------

    def _render_reset_template(self, nickname: str, reset_url: str) -> str:
        content = f"""{self._greeting(nickname)}
<p style="margin:0 0 16px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  We received a request to reset the password for your Trading Forge account.
</p>
<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  Click the button below to choose a new password. This link is valid for
  <strong style="color:#e5e7eb;">1 hour</strong>.
</p>
{self._cta_button(reset_url, "Reset My Password", "#ef4444")}
{self._fallback_url_line(reset_url)}
<div style="margin-top:32px;padding:16px;background-color:#0d0e14;
            border-radius:6px;border-left:3px solid #ef4444;">
  <p style="margin:0;font-size:13px;color:#6b7280;line-height:1.6;">
    If you didn&rsquo;t request a password reset, your account is safe — no
    changes have been made. You can ignore this email.
  </p>
</div>"""
        return self._base_layout("Reset your Trading Forge password", content)

    # ---- Contest Starting ---------------------------------------------------

    def _render_contest_starting_template(
        self, nickname: str, contest_name: str, start_time: datetime
    ) -> str:
        start_str = start_time.strftime("%A %d %B %Y at %H:%M UTC")
        contests_url = f"{self.frontend_url}/contests"
        content = f"""{self._greeting(nickname)}
<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  A contest you&rsquo;re registered in is about to begin:
</p>

<div style="margin:24px 0;padding:24px;background-color:#0d0e14;
            border-radius:8px;border:1px solid #1e2030;">
  <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
            text-transform:uppercase;letter-spacing:1px;">Contest</p>
  <p style="margin:0 0 20px 0;font-size:20px;font-weight:700;color:#f3f4f6;">
    {contest_name}
  </p>
  <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
            text-transform:uppercase;letter-spacing:1px;">Starts</p>
  <p style="margin:0;font-family:'Courier New',Courier,monospace;
            font-size:16px;color:#3b82f6;font-weight:700;">
    {start_str}
  </p>
</div>

<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  Make sure you&rsquo;re ready. Head to your dashboard to review your strategy
  before the starting bell.
</p>
{self._cta_button(contests_url, "Go to Contests")}"""
        return self._base_layout(f"Contest starting soon: {contest_name}", content)

    # ---- Contest Results ----------------------------------------------------

    def _render_contest_results_template(
        self,
        nickname: str,
        contest_name: str,
        rank: int,
        pnl_percent: float,
        prize_usd: float,
    ) -> str:
        pnl_color = "#22c55e" if pnl_percent >= 0 else "#ef4444"
        pnl_sign = "+" if pnl_percent >= 0 else ""
        rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "🏅")
        prize_str = (
            f'<p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:1px;">Prize Awarded</p>'
            f'<p style="margin:0;font-family:\'Courier New\',Courier,monospace;'
            f'font-size:22px;color:#22c55e;font-weight:700;">'
            f'${prize_usd:,.2f}</p>'
        ) if prize_usd > 0 else ""

        dashboard_url = f"{self.frontend_url}/dashboard"
        content = f"""{self._greeting(nickname)}
<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  The contest has ended. Here&rsquo;s how you performed:
</p>

<div style="margin:24px 0;padding:24px;background-color:#0d0e14;
            border-radius:8px;border:1px solid #1e2030;">
  <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
            text-transform:uppercase;letter-spacing:1px;">Contest</p>
  <p style="margin:0 0 24px 0;font-size:18px;font-weight:700;color:#f3f4f6;">
    {contest_name}
  </p>

  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td style="padding-right:16px;">
        <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
                  text-transform:uppercase;letter-spacing:1px;">Final Rank</p>
        <p style="margin:0;font-family:'Courier New',Courier,monospace;
                  font-size:28px;font-weight:700;color:#f3f4f6;">
          {rank_emoji} #{rank}
        </p>
      </td>
      <td>
        <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
                  text-transform:uppercase;letter-spacing:1px;">P&amp;L</p>
        <p style="margin:0;font-family:'Courier New',Courier,monospace;
                  font-size:28px;font-weight:700;color:{pnl_color};">
          {pnl_sign}{pnl_percent:.2f}%
        </p>
      </td>
    </tr>
  </table>

  {f'<div style="margin-top:24px;padding-top:24px;border-top:1px solid #1e2030;">{prize_str}</div>' if prize_usd > 0 else ""}
</div>

{self._cta_button(dashboard_url, "View Dashboard")}"""
        return self._base_layout(f"Your results: {contest_name}", content)

    # ---- Auto-Close Alert ---------------------------------------------------

    def _render_auto_close_template(
        self, nickname: str, symbol: str, reason: str, pnl_usd: float
    ) -> str:
        pnl_color = "#22c55e" if pnl_usd >= 0 else "#ef4444"
        pnl_sign = "+" if pnl_usd >= 0 else ""

        reason_labels = {
            "stop_loss": ("Stop-Loss Triggered", "#ef4444"),
            "take_profit": ("Take-Profit Hit", "#22c55e"),
            "trailing_stop": ("Trailing Stop Triggered", "#f59e0b"),
        }
        reason_label, reason_color = reason_labels.get(
            reason, (reason.replace("_", " ").title(), "#9ca3af")
        )

        dashboard_url = f"{self.frontend_url}/dashboard"
        content = f"""{self._greeting(nickname)}
<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  One of your positions was automatically closed by your risk management rules.
</p>

<div style="margin:24px 0;padding:24px;background-color:#0d0e14;
            border-radius:8px;border:1px solid #1e2030;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td style="padding-bottom:20px;padding-right:16px;">
        <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
                  text-transform:uppercase;letter-spacing:1px;">Symbol</p>
        <p style="margin:0;font-family:'Courier New',Courier,monospace;
                  font-size:22px;font-weight:700;color:#f3f4f6;">
          {symbol}
        </p>
      </td>
      <td style="padding-bottom:20px;">
        <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
                  text-transform:uppercase;letter-spacing:1px;">Reason</p>
        <p style="margin:0;font-size:16px;font-weight:700;color:{reason_color};">
          {reason_label}
        </p>
      </td>
    </tr>
    <tr>
      <td colspan="2" style="padding-top:20px;border-top:1px solid #1e2030;">
        <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;
                  text-transform:uppercase;letter-spacing:1px;">Realised P&amp;L</p>
        <p style="margin:0;font-family:'Courier New',Courier,monospace;
                  font-size:26px;font-weight:700;color:{pnl_color};">
          {pnl_sign}${abs(pnl_usd):,.2f}
        </p>
      </td>
    </tr>
  </table>
</div>

<p style="margin:0 0 8px 0;font-size:15px;color:#9ca3af;line-height:1.7;">
  Visit your dashboard to review your portfolio and open new positions.
</p>
{self._cta_button(dashboard_url, "View Portfolio")}"""
        return self._base_layout(f"Position closed automatically: {symbol}", content)


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------

email_service = EmailService()

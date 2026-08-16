"""Resolven-branded regulatory update email content."""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any

from backend.core.config import settings
from backend.core.models import SummaryPayload


def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _format_date(value: date | datetime | None) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d %b %Y")


def _summary_fields(context: dict[str, Any]) -> tuple[str, str]:
    """Return (headline, body) from existing pipeline summary fields."""

    title = str(context.get("title") or "Regulatory update").strip()
    raw = (context.get("raw_summary") or "").strip()
    summary_json = context.get("summary_json")
    plain = ""
    why = ""
    if summary_json:
        try:
            payload = (
                summary_json
                if isinstance(summary_json, SummaryPayload)
                else SummaryPayload.model_validate(summary_json)
            )
            plain = (payload.plain_english_summary or "").strip()
            why = (payload.why_it_matters or "").strip()
        except Exception:  # noqa: BLE001 — fall back to raw/title
            plain = ""
            why = ""

    headline = title
    body = plain or raw or why or (
        f"A regulatory update from {context.get('source_name') or 'a subscribed source'} "
        "is now available in Resolven."
    )
    return headline, body


def build_notification_email(context: dict[str, Any]) -> tuple[str, str, str]:
    """Build subject, html, and text for a NEW/CHANGED regulatory event email."""

    source_name = str(context.get("source_name") or "Regulatory source").strip()
    event_type = str(context.get("event_type") or "NEW").upper()
    event_id = int(context["event_id"])
    headline, summary = _summary_fields(context)
    issue_date = _format_date(context.get("issue_date") or context.get("detected_at"))
    doc_type = (context.get("doc_type") or "").strip() or "Regulatory document"
    cta_url = f"{settings.app_base_url.rstrip('/')}/events/{event_id}"
    preferences_url = f"{settings.app_base_url.rstrip('/')}/dashboard"
    logo_url = f"{settings.app_base_url.rstrip('/')}/logo_wordmark.png"
    mark_url = f"{settings.app_base_url.rstrip('/')}/logo_mark.png"

    if event_type == "CHANGED":
        subject = f"Regulatory update changed: {headline}"[:180]
        lead = f"An update you follow from {source_name} has changed."
        section_title = "What changed?"
    else:
        subject = f"New {source_name} regulatory update: {headline}"[:180]
        if not headline or headline.lower() == "regulatory update":
            subject = f"New regulatory update from {source_name}"
        lead = f"A new regulatory update from {source_name} is available."
        section_title = "What happened?"

    text = "\n".join(
        [
            "Resolven Regulatory Intelligence",
            "",
            subject,
            "",
            lead,
            "",
            section_title,
            summary,
            "",
            f"Source: {source_name}",
            f"Published: {issue_date}",
            f"Type: {doc_type}",
            "",
            f"View regulatory update: {cta_url}",
            "",
            f"Manage notification preferences: {preferences_url}",
        ]
    )

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background:#f4f1f8;font-family:Arial,Helvetica,sans-serif;color:#1f1633;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f1f8;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e4d8ef;">
          <tr>
            <td style="background:#522b91;padding:20px 28px;text-align:center;">
              <img src="{_escape(logo_url)}" alt="Resolven" width="160" style="display:inline-block;max-width:160px;height:auto;border:0;" />
            </td>
          </tr>
          <tr>
            <td style="padding:28px 28px 8px 28px;">
              <p style="margin:0 0 8px 0;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#3db769;font-weight:700;">
                Regulatory update
              </p>
              <h1 style="margin:0 0 12px 0;font-size:22px;line-height:1.35;color:#522b91;">
                {_escape(subject if event_type != 'CHANGED' else f'Regulatory update changed')}
              </h1>
              <p style="margin:0 0 18px 0;font-size:15px;line-height:1.6;color:#4a3f63;">
                {_escape(lead)}
              </p>
              <h2 style="margin:0 0 8px 0;font-size:16px;color:#1f1633;">{_escape(headline)}</h2>
              <p style="margin:0 0 4px 0;font-size:13px;font-weight:700;color:#522b91;">{_escape(section_title)}</p>
              <p style="margin:0 0 20px 0;font-size:15px;line-height:1.65;color:#3a3150;">
                {_escape(summary)}
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 0 24px 0;width:100%;background:#f8f5fb;border-radius:12px;">
                <tr>
                  <td style="padding:14px 16px;font-size:13px;line-height:1.6;color:#4a3f63;">
                    <strong style="color:#522b91;">Source:</strong> {_escape(source_name)}<br />
                    <strong style="color:#522b91;">Published:</strong> {_escape(issue_date)}<br />
                    <strong style="color:#522b91;">Type:</strong> {_escape(doc_type)}
                  </td>
                </tr>
              </table>
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 0 8px 0;">
                <tr>
                  <td style="border-radius:999px;background:#522b91;">
                    <a href="{_escape(cta_url)}" style="display:inline-block;padding:12px 22px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;">
                      View Regulatory Update
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background:linear-gradient(90deg,#522b91 0%,#3db769 100%);padding:18px 28px;text-align:center;">
              <img src="{_escape(mark_url)}" alt="" width="28" height="28" style="display:inline-block;vertical-align:middle;border:0;margin-right:8px;" />
              <span style="display:inline-block;vertical-align:middle;color:#ffffff;font-size:13px;font-weight:700;letter-spacing:0.04em;">
                RESOLVEN · Regulatory Intelligence
              </span>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 28px 24px 28px;text-align:center;font-size:12px;line-height:1.5;color:#7a6f8f;">
              You received this email because you enabled instant regulatory update notifications.
              <br />
              <a href="{_escape(preferences_url)}" style="color:#522b91;text-decoration:underline;">Manage notification preferences</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return subject, html_body, text

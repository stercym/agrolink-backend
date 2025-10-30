import html
from typing import Iterable, Union, Dict, Any, Optional, List

from flask import current_app

import sib_api_v3_sdk
from sib_api_v3_sdk.api.transactional_emails_api import TransactionalEmailsApi
from sib_api_v3_sdk.rest import ApiException

Recipient = Union[str, Dict[str, Any]]


def _normalise_recipients(recipients: Union[Recipient, Iterable[Recipient]]) -> List[Dict[str, Optional[str]]]:
    if not recipients:
        return []

    if isinstance(recipients, (str, dict)):
        recipients = [recipients]

    normalised: List[Dict[str, Optional[str]]] = []
    for entry in recipients:
        if isinstance(entry, str):
            email = entry.strip()
            if email:
                normalised.append({"email": email})
        elif isinstance(entry, dict):
            email = entry.get("email")
            if email:
                normalised.append({
                    "email": email,
                    "name": entry.get("name") or entry.get("full_name"),
                })
    return normalised


def send_email(
    *,
    subject: str,
    recipients: Union[Recipient, Iterable[Recipient]],
    text_body: Optional[str] = None,
    html_body: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> bool:
    """Send an email using Brevo's transactional API.

    Returns ``True`` on success, ``False`` when the message could not be sent.
    """

    api_key = current_app.config.get("BREVO_API_KEY")
    sender_email = current_app.config.get("MAIL_DEFAULT_SENDER")
    sender_name = sender_name or current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "AgroLink")

    if not api_key or not sender_email:
        current_app.logger.error(
            "Email not sent. Missing BREVO_API_KEY or MAIL_DEFAULT_SENDER configuration."
        )
        return False

    payload_recipients = _normalise_recipients(recipients)
    if not payload_recipients:
        current_app.logger.warning("Email not sent. No valid recipients for subject '%s'.", subject)
        return False

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = api_key

    if not html_body and text_body:
        html_body = "<br>".join(html.escape(text_body).splitlines())

    email = sib_api_v3_sdk.SendSmtpEmail(
        sender={"email": sender_email, "name": sender_name},
        to=payload_recipients,
        subject=subject,
        html_content=html_body,
        text_content=text_body,
    )

    api_client = sib_api_v3_sdk.ApiClient(configuration)

    try:
        api_instance = TransactionalEmailsApi(api_client)
        api_instance.send_transac_email(email)
        return True
    except ApiException as exc:
        current_app.logger.error("Brevo API error while sending '%s': %s", subject, exc)
    except Exception as exc:  
        current_app.logger.exception("Unexpected error while sending '%s': %s", subject, exc)
    finally:
        if hasattr(api_client, "close"):
            api_client.close()

    return False
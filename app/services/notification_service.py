import logging

logger = logging.getLogger("quickcart.notifications")


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def send_order_confirmation(order_id: int, email: str, total_amount: str) -> None:
    """Today: write a log line. Later: send a real email (SMTP / AWS SES / SendGrid)."""
    logger.info(
        "order_confirmation_sent",
        extra={
            "order_id": order_id,
            "recipient": _mask_email(email),  # never log full personal data
            "total_amount": total_amount,
            "channel": "log",
        },
    )

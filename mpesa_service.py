"""
Simple Daraja (M-Pesa) service adapter.
- Uses sandbox endpoints when credentials provided (MPESA_CONSUMER_KEY/SECRET)
- Falls back to a mocked response for local testing if credentials absent
"""
import os
import base64
import datetime
import requests
from flask import current_app

BASE_URL = "https://sandbox.safaricom.co.ke"

def get_access_token():
    consumer_key = current_app.config.get("MPESA_CONSUMER_KEY")
    consumer_secret = current_app.config.get("MPESA_CONSUMER_SECRET")
    if not consumer_key or not consumer_secret:
        return None

    url = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    res = requests.get(url, auth=(consumer_key, consumer_secret))
    res.raise_for_status()
    return res.json().get("access_token")


def initiate_stk_push(phone: str, amount: float, order_id: int):
    """
    Initiate an STK Push via Daraja. Returns Daraja response dict.
    If no credentials are set, returns a mocked success response (useful locally).
    """
    consumer_token = get_access_token()
    shortcode = current_app.config.get("MPESA_SHORTCODE")
    passkey = current_app.config.get("MPESA_PASSKEY")
    callback_url = current_app.config.get("MPESA_CALLBACK_URL")

    # Local mock if credentials not set
    if not consumer_token or not shortcode or not passkey:
        # Provide a fake CheckoutRequestID for testing
        checkout_id = f"MOCK-{order_id}-{int(datetime.datetime.utcnow().timestamp())}"
        return {
            "ResponseCode": "0",
            "ResponseDescription": "Mocked STK Push initiated",
            "CheckoutRequestID": checkout_id
        }

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": str(phone),
        "PartyB": shortcode,
        "PhoneNumber": str(phone),
        "CallBackURL": callback_url,
        "AccountReference": f"Order{order_id}",
        "TransactionDesc": f"Payment for order {order_id}"
    }

    headers = {
        "Authorization": f"Bearer {consumer_token}",
        "Content-Type": "application/json"
    }

    url = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

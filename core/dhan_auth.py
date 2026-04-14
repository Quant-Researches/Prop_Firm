import json
from pathlib import Path

import pyotp
import requests

BASE_AUTH_URL = "https://auth.dhan.co/app/generateAccessToken"
BASE_API_URL = "https://api.dhan.co/v2"

class DhanAutoLogin:
    @staticmethod
    def generate_and_save_token(client_id: str, pin: str, totp_secret: str, prefs_path: str = "config/user_prefs.json") -> dict:
        current_totp = pyotp.TOTP(totp_secret).now()

        params = {
            "dhanClientId": client_id,
            "pin": pin,
            "totp": current_totp
        }

        response = requests.post(BASE_AUTH_URL, params=params, timeout=20)
        response.raise_for_status()

        data = response.json()

        if "accessToken" not in data:
            raise RuntimeError(f"Access token missing in response: {data}")

        access_token = data.get("accessToken")
        
        p_path = Path(prefs_path)
        if p_path.exists():
            try:
                with open(p_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            except Exception:
                prefs = {}
        else:
            prefs = {}
            p_path.parent.mkdir(parents=True, exist_ok=True)
            
        prefs["dhan_api_key"] = access_token
        prefs["dhan_client_id"] = client_id
        prefs["dhan_pin"] = pin
        prefs["totp_secret"] = totp_secret
        
        with open(p_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)

        return data

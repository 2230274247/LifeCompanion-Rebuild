"""Create local synthetic accounts through official APIs; credentials stay ignored."""
import json
import secrets
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
runtime = root / "infra/runtime/v02-memory-reminders"
accounts_file = runtime / "accounts.json"
env = {}
for line in (root/"infra/.env").read_text(encoding="utf-8-sig").splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=",1)
        env[key] = value
accounts = json.loads(accounts_file.read_text(encoding="utf-8")) if accounts_file.exists() else {}
tokens_file = runtime/"memos-tokens.json"
tokens = json.loads(tokens_file.read_text(encoding="utf-8")) if tokens_file.exists() else {}
with httpx.Client(timeout=30,trust_env=False) as client:
    for letter in ("a","b"):
        account = accounts.setdefault(letter,{
            "email":f"life-v021-{letter}@example.test","username":f"life-v021-{letter}",
            "name":f"Synthetic V021 {letter.upper()}","password":secrets.token_urlsafe(30)+"aA1!",
        })
        accounts_file.write_text(json.dumps(accounts,indent=2),encoding="utf-8")
        if not account.get("librechat_user_id"):
            response=client.post("http://127.0.0.1:3001/api/auth/register",
                json={**account,"confirm_password":account["password"]})
            assert response.status_code==200, f"LibreChat register HTTP {response.status_code}"
            login=client.post("http://127.0.0.1:3001/api/auth/login",
                json={"email":account["email"],"password":account["password"]})
            assert login.status_code==200, f"LibreChat login HTTP {login.status_code}"
            account["librechat_user_id"]=login.json()["user"]["id"]
            accounts_file.write_text(json.dumps(accounts,indent=2),encoding="utf-8")
        if not account.get("memos_user_id"):
            response=client.post("http://127.0.0.1:5230/api/users",
                headers={"Authorization":"Bearer "+env["MEMOS_API_TOKEN"]},
                json={"username":account["username"],"password":account["password"],
                      "displayName":account["name"],"role":"USER","state":"NORMAL"})
            assert response.status_code==200, f"Memos create user HTTP {response.status_code}"
            account["memos_user_id"]=response.json()["name"]
            accounts_file.write_text(json.dumps(accounts,indent=2),encoding="utf-8")
        login=client.post("http://127.0.0.1:5230/api/auth/signin",json={
            "passwordCredentials":{"username":account["username"],"password":account["password"]}})
        assert login.status_code==200, f"Memos login HTTP {login.status_code}"
        auth={"Authorization":"Bearer "+login.json()["accessToken"]}
        if account["memos_user_id"] not in tokens:
            response=client.post("http://127.0.0.1:5230/api/"+account["memos_user_id"]+"/personalAccessTokens",
                headers=auth,json={"description":"Local isolated V0.2 integration test","expiresInDays":7})
            assert response.status_code==200, f"Memos PAT HTTP {response.status_code}"
            tokens[account["memos_user_id"]]=response.json()["token"]
            tokens_file.write_text(json.dumps(tokens,indent=2),encoding="utf-8")
        response=client.post("http://127.0.0.1:8010/internal/v1/users/bootstrap",
            headers={"X-Internal-Token":env["LIFE_INTERNAL_TOKEN"]},json={
                "librechat_user_id":account["librechat_user_id"],"memos_user_id":account["memos_user_id"],
                "memos_username":account["username"],"display_name":account["name"],"memory_consent":True})
        assert response.status_code==200, f"life-core mapping HTTP {response.status_code}"
accounts_file.write_text(json.dumps(accounts,indent=2),encoding="utf-8")
config_path=root/"infra/.env"
old=config_path.read_text(encoding="utf-8-sig")
if "LIFE_MEMOS_TOKENS_FILE=" not in old:
    (runtime/"infra.env.before-memory-mapping").write_text(old,encoding="utf-8")
    config_path.write_text(old.rstrip()+"\nLIFE_MEMOS_TOKENS_FILE="+str(tokens_file)+"\n",encoding="utf-8")
print("PASS: two local synthetic LibreChat + Memos accounts; distinct server-side PAT mappings. No credentials printed.")

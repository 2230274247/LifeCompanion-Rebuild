"""Sanitized, non-generative provider preflight for the V0.3 B2 acceptance run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]
MODEL = "Kwai-Kolors/Kolors"
PRICING_URL = "https://www.siliconflow.cn/pricing"
DOCS_URL = "https://api-docs.siliconflow.cn/docs/api/images-generations-post"
MODELS_URL = "https://api.siliconflow.cn/v1/models"


def env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return values


def merged_env(*paths: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in paths:
        for name, value in env_file(path).items():
            if value or name not in values:
                values[name] = value
    return values


def page_text(content: bytes) -> str:
    html = content.decode("utf-8", errors="replace")
    visible = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    visible = unescape(re.sub(r"(?s)<[^>]+>", " ", visible))
    return " ".join(visible.split())


def trace_id(response: httpx.Response) -> str | None:
    return (
        response.headers.get("x-siliconcloud-trace-id")
        or response.headers.get("x-trace-id")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--silicon-env", required=True)
    parser.add_argument(
        "--acceptance-env",
        default=str(ROOT / "infra/runtime/p00/acceptance.env"),
    )
    parser.add_argument(
        "--main-env",
        default="H:/AI For research institute/LifeCompanion-Rebuild/infra/.env",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = merged_env(
        Path(args.acceptance_env),
        Path(args.main_env),
        Path(args.silicon_env),
    )
    deepseek_key = env.get("DEEPSEEK_API_KEY", "").strip()
    silicon_key = env.get("SILICONFLOW_API_KEY", "").strip()
    record = {
        "status": "BLOCKED",
        "classification": "REAL_PREFLIGHT",
        "started_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "prompt_generation_requests": 0,
        "image_generation_requests": 0,
        "image_downloads": 0,
        "budget": {"max_image_requests": 1, "max_images": 1, "cap_cny": "0.00"},
        "checks": {},
    }

    try:
        if not deepseek_key:
            raise RuntimeError("DEEPSEEK_API_KEY_NOT_SET")
        if not silicon_key:
            raise RuntimeError("SILICONFLOW_API_KEY_NOT_SET")
        record["checks"]["independent_api_keys_present"] = "PASS"
        record["checks"]["keys_are_distinct"] = (
            "PASS" if deepseek_key != silicon_key else "FAIL"
        )
        if deepseek_key == silicon_key:
            raise RuntimeError("PROVIDER_KEYS_NOT_INDEPENDENT")

        with httpx.Client(
            timeout=httpx.Timeout(40, connect=10),
            trust_env=False,
            follow_redirects=True,
        ) as client:
            docs = client.get(DOCS_URL)
            record["official_docs"] = {
                "url": DOCS_URL,
                "status_code": docs.status_code,
                "sha256": hashlib.sha256(docs.content).hexdigest(),
                "final_url": str(docs.url),
            }
            if docs.status_code != 200:
                raise RuntimeError("OFFICIAL_API_DOCS_FETCH_FAILED")
            record["checks"]["official_api_docs"] = "PASS"

            pricing = client.get(PRICING_URL)
            expected = f"{MODEL} 生成图片 每图片 免费"
            visible = page_text(pricing.content)
            record["official_price"] = {
                "url": PRICING_URL,
                "status_code": pricing.status_code,
                "sha256": hashlib.sha256(pricing.content).hexdigest(),
                "model": MODEL,
                "price_cny_per_image": 0 if expected in visible else None,
                "evidence": expected if expected in visible else None,
            }
            if pricing.status_code != 200 or expected not in visible:
                raise RuntimeError("OFFICIAL_FREE_PRICE_NOT_CONFIRMED")
            if record["official_price"]["price_cny_per_image"] != 0:
                raise RuntimeError("BUDGET_CAP_EXCEEDED")
            record["checks"]["official_free_price"] = "PASS"
            record["checks"]["zero_cny_budget"] = "PASS"

            models = client.get(
                MODELS_URL,
                headers={"Authorization": "Bearer " + silicon_key},
            )
            if models.status_code in (401, 403):
                raise RuntimeError("SILICONFLOW_PERMISSION_DENIED")
            if models.status_code != 200:
                raise RuntimeError("SILICONFLOW_MODEL_ACCESS_HTTP_ERROR")
            ids = {item.get("id") for item in models.json().get("data", [])}
            record["kolors_model_access"] = {
                "status_code": models.status_code,
                "model_visible_to_account": MODEL in ids,
                "trace_id": trace_id(models),
            }
            if MODEL not in ids:
                raise RuntimeError("KOLORS_NOT_AVAILABLE_TO_ACCOUNT")
            record["checks"]["kolors_model_access"] = "PASS"

            balance = client.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": "Bearer " + deepseek_key},
            )
            if balance.status_code != 200:
                raise RuntimeError("DEEPSEEK_ACCOUNT_CHECK_FAILED")
            payload = balance.json()
            available = bool(payload.get("is_available"))
            record["deepseek_account_access"] = {
                "status_code": balance.status_code,
                "is_available": available,
            }
            if not available:
                raise RuntimeError("DEEPSEEK_ACCOUNT_UNAVAILABLE")
            record["checks"]["deepseek_account_access"] = "PASS"

        record["status"] = "PASS"
        return_code = 0
    except Exception as exc:
        record["error_code"] = str(exc)
        return_code = 2
    finally:
        record["completed_at"] = datetime.now(UTC).isoformat()
        output_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "error_code": record.get("error_code"),
                    "checks": record["checks"],
                    "prompt_generation_requests": 0,
                    "image_generation_requests": 0,
                    "output": str(output_path),
                },
                ensure_ascii=False,
            )
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

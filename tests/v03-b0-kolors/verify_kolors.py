"""Run one real, budget-gated Kolors image-generation smoke test."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time
import uuid

import httpx

from provider import (
    GenerationRequest,
    KolorsProvider,
    ProviderError,
    check_model_access,
    check_official_free_price,
    redact_response_text,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "evidence" / "runtime" / "v03-b0-kolors"
DEFAULT_KEY_FILE = Path(__file__).resolve().parent / ".env.local"
PROMPT = (
    "清晨七点，一位虚构的年轻人在香港旧区的小公寓厨房里给窗台的薄荷浇水，"
    "阳光落在白瓷杯、木质餐桌和刚烤好的吐司上；生活化纪实摄影，温暖安静，"
    "自然光，真实材质，3:4 竖构图，不出现文字、品牌标志或可识别身份。"
)
MAX_APPROVED_CNY = Decimal("0.00")
MAX_IMAGES = 1
GENERIC_BINARY_FALLBACK_ENV = "SILICONFLOW_ALLOW_GENERIC_BINARY_MIME"
BLOCKED_CODES = {
    "OFFICIAL_PRICE_FETCH_FAILED",
    "OFFICIAL_FREE_PRICE_NOT_CONFIRMED",
    "BUDGET_CAP_EXCEEDED",
    "SILICONFLOW_API_KEY_NOT_SET",
    "MODEL_ACCESS_CHECK_TIMEOUT",
    "MODEL_ACCESS_CHECK_NETWORK_FAILED",
    "ACCOUNT_PERMISSION_DENIED",
    "MODEL_ACCESS_CHECK_HTTP_ERROR",
    "MODEL_ACCESS_RESPONSE_INVALID",
    "MODEL_NOT_AVAILABLE_TO_ACCOUNT",
    "B0_SINGLE_ATTEMPT_ALREADY_USED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _reserve_single_attempt(path: Path) -> None:
    if path.exists():
        raise ProviderError("B0_SINGLE_ATTEMPT_ALREADY_USED")
    payload = {
        "status": "RESERVED_BEFORE_IMAGE_REQUEST",
        "reserved_at": _now(),
        "max_requests": 1,
        "max_images": MAX_IMAGES,
        "budget_cap_cny": "0.00",
    }
    _write_json(path, payload)


def _update_attempt(path: Path, status: str, **extra) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(status=status, updated_at=_now(), **extra)
    _write_json(path, payload)


def _load_api_key(key_file: Path = DEFAULT_KEY_FILE) -> tuple[str, str]:
    environment_value = os.getenv("SILICONFLOW_API_KEY", "").strip()
    if environment_value:
        return environment_value, "SILICONFLOW_API_KEY_ENV"
    if key_file.exists():
        for raw_line in key_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "SILICONFLOW_API_KEY":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                if value:
                    return value, "SILICONFLOW_API_KEY_FILE"
    return "", "NOT_CONFIGURED"


def _apply_failure_diagnostics(record: dict, request_record: dict, exc: ProviderError) -> dict:
    diagnostics = dict(exc.diagnostics)
    stage = exc.stage if exc.stage != "unknown" else diagnostics.get("stage")
    response_record = {
        "status": "PROVIDER_ERROR",
        "failure_stage": stage,
        "request_sent": diagnostics.get("request_sent"),
        "response_received": diagnostics.get("response_received"),
        "download_completed": diagnostics.get("download_completed"),
        "api_http_status": diagnostics.get("api_http_status", exc.status_code),
        "download_http_status": diagnostics.get("download_http_status"),
        "provider_trace_id": diagnostics.get("provider_trace_id") or exc.trace_id,
        "declared_content_type": diagnostics.get("declared_content_type"),
        "pillow_format": diagnostics.get("pillow_format"),
        "detected_mime": diagnostics.get("detected_mime"),
        "dimensions": diagnostics.get("dimensions"),
        "image_bytes": diagnostics.get("image_bytes"),
        "magic_hex": diagnostics.get("magic_hex"),
        "body_excerpt": exc.detail,
    }
    record["failure_stage"] = stage
    record["failure_diagnostics"] = diagnostics
    if diagnostics.get("request_sent") is not None:
        request_record["request_sent"] = diagnostics["request_sent"]
    if diagnostics.get("response_received") is not None:
        request_record["response_received"] = diagnostics["response_received"]
        request_record["download_completed"] = diagnostics.get("download_completed")
    if diagnostics.get("download_completed"):
        record["image_downloads"] = 1
    return response_record


def _save_rejected_image(output_dir: Path, exc: ProviderError) -> dict | None:
    if not exc.raw_image:
        return None
    trace = (
        exc.diagnostics.get("provider_trace_id")
        or exc.trace_id
        or uuid.uuid4().hex
    )
    safe_trace = "".join(character for character in trace if character.isalnum() or character in "-_")
    target = output_dir / "quarantine" / f"rejected-{safe_trace}.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(exc.raw_image)
    digest = sha256(exc.raw_image).hexdigest()
    if digest != exc.diagnostics.get("file_sha256"):
        raise ProviderError("QUARANTINE_HASH_MISMATCH", stage="evidence_write")
    return {
        "status": "REJECTED_NOT_ACCEPTED",
        "path": str(target),
        "bytes": len(exc.raw_image),
        "sha256": digest,
        "reason": exc.code,
        "stage": exc.stage,
    }


def run(output_dir: Path = DEFAULT_OUTPUT) -> int:
    started_at = _now()
    started = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "request.redacted.json"
    response_path = output_dir / "response.redacted.json"
    verification_path = output_dir / "verification.json"
    error_path = output_dir / "errors.log"
    ledger_path = output_dir / "attempt-ledger.json"
    request = GenerationRequest(prompt=PROMPT, width=960, height=1280)
    trace_id = "lc-b0-kolors-" + uuid.uuid4().hex
    allow_generic_binary_mime = (
        os.getenv(GENERIC_BINARY_FALLBACK_ENV, "").strip() == "1"
    )
    if ledger_path.exists():
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_code": "B0_SINGLE_ATTEMPT_ALREADY_USED",
                    "image_generation_requests": "SEE_EXISTING_LEDGER",
                    "output_dir": str(output_dir),
                },
                ensure_ascii=False,
            )
        )
        return 2
    record = {
        "status": "BLOCKED",
        "classification": "BLOCKED",
        "started_at": started_at,
        "provider": "SiliconFlow",
        "model": "Kwai-Kolors/Kolors",
        "request_mode": "REAL",
        "account_preflight_requests": 0,
        "image_generation_requests": 0,
        "image_downloads": 0,
        "max_requests": 1,
        "max_images": MAX_IMAGES,
        "budget_cap_cny": str(MAX_APPROVED_CNY),
        "prompt": PROMPT,
        "requested_size": request.image_size,
        "steps": request.steps,
        "guidance_scale": request.guidance_scale,
        "seed": request.seed,
        "trace_id": trace_id,
        "generic_binary_mime_fallback_enabled": allow_generic_binary_mime,
        "checks": {},
    }
    request_record = {
        "request_mode": "REAL",
        "endpoint": "https://api.siliconflow.cn/v1/images/generations",
        "method": "POST",
        "request_sent": False,
        "headers": {
            "Authorization": "[REDACTED]",
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
        },
        "body": {
            "model": "Kwai-Kolors/Kolors",
            "prompt": PROMPT,
            "negative_prompt": request.negative_prompt,
            "image_size": request.image_size,
            "num_inference_steps": request.steps,
            "guidance_scale": request.guidance_scale,
            "seed": request.seed,
        },
        "credential_source": "NOT_CONFIGURED",
        "generic_binary_mime_fallback_enabled": allow_generic_binary_mime,
    }
    _write_json(request_path, request_record)
    _write_json(response_path, {"status": "NOT_CALLED"})
    _write_text(error_path, "")

    exit_code = 2
    image_attempt_started = False
    image_started: float | None = None
    try:
        timeout = httpx.Timeout(120, connect=10)
        with httpx.Client(
            timeout=timeout, trust_env=False, follow_redirects=False
        ) as client:
            price = check_official_free_price(client)
            record["checks"]["official_free_price"] = "PASS"
            record["official_price"] = price
            if Decimal(str(price["price_cny_per_image"])) > MAX_APPROVED_CNY:
                raise ProviderError("BUDGET_CAP_EXCEEDED")

            api_key, credential_source = _load_api_key()
            if not api_key:
                raise ProviderError("SILICONFLOW_API_KEY_NOT_SET")
            request_record["credential_source"] = credential_source
            _write_json(request_path, request_record)
            record["checks"]["independent_api_key_present"] = "PASS"

            access = check_model_access(client, api_key)
            record["account_preflight_requests"] = 1
            record["checks"]["account_model_access"] = "PASS"
            record["account_access"] = access

            _reserve_single_attempt(ledger_path)
            record["checks"]["single_attempt_budget_ledger"] = "PASS"
            provider = KolorsProvider(
                api_key,
                client,
                allow_generic_binary_mime=allow_generic_binary_mime,
            )
            image_started = time.monotonic()
            image_attempt_started = True
            request_record["request_attempted"] = True
            record["image_generation_requests"] = 1
            _write_json(request_path, request_record)
            _update_attempt(
                ledger_path,
                "IMAGE_REQUEST_ATTEMPTED_UNCONFIRMED",
                image_generation_requests=1,
            )
            image = provider.generate(request, trace_id)
            image_ms = round((time.monotonic() - image_started) * 1000, 2)
            request_record["request_sent"] = True
            request_record["response_received"] = True
            request_record["download_completed"] = True
            _write_json(request_path, request_record)
            record["image_downloads"] = 1
            record["image_duration_ms"] = image_ms

            extension = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/webp": ".webp",
            }[image.content_type]
            image_path = output_dir / ("kolors-b0-real" + extension)
            image_path.write_bytes(image.data)
            saved_hash = sha256(image_path.read_bytes()).hexdigest()
            if saved_hash != image.sha256:
                raise ProviderError("SAVED_IMAGE_HASH_MISMATCH")

            response_record = {
                "status": "RECEIVED_AND_DOWNLOADED",
                "http_status": 200,
                "provider_trace_id": image.trace_id,
                "images_count": 1,
                "image_url_host": image.image_host,
                "image_url_path": "[REDACTED]",
                "declared_content_type": image.declared_content_type,
                "mime_policy": image.mime_policy,
                "generic_binary_fallback_used": (
                    image.mime_policy == "TRUSTED_GENERIC_BINARY_FALLBACK"
                ),
                "timings": image.timings,
                "seed": image.seed,
            }
            _write_json(response_path, response_record)
            record.update(
                status="REAL",
                classification="REAL",
                checks={
                    **record["checks"],
                    "single_image_response": "PASS",
                    "https_public_download": "PASS",
                    "full_decode": "PASS",
                    "dimensions_960x1280": "PASS",
                    "format_and_mime": "PASS",
                    "generic_binary_mime_fallback": (
                        "PASS"
                        if image.mime_policy == "TRUSTED_GENERIC_BINARY_FALLBACK"
                        else "NOT_USED"
                    ),
                    "sha256_saved_file": "PASS",
                    "not_blank_technical_proxy": "PASS",
                    "manual_semantic_quality": "NOT TESTED",
                },
                image={
                    "path": str(image_path),
                    "content_type": image.content_type,
                    "declared_content_type": image.declared_content_type,
                    "mime_policy": image.mime_policy,
                    "format": image.image_format,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "bytes": len(image.data),
                    "sha256": image.sha256,
                    "pixel_variance": image.pixel_variance,
                    "exif_entries": image.exif_entries,
                },
            )
            _update_attempt(
                ledger_path,
                "REAL_IMAGE_VERIFIED",
                image_generation_requests=1,
                sha256=image.sha256,
            )
            exit_code = 0
    except ProviderError as exc:
        classification = "BLOCKED" if exc.code in BLOCKED_CODES else "FAIL"
        record["status"] = classification
        record["classification"] = classification
        record["error_code"] = exc.code
        if image_started is not None:
            record["image_duration_ms"] = round(
                (time.monotonic() - image_started) * 1000, 2
            )
        if exc.status_code is not None:
            record["error_http_status"] = exc.status_code
        if exc.trace_id:
            record["provider_trace_id"] = exc.trace_id
        if exc.detail:
            record["provider_error_excerpt"] = exc.detail
        if exc.code not in record["checks"]:
            record["checks"][exc.code] = classification
        if request_record.get("request_attempted"):
            response_record = _apply_failure_diagnostics(
                record, request_record, exc
            )
            quarantine = _save_rejected_image(output_dir, exc)
            if quarantine:
                record["rejected_image"] = quarantine
                response_record["rejected_image"] = quarantine
            _write_json(request_path, request_record)
            _write_json(response_path, response_record)
            if ledger_path.exists():
                _update_attempt(
                    ledger_path,
                    "IMAGE_REQUEST_REJECTED_OR_FAILED",
                    error_code=exc.code,
                    image_generation_requests=1,
                )
        with error_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "at": _now(),
                        "classification": classification,
                        "code": exc.code,
                        "failure_stage": record.get("failure_stage"),
                        "http_status": exc.status_code,
                        "request_sent": request_record.get("request_sent"),
                        "response_received": request_record.get("response_received"),
                        "download_completed": request_record.get("download_completed"),
                        "diagnostics": record.get("failure_diagnostics"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        exit_code = 2 if classification == "BLOCKED" else 1
    except Exception as exc:
        record["status"] = "FAIL"
        record["classification"] = "FAIL"
        record["failure_code"] = type(exc).__name__
        record["failure_stage"] = "unexpected"
        record["image_generation_requests"] = 1 if image_attempt_started else 0
        if image_started is not None:
            record["image_duration_ms"] = round(
                (time.monotonic() - image_started) * 1000, 2
            )
        with error_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "at": _now(),
                        "classification": "FAIL",
                        "code": type(exc).__name__,
                        "message": redact_response_text(str(exc)),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        exit_code = 1
    finally:
        record["ended_at"] = _now()
        record["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        _write_json(verification_path, record)
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "error_code": record.get("error_code"),
                    "image_generation_requests": record["image_generation_requests"],
                    "output_dir": str(output_dir),
                },
                ensure_ascii=False,
            )
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT))


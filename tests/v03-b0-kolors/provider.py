"""Minimal Kolors provider contract for B0 without coupling to business code."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import unescape
from io import BytesIO
import ipaddress
import re
import socket
import statistics
from typing import Protocol
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError


MODEL = "Kwai-Kolors/Kolors"
API_ENDPOINT = "https://api.siliconflow.cn/v1/images/generations"
MODELS_ENDPOINT = "https://api.siliconflow.cn/v1/models"
PRICING_URL = "https://www.siliconflow.cn/pricing"
MAX_IMAGE_BYTES = 20_000_000
MAX_PIXELS = 20_000_000
ALLOWED_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
TRUSTED_GENERIC_BINARY_HOST_SUFFIXES = ("siliconflow.cn",)


class ProviderError(Exception):
    """Stable, non-secret provider failure."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        trace_id: str | None = None,
        detail: str | None = None,
        stage: str = "unknown",
        diagnostics: dict | None = None,
        raw_image: bytes | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.trace_id = trace_id
        self.detail = detail
        self.stage = stage
        self.diagnostics = diagnostics or {}
        self.raw_image = raw_image


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    width: int = 960
    height: int = 1280
    steps: int = 20
    guidance_scale: float = 7.5
    seed: int | None = 20261104
    negative_prompt: str = (
        "文字，水印，品牌标志，畸形手部，多余手指，真实人物身份，低清晰度，"
        "重复主体，过度锐化"
    )

    @property
    def image_size(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    content_type: str
    declared_content_type: str
    mime_policy: str
    image_format: str
    width: int
    height: int
    mode: str
    sha256: str
    pixel_variance: float
    exif_entries: int
    seed: int | None
    timings: dict
    trace_id: str | None
    image_host: str


class ImageProvider(Protocol):
    def generate(self, request: GenerationRequest) -> GeneratedImage:
        """Generate and fully validate exactly one image."""


def _single_line(value: str, limit: int = 500) -> str:
    text = " ".join(value.split())
    return text[:limit]


def redact_response_text(value: str, limit: int = 1000) -> str:
    """Remove credentials, signed URLs and accidental key-shaped strings."""
    text = _single_line(value, limit)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b", "sk-[REDACTED]", text)
    text = re.sub(r"https://([^/\s?]+)[^\s]*\?[^\s]*", r"https://\1/<redacted>", text)
    return text


def _public_https_target(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderError("IMAGE_URL_NOT_HTTPS")
    if parsed.username or parsed.password:
        raise ProviderError("IMAGE_URL_HAS_USERINFO")
    port = parsed.port or 443
    if port != 443:
        raise ProviderError("IMAGE_URL_NONSTANDARD_PORT")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ProviderError("IMAGE_HOST_RESOLUTION_FAILED") from exc
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise ProviderError("IMAGE_HOST_NOT_PUBLIC")
    return parsed.hostname


def _normalize_content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _magic_image_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _is_trusted_generic_binary_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith("." + suffix)
        for suffix in TRUSTED_GENERIC_BINARY_HOST_SUFFIXES
    )


def _validate_image(
    data: bytes,
    content_type: str,
    request: GenerationRequest,
    *,
    seed: int | None,
    timings: dict,
    trace_id: str | None,
    image_host: str,
    diagnostics: dict | None = None,
    allow_generic_binary_mime: bool = False,
) -> GeneratedImage:
    magic_format = _magic_image_format(data)
    evidence = {
        **(diagnostics or {}),
        "stage": "image_validation",
        "request_sent": True,
        "response_received": True,
        "download_completed": True,
        "image_bytes": len(data),
        "magic_hex": data[:16].hex(),
        "file_sha256": sha256(data).hexdigest(),
        "magic_format": magic_format,
        "allow_generic_binary_mime": allow_generic_binary_mime,
    }
    if not data:
        raise ProviderError("EMPTY_IMAGE", stage="image_decode", diagnostics=evidence)
    if len(data) > MAX_IMAGE_BYTES:
        raise ProviderError(
            "IMAGE_TOO_LARGE", stage="image_download", diagnostics=evidence
        )
    if magic_format is None:
        raise ProviderError(
            "IMAGE_MAGIC_UNRECOGNIZED",
            stage="image_magic_validation",
            diagnostics=evidence,
        )
    try:
        with Image.open(BytesIO(data)) as probe:
            image_format = probe.format or ""
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise ProviderError(
                    "IMAGE_PIXEL_LIMIT",
                    stage="image_decode",
                    diagnostics={
                        **evidence,
                        "pillow_format": image_format,
                        "dimensions": [width, height],
                    },
                )
            probe.verify()
        with Image.open(BytesIO(data)) as decoded:
            decoded.load()
            width, height = decoded.size
            image_format = decoded.format or ""
            mode = decoded.mode
            exif_entries = len(decoded.getexif())
            gray = decoded.convert("L").resize((64, 64))
            pixel_variance = float(statistics.pvariance(gray.getdata()))
    except ProviderError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProviderError(
            "IMAGE_DECODE_FAILED", stage="image_decode", diagnostics=evidence
        ) from exc

    expected_mime = ALLOWED_FORMATS.get(image_format)
    evidence.update(
        {
            "pillow_format": image_format,
            "detected_mime": expected_mime,
            "declared_content_type": content_type[:120],
            "declared_mime_normalized": _normalize_content_type(content_type),
            "dimensions": [width, height],
            "magic_format": magic_format,
        }
    )
    if expected_mime is None:
        raise ProviderError(
            "UNSUPPORTED_IMAGE_FORMAT",
            stage="image_format_validation",
            diagnostics=evidence,
        )
    if image_format != magic_format:
        raise ProviderError(
            "IMAGE_MAGIC_FORMAT_MISMATCH",
            stage="image_magic_validation",
            diagnostics=evidence,
        )
    actual_mime = _normalize_content_type(content_type)
    trusted_generic_host = _is_trusted_generic_binary_host(image_host)
    evidence.update(
        {
            "image_url_host": image_host,
            "trusted_generic_binary_host": trusted_generic_host,
        }
    )
    if actual_mime == expected_mime:
        mime_policy = "STRICT_MATCH"
    elif actual_mime == "application/octet-stream" and allow_generic_binary_mime:
        if not trusted_generic_host:
            raise ProviderError(
                "UNTRUSTED_GENERIC_IMAGE_HOST",
                stage="image_mime_validation",
                diagnostics=evidence,
            )
        mime_policy = "TRUSTED_GENERIC_BINARY_FALLBACK"
    else:
        raise ProviderError(
            "IMAGE_MIME_FORMAT_MISMATCH",
            stage="image_mime_validation",
            diagnostics=evidence,
        )
    if (width, height) != (request.width, request.height):
        raise ProviderError(
            "IMAGE_DIMENSION_MISMATCH",
            stage="image_dimension_validation",
            diagnostics=evidence,
        )
    if pixel_variance < 1.0:
        raise ProviderError(
            "IMAGE_APPEARS_BLANK",
            stage="image_quality_validation",
            diagnostics=evidence,
        )

    return GeneratedImage(
        data=data,
        content_type=expected_mime,
        declared_content_type=content_type,
        mime_policy=mime_policy,
        image_format=image_format,
        width=width,
        height=height,
        mode=mode,
        sha256=sha256(data).hexdigest(),
        pixel_variance=round(pixel_variance, 4),
        exif_entries=exif_entries,
        seed=seed,
        timings=timings,
        trace_id=trace_id,
        image_host=image_host,
    )


class KolorsProvider:
    """One-shot Kolors implementation; callers own consent and persistence."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client,
        *,
        allow_generic_binary_mime: bool = False,
    ):
        if not api_key.strip():
            raise ValueError("API_KEY_REQUIRED")
        self._api_key = api_key
        self._client = client
        self._allow_generic_binary_mime = allow_generic_binary_mime

    def generate(self, request: GenerationRequest, trace_id: str) -> GeneratedImage:
        diagnostics = {
            "stage": "image_request",
            "request_sent": False,
            "response_received": False,
            "download_completed": False,
        }
        payload = {
            "model": MODEL,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "image_size": request.image_size,
            "num_inference_steps": request.steps,
            "guidance_scale": request.guidance_scale,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
        }
        try:
            response = self._client.post(API_ENDPOINT, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "IMAGE_REQUEST_TIMEOUT_UNKNOWN",
                stage="image_request",
                diagnostics={
                    **diagnostics,
                    "request_sent": None,
                    "detail": "timeout_before_confirmed_response",
                },
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "IMAGE_REQUEST_NETWORK_FAILED",
                stage="image_request",
                diagnostics={
                    **diagnostics,
                    "request_sent": None,
                    "detail": type(exc).__name__,
                },
            ) from exc
        provider_trace = (
            response.headers.get("x-siliconcloud-trace-id")
            or response.headers.get("x-trace-id")
        )
        diagnostics.update(
            {
                "stage": "provider_response",
                "request_sent": True,
                "response_received": True,
                "api_http_status": response.status_code,
                "provider_trace_id": provider_trace,
            }
        )
        if response.status_code != 200:
            raise ProviderError(
                "IMAGE_HTTP_ERROR",
                status_code=response.status_code,
                trace_id=provider_trace,
                detail=redact_response_text(response.text),
                stage="provider_response",
                diagnostics=diagnostics,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                "INVALID_IMAGE_RESULT",
                trace_id=provider_trace,
                detail=redact_response_text(response.text),
                stage="provider_response",
                diagnostics=diagnostics,
            ) from exc
        try:
            images = body["images"]
            if not isinstance(images, list) or len(images) != 1:
                raise ProviderError(
                    "INVALID_IMAGE_COUNT",
                    trace_id=provider_trace,
                    stage="provider_response",
                    diagnostics={**diagnostics, "images_count": len(images) if isinstance(images, list) else None},
                )
            diagnostics.update(
                {
                    "images_count": len(images),
                    "provider_seed": body.get("seed"),
                    "provider_timings": body.get("timings"),
                }
            )
            image_url = images[0]["url"]
            if not isinstance(image_url, str) or not image_url:
                raise ProviderError(
                    "INVALID_IMAGE_RESULT",
                    trace_id=provider_trace,
                    detail=redact_response_text(response.text),
                    stage="provider_response",
                    diagnostics=diagnostics,
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(
                "INVALID_IMAGE_RESULT",
                trace_id=provider_trace,
                detail=redact_response_text(response.text),
                stage="provider_response",
                diagnostics=diagnostics,
            ) from exc

        try:
            image_host = _public_https_target(image_url)
        except ProviderError as exc:
            exc.stage = "image_url_validation"
            exc.diagnostics = {**diagnostics, **exc.diagnostics}
            raise
        diagnostics.update(
            {
                "stage": "image_download",
                "image_url_host": image_host,
                "download_started": True,
            }
        )
        declared_content_type = ""
        download_status = None
        try:
            with self._client.stream("GET", image_url, follow_redirects=False) as download:
                download_status = download.status_code
                declared_content_type = download.headers.get("Content-Type", "")
                diagnostics.update(
                    {
                        "download_http_status": download_status,
                        "declared_content_type": declared_content_type[:120],
                    }
                )
                if 300 <= download.status_code < 400:
                    raise ProviderError(
                        "IMAGE_DOWNLOAD_REDIRECT",
                        stage="image_download",
                        diagnostics=diagnostics,
                    )
                if download.status_code != 200:
                    raise ProviderError(
                        "IMAGE_DOWNLOAD_HTTP_ERROR",
                        status_code=download.status_code,
                        stage="image_download",
                        diagnostics=diagnostics,
                    )
                content_length = download.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_IMAGE_BYTES:
                    raise ProviderError(
                        "IMAGE_TOO_LARGE",
                        stage="image_download",
                        diagnostics={**diagnostics, "content_length": content_length},
                    )
                parts: list[bytes] = []
                total = 0
                for chunk in download.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise ProviderError(
                            "IMAGE_TOO_LARGE",
                            stage="image_download",
                            diagnostics={**diagnostics, "image_bytes": total},
                        )
                    parts.append(chunk)
        except ProviderError as exc:
            exc.diagnostics = {**diagnostics, **exc.diagnostics}
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(
                "IMAGE_DOWNLOAD_FAILED",
                stage="image_download",
                diagnostics={**diagnostics, "detail": type(exc).__name__},
            ) from exc

        diagnostics.update(
            {
                "stage": "image_validation",
                "download_completed": True,
                "image_bytes": total,
            }
        )
        image_bytes = b"".join(parts)
        try:
            return _validate_image(
                image_bytes,
                declared_content_type,
                request,
                seed=body.get("seed", request.seed),
                timings=body.get("timings", {}),
                trace_id=provider_trace or trace_id,
                image_host=image_host,
                diagnostics=diagnostics,
                allow_generic_binary_mime=self._allow_generic_binary_mime,
            )
        except ProviderError as exc:
            exc.raw_image = image_bytes
            raise


def check_official_free_price(client: httpx.Client) -> dict:
    response = client.get(PRICING_URL)
    if response.status_code != 200:
        raise ProviderError("OFFICIAL_PRICE_FETCH_FAILED", status_code=response.status_code)
    html = response.text
    visible = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    visible = unescape(re.sub(r"(?s)<[^>]+>", " ", visible))
    visible = " ".join(visible.split())
    expected = f"{MODEL} 生成图片 每图片 免费"
    if expected not in visible:
        raise ProviderError("OFFICIAL_FREE_PRICE_NOT_CONFIRMED")
    return {
        "url": PRICING_URL,
        "status_code": response.status_code,
        "page_sha256": sha256(response.content).hexdigest(),
        "model": MODEL,
        "price_cny_per_image": 0,
        "evidence": expected,
    }


def check_model_access(client: httpx.Client, api_key: str) -> dict:
    try:
        response = client.get(
            MODELS_ENDPOINT,
            headers={"Authorization": "Bearer " + api_key},
        )
    except httpx.TimeoutException as exc:
        raise ProviderError("MODEL_ACCESS_CHECK_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise ProviderError("MODEL_ACCESS_CHECK_NETWORK_FAILED") from exc
    if response.status_code in (401, 403):
        raise ProviderError(
            "ACCOUNT_PERMISSION_DENIED", status_code=response.status_code
        )
    if response.status_code != 200:
        raise ProviderError(
            "MODEL_ACCESS_CHECK_HTTP_ERROR", status_code=response.status_code
        )
    try:
        payload = response.json()
        items = payload["data"]
        ids = {item["id"] for item in items}
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("MODEL_ACCESS_RESPONSE_INVALID") from exc
    if MODEL not in ids:
        raise ProviderError("MODEL_NOT_AVAILABLE_TO_ACCOUNT")
    return {
        "status_code": response.status_code,
        "model": MODEL,
        "model_visible_to_account": True,
        "trace_id": (
            response.headers.get("x-siliconcloud-trace-id")
            or response.headers.get("x-trace-id")
        ),
    }


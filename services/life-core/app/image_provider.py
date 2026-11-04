"""Validated image-provider boundary shared by Moments and local media storage."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import ipaddress
import socket
import statistics
from typing import Protocol
from urllib.parse import urlparse
import warnings

import httpx
from PIL import Image, UnidentifiedImageError


KOLORS_MODEL = "Kwai-Kolors/Kolors"
KOLORS_ENDPOINT = "https://api.siliconflow.cn/v1/images/generations"
MAX_IMAGE_BYTES = 20_000_000
MAX_IMAGE_PIXELS = 20_000_000
MIN_IMAGE_SIDE = 64
ALLOWED_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
TRUSTED_GENERIC_BINARY_SUFFIXES = ("siliconflow.cn",)


class ImageProviderError(ValueError):
    """A stable failure code with redacted stage diagnostics."""

    def __init__(
        self,
        code: str,
        *,
        stage: str,
        diagnostics: dict | None = None,
        status_code: int | None = None,
        trace_id: str | None = None,
        raw_image: bytes | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.diagnostics = diagnostics or {}
        self.status_code = status_code
        self.trace_id = trace_id
        self.raw_image = raw_image


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    width: int = 960
    height: int = 1280
    negative_prompt: str = (
        "文字，水印，品牌标志，畸形手部，多余手指，真实人物身份，低清晰度，"
        "重复主体，过度锐化"
    )
    steps: int = 20
    guidance_scale: float = 7.5
    seed: int | None = 20261104


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime: str
    image_format: str
    width: int
    height: int
    sha256: str
    declared_mime: str
    mime_policy: str
    trace_id: str | None
    provider_metadata: dict = field(default_factory=dict)


class ImageProvider(Protocol):
    def generate(
        self, request: ImageGenerationRequest, trace_id: str
    ) -> GeneratedImage:
        """Generate exactly one validated image."""


def normalize_mime(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def magic_image_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def trusted_generic_binary_host(host: str | None) -> bool:
    normalized = (host or "").lower().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith("." + suffix)
        for suffix in TRUSTED_GENERIC_BINARY_SUFFIXES
    )


def validate_image_bytes(
    data: bytes,
    declared_mime: str | None,
    *,
    expected_dimensions: tuple[int, int] | None = None,
    allow_generic_binary_mime: bool = False,
    image_host: str | None = None,
) -> GeneratedImage:
    """Strictly pair magic bytes, Pillow format and declared MIME."""
    digest = sha256(data).hexdigest()
    magic = magic_image_format(data)
    diagnostics = {
        "stage": "image_validation",
        "image_bytes": len(data),
        "magic_format": magic,
        "file_sha256": digest,
        "declared_mime": normalize_mime(declared_mime),
    }
    if not data:
        raise ImageProviderError(
            "EMPTY_IMAGE", stage="image_decode", diagnostics=diagnostics
        )
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageProviderError(
            "IMAGE_TOO_LARGE", stage="image_size_validation", diagnostics=diagnostics
        )
    if magic is None:
        raise ImageProviderError(
            "IMAGE_MAGIC_UNRECOGNIZED",
            stage="image_magic_validation",
            diagnostics=diagnostics,
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                image_format = probe.format or ""
                width, height = probe.size
                diagnostics.update(
                    pillow_format=image_format, dimensions=[width, height]
                )
                if width * height > MAX_IMAGE_PIXELS:
                    raise ImageProviderError(
                        "IMAGE_PIXEL_LIMIT",
                        stage="image_dimension_validation",
                        diagnostics=diagnostics,
                    )
                if min(width, height) < MIN_IMAGE_SIDE:
                    raise ImageProviderError(
                        "IMAGE_TOO_SMALL",
                        stage="image_dimension_validation",
                        diagnostics=diagnostics,
                    )
                probe.verify()
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()
                width, height = decoded.size
                image_format = decoded.format or ""
                mode = decoded.mode
                exif_entries = len(decoded.getexif())
                gray = decoded.convert("L").resize((64, 64))
                variance = float(statistics.pvariance(gray.getdata()))
    except ImageProviderError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageProviderError(
            "IMAGE_DECODE_FAILED", stage="image_decode", diagnostics=diagnostics
        ) from exc

    actual_mime = ALLOWED_FORMATS.get(image_format)
    diagnostics.update(
        detected_mime=actual_mime, mode=mode, exif_entries=exif_entries
    )
    if actual_mime is None:
        raise ImageProviderError(
            "UNSUPPORTED_IMAGE_FORMAT",
            stage="image_format_validation",
            diagnostics=diagnostics,
        )
    if image_format != magic:
        raise ImageProviderError(
            "IMAGE_MAGIC_FORMAT_MISMATCH",
            stage="image_magic_validation",
            diagnostics=diagnostics,
        )
    normalized = normalize_mime(declared_mime)
    if normalized == actual_mime:
        mime_policy = "STRICT_MATCH"
    elif (
        normalized == "application/octet-stream"
        and allow_generic_binary_mime
        and trusted_generic_binary_host(image_host)
    ):
        mime_policy = "TRUSTED_GENERIC_BINARY_FALLBACK"
    else:
        raise ImageProviderError(
            "IMAGE_MIME_FORMAT_MISMATCH",
            stage="image_mime_validation",
            diagnostics={
                **diagnostics,
                "image_host": image_host,
            },
        )
    if expected_dimensions is not None and (width, height) != expected_dimensions:
        raise ImageProviderError(
            "IMAGE_DIMENSION_MISMATCH",
            stage="image_dimension_validation",
            diagnostics=diagnostics,
        )
    if variance < 1.0:
        raise ImageProviderError(
            "IMAGE_APPEARS_BLANK",
            stage="image_quality_validation",
            diagnostics=diagnostics,
        )
    return GeneratedImage(
        data=data,
        mime=actual_mime,
        image_format=image_format,
        width=width,
        height=height,
        sha256=digest,
        declared_mime=declared_mime or "",
        mime_policy=mime_policy,
        trace_id=None,
        provider_metadata={
            "mode": mode,
            "exif_entries": exif_entries,
            "pixel_variance": round(variance, 4),
        },
    )


def _public_https_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ImageProviderError("IMAGE_URL_NOT_HTTPS", stage="image_url_validation")
    if parsed.username or parsed.password:
        raise ImageProviderError("IMAGE_URL_HAS_USERINFO", stage="image_url_validation")
    if (parsed.port or 443) != 443:
        raise ImageProviderError(
            "IMAGE_URL_NONSTANDARD_PORT", stage="image_url_validation"
        )
    try:
        addresses = {
            entry[4][0]
            for entry in socket.getaddrinfo(
                parsed.hostname, 443, type=socket.SOCK_STREAM
            )
        }
    except OSError as exc:
        raise ImageProviderError(
            "IMAGE_HOST_RESOLUTION_FAILED", stage="image_url_validation"
        ) from exc
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ImageProviderError(
            "IMAGE_HOST_NOT_PUBLIC", stage="image_url_validation"
        )
    return parsed.hostname


class KolorsImageProvider:
    """One-shot Kolors adapter; callers still own consent and persistence."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        allow_generic_binary_mime: bool = False,
    ):
        if not api_key.strip():
            raise ValueError("IMAGE_PROVIDER_KEY_REQUIRED")
        self._api_key = api_key
        self._client = client
        self._allow_generic_binary_mime = allow_generic_binary_mime

    def generate(
        self, request: ImageGenerationRequest, trace_id: str
    ) -> GeneratedImage:
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(90, connect=8),
            trust_env=False,
            follow_redirects=False,
        )
        owns_client = self._client is None
        try:
            return self._generate(client, request, trace_id)
        finally:
            if owns_client:
                client.close()

    def _generate(
        self, client: httpx.Client, request: ImageGenerationRequest, trace_id: str
    ) -> GeneratedImage:
        payload = {
            "model": KOLORS_MODEL,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "image_size": f"{request.width}x{request.height}",
            "num_inference_steps": request.steps,
            "guidance_scale": request.guidance_scale,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        try:
            response = client.post(
                KOLORS_ENDPOINT,
                headers={
                    "Authorization": "Bearer " + self._api_key,
                    "Content-Type": "application/json",
                    "X-Trace-Id": trace_id,
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "IMAGE_REQUEST_TIMEOUT_UNKNOWN",
                stage="provider_request",
                diagnostics={"request_sent": None},
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                "IMAGE_REQUEST_NETWORK_FAILED",
                stage="provider_request",
                diagnostics={"request_sent": None, "detail": type(exc).__name__},
            ) from exc
        provider_trace = (
            response.headers.get("x-siliconcloud-trace-id")
            or response.headers.get("x-trace-id")
        )
        diagnostics = {
            "stage": "provider_response",
            "request_sent": True,
            "response_received": True,
            "api_http_status": response.status_code,
            "provider_trace_id": provider_trace,
        }
        if response.status_code != 200:
            raise ImageProviderError(
                "IMAGE_HTTP_ERROR",
                stage="provider_response",
                status_code=response.status_code,
                trace_id=provider_trace,
                diagnostics=diagnostics,
            )
        try:
            body = response.json()
            images = body["images"]
            if not isinstance(images, list) or len(images) != 1:
                raise ValueError("INVALID_IMAGE_COUNT")
            image_url = images[0]["url"]
            if not isinstance(image_url, str) or not image_url:
                raise ValueError("INVALID_IMAGE_URL")
        except (KeyError, TypeError, ValueError) as exc:
            raise ImageProviderError(
                "INVALID_IMAGE_RESULT",
                stage="provider_response",
                trace_id=provider_trace,
                diagnostics={
                    **diagnostics,
                    "response_sha256": sha256(response.content).hexdigest(),
                },
            ) from exc

        image_host = _public_https_host(image_url)
        try:
            with client.stream(
                "GET", image_url, follow_redirects=False
            ) as downloaded:
                declared_mime = downloaded.headers.get("Content-Type", "")
                if 300 <= downloaded.status_code < 400:
                    raise ImageProviderError(
                        "IMAGE_DOWNLOAD_REDIRECT", stage="image_download"
                    )
                if downloaded.status_code != 200:
                    raise ImageProviderError(
                        "IMAGE_DOWNLOAD_HTTP_ERROR",
                        stage="image_download",
                        status_code=downloaded.status_code,
                    )
                content_length = downloaded.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_IMAGE_BYTES:
                    raise ImageProviderError(
                        "IMAGE_TOO_LARGE", stage="image_download"
                    )
                parts: list[bytes] = []
                total = 0
                for chunk in downloaded.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise ImageProviderError(
                            "IMAGE_TOO_LARGE", stage="image_download"
                        )
                    parts.append(chunk)
        except ImageProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ImageProviderError(
                "IMAGE_DOWNLOAD_FAILED",
                stage="image_download",
                diagnostics={"detail": type(exc).__name__},
            ) from exc

        image_bytes = b"".join(parts)
        try:
            validated = validate_image_bytes(
                image_bytes,
                declared_mime,
                expected_dimensions=(request.width, request.height),
                allow_generic_binary_mime=self._allow_generic_binary_mime,
                image_host=image_host,
            )
        except ImageProviderError as exc:
            exc.raw_image = image_bytes
            raise
        return GeneratedImage(
            **{
                **validated.__dict__,
                "trace_id": provider_trace or trace_id,
                "provider_metadata": {
                    **validated.provider_metadata,
                    "api_http_status": response.status_code,
                    "provider_seed": body.get("seed"),
                    "provider_timings": body.get("timings", {}),
                    "image_host": image_host,
                },
            }
        )

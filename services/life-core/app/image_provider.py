"""Minimal Kolors adapter for the fixed admin direct-image test flow."""
from __future__ import annotations

import hashlib
import io
import ipaddress
import socket
import statistics
from dataclasses import dataclass
from urllib.parse import urlparse
import warnings

import httpx
from PIL import Image, UnidentifiedImageError


KOLORS_MODEL = "Kwai-Kolors/Kolors"
KOLORS_ENDPOINT = "https://api.siliconflow.cn/v1/images/generations"
MAX_IMAGE_BYTES = 20_000_000
MIN_IMAGE_SIDE = 64
TRUSTED_GENERIC_BINARY_SUFFIXES = ("siliconflow.cn",)


class ImageProviderError(ValueError):
    """Stable, redacted provider failure code."""


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    width: int = 960
    height: int = 1280
    negative_prompt: str = "文字，水印，真实人物身份，低清晰度"


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime: str
    width: int
    height: int
    sha256: str


def normalize_mime(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def magic_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _public_https_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or (parsed.port or 443) != 443:
        raise ImageProviderError("IMAGE_URL_NOT_PUBLIC")
    try:
        addresses = {
            entry[4][0]
            for entry in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ImageProviderError("IMAGE_HOST_RESOLUTION_FAILED") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ImageProviderError("IMAGE_URL_NOT_PUBLIC")
    return parsed.hostname


def validate_image_bytes(data: bytes, declared_mime: str | None, image_host: str):
    if not data or len(data) > MAX_IMAGE_BYTES or magic_mime(data) is None:
        raise ImageProviderError("INVALID_IMAGE_RESULT")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                image_format, dimensions = probe.format, probe.size
                probe.verify()
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            dimensions = decoded.size
            gray = decoded.convert("L").resize((64, 64))
            variance = float(statistics.pvariance(gray.getdata()))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageProviderError("INVALID_IMAGE_RESULT") from exc
    allowed = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
    actual_mime = allowed.get(image_format or "")
    if actual_mime is None:
        raise ImageProviderError("UNSUPPORTED_IMAGE_FORMAT")
    normalized = normalize_mime(declared_mime)
    trusted_generic = normalized == "application/octet-stream" and any(
        image_host == suffix or image_host.endswith("." + suffix)
        for suffix in TRUSTED_GENERIC_BINARY_SUFFIXES
    )
    if normalized != actual_mime and not trusted_generic:
        raise ImageProviderError("IMAGE_MIME_FORMAT_MISMATCH")
    if min(dimensions) < MIN_IMAGE_SIDE or variance < 1.0:
        raise ImageProviderError("INVALID_IMAGE_RESULT")
    return GeneratedImage(
        data=data, mime=actual_mime, width=dimensions[0], height=dimensions[1],
        sha256=hashlib.sha256(data).hexdigest(),
    )


class KolorsImageProvider:
    def __init__(self, api_key: str, *, client: httpx.Client | None = None):
        if not api_key.strip():
            raise ValueError("IMAGE_PROVIDER_KEY_REQUIRED")
        self._api_key = api_key
        self._client = client

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(90, connect=8), trust_env=False, follow_redirects=False
        )
        owns_client = self._client is None
        try:
            payload = {
                "model": KOLORS_MODEL,
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "image_size": f"{request.width}x{request.height}",
                "num_inference_steps": 20,
                "guidance_scale": 7.5,
                "seed": 20261105,
            }
            response = client.post(
                KOLORS_ENDPOINT,
                headers={"Authorization": "Bearer " + self._api_key},
                json=payload,
            )
            if response.status_code != 200:
                raise ImageProviderError(f"IMAGE_HTTP_{response.status_code}")
            try:
                image_url = response.json()["images"][0]["url"]
            except (KeyError, TypeError, IndexError) as exc:
                raise ImageProviderError("INVALID_IMAGE_RESULT") from exc
            image_host = _public_https_host(image_url)
            with client.stream("GET", image_url) as download:
                if download.status_code != 200:
                    raise ImageProviderError(f"IMAGE_HTTP_{download.status_code}")
                declared_mime = download.headers.get("Content-Type", "")
                parts, total = [], 0
                for chunk in download.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise ImageProviderError("IMAGE_TOO_LARGE")
                    parts.append(chunk)
            return validate_image_bytes(b"".join(parts), declared_mime, image_host)
        except httpx.TimeoutException as exc:
            raise ImageProviderError("IMAGE_PROVIDER_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise ImageProviderError("IMAGE_PROVIDER_FAILED") from exc
        finally:
            if owns_client:
                client.close()

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from provider import (
    API_ENDPOINT,
    GenerationRequest,
    KolorsProvider,
    ProviderError,
    check_model_access,
    check_official_free_price,
)
from verify_kolors import (
    _apply_failure_diagnostics,
    _load_api_key,
    _reserve_single_attempt,
    _save_rejected_image,
)


def _encoded_image(image_format: str, width: int = 64, height: int = 64) -> bytes:
    image = Image.new("RGB", (width, height), (30, 90, 160))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = ((x * 3 + y) % 256, (x + y * 2) % 256, (x * y) % 256)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


class ProviderContractTests(unittest.TestCase):
    def _public_dns(self):
        return patch(
            "provider.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        )

    def test_kolors_mock_contract_downloads_and_fully_decodes(self):
        png = _encoded_image("PNG", 960, 1280)

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == API_ENDPOINT:
                self.assertEqual(
                    request.headers["Authorization"], "Bearer synthetic"
                )
                payload = json.loads(request.content)
                self.assertEqual(payload["model"], "Kwai-Kolors/Kolors")
                self.assertEqual(payload["image_size"], "960x1280")
                return httpx.Response(
                    200,
                    headers={"x-siliconcloud-trace-id": "trace-mock-001"},
                    json={
                        "images": [
                            {
                                "url": "https://images.example.com/mock.png?sig=redacted"
                            }
                        ],
                        "timings": {"inference": 0.25},
                        "seed": 20261104,
                    },
                )
            self.assertTrue(
                str(request.url).startswith("https://images.example.com/")
            )
            return httpx.Response(
                200, headers={"Content-Type": "image/png"}, content=png
            )

        with self._public_dns(), httpx.Client(
            transport=httpx.MockTransport(handler)
        ) as client:
            result = KolorsProvider("synthetic", client).generate(
                GenerationRequest(prompt="合成场景", width=960, height=1280),
                "trace-request-001",
            )
        self.assertEqual(result.image_format, "PNG")
        self.assertEqual((result.width, result.height), (960, 1280))
        self.assertEqual(result.trace_id, "trace-mock-001")
        self.assertEqual(len(result.sha256), 64)
        self.assertGreater(result.pixel_variance, 1)

    def test_png_jpeg_webp_require_matching_declared_mime(self):
        cases = [
            ("PNG", "image/png"),
            ("JPEG", "image/jpeg"),
            ("WEBP", "image/webp"),
        ]
        for image_format, declared_mime in cases:
            with self.subTest(image_format=image_format):
                image_bytes = _encoded_image(image_format)

                def handler(
                    request: httpx.Request,
                    *,
                    payload=image_bytes,
                    mime=declared_mime,
                ) -> httpx.Response:
                    if str(request.url) == API_ENDPOINT:
                        return httpx.Response(
                            200,
                            headers={"x-siliconcloud-trace-id": "trace-format"},
                            json={
                                "images": [
                                    {
                                        "url": "https://images.example.com/format-image"
                                    }
                                ]
                            },
                        )
                    return httpx.Response(
                        200,
                        headers={"Content-Type": mime},
                        content=payload,
                    )

                with self._public_dns(), httpx.Client(
                    transport=httpx.MockTransport(handler)
                ) as client:
                    result = KolorsProvider("synthetic", client).generate(
                        GenerationRequest(prompt="合成格式场景", width=64, height=64),
                        "trace-format",
                    )
                self.assertEqual(result.image_format, image_format)
                self.assertEqual(result.content_type, declared_mime)
                self.assertEqual(result.declared_content_type, declared_mime)
                self.assertEqual(result.mime_policy, "STRICT_MATCH")

    def test_png_declared_as_jpeg_is_rejected_with_stage(self):
        png = _encoded_image("PNG")

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == API_ENDPOINT:
                return httpx.Response(
                    200,
                    headers={"x-siliconcloud-trace-id": "trace-mismatch"},
                    json={
                        "images": [
                            {"url": "https://images.example.com/mismatch-image"}
                        ]
                    },
                )
            return httpx.Response(
                200, headers={"Content-Type": "image/jpeg"}, content=png
            )

        with self._public_dns(), httpx.Client(
            transport=httpx.MockTransport(handler)
        ) as client:
            with self.assertRaises(ProviderError) as caught:
                KolorsProvider("synthetic", client).generate(
                    GenerationRequest(prompt="合成错配场景", width=64, height=64),
                    "trace-mismatch",
                )
        self.assertEqual(caught.exception.code, "IMAGE_MIME_FORMAT_MISMATCH")
        self.assertEqual(caught.exception.stage, "image_mime_validation")
        self.assertEqual(caught.exception.diagnostics["pillow_format"], "PNG")
        self.assertEqual(caught.exception.diagnostics["detected_mime"], "image/png")
        self.assertEqual(
            caught.exception.diagnostics["declared_mime_normalized"], "image/jpeg"
        )
        self.assertTrue(caught.exception.diagnostics["download_completed"])
        self.assertEqual(len(caught.exception.diagnostics["file_sha256"]), 64)
        self.assertEqual(caught.exception.raw_image, png)

    def test_missing_or_generic_content_type_is_rejected(self):
        png = _encoded_image("PNG")
        for declared in (None, "application/octet-stream"):
            with self.subTest(declared=declared):

                def handler(
                    request: httpx.Request, *, content_type=declared
                ) -> httpx.Response:
                    if str(request.url) == API_ENDPOINT:
                        return httpx.Response(
                            200,
                            json={
                                "images": [
                                    {"url": "https://images.example.com/no-mime"}
                                ]
                            },
                        )
                    headers = (
                        {} if content_type is None else {"Content-Type": content_type}
                    )
                    return httpx.Response(200, headers=headers, content=png)

                with self._public_dns(), httpx.Client(
                    transport=httpx.MockTransport(handler)
                ) as client:
                    with self.assertRaises(ProviderError) as caught:
                        KolorsProvider("synthetic", client).generate(
                            GenerationRequest(
                                prompt="合成声明缺失场景", width=64, height=64
                            ),
                            "trace-no-mime",
                        )
                self.assertEqual(
                    caught.exception.code, "IMAGE_MIME_FORMAT_MISMATCH"
                )
                self.assertEqual(
                    caught.exception.diagnostics["declared_mime_normalized"],
                    declared or "",
                )
                self.assertEqual(
                    caught.exception.diagnostics["detected_mime"], "image/png"
                )

    def test_trusted_generic_binary_mime_uses_strict_fallback(self):
        png = _encoded_image("PNG")

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == API_ENDPOINT:
                return httpx.Response(
                    200,
                    headers={"x-siliconcloud-trace-id": "trace-generic"},
                    json={
                        "images": [
                            {"url": "https://s3.siliconflow.cn/generic-image"}
                        ]
                    },
                )
            return httpx.Response(
                200,
                headers={"Content-Type": "application/octet-stream"},
                content=png,
            )

        with self._public_dns(), httpx.Client(
            transport=httpx.MockTransport(handler)
        ) as client:
            result = KolorsProvider(
                "synthetic", client, allow_generic_binary_mime=True
            ).generate(
                GenerationRequest(prompt="合成通用二进制场景", width=64, height=64),
                "trace-generic",
            )
        self.assertEqual(result.image_format, "PNG")
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(
            result.declared_content_type, "application/octet-stream"
        )
        self.assertEqual(
            result.mime_policy, "TRUSTED_GENERIC_BINARY_FALLBACK"
        )

    def test_generic_fallback_rejects_untrusted_host_or_corrupt_bytes(self):
        png = _encoded_image("PNG")
        cases = [
            ("https://images.example.com/generic-image", png, "UNTRUSTED_GENERIC_IMAGE_HOST"),
            (
                "https://s3.siliconflow.cn/corrupt",
                b"\x89PNG\r\n\x1a\nbroken",
                "IMAGE_DECODE_FAILED",
            ),
        ]
        for image_url, payload, expected_code in cases:
            with self.subTest(image_url=image_url, expected_code=expected_code):

                def handler(
                    request: httpx.Request,
                    *,
                    url=image_url,
                    content=payload,
                ) -> httpx.Response:
                    if str(request.url) == API_ENDPOINT:
                        return httpx.Response(
                            200,
                            json={"images": [{"url": url}]},
                        )
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/octet-stream"},
                        content=content,
                    )

                with self._public_dns(), httpx.Client(
                    transport=httpx.MockTransport(handler)
                ) as client:
                    with self.assertRaises(ProviderError) as caught:
                        KolorsProvider(
                            "synthetic",
                            client,
                            allow_generic_binary_mime=True,
                        ).generate(
                            GenerationRequest(
                                prompt="合成危险场景", width=64, height=64
                            ),
                            "trace-generic-reject",
                        )
                self.assertEqual(caught.exception.code, expected_code)

    def test_fake_magic_and_truncated_images_are_rejected(self):
        fake = b"\x89PNG\r\n\x1a\nnot-a-real-image"
        valid = _encoded_image("PNG")
        truncated = valid[: max(16, len(valid) // 2)]
        for label, payload in (("fake", fake), ("truncated", truncated)):
            with self.subTest(label=label):

                def handler(
                    request: httpx.Request, *, content=payload
                ) -> httpx.Response:
                    if str(request.url) == API_ENDPOINT:
                        return httpx.Response(
                            200,
                            headers={"x-siliconcloud-trace-id": "trace-corrupt"},
                            json={
                                "images": [
                                    {"url": "https://images.example.com/corrupt"}
                                ]
                            },
                        )
                    return httpx.Response(
                        200, headers={"Content-Type": "image/png"}, content=content
                    )

                with self._public_dns(), httpx.Client(
                    transport=httpx.MockTransport(handler)
                ) as client:
                    with self.assertRaises(ProviderError) as caught:
                        KolorsProvider("synthetic", client).generate(
                            GenerationRequest(
                                prompt="合成损坏场景", width=64, height=64
                            ),
                            "trace-corrupt",
                        )
                self.assertEqual(caught.exception.code, "IMAGE_DECODE_FAILED")
                self.assertEqual(caught.exception.stage, "image_decode")
                self.assertTrue(caught.exception.diagnostics["download_completed"])

    def test_failure_diagnostics_preserve_real_request_stage(self):
        record = {"image_generation_requests": 1, "image_downloads": 0}
        request_record = {"request_attempted": True}
        error = ProviderError(
            "IMAGE_MIME_FORMAT_MISMATCH",
            stage="image_mime_validation",
            diagnostics={
                "stage": "image_validation",
                "request_sent": True,
                "response_received": True,
                "download_completed": True,
                "declared_content_type": "application/octet-stream",
                "pillow_format": "PNG",
                "detected_mime": "image/png",
            },
        )
        response = _apply_failure_diagnostics(record, request_record, error)
        self.assertEqual(record["failure_stage"], "image_mime_validation")
        self.assertEqual(record["image_downloads"], 1)
        self.assertTrue(request_record["request_sent"])
        self.assertTrue(request_record["response_received"])
        self.assertEqual(response["detected_mime"], "image/png")

    def test_rejected_image_bytes_are_quarantined_with_sha256(self):
        payload = _encoded_image("PNG")
        from hashlib import sha256

        error = ProviderError(
            "IMAGE_MIME_FORMAT_MISMATCH",
            stage="image_mime_validation",
            diagnostics={"file_sha256": sha256(payload).hexdigest()},
            raw_image=payload,
        )
        with TemporaryDirectory() as directory:
            result = _save_rejected_image(Path(directory), error)
            saved = Path(result["path"]).read_bytes()
        self.assertEqual(saved, payload)
        self.assertEqual(result["status"], "REJECTED_NOT_ACCEPTED")
        self.assertEqual(result["stage"], "image_mime_validation")

    def test_kolors_rejects_more_than_one_image(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "images": [
                        {"url": "https://images.example.com/one.png"},
                        {"url": "https://images.example.com/two.png"},
                    ]
                },
            )

        with self._public_dns(), httpx.Client(
            transport=httpx.MockTransport(handler)
        ) as client:
            with self.assertRaises(ProviderError) as caught:
                KolorsProvider("synthetic", client).generate(
                    GenerationRequest(prompt="合成场景"), "trace-request-002"
                )
        self.assertEqual(caught.exception.code, "INVALID_IMAGE_COUNT")

    def test_pricing_and_model_access_checks_are_mock_only(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "pricing" in str(request.url):
                return httpx.Response(
                    200,
                    text=(
                        "<table><tr><td>Kwai-Kolors/Kolors</td><td>生成图片</td>"
                        "<td>每图片</td><td>免费</td></tr></table>"
                    ),
                )
            self.assertEqual(
                request.headers["Authorization"], "Bearer synthetic"
            )
            return httpx.Response(
                200, json={"data": [{"id": "Kwai-Kolors/Kolors"}]}
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            self.assertEqual(
                check_official_free_price(client)["price_cny_per_image"], 0
            )
            self.assertTrue(
                check_model_access(client, "synthetic")[
                    "model_visible_to_account"
                ]
            )

    def test_single_attempt_ledger_rejects_second_reservation(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "attempt-ledger.json"
            _reserve_single_attempt(ledger)
            with self.assertRaises(ProviderError) as caught:
                _reserve_single_attempt(ledger)
        self.assertEqual(caught.exception.code, "B0_SINGLE_ATTEMPT_ALREADY_USED")

    def test_api_key_file_loader_never_requires_logging_secret(self):
        with TemporaryDirectory() as directory:
            key_file = Path(directory) / ".env.local"
            key_file.write_text(
                "# local only\nSILICONFLOW_API_KEY=synthetic-file-value\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ, {"SILICONFLOW_API_KEY": ""}, clear=False
            ):
                value, source = _load_api_key(key_file)
        self.assertEqual(value, "synthetic-file-value")
        self.assertEqual(source, "SILICONFLOW_API_KEY_FILE")


if __name__ == "__main__":
    unittest.main()


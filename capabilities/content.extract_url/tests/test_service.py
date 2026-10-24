"""
Unit and integration tests for the HTTP Content Resolver FastAPI service.
Tests /healthz, /readyz (fail-closed semantics), authentication, structured error codes,
and V1 contract response formats.
"""

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient

from src.models import ContentMetadata, ResolveError, UnsupportedURLError
from src.service import app

client = TestClient(app)

VALID_TOKEN = "secret-test-internal-token-12345"


class TestResolverService(unittest.TestCase):
    def test_healthz_unauthenticated(self):
        """Liveness probe: unauthenticated, returns 200 OK."""
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_readyz_fails_closed_when_token_unconfigured(self):
        """Readiness probe: fail closed (503) if TOOLS_INTERNAL_TOKEN is unset."""
        with patch.dict(os.environ, {}, clear=True):
            resp = client.get("/readyz")
            self.assertEqual(resp.status_code, 503)
            data = resp.json()
            self.assertEqual(data["status"], "not_ready")
            self.assertIn("TOOLS_INTERNAL_TOKEN is not configured", data["error"])

    def test_readyz_succeeds_when_token_is_configured(self):
        """Readiness probe: returns 200 Ready when TOOLS_INTERNAL_TOKEN is present."""
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}):
            resp = client.get("/readyz")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"status": "ready"})

    def test_resolve_fails_if_server_auth_unconfigured(self):
        """POST /v1/resolve returns 500 if TOOLS_INTERNAL_TOKEN is not set on server."""
        with patch.dict(os.environ, {}, clear=True):
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"schema_version": 1, "url": "https://www.youtube.com/watch?v=123"},
            )
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "auth_not_configured")

    def test_resolve_rejects_missing_authorization_header(self):
        """POST /v1/resolve returns 401 if Authorization header is missing."""
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}):
            resp = client.post(
                "/v1/resolve",
                json={"schema_version": 1, "url": "https://www.youtube.com/watch?v=123"},
            )
            self.assertEqual(resp.status_code, 401)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "missing_token")

    def test_resolve_rejects_invalid_authorization_token(self):
        """POST /v1/resolve returns 401 if Bearer token does not match."""
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}):
            # Wrong token
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": "Bearer wrong-token-xyz"},
                json={"schema_version": 1, "url": "https://www.youtube.com/watch?v=123"},
            )
            self.assertEqual(resp.status_code, 401)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "invalid_token")

            # Non-Bearer scheme
            resp_basic = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Basic {VALID_TOKEN}"},
                json={"schema_version": 1, "url": "https://www.youtube.com/watch?v=123"},
            )
            self.assertEqual(resp_basic.status_code, 401)
            self.assertEqual(resp_basic.json()["error"]["code"], "invalid_token")

    def test_resolve_rejects_unsupported_schema_version(self):
        """POST /v1/resolve returns 400 for unsupported schema version."""
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}):
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"schema_version": 99, "url": "https://www.youtube.com/watch?v=123"},
            )
            self.assertEqual(resp.status_code, 400)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "unsupported_schema_version")

    def test_resolve_rejects_empty_url(self):
        """POST /v1/resolve returns 400 for empty or whitespace url."""
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}):
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"schema_version": 1, "url": "   "},
            )
            self.assertEqual(resp.status_code, 400)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "invalid_url")

    def test_resolve_returns_400_for_unsupported_url(self):
        """POST /v1/resolve maps UnsupportedURLError to HTTP 400 with code 'unsupported_url'."""
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}):
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"schema_version": 1, "url": "https://dailymotion.com/video/x7xyz"},
            )
            self.assertEqual(resp.status_code, 400)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "unsupported_url")

    def test_resolve_returns_502_for_upstream_resolution_error(self):
        """
        POST /v1/resolve maps ResolveError (upstream platform failure)
        to HTTP 502 Bad Gateway with code 'resolve_failed'.
        """
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}), \
             patch("src.service.resolve_url", side_effect=ResolveError("Upstream preview API timeout")):
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"schema_version": 1, "url": "https://weixin.qq.com/sph/AF17JEGHVd"},
            )
            self.assertEqual(resp.status_code, 502)
            data = resp.json()
            self.assertEqual(data["error"]["code"], "resolve_failed")
            self.assertIn("Upstream preview API timeout", data["error"]["message"])

    def test_resolve_success_returns_v1_contract(self):
        """POST /v1/resolve returns HTTP 200 with ContentMetadataV1 payload."""
        mock_meta = ContentMetadata(
            source_type="weixin",
            source_url="https://weixin.qq.com/sph/AF17JEGHVd",
            canonical_url="https://weixin.qq.com/sph/AF17JEGHVd",
            source_id="AF17JEGHVd",
            title="鹦鹉视频",
            creator="玩娱少女",
            published_at="2026-09-05",
            like_count="9071",
            comment_count="732",
        )
        with patch.dict(os.environ, {"TOOLS_INTERNAL_TOKEN": VALID_TOKEN}), \
             patch("src.service.resolve_url", return_value=mock_meta):
            resp = client.post(
                "/v1/resolve",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={"schema_version": 1, "url": "https://weixin.qq.com/sph/AF17JEGHVd"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["source_type"], "weixin")
            self.assertEqual(data["source_id"], "AF17JEGHVd")
            self.assertEqual(data["title"], "鹦鹉视频")
            self.assertEqual(data["creator"], "玩娱少女")
            self.assertEqual(data["like_count"], "9071")
            self.assertIsNone(data["duration_seconds"])  # Real null

    def test_service_startup_isolation(self):
        """Verify starting FastAPI app in clean process does not import ASR or NumPy modules."""
        check_code = (
            "import sys; "
            "from src.service import app; "
            "heavy_mods = ['sherpa_onnx', 'numpy', 'src.asr', 'src.media', 'src.model_manager']; "
            "loaded = [m for m in heavy_mods if m in sys.modules]; "
            "assert not loaded, f'Heavy modules unexpectedly loaded on service import: {loaded}'; "
            "print('SERVICE_ISOLATION_OK')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", check_code],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"Service startup isolation check failed: {proc.stderr}")
        self.assertIn("SERVICE_ISOLATION_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()

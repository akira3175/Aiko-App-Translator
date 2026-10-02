"""Contract tests for the experimental ChatGPT plan provider."""

import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from providers import chatgpt_plan_client
from services import chatgpt_plan


def _encoded(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class _Stream(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class ChatGptPlanTests(unittest.TestCase):
    def test_fallback_model_comes_from_account_catalog(self):
        with patch.object(chatgpt_plan, "list_models", return_value=[{"slug": "first-model"}, {"slug": "second-model"}]):
            self.assertEqual(chatgpt_plan.default_model(), "first-model")
        with patch.object(chatgpt_plan, "list_models", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "chưa có model"):
                chatgpt_plan.default_model()

    def test_dynamic_registration_uses_pkce_and_issued_client_id(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(chatgpt_plan, "STORE", Path(folder) / "plan.dpapi"), patch.object(chatgpt_plan.threading, "Thread"):
            service = chatgpt_plan.ChatGptPlanService()
            auth_url = service.connect()["url"]
            params = parse_qs(urlparse(auth_url).query)
            self.assertEqual(params["client_id"], ["dynamic_agent_client"])
            self.assertEqual(params["code_challenge_method"], ["S256"])
            self.assertTrue(params["ext_agent_host_id"][0].startswith("urn:uuid:"))
            with patch.object(chatgpt_plan, "_request_json", return_value={
                "id_token": "signed-token", "access_token": "access-secret",
                "refresh_token": "refresh-secret", "scope": chatgpt_plan.SCOPES,
                "expires_in": 3600,
            }) as exchange, patch.object(chatgpt_plan, "_validated_identity", return_value={"sub": "user", "email": "user@example.com"}):
                service._complete({"state": params["state"][0], "code": "authorization-code", "client_id": "oaiapp_test"})
            sent = exchange.call_args.kwargs["data"]
            self.assertEqual(sent["client_id"], "oaiapp_test")
            self.assertEqual(sent["redirect_uri"], params["redirect_uri"][0])
            self.assertEqual(chatgpt_plan._read()["client_id"], "oaiapp_test")
            service.pending["server"].server_close()

    def test_protected_credentials_refresh_without_exposing_tokens(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(chatgpt_plan, "STORE", Path(folder) / "plan.dpapi"):
            chatgpt_plan._write({"host_id": "urn:uuid:test", "client_id": "oaiapp_test",
                                 "subject": "user", "email": "user@example.com",
                                 "access_token": "expired-secret", "refresh_token": "refresh-secret",
                                 "scopes": ["chatgpt.tokens.use.direct"], "expires_at": 0})
            self.assertNotIn(b"expired-secret", chatgpt_plan.STORE.read_bytes())
            with patch.object(chatgpt_plan, "_request_json", return_value={
                "access_token": "new-secret", "refresh_token": "rotated-secret",
                "expires_in": 3600, "scope": "chatgpt.tokens.use.direct offline_access",
            }) as request:
                self.assertEqual(chatgpt_plan.access_token(), "new-secret")
            self.assertEqual(request.call_args.kwargs["data"]["client_id"], "oaiapp_test")
            self.assertEqual(chatgpt_plan._read()["refresh_token"], "rotated-secret")
            status = chatgpt_plan.ChatGptPlanService()
            with patch.object(chatgpt_plan, "list_models", return_value=[]):
                self.assertNotIn("secret", json.dumps(status.status()))

    def test_id_token_requires_valid_signature_and_nonce(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = private.public_key().public_numbers()
        header = _encoded(json.dumps({"alg": "RS256", "kid": "test"}).encode())
        claims = _encoded(json.dumps({"iss": chatgpt_plan.AUTH, "aud": "oaiapp_test",
                                      "sub": "user", "nonce": "expected", "exp": time.time() + 60}).encode())
        signed = f"{header}.{claims}".encode("ascii")
        token = signed.decode() + "." + _encoded(private.sign(signed, padding.PKCS1v15(), hashes.SHA256()))
        key = {"kid": "test", "kty": "RSA", "e": _encoded(public.e.to_bytes(3, "big")),
               "n": _encoded(public.n.to_bytes(256, "big"))}
        def lookup(url, **_kwargs):
            return {"jwks_uri": chatgpt_plan.AUTH + "/jwks"} if url.endswith("openid-configuration") else {"keys": [key]}
        with patch.object(chatgpt_plan, "_request_json", side_effect=lookup):
            self.assertEqual(chatgpt_plan._validated_identity(token, "oaiapp_test", "expected")["sub"], "user")
            with self.assertRaises(RuntimeError):
                chatgpt_plan._validated_identity(token, "oaiapp_test", "wrong")

    def test_stream_requires_completed_and_sends_preview_fields(self):
        stream = b'data: {"type":"response.output_text.delta","delta":"Xin "}\n\n' \
                 b'data: {"type":"response.output_text.delta","delta":"chao"}\n\n' \
                 b'data: {"type":"response.completed"}\n\n'
        with patch.object(chatgpt_plan_client, "access_token", return_value="secret"), patch.object(
            chatgpt_plan_client, "urlopen", return_value=_Stream(stream)
        ) as send:
            self.assertEqual(chatgpt_plan_client.call_chatgpt_plan(
                "prompt", model="gpt-test", reasoning_effort="auto", stage="translate"), "Xin chao")
        payload = json.loads(send.call_args.args[0].data)
        self.assertEqual(payload["input"][0]["content"][0]["text"], "prompt")
        self.assertFalse(payload["store"])
        self.assertTrue(payload["stream"])
        self.assertNotIn("max_output_tokens", payload)
        self.assertNotIn("reasoning", payload)
        with self.assertRaisesRegex(RuntimeError, "trước khi hoàn tất"):
            chatgpt_plan_client._stream_text(_Stream(stream.replace(b'data: {"type":"response.completed"}\n\n', b"")))

    def test_usage_limit_is_explained_without_retrying(self):
        stream = (b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n'
                  b'data: {"type":"response.failed","response":{"error":'
                  b'{"code":"subscription_sharing_usage_limit_exceeded"}}}\n\n')
        with self.assertRaisesRegex(RuntimeError, "model gpt-6-astra đã hết lượt"):
            chatgpt_plan_client._stream_text(_Stream(stream), model="gpt-6-astra")


if __name__ == "__main__":
    unittest.main()

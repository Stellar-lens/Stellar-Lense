import logging
import os
import unittest
from io import StringIO

from cli.diagnostics import run_diagnostics
from utils.logging import SecretsRedactingFormatter
from utils.secrets import SecretString, mask_secret, sanitize_config, sanitize_text, sanitize_url


class TestSecretsSafety(unittest.TestCase):

    def test_secret_string_masking(self):
        s = SecretString("super_secret_password_123")
        self.assertEqual(s.expose(), "super_secret_password_123")
        self.assertEqual(repr(s), "<SecretString [REDACTED]>")
        self.assertNotIn("super_secret_password_123", str(s))
        self.assertTrue(s == "super_secret_password_123")

    def test_mask_secret(self):
        self.assertEqual(mask_secret("123456789"), "*****6789")
        self.assertEqual(mask_secret("123"), "***")
        self.assertEqual(mask_secret(""), "")

    def test_sanitize_url(self):
        db_url = "postgresql://db_user:super_secret_pass@localhost:5432/ledgerlens"
        sanitized = sanitize_url(db_url)
        self.assertNotIn("super_secret_pass", sanitized)
        self.assertIn("db_user:****@localhost:5432/ledgerlens", sanitized)

    def test_sanitize_text_patterns(self):
        text = "Failed connect with api_key=secret_key_abc123 and Bearer eyJhbGciOiJIUzI1NiIn1"
        sanitized = sanitize_text(text)
        self.assertNotIn("secret_key_abc123", sanitized)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIn1", sanitized)

    def test_sanitize_config_dict(self):
        cfg = {
            "HORIZON_URL": "https://horizon.stellar.org",
            "KAFKA_SASL_PASSWORD": "my_kafka_password",
            "RISK_SCORE_DB_URL": "postgres://admin:secret123@localhost/db",
        }
        clean = sanitize_config(cfg)
        self.assertNotIn("my_kafka_password", clean["KAFKA_SASL_PASSWORD"])
        self.assertNotIn("secret123", clean["RISK_SCORE_DB_URL"])
        self.assertEqual(clean["HORIZON_URL"], "https://horizon.stellar.org")

    def test_log_redaction(self):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SecretsRedactingFormatter("%(message)s"))
        logger = logging.getLogger("test_redact")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        logger.info("Connecting to postgresql://user:my_secret_pass@localhost/db")
        log_output = stream.getvalue()
        self.assertNotIn("my_secret_pass", log_output)
        self.assertIn("****@", log_output)

    def test_diagnostics_sanitizes_urls(self):
        os.environ["RISK_SCORE_DB_URL"] = "postgresql://user:dbpass123@localhost:5432/db"
        os.environ["HORIZON_URL"] = "https://horizon.stellar.org"
        os.environ["KAFKA_SASL_PASSWORD"] = "secret_sasl_pass"

        diag = run_diagnostics()
        details = diag["checks"]["environment"]["details"]
        self.assertNotIn("dbpass123", details["RISK_SCORE_DB_URL"])
        self.assertNotIn("secret_sasl_pass", details["KAFKA_SASL_PASSWORD"])


if __name__ == "__main__":
    unittest.main()

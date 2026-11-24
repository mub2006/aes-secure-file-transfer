import io
import json
import tempfile
import unittest
from pathlib import Path

import app as secure_app


class TransferApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        secure_app.DATA_DIR = Path(self.temp.name)
        secure_app.UPLOAD_DIR = secure_app.DATA_DIR / "encrypted"
        secure_app.DB_PATH = secure_app.DATA_DIR / "test.sqlite3"
        secure_app.init_db()
        self.client = secure_app.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def create_transfer(self):
        metadata = {
            "original_name": "example.txt",
            "mime_type": "text/plain",
            "original_size": 5,
            "nonce": "AAAAAAAAAAAAAAAA",
            "algorithm": "AES-256-GCM"
        }
        # 16 bytes is the minimum GCM tag length; API treats this as opaque ciphertext.
        response = self.client.post(
            "/api/transfers",
            data={
                "file": (io.BytesIO(b"x" * 21), "encrypted.bin"),
                "metadata": json.dumps(metadata)
            },
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").get_json()["status"], "ok")

    def test_upload_and_authorized_download(self):
        created = self.create_transfer()
        response = self.client.get(
            f"/api/transfers/{created['transfer_id']}",
            headers={"X-Transfer-Token": created["access_token"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"x" * 21)
        self.assertEqual(response.headers["X-Original-Name"], "example.txt")

    def test_wrong_token_is_rejected(self):
        created = self.create_transfer()
        response = self.client.get(
            f"/api/transfers/{created['transfer_id']}",
            headers={"X-Transfer-Token": "not-the-token"}
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_file_is_rejected(self):
        response = self.client.post("/api/transfers", data={})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

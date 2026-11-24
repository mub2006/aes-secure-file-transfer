# SecureDrop — AES-Based Secure File Transfer

A working student-project prototype for **CSA5116 Cryptography and Network Security**. It implements the workflow in the project presentation:

1. Select a file in the sender browser.
2. Generate a fresh 256-bit AES key and 96-bit nonce.
3. Encrypt locally using AES-256-GCM (Web Crypto API).
4. Upload ciphertext only to the Flask transfer server.
5. Share the transfer ID, access token, and AES key with the receiver. Share the AES key through a separate trusted channel.
6. Receiver downloads ciphertext and decrypts locally. AES-GCM authentication is verified before the browser releases the plaintext file.

## Security design

- The AES key is generated and used in the sender's browser. It is never sent to Flask or stored in SQLite.
- The server stores encrypted bytes, nonce, basic file metadata, a SHA-256 hash of the access token, expiry time, and download count.
- The access token is returned once at creation and must be provided in the `X-Transfer-Token` header.
- AES-GCM uses a fresh random 12-byte nonce for each file encryption. The 128-bit authentication tag is appended to the ciphertext by the Web Crypto API.
- A wrong key or modified ciphertext causes authenticated decryption to fail. No plaintext is returned in that case.
- The AES key is shown once in the sender result and can be downloaded as a text file. Keep it private and transmit it separately from the transfer ID/token.

## Requirements

- Python 3.10 or newer
- A modern browser with Web Crypto support (Chrome, Edge, Firefox)
- `localhost` or HTTPS. Browsers restrict Web Crypto on insecure non-local origins.

## Run on Windows

1. Extract the ZIP file.
2. Open the extracted `aes_secure_file_transfer` folder.
3. In File Explorer's address bar type `cmd` and press Enter.
4. Create a virtual environment:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   ```

5. Install Flask:

   ```bat
   pip install -r requirements.txt
   ```

6. Start the application:

   ```bat
   py app.py
   ```

7. Open **http://127.0.0.1:5000** in Edge or Chrome.

To stop the server, press `Ctrl+C` in the terminal.

## Run on macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Test the application

Run the server and test these scenarios:

| Test | Steps | Expected result |
|---|---|---|
| Valid file | Send a file, then receive it using all three credentials | Original file downloads correctly |
| Wrong access token | Enter a wrong token | Server denies access |
| Wrong AES key | Use a different valid 32-byte Base64 key | AES-GCM authentication fails |
| Tampered ciphertext | Change one or more bytes in the stored `.bin` payload | AES-GCM authentication fails |
| Empty file | Send a zero-byte file | Empty file decrypts successfully |
| Missing field | Leave one receiver field blank | UI asks for all credentials |
| Oversized file | Select a file above 100 MB | UI rejects it |

## Configuration

Environment variables:

- `PORT` — server port (default `5000`)
- `MAX_FILE_BYTES` — maximum original/encrypted payload size in bytes (default 100 MiB)
- `TRANSFER_EXPIRY_HOURS` — transfer lifetime (default 24 hours)
- `AES_TRANSFER_DATA` — location for SQLite database and encrypted files

The default data folder is `data/`. It contains encrypted payloads and transfer metadata. Do not place plaintext files or AES keys there.

## Project structure

```text
aes_secure_file_transfer/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
├── tests/
│   └── test_api.py
└── data/                 # created automatically at runtime
```

## Important prototype limitations

- The default server binds to `127.0.0.1`, so it is intended for local demonstration on one computer. To transfer between different computers, deploy behind HTTPS on a reachable server and configure firewall/network access appropriately.
- The built-in Flask development server is for demonstration only. Use a production WSGI server and HTTPS for deployment.
- The server does not implement institutional identity management, MFA, malware scanning, resumable uploads, cloud storage, or formal penetration testing.
- The 100 MB default limit keeps this prototype manageable; browser encryption currently reads the selected file into memory.
- The server uses a random bearer-style access token. Anyone who obtains the transfer ID and token can download the ciphertext; they still need the separate AES key to decrypt it.
- The sender's browser displays the AES key once. Do not share the key in the same message/channel as the transfer ID and token.
- For a real production system, add rate limiting, cleanup of expired records/files, hardened deployment, security review, and a formally designed key exchange process.

## Mapping to the four project modules

1. **User Interface & File Handling (Mohamed Mubeen J):** sender/receiver screens, file selection, validation, progress/status, error handling.
2. **AES Encryption & Key Management (M. S. Livesh Vetrivel):** browser Web Crypto AES-256-GCM, random key/nonce, separate key handling.
3. **Secure Transfer & Access Control (Akash M):** Flask upload/download API, random transfer ID/token, token hash verification, expiry.
4. **Integrity Verification & Testing (Manyam Ratish Reddy):** authenticated decryption, wrong-key/tamper rejection, test scenarios and timing display.

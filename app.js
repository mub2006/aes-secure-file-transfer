const $ = (id) => document.getElementById(id);
const MAX_FILE_BYTES = Number(document.querySelector('meta[name="max-file-bytes"]')?.content || (100 * 1024 * 1024));
let selectedFile = null;
let currentKey = null;
let activity = [];

function showToast(message) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 2800);
}
function logAction(message) {
  activity.unshift({message, time: new Date().toLocaleTimeString()});
  activity = activity.slice(0, 12);
  renderLog();
}
function renderLog() {
  const target = $('activity-log');
  if (!activity.length) {
    target.className = 'log-empty';
    target.textContent = 'Your recent actions will appear here. This log stays in this browser session.';
    return;
  }
  target.className = '';
  target.innerHTML = '<ul class="log-list">' + activity.map(item =>
    `<li><span>${escapeHtml(item.message)}</span><time>${escapeHtml(item.time)}</time></li>`
  ).join('') + '</ul>';
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function bytesToBase64(bytes) {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(binary);
}
function base64ToBytes(value) {
  const binary = atob(value.trim());
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
function randomNonce() {
  return crypto.getRandomValues(new Uint8Array(12));
}
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
function setBusy(button, busy, text) {
  button.disabled = busy;
  if (busy) {
    button.dataset.original = button.innerHTML;
    button.textContent = text;
  } else if (button.dataset.original) {
    button.innerHTML = button.dataset.original;
    delete button.dataset.original;
  }
}

$('send-tab').addEventListener('click', () => switchTab('send'));
$('receive-tab').addEventListener('click', () => switchTab('receive'));
function switchTab(which) {
  const sending = which === 'send';
  $('send-panel').hidden = !sending;
  $('receive-panel').hidden = sending;
  $('send-tab').classList.toggle('active', sending);
  $('receive-tab').classList.toggle('active', !sending);
  $('send-tab').setAttribute('aria-selected', String(sending));
  $('receive-tab').setAttribute('aria-selected', String(!sending));
}

$('file-input').addEventListener('change', (event) => chooseFile(event.target.files[0]));
function chooseFile(file) {
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) {
    showToast('File is larger than the 100 MB prototype limit.');
    $('file-input').value = '';
    return;
  }
  selectedFile = file;
  $('selected-file').hidden = false;
  $('selected-file').textContent = `${file.name} · ${formatBytes(file.size)}`;
  $('encrypt-send-btn').disabled = false;
}
const dropzone = $('dropzone');
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
  e.preventDefault(); dropzone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) chooseFile(file);
});

$('encrypt-send-btn').addEventListener('click', async () => {
  if (!selectedFile) return;
  const button = $('encrypt-send-btn');
  setBusy(button, true, 'Encrypting and uploading…');
  try {
    if (!window.crypto?.subtle) throw new Error('Web Crypto is unavailable. Open this app on localhost or through HTTPS.');
    const started = performance.now();
    const key = await crypto.subtle.generateKey({name: 'AES-GCM', length: 256}, true, ['encrypt', 'decrypt']);
    const rawKey = new Uint8Array(await crypto.subtle.exportKey('raw', key));
    const nonce = randomNonce();
    const plain = await selectedFile.arrayBuffer();
    // Web Crypto AES-GCM output includes the 128-bit authentication tag at the end.
    const encrypted = await crypto.subtle.encrypt({name: 'AES-GCM', iv: nonce, tagLength: 128}, key, plain);
    const encryptionMs = performance.now() - started;
    const metadata = {
      original_name: selectedFile.name,
      mime_type: selectedFile.type || 'application/octet-stream',
      original_size: selectedFile.size,
      nonce: bytesToBase64(nonce),
      algorithm: 'AES-256-GCM'
    };
    const form = new FormData();
    form.append('file', new Blob([encrypted], {type: 'application/octet-stream'}), 'encrypted.bin');
    form.append('metadata', JSON.stringify(metadata));
    const response = await fetch('/api/transfers', {method: 'POST', body: form});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not create transfer.');
    currentKey = bytesToBase64(rawKey);
    $('result-id').textContent = result.transfer_id;
    $('result-token').textContent = result.access_token;
    $('result-key').textContent = currentKey;
    $('expiry-text').textContent = `Transfer expires in ${result.expires_in_hours} hours. Encryption took ${encryptionMs.toFixed(1)} ms. Encrypted size: ${formatBytes(result.encrypted_size)}.`;
    $('sender-result').hidden = false;
    logAction(`Encrypted ${selectedFile.name} and created transfer ${result.transfer_id}`);
    showToast('Encrypted transfer created successfully.');
  } catch (error) {
    showToast(error.message || 'An unexpected error occurred.');
    logAction(`Send failed: ${error.message}`);
  } finally {
    setBusy(button, false);
  }
});

$('download-key-btn').addEventListener('click', () => {
  if (!currentKey) return;
  const blob = new Blob([`AES-256 key (Base64)\n${currentKey}\n\nKeep this key private. Share it separately from the transfer ID and access token.\n`], {type: 'text/plain'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'secure-file-aes-key.txt'; a.click();
  URL.revokeObjectURL(url);
});

document.querySelectorAll('.copy-btn').forEach(button => button.addEventListener('click', async () => {
  const value = $(button.dataset.copy).textContent;
  try { await navigator.clipboard.writeText(value); showToast('Copied to clipboard.'); }
  catch { showToast('Clipboard access blocked by browser. Select and copy the value manually.'); }
}));

$('download-decrypt-btn').addEventListener('click', async () => {
  const button = $('download-decrypt-btn');
  const id = $('transfer-id').value.trim().toUpperCase();
  const token = $('access-token').value.trim();
  const keyText = $('aes-key').value.trim();
  const resultBox = $('receiver-result');
  resultBox.hidden = true;
  if (!id || !token || !keyText) { showToast('Enter the transfer ID, access token and AES key.'); return; }
  setBusy(button, true, 'Downloading and verifying…');
  try {
    if (!window.crypto?.subtle) throw new Error('Web Crypto is unavailable. Open this app on localhost or through HTTPS.');
    const started = performance.now();
    const response = await fetch(`/api/transfers/${encodeURIComponent(id)}`, {headers: {'X-Transfer-Token': token}});
    if (!response.ok) {
      let message = 'Could not access this transfer.';
      try { message = (await response.json()).error || message; } catch {}
      throw new Error(message);
    }
    const encrypted = await response.arrayBuffer();
    const nonceB64 = response.headers.get('X-Nonce');
    const originalName = response.headers.get('X-Original-Name') || 'decrypted-file';
    const mimeType = response.headers.get('X-Original-Mime') || 'application/octet-stream';
    if (!nonceB64) throw new Error('Transfer metadata is incomplete.');
    let rawKey;
    try { rawKey = base64ToBytes(keyText); } catch { throw new Error('AES key is not valid Base64.'); }
    if (rawKey.length !== 32) throw new Error('AES-256 key must decode to exactly 32 bytes (Base64).');
    const key = await crypto.subtle.importKey('raw', rawKey, {name: 'AES-GCM'}, false, ['decrypt']);
    const nonce = base64ToBytes(nonceB64);
    if (nonce.length !== 12) throw new Error('The transfer nonce is invalid.');
    // Authentication is verified as part of decrypt. Modified data or a wrong key throws here.
    let plain;
    try {
      plain = await crypto.subtle.decrypt({name: 'AES-GCM', iv: nonce, tagLength: 128}, key, encrypted);
    } catch {
      throw new Error('Authentication failed. The AES key is incorrect or the encrypted file has been modified.');
    }
    const elapsed = performance.now() - started;
    const blob = new Blob([plain], {type: mimeType});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = originalName; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    resultBox.innerHTML = `<div class="result-message"><strong>✓ File authenticated and decrypted successfully</strong>${escapeHtml(originalName)} · ${formatBytes(plain.byteLength)}<br>Download started. Verification and decryption took ${elapsed.toFixed(1)} ms.</div>`;
    resultBox.hidden = false;
    logAction(`Authenticated and decrypted transfer ${id}`);
    showToast('Authentication successful. Your file is ready.');
  } catch (error) {
    resultBox.innerHTML = `<div class="result-message error"><strong>✕ Decryption failed</strong>${escapeHtml(error.message)}</div>`;
    resultBox.hidden = false;
    logAction(`Receive failed for ${id}: ${error.message}`);
    showToast(error.message);
  } finally {
    setBusy(button, false);
  }
});

$('clear-log-btn').addEventListener('click', () => { activity = []; renderLog(); });
$('transfer-id').addEventListener('input', e => { e.target.value = e.target.value.toUpperCase().replace(/[^A-F0-9]/g, '').slice(0, 12); });

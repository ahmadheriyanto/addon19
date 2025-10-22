/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.MobileScanner = publicWidget.Widget.extend({
  selector: "#mobile-scanner-root",

  /**
   * Lifecycle: start
   */
  async start() {
    if (publicWidget.Widget.prototype.start) {
      await publicWidget.Widget.prototype.start.apply(this, arguments);
    }
    try {
      const root = this.el;
      if (!root) return;

      // scoped elements
      this.video = root.querySelector('#mobile-video');
      this.canvas = root.querySelector('#mobile-canvas');
      this.scannedInput = root.querySelector('#scanned-barcode');
      this.logEl = root.querySelector('#mobile-log');
      this.btnToggle = root.querySelector('#btn-toggle');
      this.btnCreate = root.querySelector('#btn-create');
      this.btnComplete = root.querySelector('#btn-complete');
      this.qtyInput = root.querySelector('#qty');
      this.lotInput = root.querySelector('#lot');
      this.lastAction = root.querySelector('#last_action');
      this.scanFeedback = root.querySelector('#scan_feedback');

      if (!this.video || !this.canvas || !this.scannedInput || !this.logEl || !this.btnToggle) {
        console.warn('MobileScanner: missing required DOM elements, initialization aborted.');
        return;
      }

      // device selector created inside the root only (hidden if single camera)
      this.deviceSelect = root.querySelector('#camera-device-select');
      if (!this.deviceSelect) {
        this.deviceSelect = document.createElement('select');
        this.deviceSelect.id = 'camera-device-select';
        this.deviceSelect.className = 'form-select form-select-sm mb-2 d-none';
        this.deviceSelect.setAttribute('aria-label', 'Camera');
        const body = root.querySelector('.o_scanner_body') || root;
        body.insertBefore(this.deviceSelect, body.firstChild);
      }

      // state
      this.stream = null;
      this.scanning = false;
      this.detector = null;
      this.rafId = null;
      this.lastDetected = '';
      this.lastCreated = null;

      // bind handlers
      this._onToggle = this._onToggle.bind(this);
      this._onCreate = this._onCreate.bind(this);
      this._onComplete = this._onComplete.bind(this);
      this._onDeviceChange = this._onDeviceChange.bind(this);

      this.btnToggle.addEventListener('click', this._onToggle);
      if (this.btnCreate) this.btnCreate.addEventListener('click', this._onCreate);
      if (this.btnComplete) this.btnComplete.addEventListener('click', this._onComplete);
      this.deviceSelect.addEventListener('change', this._onDeviceChange);

      this._log('Mobile scanner initialized.');
    } catch (e) {
      // Protect global scope — do not break the site if widget fails
      console.error('MobileScanner initialization failed', e);
    }
  },

  // teardown
  destroy() {
    try { this._stopCamera(); } catch (e) { console.warn('MobileScanner stop error', e); }
    try {
      if (this.btnToggle) this.btnToggle.removeEventListener('click', this._onToggle);
      if (this.btnCreate) this.btnCreate.removeEventListener('click', this._onCreate);
      if (this.btnComplete) this.btnComplete.removeEventListener('click', this._onComplete);
      if (this.deviceSelect) this.deviceSelect.removeEventListener('change', this._onDeviceChange);
    } catch (e) { /* ignore */ }
    return publicWidget.Widget.prototype.destroy.apply(this, arguments);
  },

  _log(msg) {
    try {
      const t = new Date().toLocaleTimeString();
      this.logEl.textContent = `${t} ${msg}\n` + this.logEl.textContent;
      console.log('[mobile-scanner]', msg);
    } catch (e) { /* ignore */ }
  },

  _setFeedback(msg, level = 'info') {
    if (!this.scanFeedback) return;
    this.scanFeedback.textContent = msg;
    this.scanFeedback.style.color = level === 'error' ? '#c0392b' : '#2c3e50';
  },

  _isSecureContext() {
    return window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  },

  async _listVideoDevices() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(d => d.kind === 'videoinput');
      this.deviceSelect.innerHTML = '';
      if (videoDevices.length > 1) {
        videoDevices.forEach((d, idx) => {
          const opt = document.createElement('option');
          opt.value = d.deviceId;
          opt.textContent = d.label || `Camera ${idx + 1}`;
          this.deviceSelect.appendChild(opt);
        });
        this.deviceSelect.classList.remove('d-none');
      } else {
        this.deviceSelect.classList.add('d-none');
      }
      return videoDevices;
    } catch (err) {
      console.warn('MobileScanner: enumerateDevices failed', err);
      return [];
    }
  },

  _handleGetUserMediaError(err) {
    console.error('MobileScanner getUserMedia error', err);
    if (err && err.name) {
      switch (err.name) {
        case 'NotAllowedError':
        case 'PermissionDeniedError':
          this._setFeedback('Camera access denied. Allow camera in your browser/site settings.', 'error');
          break;
        case 'NotFoundError':
        case 'OverconstrainedError':
          this._setFeedback('No camera found or constraints not supported.', 'error');
          break;
        case 'NotReadableError':
        case 'TrackStartError':
          this._setFeedback('Camera is already in use by another application.', 'error');
          break;
        default:
          this._setFeedback('Could not start camera: ' + (err.message || err.name), 'error');
      }
    } else {
      this._setFeedback('Could not start camera.', 'error');
    }
    this._log('getUserMedia error: ' + (err && err.message ? err.message : String(err)));
  },

  async _startCamera() {
    if (this.scanning) return;

    if (!this._isSecureContext()) {
      this._setFeedback('Camera requires HTTPS (or localhost).', 'error');
      this._log('getUserMedia blocked: insecure context');
      return;
    }

    await this._listVideoDevices();

    const selectedDeviceId = this.deviceSelect && this.deviceSelect.value ? this.deviceSelect.value : null;

    const constraintsCandidates = [];
    if (selectedDeviceId) constraintsCandidates.push({ video: { deviceId: { exact: selectedDeviceId } }, audio: false });
    constraintsCandidates.push({ video: { facingMode: { ideal: 'environment' } }, audio: false });
    constraintsCandidates.push({ video: true, audio: false });

    let lastError = null;
    for (const constraints of constraintsCandidates) {
      try {
        this.stream = await navigator.mediaDevices.getUserMedia(constraints);
        break;
      } catch (err) {
        lastError = err;
      }
    }

    if (!this.stream) {
      this._handleGetUserMediaError(lastError || new Error('getUserMedia failed'));
      return;
    }

    try {
      this.video.srcObject = this.stream;
      this.video.muted = true;
      this.video.setAttribute('playsinline', '');
      await this.video.play();
      this.scanning = true;
      this.btnToggle.textContent = 'Stop Camera';
      this._setFeedback('Camera ready — scanning…');
      this._log('Camera stream started');

      await this._listVideoDevices();

      if ('BarcodeDetector' in window) {
        try {
          const formats = await BarcodeDetector.getSupportedFormats();
          this.detector = new BarcodeDetector({ formats: formats });
          this._log('Using native BarcodeDetector: ' + formats.join(','));
        } catch (e) {
          this.detector = null;
          this._log('Native BarcodeDetector init failed: ' + e);
        }
      } else {
        this.detector = null;
        this._log('No native BarcodeDetector available; jsQR fallback will be used if present.');
      }

      this._tick();
    } catch (err) {
      this._handleGetUserMediaError(err);
    }
  },

  _stopCamera() {
    if (!this.scanning) return;
    try {
      if (this.stream) {
        this.stream.getTracks().forEach(t => t.stop());
        this.stream = null;
      }
      if (this.video) this.video.srcObject = null;
    } catch (e) {
      console.warn('MobileScanner stop error', e);
    }
    this.scanning = false;
    if (this.btnToggle) this.btnToggle.textContent = 'Start Camera';
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this._setFeedback('Camera stopped');
    this._log('Camera stopped');
  },

  async _tick() {
    if (!this.scanning) return;
    try {
      if (this.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        this.canvas.width = this.video.videoWidth || 640;
        this.canvas.height = this.video.videoHeight || 480;
        const ctx = this.canvas.getContext('2d');
        try {
          ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
        } catch (e) {
          this.rafId = requestAnimationFrame(this._tick.bind(this));
          return;
        }

        if (this.detector) {
          try {
            const barcodes = await this.detector.detect(this.canvas);
            if (barcodes && barcodes.length) {
              const code = barcodes[0].rawValue;
              this._onDetected(code);
            }
          } catch (err) {
            console.warn('BarcodeDetector error', err);
          }
        } else if (window.jsQR) {
          try {
            const imageData = ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
            const code = jsQR(imageData.data, imageData.width, imageData.height);
            if (code && code.data) this._onDetected(code.data);
          } catch (e) { /* ignore */ }
        }
      }
    } catch (e) {
      console.warn('MobileScanner tick error', e);
    }
    this.rafId = requestAnimationFrame(this._tick.bind(this));
  },

  _onDetected(value) {
    if (!value) return;
    if (value === this.lastDetected) return;
    this.lastDetected = value;
    if (this.scannedInput) this.scannedInput.value = value;
    this._setFeedback('Detected: ' + value);
    this._log('Detected: ' + value);
    if (navigator.vibrate) navigator.vibrate(70);
  },

  _onToggle() {
    try {
      if (this.scanning) this._stopCamera();
      else this._startCamera();
    } catch (e) {
      console.error('Toggle error', e);
    }
  },

  _onDeviceChange() {
    if (this.scanning) {
      this._stopCamera();
      this._startCamera();
    }
  },

  async _onCreate() {
    const barcode = this.scannedInput ? this.scannedInput.value.trim() : '';
    const qty = this.qtyInput ? this.qtyInput.value : 0;
    const lot = this.lotInput ? this.lotInput.value : '';
    if (!barcode) { this._setFeedback('No barcode to create', 'error'); return; }

    const payload = { product_barcode: barcode, quantity: qty, lot: lot };
    this._setFeedback('Sending create…');
    this._log('Create payload: ' + JSON.stringify(payload));
    try {
      const res = await fetch('/mobile_warehouse/api/scan', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.error) {
        this._setFeedback('Create error: ' + data.error, 'error');
        this._log('Create response error: ' + JSON.stringify(data));
      } else {
        this._setFeedback('Created picking ' + data.picking_id + ', move ' + data.move_id);
        this.lastCreated = data;
        if (this.lastAction) this.lastAction.textContent = `Created move ${data.move_id} (picking ${data.picking_id})`;
        this._log('Create response: ' + JSON.stringify(data));
        if (this.scannedInput) this.scannedInput.value = '';
      }
    } catch (err) {
      this._setFeedback('Create request failed', 'error');
      this._log('Create request error: ' + err);
    }
  },

  async _onComplete() {
    const defaultMove = this.lastCreated && this.lastCreated.move_id ? this.lastCreated.move_id : prompt('Enter move id to complete:');
    const qty = this.qtyInput ? this.qtyInput.value : 0;
    const lot = this.lotInput ? this.lotInput.value : '';
    if (!defaultMove) { this._setFeedback('No move id', 'error'); return; }

    const payload = { move_id: defaultMove, qty_done: qty, lot_name: lot };
    this._setFeedback('Completing move…');
    this._log('Complete payload: ' + JSON.stringify(payload));
    try {
      const res = await fetch('/mobile_warehouse/api/complete', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.error) {
        this._setFeedback('Complete error: ' + data.error, 'error');
        this._log('Complete response error: ' + JSON.stringify(data));
      } else {
        this._setFeedback('Complete OK — picking state: ' + (data.picking_state || 'unknown'));
        if (this.lastAction) this.lastAction.textContent = `Completed move ${payload.move_id}`;
        this._log('Complete response: ' + JSON.stringify(data));
      }
    } catch (err) {
      this._setFeedback('Complete request failed', 'error');
      this._log('Complete request error: ' + err);
    }
  },
});
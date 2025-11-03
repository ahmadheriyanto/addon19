// mobile_scanner.js
// Live camera QR scanning for the Mobile Warehouse Scanner page.
// Uses BarcodeDetector when available (fast native path), falls back to jsQR if loaded.
(function () {
  'use strict';

  function onReady(cb) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', cb);
    } else {
      cb();
    }
  }

  onReady(function () {
    var holder = document.getElementById('camera-scanner-holder');
    var resultArea = document.getElementById('qr_result_area');
    var statusEl = document.getElementById('qr_status');

    if (!holder) {
      // Page does not include camera holder
      return;
    }

    // Build UI (video + controls)
    var controls = document.createElement('div');
    controls.className = 'mb-2';

    var startBtn = document.createElement('button');
    startBtn.type = 'button';
    startBtn.className = 'btn btn-primary';
    startBtn.id = 'start_camera_btn';
    startBtn.textContent = 'Start Camera';

    var stopBtn = document.createElement('button');
    stopBtn.type = 'button';
    stopBtn.className = 'btn btn-secondary ms-2';
    stopBtn.id = 'stop_camera_btn';
    stopBtn.textContent = 'Stop Camera';
    stopBtn.disabled = true;

    var video = document.createElement('video');
    video.id = 'qr_video';
    video.autoplay = true;
    video.playsInline = true;
    video.style.width = '100%';
    video.style.maxHeight = '50vh';
    video.style.backgroundColor = '#000';
    video.setAttribute('aria-hidden', 'false');

    controls.appendChild(startBtn);
    controls.appendChild(stopBtn);
    holder.appendChild(controls);
    holder.appendChild(video);

    // hidden canvas for decoding
    var canvas = document.createElement('canvas');
    canvas.id = 'qr_video_canvas';
    canvas.style.display = 'none';
    holder.appendChild(canvas);
    var ctx = canvas.getContext && canvas.getContext('2d');

    var stream = null;
    var scanning = false;
    var bd = null; // BarcodeDetector instance if available

    function showStatus(html, cls) {
      if (!statusEl) return;
      statusEl.innerHTML = '<div class="alert ' + (cls || 'alert-info') + ' p-2 mb-0">' + html + '</div>';
    }

    function clearStatus() {
      if (!statusEl) return;
      statusEl.innerHTML = '';
    }

    function setResult(text) {
      if (!resultArea) return;
      resultArea.innerHTML = '<pre style="white-space:pre-wrap;">' + (text ? text : '<em>No scan yet</em>') + '</pre>';
      // Optionally you may also trigger further UI actions here
      // Keep same UI contract as scan_from_file.js
    }

    // Try to initialize BarcodeDetector if available
    if (window.BarcodeDetector) {
      try {
        var supported = BarcodeDetector.getSupportedFormats ? BarcodeDetector.getSupportedFormats() : null;
        // prefer QR format
        bd = new BarcodeDetector({ formats: ['qr_code'] });
      } catch (e) {
        bd = null;
      }
    }

    async function startCamera() {
      clearStatus();
      setResult(null);
      if (scanning) return;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false
        });
      } catch (err) {
        showStatus('Camera access denied or unavailable: ' + err.message, 'alert-danger');
        return;
      }
      video.srcObject = stream;
      try {
        await video.play();
      } catch (err) {
        // play() might fail silently on some browsers without user gesture
      }
      scanning = true;
      startBtn.disabled = true;
      stopBtn.disabled = false;
      showStatus('Camera started', 'alert-success');
      requestAnimationFrame(tick);
    }

    function stopCamera() {
      if (!scanning) return;
      scanning = false;
      startBtn.disabled = false;
      stopBtn.disabled = true;
      if (stream) {
        stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) { } });
        stream = null;
      }
      video.pause();
      video.srcObject = null;
      showStatus('Camera stopped', 'alert-info');
    }

    async function tick() {
      if (!scanning) return;
      if (video.readyState === video.HAVE_ENOUGH_DATA && ctx) {
        // scale video frame into canvas
        var w = video.videoWidth;
        var h = video.videoHeight;
        if (w && h) {
          // limit max dims to avoid huge canvases
          var maxDim = 1280;
          if (Math.max(w, h) > maxDim) {
            var scale = maxDim / Math.max(w, h);
            w = Math.round(w * scale);
            h = Math.round(h * scale);
          }
          canvas.width = w;
          canvas.height = h;
          ctx.drawImage(video, 0, 0, w, h);

          try {
            // Prefer native BarcodeDetector if available
            if (bd) {
              try {
                const detections = await bd.detect(canvas);
                if (detections && detections.length) {
                  const d = detections[0];
                  if (d && d.rawValue) {
                    onDecoded(d.rawValue);
                    return; // stop further scans by default (you can continue if you want)
                  }
                }
              } catch (err) {
                // ignore barcode detector runtime errors and fallback
                bd = null;
              }
            }

            // Fallback to jsQR if provided
            if (typeof jsQR === 'function') {
              var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
              var code = jsQR(imageData.data, imageData.width, imageData.height);
              if (code && code.data) {
                onDecoded(code.data);
                return;
              }
            }
          } catch (err) {
            // ignore decoding errors
            console.error('Decoding error', err);
          }
        }
      }
      requestAnimationFrame(tick);
    }

    function onDecoded(text) {
      // Found a code
      showStatus('QR code detected', 'alert-success');
      setResult(text);
      // Optionally stop scanning after detection
      // stopCamera();

      // If you want to continue scanning and update result live, comment out stopCamera()
    }

    // Attach events
    startBtn.addEventListener('click', function (ev) { ev.preventDefault(); startCamera(); });
    stopBtn.addEventListener('click', function (ev) { ev.preventDefault(); stopCamera(); });

    // Stop camera when leaving page
    window.addEventListener('pagehide', function () {
      stopCamera();
    });

    // restore initial state
    setResult(null);
  });
}());
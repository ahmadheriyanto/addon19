/** @odoo-module **/
import { rpc } from "@web/core/network/rpc";

// mobile_scanner.js
// Live camera QR scanning for the Mobile Warehouse Scanner page.
// Uses BarcodeDetector when available, falls back to jsQR.
// Uses Odoo rpc(...) helper imported from @web/core/network/rpc for Odoo 19.
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
    }

    // Try to initialize BarcodeDetector if available
    if (window.BarcodeDetector) {
      try {
        bd = new BarcodeDetector({ formats: ['qr_code'] });
      } catch (e) {
        bd = null;
      }
    }

    function rpcPostPayload(parsedPayload) {
      // Use imported rpc helper
      try {
        if (typeof rpc !== 'function') {
          throw new Error('rpc helper is not available in this environment');
        }
      } catch (e) {
        showStatus('RPC helper unavailable: ' + e.message, 'alert-danger');
        console.error(e);
        return Promise.reject(e);
      }

      return rpc('/mobile_warehouse/api/process_incoming_qr', {
        payload: parsedPayload
      });
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
        var w = video.videoWidth;
        var h = video.videoHeight;
        if (w && h) {
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
            if (bd) {
              try {
                const detections = await bd.detect(canvas);
                if (detections && detections.length) {
                  const d = detections[0];
                  if (d && d.rawValue) {
                    onDecoded(d.rawValue);
                    return;
                  }
                }
              } catch (err) {
                bd = null;
              }
            }

            if (typeof jsQR === 'function') {
              var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
              var code = jsQR(imageData.data, imageData.width, imageData.height);
              if (code && code.data) {
                onDecoded(code.data);
                return;
              }
            }
          } catch (err) {
            console.error('Decoding error', err);
          }
        }
      }
      requestAnimationFrame(tick);
    }

    function onDecoded(text) {
      showStatus('QR code detected', 'alert-success');
      setResult(text);

      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.qr_type === 'incomingstaging') {
          showStatus('Processing incoming staging QR...', 'alert-info');

          rpcPostPayload(parsed).then(function (result) {
            // user pattern: result.result === 'updated'
            if (result && result.result && result.result === 'updated') {
              showStatus('Processing complete', 'alert-success');
              setResult('updated');
              return;
            }
            var payload = result;
            if (payload && payload.success) {
              setResult(JSON.stringify(payload.results || payload, null, 2));
              showStatus('Processing complete', 'alert-success');
              return;
            }
            var msg = (payload && (payload.error || payload.details)) ? (payload.error || payload.details) : 'Processing failed (unknown server response)';
            showStatus(msg, 'alert-danger');
            console.error('RPC returned unexpected payload:', result);
          }).catch(function (err) {
            console.error('RPC error:', err);
            var userMsg = 'Processing failed (network or permissions).';
            try {
              if (err && err.data && err.data.message) {
                userMsg = err.data.message;
              } else if (err && err.data && err.data.debug && typeof err.data.debug === 'string') {
                userMsg = err.data.debug.split('\n')[0];
              } else if (err && err.message) {
                userMsg = err.message;
              }
            } catch (e) {}
            showStatus(userMsg, 'alert-danger');
          });
        }
      } catch (e) {
        // not JSON — ignore
      }
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
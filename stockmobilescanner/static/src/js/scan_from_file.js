// scan_from_file.js
// Client-side QR-from-file support using jsQR (https://github.com/cozmo/jsQR).
// This file is intended to be loaded as a normal script (non-odoo-module).
(function () {
  'use strict';

  // Wait until DOM ready
  function onReady(cb) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', cb);
    } else {
      cb();
    }
  }

  onReady(function () {
    var input = document.getElementById('qr_file_input');
    var scanBtn = document.getElementById('scan_file_btn');
    var clearBtn = document.getElementById('clear_file_btn');
    var statusEl = document.getElementById('qr_status');
    var resultArea = document.getElementById('qr_result_area');
    var actionsEl = document.getElementById('qr_actions');
    var canvas = document.getElementById('qr_canvas');
    var ctx = canvas && canvas.getContext ? canvas.getContext('2d') : null;

    if (!input || !scanBtn || !clearBtn || !statusEl || !resultArea || !canvas || !ctx) {
      // Template not present on this page
      return;
    }

    function showStatus(html, cls) {
      statusEl.innerHTML = '<div class="alert ' + (cls || 'alert-info') + ' p-2 mb-0">' + html + '</div>';
    }

    function clearStatus() {
      statusEl.innerHTML = '';
    }

    function setResult(text) {
      resultArea.innerHTML = '<pre style="white-space:pre-wrap;">' + (text ? text : '<em>No scan yet</em>') + '</pre>';
      actionsEl.innerHTML = '';
      if (text) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-sm btn-outline-primary';
        btn.textContent = 'Copy';
        btn.onclick = function () {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
              showStatus('Copied to clipboard', 'alert-success');
              setTimeout(clearStatus, 1500);
            }).catch(function () {
              showStatus('Copy failed', 'alert-danger');
              setTimeout(clearStatus, 1500);
            });
          } else {
            // fallback
            var ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            try {
              document.execCommand('copy');
              showStatus('Copied to clipboard', 'alert-success');
            } catch (e) {
              showStatus('Copy not supported', 'alert-warning');
            }
            document.body.removeChild(ta);
            setTimeout(clearStatus, 1500);
          }
        };
        actionsEl.appendChild(btn);
      }
    }

    function decodeDataURL(dataURL) {
      return new Promise(function (resolve, reject) {
        var img = new Image();
        img.onload = function () {
          try {
            var w = img.naturalWidth;
            var h = img.naturalHeight;
            var maxDim = 1600;
            if (Math.max(w, h) > maxDim) {
              var scale = maxDim / Math.max(w, h);
              w = Math.round(w * scale);
              h = Math.round(h * scale);
            }
            canvas.width = w;
            canvas.height = h;
            ctx.clearRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            var imageData = ctx.getImageData(0, 0, w, h);
            if (typeof jsQR !== 'function') {
              return reject(new Error('jsQR library not loaded'));
            }
            var code = jsQR(imageData.data, imageData.width, imageData.height);
            if (code && code.data) {
              resolve(code.data);
            } else {
              resolve(null);
            }
          } catch (err) {
            reject(err);
          }
        };
        img.onerror = function () {
          reject(new Error('Failed to load image'));
        };
        img.src = dataURL;
      });
    }

    scanBtn.addEventListener('click', function () {
      clearStatus();
      setResult(null);
      var file = input.files && input.files[0];
      if (!file) {
        showStatus('Please select an image file from your device first.', 'alert-warning');
        return;
      }
      var maxBytes = 8 * 1024 * 1024;
      if (file.size > maxBytes) {
        showStatus('Selected file is too large. Choose a smaller image.', 'alert-warning');
        return;
      }
      var reader = new FileReader();
      reader.onload = function (ev) {
        var dataURL = ev.target.result;
        showStatus('Decoding image...', 'alert-info');
        decodeDataURL(dataURL).then(function (decoded) {
          if (decoded) {
            showStatus('QR code decoded', 'alert-success');
            setResult(decoded);
          } else {
            showStatus('No QR code detected in the image.', 'alert-danger');
            setResult(null);
          }
        }).catch(function (err) {
          console.error(err);
          showStatus('Error decoding image: ' + (err && err.message ? err.message : err), 'alert-danger');
        });
      };
      reader.onerror = function () {
        showStatus('Failed to read the selected file', 'alert-danger');
      };
      reader.readAsDataURL(file);
    });

    clearBtn.addEventListener('click', function () {
      input.value = '';
      clearStatus();
      setResult(null);
    });

    // initialize
    setResult(null);
  });
}());
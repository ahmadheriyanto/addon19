// Minimal mobile scanner JS (vanilla). Uses BarcodeDetector when available, otherwise falls back to jsQR (if you include it).
// Place this file in stock_mobile_scanner/static/src/js/mobile_scanner.js

(function () {
    'use strict';

    const video = document.getElementById('mobile-video');
    const canvas = document.getElementById('mobile-canvas');
    const scannedInput = document.getElementById('scanned-barcode');
    const logEl = document.getElementById('mobile-log');
    const btnToggle = document.getElementById('btn-toggle');
    const btnCreate = document.getElementById('btn-create');
    const btnComplete = document.getElementById('btn-complete');
    const qtyInput = document.getElementById('qty');
    const lotInput = document.getElementById('lot');

    let stream = null;
    let scanning = false;
    let detector = null;
    let rafId = null;

    function log(msg) {
        const t = new Date().toISOString();
        logEl.textContent = t + ' ' + msg + "\\n" + logEl.textContent;
    }

    async function startCamera() {
        if (scanning) return;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
            video.srcObject = stream;
            scanning = true;
            btnToggle.textContent = 'Stop Camera';
            // init detector if available
            if ('BarcodeDetector' in window) {
                const formats = await BarcodeDetector.getSupportedFormats();
                detector = new BarcodeDetector({formats: formats});
                log('Using native BarcodeDetector, formats: ' + formats.join(','));
            } else {
                log('BarcodeDetector not available; using canvas fallback (requires jsQR).');
                detector = null;
            }
            tick();
        } catch (err) {
            log('Camera start error: ' + err);
        }
    }

    function stopCamera() {
        if (!scanning) return;
        if (stream) {
            stream.getTracks().forEach(t => t.stop());
            stream = null;
        }
        video.srcObject = null;
        scanning = false;
        btnToggle.textContent = 'Start Camera';
        if (rafId) cancelAnimationFrame(rafId);
    }

    btnToggle.addEventListener('click', function () {
        if (scanning) stopCamera(); else startCamera();
    });

    async function tick() {
        if (!scanning) return;
        if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

            if (detector) {
                try {
                    const barcodes = await detector.detect(canvas);
                    if (barcodes && barcodes.length) {
                        const code = barcodes[0].rawValue;
                        onDetected(code);
                    }
                } catch (err) {
                    // detection sometimes throws, ignore
                }
            } else {
                // fallback: use jsQR if present
                if (window.jsQR) {
                    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    const code = jsQR(imageData.data, imageData.width, imageData.height);
                    if (code && code.data) onDetected(code.data);
                }
            }
        }
        rafId = requestAnimationFrame(tick);
    }

    let lastDetected = '';
    function onDetected(value) {
        if (!value) return;
        if (value === lastDetected) return; // reduce duplicates
        lastDetected = value;
        scannedInput.value = value;
        log('Detected: ' + value);
        // auto-send optional: here we don't auto create to avoid mistakes; user presses Create/Complete
    }

    btnCreate.addEventListener('click', async function () {
        const barcode = scannedInput.value.trim();
        const qty = qtyInput.value || 0;
        const lot = lotInput.value || '';
        if (!barcode) { log('No barcode'); return; }

        const payload = {
            product_barcode: barcode,
            quantity: qty,
            lot: lot,
        };
        log('Sending create: ' + JSON.stringify(payload));
        try {
            const res = await fetch('/mobile_warehouse/api/scan', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            log('Create response: ' + JSON.stringify(data));
            if (data.success) {
                scannedInput.value = '';
            }
        } catch (err) {
            log('Create error: ' + err);
        }
    });

    btnComplete.addEventListener('click', async function () {
        const moveId = prompt('Enter move id to complete (or leave blank to use last created move id):');
        const qty = qtyInput.value || 0;
        const lot = lotInput.value || '';
        if (!moveId) { log('No move id provided'); return; }
        const payload = { move_id: moveId, qty_done: qty, lot_name: lot };
        log('Sending complete: ' + JSON.stringify(payload));
        try {
            const res = await fetch('/mobile_warehouse/api/complete', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            log('Complete response: ' + JSON.stringify(data));
        } catch (err) {
            log('Complete error: ' + err);
        }
    });

    // init small log
    log('Mobile scanner loaded. Press Start Camera.');
})();
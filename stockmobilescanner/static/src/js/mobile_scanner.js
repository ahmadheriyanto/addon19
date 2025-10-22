(function () {
    'use strict';

    // Run only after DOM loaded
    document.addEventListener('DOMContentLoaded', function () {

        // Quick guard: only initialize if the scanner root exists.
        // Put a root element with id="mobile-scanner-root" in your template (or use existing unique id).
        var root = document.getElementById('mobile-scanner-root');
        if (!root) {
            // Not on scanner page, do nothing.
            return;
        }

        const video = document.getElementById('mobile-video');
        const canvas = document.getElementById('mobile-canvas');
        const scannedInput = document.getElementById('scanned-barcode');
        const logEl = document.getElementById('mobile-log');
        const btnToggle = document.getElementById('btn-toggle');
        const btnCreate = document.getElementById('btn-create');
        const btnComplete = document.getElementById('btn-complete');
        const qtyInput = document.getElementById('qty');
        const lotInput = document.getElementById('lot');
        const lastAction = document.getElementById('last_action');
        const scanFeedback = document.getElementById('scan_feedback');

        // Ensure required elements exist before proceeding
        if (!video || !canvas || !scannedInput || !logEl || !btnToggle) {
            // If some essential elements are missing, do not initialize to avoid exceptions.
            console.warn('Mobile scanner: missing required DOM elements, initialization aborted.');
            return;
        }

        let stream = null;
        let scanning = false;
        let detector = null;
        let rafId = null;
        let lastDetected = '';
        let lastCreated = null;

        function log(msg) {
            const t = new Date().toLocaleTimeString();
            logEl.textContent = `${t} ${msg}\n` + logEl.textContent;
        }

        function setFeedback(msg, level='info') {
            if (!scanFeedback) return;
            scanFeedback.textContent = msg;
            scanFeedback.style.color = level === 'error' ? '#c0392b' : '#2c3e50';
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
                    try {
                        const formats = await BarcodeDetector.getSupportedFormats();
                        detector = new BarcodeDetector({formats: formats});
                        log('Using native BarcodeDetector: ' + formats.join(','));
                        setFeedback('Camera ready — scanning…');
                    } catch (e) {
                        detector = null;
                        setFeedback('Camera ready (no native detector).', 'info');
                    }
                } else {
                    setFeedback('Camera ready — using canvas fallback. If no detection, add fallback library.', 'info');
                }
                tick();
            } catch (err) {
                setFeedback('Camera permission or start error', 'error');
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
            setFeedback('Camera stopped');
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
                        // ignore detection errors
                    }
                } else {
                    // fallback: try jsQR if available
                    if (window.jsQR) {
                        try {
                            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                            const code = jsQR(imageData.data, imageData.width, imageData.height);
                            if (code && code.data) onDetected(code.data);
                        } catch (e) {}
                    }
                }
            }
            rafId = requestAnimationFrame(tick);
        }

        function onDetected(value) {
            if (!value) return;
            if (value === lastDetected) return;
            lastDetected = value;
            if (scannedInput) scannedInput.value = value;
            setFeedback('Detected: ' + value);
            log('Detected: ' + value);
            if (navigator.vibrate) navigator.vibrate(70);
        }

        // safe creation/complete handlers - check elements exist before using
        if (btnCreate) {
            btnCreate.addEventListener('click', async function () {
                const barcode = scannedInput ? scannedInput.value.trim() : '';
                const qty = qtyInput ? qtyInput.value : 0;
                const lot = lotInput ? lotInput.value : '';
                if (!barcode) { setFeedback('No barcode to create', 'error'); return; }

                const payload = { product_barcode: barcode, quantity: qty, lot: lot };
                setFeedback('Sending create…');
                log('Create payload: ' + JSON.stringify(payload));
                try {
                    const res = await fetch('/mobile_warehouse/api/scan', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    const data = await res.json();
                    if (data.error) {
                        setFeedback('Create error: ' + data.error, 'error');
                        log('Create response error: ' + JSON.stringify(data));
                    } else {
                        setFeedback('Created picking ' + data.picking_id + ', move ' + data.move_id);
                        lastCreated = data;
                        if (lastAction) lastAction.textContent = `Created move ${data.move_id} (picking ${data.picking_id})`;
                        log('Create response: ' + JSON.stringify(data));
                        if (scannedInput) scannedInput.value = '';
                    }
                } catch (err) {
                    setFeedback('Create request failed', 'error');
                    log('Create request error: ' + err);
                }
            });
        }

        if (btnComplete) {
            btnComplete.addEventListener('click', async function () {
                const defaultMove = lastCreated && lastCreated.move_id ? lastCreated.move_id : prompt('Enter move id to complete:');
                const qty = qtyInput ? qtyInput.value : 0;
                const lot = lotInput ? lotInput.value : '';
                if (!defaultMove) { setFeedback('No move id', 'error'); return; }

                const payload = { move_id: defaultMove, qty_done: qty, lot_name: lot };
                setFeedback('Completing move…');
                log('Complete payload: ' + JSON.stringify(payload));
                try {
                    const res = await fetch('/mobile_warehouse/api/complete', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    const data = await res.json();
                    if (data.error) {
                        setFeedback('Complete error: ' + data.error, 'error');
                        log('Complete response error: ' + JSON.stringify(data));
                    } else {
                        setFeedback('Complete OK — picking state: ' + (data.picking_state || 'unknown'));
                        if (lastAction) lastAction.textContent = `Completed move ${payload.move_id}`;
                        log('Complete response: ' + JSON.stringify(data));
                    }
                } catch (err) {
                    setFeedback('Complete request failed', 'error');
                    log('Complete request error: ' + err);
                }
            });
        }

        // small init log
        log('Mobile scanner ready. Tap Start Camera.');
    });
})();
odoo.define('@fulfillment/client_actions/stock_traceability_report_extend', function (require) {
    "use strict";
    const { rpc } = require('@web/core/network/rpc');
    const stock = require('stock/static/src/client_actions/stock_traceability_report_backend.js');

    function getExpiryFromCache(line, lotCache) {
        const lotId = line.lot_id || (line.lot && line.lot.id);
        if (!lotId) return '';
        const lot = lotCache.get(lotId);
        return lot?.use_date || lot?.life_date || '';
    }

    const origSetup = stock.StockTraceabilityReport.prototype.setup;
    stock.StockTraceabilityReport.prototype.setup = async function () {
        await origSetup.apply(this, arguments);

        const lines = this.state?.lines || [];
        // Collect lot ids to fetch expiry fields
        const lotIds = [];
        for (const line of lines) {
            const lotId = line.lot_id || (line.lot && line.lot.id);
            if (lotId) lotIds.push(lotId);
        }
        const uniqLotIds = [...new Set(lotIds)];

        const lotCache = new Map();
        if (uniqLotIds.length) {
            // Read expiry-related fields from lots
            const lots = await rpc('/web/dataset/call_kw', {
                model: 'stock.lot',
                method: 'read',
                args: [uniqLotIds, ['use_date', 'life_date']],
                kwargs: {},
            });
            for (const l of lots) {
                lotCache.set(l.id, l);
            }
        }

        // Attach expiration_date and insert an extra column value
        for (const line of lines) {
            const expiry = getExpiryFromCache(line, lotCache);
            line.expiration_date = expiry;
            if (Array.isArray(line.columns)) {
                // Insert after Lot/Serial # (index 3 -> add at index 4)
                line.columns.splice(4, 0, expiry || '');
            }
        }
    };
});
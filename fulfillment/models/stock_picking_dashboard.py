# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPickingDashboard(models.Model):
    _name = 'stock.picking.dashboard'
    _description = 'Helper for stock.picking dashboard statistics'

    @api.model
    def get_picking_status_priority_stats(self, company=None):
        """
        Return stats grouped by picking state (rows) and priority labels (columns).
        Columns (priority labels) are taken from company settings:
          - company.fulfillment_courier_label_reguler
          - company.fulfillment_courier_label_medium
          - company.fulfillment_courier_label_priority

        Returns a dict:
            {
                'statuses': [
                    {'key': 'draft', 'label': 'Draft', 'total': <int>, 'by_priority': {priority_label: count, ...}},
                    ...
                ],
                'priorities': [pr1, pr2, pr3],
                'total': <int_all_states>
            }
        """
        env = self.env
        Picking = env['stock.picking'].sudo()

        if company is None:
            company = env.company

        # Read priority labels from company settings (use friendly defaults)
        pr_reg = (getattr(company, 'fulfillment_courier_label_reguler', None) or 'Reguler').strip()
        pr_med = (getattr(company, 'fulfillment_courier_label_medium', None) or 'Medium').strip()
        pr_pri = (getattr(company, 'fulfillment_courier_label_priority', None) or 'Instan').strip()
        priorities = [pr_reg, pr_med, pr_pri]

        # Rows: typical picking states and friendly labels
        states = [
            ('draft', 'Draft'),
            ('confirmed', 'To Process'),
            ('waiting', 'Waiting'),
            ('assigned', 'Ready'),
            ('backorder', 'Backorder'),
            ('done', 'Done'),
        ]

        statuses = []
        total_all = 0

        for state_key, state_label in states:
            try:
                total_state = Picking.search_count([('state', '=', state_key)])
            except Exception:
                total_state = 0
            total_all += total_state

            by_priority = {}
            for pr in priorities:
                try:
                    cnt = Picking.search_count([('state', '=', state_key), ('courier_priority', '=', pr)])
                except Exception:
                    cnt = 0
                by_priority[pr] = cnt

            statuses.append({
                'key': state_key,
                'label': state_label,
                'total': total_state,
                'by_priority': by_priority,
            })

        return {
            'statuses': statuses,
            'priorities': priorities,
            'total': total_all,
        }
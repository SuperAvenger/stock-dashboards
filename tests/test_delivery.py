import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import push_to_feishu as app
import longport_simple_client as client


class DeliveryTests(unittest.TestCase):
    def send(self, response):
        stock = {'symbol': 'NVDA.US', 'name': 'NVDA'}
        with patch.object(app, 'FEISHU_WEBHOOK', 'https://example.com/hook'), patch.object(
            app, 'detect_changes', side_effect=[([], []), ([stock], [])]
        ), patch.object(app, 'build_current_state', return_value={}), patch.object(
            app, 'format_stock_line', return_value='NVDA'
        ), patch.object(app, 'format_change_summary', return_value=''), patch.object(
            app.requests, 'post', return_value=response
        ), patch.object(app, 'save_state') as save:
            try:
                app.push_to_feishu({}, {'stocks': [stock]}, {})
            finally:
                self.saved = save.call_count

    def test_business_failure_does_not_advance_dedupe_state(self):
        response = Mock()
        response.json.return_value = {'code': 19001}
        with self.assertRaises(RuntimeError):
            self.send(response)
        self.assertEqual(self.saved, 0)

    def test_confirmed_delivery_advances_state(self):
        response = Mock()
        response.json.return_value = {'code': 0}
        self.send(response)
        self.assertEqual(self.saved, 1)

    def test_missing_status_is_not_confirmed_delivery(self):
        response = Mock()
        response.json.return_value = {}
        with self.assertRaises(RuntimeError):
            self.send(response)
        self.assertEqual(self.saved, 0)

    def test_symbols_use_sdk_market_suffixes(self):
        self.assertEqual(client.normalize_symbol('00700.HK'), '700.HK')
        self.assertEqual(client.normalize_symbol('NVDA'), 'NVDA.US')
        self.assertEqual(client.normalize_symbol('TSM.US'), 'TSM.US')

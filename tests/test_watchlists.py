import csv
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from openalgo_client import OpenAlgoClient, OpenAlgoError
from watchlists import IST, build_watchlists
from news_import import parse_feed


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = self.root / 'history'
        self.history.mkdir()
        self.news = self.root / 'news.json'
        self.news.write_text('[]')
        self.now = datetime(2026, 10, 19, 10, 0, tzinfo=IST)
        self.rows('ABC')

    def rows(self, symbol, delivery=61, volume=150, high=110, low=90, offset=0):
        dates = [date(2026, 10, 16) - timedelta(days=offset + i) for i in range(21)][::-1]
        with (self.history / f'{symbol}.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['Date', 'Series', 'High', 'Low', 'TradedQty', 'DeliveryPercent'])
            writer.writeheader()
            for i, day in enumerate(dates):
                writer.writerow(dict(Date=str(day), Series='EQ', High=high, Low=low,
                                     TradedQty=volume if i == 20 else 100, DeliveryPercent=delivery))

    def build(self, **kwargs):
        return build_watchlists(self.history, self.news, now=self.now, **kwargs)

    def test_excludes_signal_day_from_volume_average(self):
        row = self.build()['daily']['delivery_volume'][0]
        self.assertEqual(row['average_volume'], 100)
        self.assertEqual(row['volume_ratio'], 1.5)

    def test_delivery_is_strict_and_volume_threshold_configurable(self):
        self.rows('ABC', delivery=60)
        self.assertEqual(self.build()['candidate_symbols'], [])
        self.rows('ABC', volume=199)
        self.assertEqual(self.build(volume_multiplier=2)['candidate_symbols'], [])

    def test_requires_full_lookback_and_ignores_current_session(self):
        path = self.history / 'ABC.csv'
        lines = path.read_text().splitlines()
        path.write_text('\n'.join(lines[0:20]) + '\n2026-10-19,EQ,999,1,10000,99\n')
        self.assertEqual(self.build()['daily']['delivery_volume'], [])
        self.assertNotEqual(self.build()['reference_date'], '2026-10-19')

    def test_news_only_candidate_and_deduplication(self):
        self.rows('ABC', delivery=10)
        item = dict(symbol='ABC', headline='Quarterly results', category='results',
                    published_at='2026-10-18T12:00:00+05:30', url='https://example.com/results')
        self.news.write_text(json.dumps([item, item, {**item, 'published_at': '2020-01-01T00:00:00Z'}]))
        result = self.build()
        self.assertEqual(result['candidate_symbols'], ['ABC'])
        self.assertEqual(len(result['daily']['news_results']), 1)

    def test_intraday_groups_equal_boundary_and_missing_quotes(self):
        for symbol in ['DEF', 'GHI', 'JKL']:
            self.rows(symbol)
        client = Mock()
        client.quotes.return_value = [dict(symbol=s, data={'ltp': p}) for s, p in
                                     [('ABC', 111), ('DEF', 89), ('GHI', 110)]]
        result = self.build(fetch_quotes=True, client=client)['intraday']
        self.assertEqual(result['above_previous_high'][0]['symbol'], 'ABC')
        self.assertEqual(result['below_previous_low'][0]['symbol'], 'DEF')
        self.assertEqual(result['within_range'][0]['symbol'], 'GHI')
        self.assertEqual(result['unavailable'], ['JKL'])

    def test_stale_symbol_excluded_and_old_dataset_blocks_quotes(self):
        self.rows('OLD', offset=1)
        self.assertNotIn('OLD', self.build()['candidate_symbols'])
        self.rows('ABC', offset=10)
        self.rows('OLD', offset=11)
        client = Mock()
        self.assertEqual(self.build(fetch_quotes=True, client=client)['quote_status'], 'history_stale')
        client.quotes.assert_not_called()

    def test_off_session_does_not_request_quotes(self):
        self.now = self.now.replace(hour=16)
        client = Mock()
        self.assertEqual(self.build(fetch_quotes=True, client=client)['quote_status'], 'outside_regular_session')
        client.quotes.assert_not_called()

    def test_quote_failure_is_visible(self):
        client = Mock()
        client.quotes.side_effect = OpenAlgoError('unavailable')
        result = self.build(fetch_quotes=True, client=client)
        self.assertEqual(result['quote_status'], 'unavailable')
        self.assertEqual(result['intraday']['unavailable'], ['ABC'])

    def test_rss_missing_date_is_never_assigned_today(self):
        xml = '<rss><channel><item><title>Results</title><link>https://example.com</link></item></channel></rss>'
        self.assertEqual(parse_feed(xml, 'ABC'), [])
        xml = xml.replace('</item>', '<pubDate>Mon, 19 Oct 2026 02:00:00 GMT</pubDate></item>')
        self.assertEqual(parse_feed(xml, 'ABC', 'results')[0]['category'], 'results')


class OpenAlgoTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.post.return_value.json.return_value = {'status': 'success', 'orderid': '123'}
        self.client = OpenAlgoClient(api_key='secret', session=self.session)

    def test_intraday_payload_and_market_price(self):
        self.client.place_order('ABC', 10, 'BUY', price=999)
        payload = self.session.post.call_args.kwargs['json']
        self.assertEqual((payload['product'], payload['exchange'], payload['price']), ('MIS', 'NSE', 0))
        self.assertFalse(self.session.post.call_args.kwargs['allow_redirects'])

    def test_invalid_orders_never_reach_broker(self):
        for kwargs in [dict(quantity=0), dict(quantity=1.5), dict(order_type='LIMIT'), dict(order_type='SL-M'), dict(price=float('nan'))]:
            values = dict(symbol='ABC', quantity=10, action='BUY')
            values.update(kwargs)
            with self.assertRaises(ValueError):
                self.client.place_order(**values)
        self.session.post.assert_not_called()

    def test_timeout_does_not_retry_or_expose_credentials(self):
        self.session.post.side_effect = requests.Timeout('secret')
        with self.assertRaises(OpenAlgoError) as caught:
            self.client.place_order('ABC', 1, 'BUY')
        self.assertNotIn('secret', str(caught.exception))
        self.session.post.assert_called_once()

    def test_multiquotes_uses_results_and_batches(self):
        self.session.post.return_value.json.return_value = {'status': 'success', 'results': [{'symbol': 'ABC', 'data': {'ltp': 1}}]}
        result = self.client.quotes([f'S{i}' for i in range(51)])
        self.assertEqual(len(result), 2)
        self.assertEqual(self.session.post.call_count, 2)

    def test_order_adapter_disabled_by_default(self):
        from broker_client import OpenAlgoAdapter
        with patch.dict(os.environ, {'OPENALGO_ORDERS_ENABLED': ''}):
            adapter = OpenAlgoAdapter()
            adapter.client = Mock()
            self.assertEqual(adapter.place_order('ABC', 1, 'BUY')['status'], 'REJECTED')
            adapter.client.place_order.assert_not_called()


if __name__ == '__main__':
    unittest.main()

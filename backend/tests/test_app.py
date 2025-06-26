import sys
import unittest
from unittest.mock import patch, MagicMock, ANY
import json
from datetime import datetime

# Mock pywhatkit at the top level before backend.app (which imports backend.notifications) is imported.
MOCK_PYWHATKIT_APP = MagicMock()
sys.modules['pywhatkit'] = MOCK_PYWHATKIT_APP

# Now safe to import app components
from backend.app import app, product_price_history, price_alert_subscriptions, check_subscribed_product_prices
# ALL_SCRAPERS is also used, ensure it's available or mocked if its definition relies on unmockable imports.
# For now, assuming ALL_SCRAPERS definition in app.py is safe after pywhatkit mock.

# We need to be able to clear these global dicts for tests
# Storing copies to restore is tricky if tests run in parallel or app is not truly stateless.
# Best practice is usually a factory pattern for app creation for tests.
# Given the current structure, we will clear them in setUp and rely on that.
# original_product_price_history = product_price_history.copy() # Avoid if possible
# original_price_alert_subscriptions = price_alert_subscriptions.copy() # Avoid if possible


class TestApp(unittest.TestCase):

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        self.client = app.test_client()

        # Clear global stores for each test to ensure isolation
        product_price_history.clear()
        price_alert_subscriptions.clear()

        # Reset the global pywhatkit mock if app tests might trigger its direct use
        MOCK_PYWHATKIT_APP.reset_mock()
        MOCK_PYWHATKIT_APP.sendwhatmsg_instantly = MagicMock()


    def tearDown(self):
        product_price_history.clear()
        price_alert_subscriptions.clear()
        # Restore original data if necessary, or ensure tests clean up fully
        # product_price_history.update(original_product_price_history) # This might be needed if not using a factory for app
        # price_alert_subscriptions.update(original_price_alert_subscriptions)
        self.app_context.pop()

    # Tests for /subscribe-price-alert endpoint
    def test_subscribe_price_alert_whatsapp_success_new(self):
        payload = {
            "product_name": "Laptop Test",
            "user_identifier": "+51999999999",
            "notification_channel": "whatsapp",
            "desired_discount_percentage": "10"
        }
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Subscribed successfully", data['message'])
        self.assertEqual(data['subscription_key'], ["laptop test", "+51999999999", "whatsapp"])

        sub_key = ("laptop test", "+51999999999", "whatsapp")
        self.assertIn(sub_key, price_alert_subscriptions)
        self.assertEqual(price_alert_subscriptions[sub_key]['product_name'], "Laptop Test")
        self.assertEqual(price_alert_subscriptions[sub_key]['user_identifier'], "+51999999999")
        self.assertEqual(price_alert_subscriptions[sub_key]['notification_channel'], "whatsapp")
        self.assertEqual(price_alert_subscriptions[sub_key]['desired_discount_percentage'], 0.10)

    def test_subscribe_price_alert_telegram_success_new(self):
        payload = {
            "product_name": "Tablet Pro",
            "user_identifier": "123456789", # Telegram Chat ID
            "notification_channel": "telegram",
            "desired_discount_percentage": "25"
        }
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Subscribed successfully", data['message'])
        self.assertEqual(data['subscription_key'], ["tablet pro", "123456789", "telegram"])

        sub_key = ("tablet pro", "123456789", "telegram")
        self.assertIn(sub_key, price_alert_subscriptions)
        self.assertEqual(price_alert_subscriptions[sub_key]['notification_channel'], "telegram")
        self.assertEqual(price_alert_subscriptions[sub_key]['user_identifier'], "123456789")

    def test_subscribe_price_alert_update_existing(self):
        # First, create a subscription
        initial_payload = {
            "product_name": "Laptop Test",
            "user_identifier": "+51999999999",
            "notification_channel": "whatsapp",
            "desired_discount_percentage": "10"
        }
        self.client.post('/subscribe-price-alert', json=initial_payload)

        # Now, update it
        update_payload = {
            "product_name": "Laptop Test", # Same product name (case variation should be handled by .lower())
            "user_identifier": "+51999999999",
            "notification_channel": "whatsapp",
            "desired_discount_percentage": "50" # New discount
        }
        response = self.client.post('/subscribe-price-alert', json=update_payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Subscription updated successfully", data['message'])

        sub_key = ("laptop test", "+51999999999", "whatsapp")
        self.assertEqual(price_alert_subscriptions[sub_key]['desired_discount_percentage'], 0.50)

    def test_subscribe_price_alert_missing_fields(self):
        payload = {"product_name": "Laptop Test"} # Missing other fields
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing fields", data['error'])

    def test_subscribe_price_alert_invalid_phone(self):
        payload = {
            "product_name": "Laptop Test", "user_identifier": "123",
            "notification_channel": "whatsapp", "desired_discount_percentage": "10"
        }
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid phone number", data['error'])

    def test_subscribe_price_alert_invalid_chat_id(self):
        payload = {
            "product_name": "Laptop Test", "user_identifier": "abc_not_digits",
            "notification_channel": "telegram", "desired_discount_percentage": "10"
        }
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid chat_id", data['error'])

    def test_subscribe_price_alert_invalid_discount(self):
        payload = {
            "product_name": "Laptop Test", "user_identifier": "+51987654321",
            "notification_channel": "whatsapp", "desired_discount_percentage": "150" # Invalid
        }
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Discount percentage must be between 0 and 100", data['error'])

    def test_subscribe_price_alert_invalid_channel(self):
        payload = {
            "product_name": "Laptop Test", "user_identifier": "12345",
            "notification_channel": "email", "desired_discount_percentage": "10"
        }
        response = self.client.post('/subscribe-price-alert', json=payload)
        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid notification_channel", data['error'])

    # Placeholder for testing the background job check_subscribed_product_prices
    # This requires more complex mocking of scrapers and time
    @patch('backend.app.enviar_notificacion_bajada_precio_async') # Mock the actual notification sender
    @patch('backend.app.run_scraper_for_product') # Mock the helper that calls individual scrapers
    def test_check_subscribed_product_prices_notification_triggered(self, mock_run_scraper, mock_send_notification):
        # 1. Setup a subscription
        sub_product_name = "Super Laptop"
        sub_user_id = "+51911223344"
        sub_channel = "whatsapp"
        sub_key = (sub_product_name.lower(), sub_user_id, sub_channel)
        price_alert_subscriptions[sub_key] = {
            'product_name': sub_product_name,
            'user_identifier': sub_user_id,
            'notification_channel': sub_channel,
            'desired_discount_percentage': 0.20, # 20%
            'last_known_prices': {('teststore', 'http://example.com/superlaptop'): 100.00}, # Previously known price
            'notified_for_price': {}
        }

        # 2. Mock scraper results from run_scraper_for_product
        #    run_scraper_for_product is called by check_subscribed_product_prices for each scraper in ALL_SCRAPERS
        #    We need it to return a list of product items.
        #    Let's assume only one scraper for simplicity or that all return similar structure.
        scraped_item_details = {
            'nombre': sub_product_name, # Must match subscription for product name
            'precio': 75.00, # New price, 25% discount from 100
            'tienda': 'TestStore', # Note: scraper might return 'TestStore', job uses .lower() for key
            'link': 'http://example.com/superlaptop'
        }

        # Mocking ALL_SCRAPERS to control which scrapers are called.
        # The `run_scraper_for_product` is already mocked by the decorator @patch('backend.app.run_scraper_for_product').
        # We need to make this `mock_run_scraper` return our desired `scraped_item_details`.
        # It will be called with (scraper_function_from_ALL_SCRAPERS, product_name_to_search).
        # We can make it return the items if the product_name_to_search matches our sub_product_name.

        def side_effect_run_scraper(scraper_func, product_name_to_search):
            if product_name_to_search == sub_product_name:
                # Make sure the item's 'tienda' matches what `item_product_key` expects, or is handled.
                # The job does: item['tienda'] = item.get('tienda', store_name)
                # and then item_product_key = (tienda_name.lower(), item['link'])
                # Our scraped_item_details has 'tienda': 'TestStore'.
                return [scraped_item_details]
            return []

        mock_run_scraper.side_effect = side_effect_run_scraper

        # Define a dummy scraper function to be part of the patched ALL_SCRAPERS
        # This scraper_func itself doesn't need to do anything as run_scraper_for_product is mocked.
        dummy_scraper_function = MagicMock()

        with patch('backend.app.ALL_SCRAPERS', [('TestStore', dummy_scraper_function)]):
            # 3. Call the job function
            check_subscribed_product_prices()

        # 4. Assert that notification was sent
        mock_send_notification.assert_called_once()
        call_args_pos = mock_send_notification.call_args[0]
        call_args_kw = mock_send_notification.call_args[1]

        self.assertEqual(call_args_pos[0], sub_user_id) # user_identifier
        self.assertEqual(call_args_pos[1]['nombre'], sub_product_name) # product_info
        self.assertEqual(call_args_pos[1]['precio'], 75.00) # This was the new price in scraped_item_details
        self.assertEqual(call_args_pos[2], 100.00) # old_price
        self.assertEqual(call_args_pos[3], 75.00)  # new_price
        self.assertAlmostEqual(call_args_pos[4], 25.0)  # discount_percentage
        self.assertEqual(call_args_kw['notification_channel'], sub_channel)

        # 5. Assert that notified_for_price is updated
        self.assertEqual(price_alert_subscriptions[sub_key]['notified_for_price'][('teststore', 'http://example.com/superlaptop')], 75.00)
        # 6. Assert last_known_prices is updated
        self.assertEqual(price_alert_subscriptions[sub_key]['last_known_prices'][('teststore', 'http://example.com/superlaptop')], 75.00)


    @patch('backend.app.enviar_notificacion_bajada_precio_async')
    @patch('backend.app.run_scraper_for_product')
    def test_check_subscribed_product_prices_no_notification_below_threshold(self, mock_run_scraper, mock_send_notification):
        sub_product_name = "Super Laptop"
        sub_user_id = "+51911223344"
        sub_channel = "whatsapp"
        sub_key = (sub_product_name.lower(), sub_user_id, sub_channel)
        price_alert_subscriptions[sub_key] = {
            'product_name': sub_product_name,
            'user_identifier': sub_user_id,
            'notification_channel': sub_channel,
            'desired_discount_percentage': 0.20, # 20%
            'last_known_prices': {('teststore', 'http://example.com/superlaptop'): 100.00},
            'notified_for_price': {}
        }
        scraped_item_details = {
            'nombre': sub_product_name, 'precio': 85.00, # 15% discount
            'tienda': 'TestStore', 'link': 'http://example.com/superlaptop'
        }

        def side_effect_run_scraper(scraper_func, product_name_to_search):
            if product_name_to_search == sub_product_name:
                return [scraped_item_details]
            return []
        mock_run_scraper.side_effect = side_effect_run_scraper
        dummy_scraper_function = MagicMock()
        with patch('backend.app.ALL_SCRAPERS', [('TestStore', dummy_scraper_function)]):
            check_subscribed_product_prices()

        mock_send_notification.assert_not_called()
        self.assertEqual(price_alert_subscriptions[sub_key]['last_known_prices'][('teststore', 'http://example.com/superlaptop')], 85.00)


    @patch('backend.app.enviar_notificacion_bajada_precio_async')
    @patch('backend.app.run_scraper_for_product')
    def test_check_subscribed_product_prices_not_called_if_already_notified_for_same_price(self, mock_run_scraper, mock_send_notification):
        sub_product_name = "Super Laptop"
        sub_user_id = "+51911223344"
        sub_channel = "whatsapp"
        item_key_in_store = ('teststore', 'http://example.com/superlaptop')
        sub_key = (sub_product_name.lower(), sub_user_id, sub_channel)

        price_alert_subscriptions[sub_key] = {
            'product_name': sub_product_name,
            'user_identifier': sub_user_id,
            'notification_channel': sub_channel,
            'desired_discount_percentage': 0.20, # 20%
            'last_known_prices': {item_key_in_store: 100.00}, # Original price before any drop
            'notified_for_price': {item_key_in_store: 75.00} # Already notified for 75.00
        }
        # Scenario: New price is exactly the same as the one already notified for.
        scraped_item_details_same_price = {
            'nombre': sub_product_name, 'precio': 75.00, # Exactly same price as notified
            'tienda': 'TestStore', 'link': 'http://example.com/superlaptop'
        }

        def side_effect_run_scraper_same_price(scraper_func, product_name_to_search):
            if product_name_to_search == sub_product_name:
                return [scraped_item_details_same_price]
            return []
        mock_run_scraper.side_effect = side_effect_run_scraper_same_price
        dummy_scraper_function = MagicMock() # Dummy for ALL_SCRAPERS patch
        with patch('backend.app.ALL_SCRAPERS', [('TestStore', dummy_scraper_function)]):
            check_subscribed_product_prices()

        mock_send_notification.assert_not_called()
        self.assertEqual(price_alert_subscriptions[sub_key]['last_known_prices'][item_key_in_store], 75.00)
        # notified_for_price should remain 75.00
        self.assertEqual(price_alert_subscriptions[sub_key]['notified_for_price'][item_key_in_store], 75.00)


    @patch('backend.app.enviar_notificacion_bajada_precio_async')
    @patch('backend.app.run_scraper_for_product')
    def test_check_subscribed_product_prices_called_for_new_lower_price(self, mock_run_scraper, mock_send_notification):
        sub_product_name = "Super Laptop"
        sub_user_id = "+51911223344"
        sub_channel = "whatsapp"
        item_key_in_store = ('teststore', 'http://example.com/superlaptop')
        sub_key = (sub_product_name.lower(), sub_user_id, sub_channel)

        price_alert_subscriptions[sub_key] = {
            'product_name': sub_product_name,
            'user_identifier': sub_user_id,
            'notification_channel': sub_channel,
            'desired_discount_percentage': 0.20, # 20%
            'last_known_prices': {item_key_in_store: 100.00}, # Original price
            'notified_for_price': {item_key_in_store: 75.00}  # Previously notified for 75.00
        }

        scraped_item_details_lower_price = {
            'nombre': sub_product_name, 'precio': 74.00, # New, even lower price
            'tienda': 'TestStore', 'link': 'http://example.com/superlaptop'
        }
        def side_effect_run_scraper_lower_price(scraper_func, product_name_to_search):
            if product_name_to_search == sub_product_name:
                return [scraped_item_details_lower_price]
            return []
        mock_run_scraper.side_effect = side_effect_run_scraper_lower_price
        dummy_scraper_function = MagicMock() # Dummy for ALL_SCRAPERS patch
        with patch('backend.app.ALL_SCRAPERS', [('TestStore', dummy_scraper_function)]):
            check_subscribed_product_prices()

        mock_send_notification.assert_called_once()
        self.assertEqual(price_alert_subscriptions[sub_key]['last_known_prices'][item_key_in_store], 74.00)
        self.assertEqual(price_alert_subscriptions[sub_key]['notified_for_price'][item_key_in_store], 74.00)


if __name__ == '__main__':
    unittest.main()

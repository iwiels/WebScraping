import sys
import unittest
from unittest.mock import patch, MagicMock, call
import asyncio

# Now, import from backend.notifications
# We will use @patch for pywhatkit specifically in tests that need it,
# instead of a global sys.modules mock for this file.
from backend.notifications import (
    _crear_mensaje_bajada_precio,
    enviar_alerta_whatsapp_bajada_precio,
    enviar_notificacion_bajada_precio_async,
    validar_numero_telefono,
    _crear_mensaje_con_resultados,
    _crear_mensaje_sin_resultados
)

class TestNotifications(unittest.TestCase):

    def setUp(self):
        # No global MOCK_PYWHATKIT setup here anymore. Will use @patch.
        self.producto_info_sample = {
            'nombre': 'Test Product X1',
            'tienda': 'Test Store',
            'link': 'http://example.com/productx1',
            'precio': 80.00 # Current (new) price
        }
        self.old_price = 100.00
        self.new_price = 80.00
        self.discount_percentage = 20.0

    def test_crear_mensaje_bajada_precio_whatsapp(self):
        mensaje = _crear_mensaje_bajada_precio(
            self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
        )
        self.assertIn("¡ALERTA DE BAJADA DE PRECIO!", mensaje)
        self.assertIn("Test Product X1", mensaje)
        self.assertIn("Test Store", mensaje)
        self.assertIn("💰 *Precio Anterior:* S/ 100.00", mensaje) # Corrected based on function output
        self.assertIn("💸 *Nuevo Precio:* S/ 80.00", mensaje)   # Corrected based on function output
        self.assertIn("🔥 *Descuento:* 20.00%", mensaje)     # Corrected based on function output
        self.assertIn("http://example.com/productx1", mensaje)

    @patch('backend.notifications.pywhatkit')
    def test_enviar_alerta_whatsapp_bajada_precio_success(self, mock_pywhatkit):
        mock_pywhatkit.sendwhatmsg_instantly = MagicMock() # Setup mock on the patched object
        numero_destino = "+51999888777"

        result = enviar_alerta_whatsapp_bajada_precio(
            numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
        )

        self.assertTrue(result)
        mock_pywhatkit.sendwhatmsg_instantly.assert_called_once()
        args, kwargs = mock_pywhatkit.sendwhatmsg_instantly.call_args
        self.assertEqual(args[0], numero_destino)
        self.assertIn("¡ALERTA DE BAJADA DE PRECIO!", args[1])

    @patch('backend.notifications.pywhatkit')
    def test_enviar_alerta_whatsapp_bajada_precio_failure_invalid_number(self, mock_pywhatkit):
        result = enviar_alerta_whatsapp_bajada_precio(
            "123", self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
        )
        self.assertFalse(result)
        mock_pywhatkit.sendwhatmsg_instantly.assert_not_called() # Check against the mock passed to the test

    @patch('backend.notifications.pywhatkit')
    def test_enviar_alerta_whatsapp_bajada_precio_failure_pywhatkit_exception(self, mock_pywhatkit):
        mock_pywhatkit.sendwhatmsg_instantly.side_effect = Exception("PyWhatKit exploded")
        numero_destino = "+51999888777"

        result = enviar_alerta_whatsapp_bajada_precio(
            numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
        )
        self.assertFalse(result)

    @patch('backend.notifications.asyncio.run') # Outermost decorator, first arg to test method
    @patch('backend.notifications.send_price_drop_alert_telegram', new_callable=MagicMock) # Second arg
    @patch('backend.notifications.enviar_alerta_whatsapp_bajada_precio') # Innermost decorator, last arg
    def test_enviar_notificacion_bajada_precio_async_whatsapp(self, mock_whatsapp_target, mock_telegram_send_func, mock_asyncio_run_mock):
        # This tests the async dispatcher function for WhatsApp
        # mock_telegram_send_func is for the telegram path, should not be called.
        # mock_whatsapp_target is for the whatsapp path, should be called.

        # Ensure TELEGRAM_BOT_TOKEN is None or not relevant for this path, or mock it if the if condition is hit
        with patch('backend.notifications.TELEGRAM_BOT_TOKEN', None): # Explicitly make it None for this test
            numero_destino = "+51123456789"
            thread = enviar_notificacion_bajada_precio_async(
                numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage,
                notification_channel='whatsapp'
            )
            thread.join(timeout=2)

            mock_whatsapp_target.assert_called_once_with(
                numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
            )
            mock_telegram_send_func.assert_not_called()
            mock_asyncio_run_mock.assert_not_called()


    @patch('backend.notifications.asyncio.run') # Outermost decorator, first arg
    @patch('backend.notifications.send_price_drop_alert_telegram') # Middle decorator, second arg (this is the one we want to check is called by asyncio.run)
    @patch('backend.notifications.enviar_alerta_whatsapp_bajada_precio') # Innermost decorator, last arg
    def test_enviar_notificacion_bajada_precio_async_telegram(self, mock_whatsapp_target, mock_telegram_actual_send_function_ref, mock_asyncio_run_mock):
        # This tests the async dispatcher function for Telegram
        # mock_telegram_actual_send_function_ref is the reference to the real async send function.
        # mock_whatsapp_target is for the whatsapp path, should not be called.

        # We need TELEGRAM_BOT_TOKEN to be truthy for the telegram path to be taken.
        with patch('backend.notifications.TELEGRAM_BOT_TOKEN', "fake-token"):
            chat_id = "123456789"
            thread = enviar_notificacion_bajada_precio_async(
                chat_id, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage,
                notification_channel='telegram'
            )
            thread.join(timeout=1)

            mock_whatsapp_target.assert_not_called()

            # Assert that asyncio.run was called
            mock_asyncio_run_mock.assert_called_once()

            # The first argument to asyncio.run should be a coroutine.
            # This coroutine is created by calling mock_telegram_actual_send_function_ref(...)
            # So, we check that mock_telegram_actual_send_function_ref was called to create the coroutine.
            mock_telegram_actual_send_function_ref.assert_called_once_with(
                chat_id, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
            )

        numero_destino = "+51123456789"
        thread = enviar_notificacion_bajada_precio_async(
            numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage,
            notification_channel='whatsapp'
        )
        thread.join(timeout=2) # Wait for thread to execute, with a timeout, increased slightly

        mock_whatsapp_sender_target.assert_called_once_with(
            numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
        )
        mock_actual_telegram_sender.assert_not_called() # This is the send_price_drop_alert_telegram mock
        mock_asyncio_run.assert_not_called() # asyncio.run should not be called for whatsapp


    @patch('backend.notifications.asyncio.run') # Outermost decorator, first arg to test method
    @patch('backend.notifications.send_price_drop_alert_telegram', new_callable=MagicMock) # Second arg
    @patch('backend.notifications.enviar_alerta_whatsapp_bajada_precio') # Innermost decorator, last arg
    def test_enviar_notificacion_bajada_precio_async_whatsapp(self, mock_whatsapp_target, mock_telegram_send_func, mock_asyncio_run_mock):
        # This tests the async dispatcher function for WhatsApp
        # mock_telegram_send_func is for the telegram path, should not be called.
        # mock_whatsapp_target is for the whatsapp path, should be called.

        # Ensure TELEGRAM_BOT_TOKEN is None or not relevant for this path, or mock it if the if condition is hit
        with patch('backend.notifications.TELEGRAM_BOT_TOKEN', None): # Explicitly make it None for this test
            numero_destino = "+51123456789"
            thread = enviar_notificacion_bajada_precio_async(
                numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage,
                notification_channel='whatsapp'
            )
            thread.join(timeout=2)

            mock_whatsapp_target.assert_called_once_with(
                numero_destino, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
            )
            mock_telegram_send_func.assert_not_called()
            mock_asyncio_run_mock.assert_not_called()


    @patch('backend.notifications.asyncio.run') # Outermost decorator, first arg
    @patch('backend.notifications.send_price_drop_alert_telegram') # Middle decorator, second arg (this is the one we want to check is called by asyncio.run)
    @patch('backend.notifications.enviar_alerta_whatsapp_bajada_precio') # Innermost decorator, last arg
    def test_enviar_notificacion_bajada_precio_async_telegram(self, mock_whatsapp_target, mock_telegram_actual_send_function_ref, mock_asyncio_run_mock):
        # This tests the async dispatcher function for Telegram
        # mock_telegram_actual_send_function_ref is the reference to the real async send function.
        # mock_whatsapp_target is for the whatsapp path, should not be called.

        # We need TELEGRAM_BOT_TOKEN to be truthy for the telegram path to be taken.
        with patch('backend.notifications.TELEGRAM_BOT_TOKEN', "fake-token"):
            chat_id = "123456789"
            thread = enviar_notificacion_bajada_precio_async(
                chat_id, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage,
                notification_channel='telegram'
            )
            thread.join(timeout=1)

            mock_whatsapp_target.assert_not_called()

            # Assert that asyncio.run was called
            mock_asyncio_run_mock.assert_called_once()

            # The first argument to asyncio.run should be a coroutine.
            # This coroutine is created by calling mock_telegram_actual_send_function_ref(...)
            # So, we check that mock_telegram_actual_send_function_ref was called to create the coroutine.
            mock_telegram_actual_send_function_ref.assert_called_once_with(
                chat_id, self.producto_info_sample, self.old_price, self.new_price, self.discount_percentage
            )

    def test_validar_numero_telefono(self):
        self.assertEqual(validar_numero_telefono("+51987654321"), (True, "+51987654321", ""))
        self.assertEqual(validar_numero_telefono("+51 987 654 321"), (True, "+51987654321", ""))
        self.assertFalse(validar_numero_telefono("12345")[0])
        self.assertFalse(validar_numero_telefono("+51abc")[0])
        self.assertFalse(validar_numero_telefono("")[0])
        self.assertIn("requerido", validar_numero_telefono("")[2].lower())
        self.assertIn("código de país", validar_numero_telefono("987654321")[2].lower())
        self.assertIn("muy corto", validar_numero_telefono("+51123")[2].lower())
        self.assertIn("el número solo debe contener dígitos después del +", validar_numero_telefono("+51987abc321")[2].lower()) # Corrected assertion string

    def test_crear_mensaje_con_resultados(self):
        producto_buscado = "Laptop X"
        resultados = [
            {'nombre': 'Laptop X Model A', 'precio': 1500, 'tienda': 'Ripley', 'link': 'linkA', 'descuento': 10},
            {'nombre': 'Laptop X Model B', 'precio': 1200, 'tienda': 'Falabella', 'link': 'linkB'},
            {'nombre': 'Laptop X Model C', 'precio': 1800, 'tienda': 'Oechsle', 'link': 'linkC', 'descuento': 5},
        ]
        mensaje = _crear_mensaje_con_resultados(producto_buscado, resultados)
        self.assertIn("¡Ofertas encontradas para: Laptop X!", mensaje)
        self.assertIn("MEJOR OFERTA", mensaje)
        self.assertIn("Laptop X Model B", mensaje) # Mejor oferta por precio
        self.assertIn("S/ 1200.00", mensaje)
        self.assertIn("Falabella", mensaje)
        self.assertIn("Otras ofertas destacadas", mensaje)
        self.assertIn("S/ 1500.00 - Ripley", mensaje)

    def test_crear_mensaje_sin_resultados(self):
        mensaje = _crear_mensaje_sin_resultados("Producto Inexistente")
        self.assertIn("Búsqueda: Producto Inexistente", mensaje)
        self.assertIn("no encontramos ofertas", mensaje)

if __name__ == '__main__':
    unittest.main()

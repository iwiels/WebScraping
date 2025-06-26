import pywhatkit
import time
from threading import Thread
import logging
import asyncio # Added for running async telegram functions

# Conditional import for telegram_notifications, as it might not be fully configured
try:
    from .telegram_notifications import send_price_drop_alert_telegram, TELEGRAM_BOT_TOKEN
except ImportError:
    send_price_drop_alert_telegram = None
    TELEGRAM_BOT_TOKEN = None
    logging.getLogger(__name__).warning("Could not import telegram_notifications. Telegram features will be unavailable.")


# Configurar logging para notificaciones
logging.basicConfig(level=logging.INFO) # Ensure basicConfig is called, or rely on Flask's logger
logger = logging.getLogger(__name__) # Get a specific logger for this module

def enviar_alerta_whatsapp(numero_destino, producto, resultados):
    """
    Envía una notificación por WhatsApp con los resultados de la búsqueda.
    
    ADVERTENCIA: Esta función utiliza pywhatkit que automatiza WhatsApp Web.
    Esto va contra los términos de servicio de WhatsApp y puede resultar
    en el bloqueo de tu cuenta. Úsalo bajo tu propio riesgo y considera
    migrar a la API oficial de Meta para uso en producción.
    
    Args:
        numero_destino (str): Número de teléfono con código de país (ej: +51987654321)
        producto (str): Nombre del producto buscado
        resultados (list): Lista de productos encontrados
    """
    try:
        # Validar el número de teléfono
        if not numero_destino or not numero_destino.startswith('+'):
            logger.error("Error: El número debe incluir el código de país (ej: +51987654321)")
            return False
        
        # Construir el mensaje
        if not resultados:
            mensaje = _crear_mensaje_sin_resultados(producto)
        else:
            mensaje = _crear_mensaje_con_resultados(producto, resultados)
        
        logger.info(f"Enviando notificación WhatsApp a {numero_destino}")
        
        # Enviar el mensaje instantáneamente
        # Nota: wait_time=15 significa que esperará 15 segundos antes de enviar
        # tab_close=True cerrará la pestaña después del envío
        pywhatkit.sendwhatmsg_instantly(
            numero_destino, 
            mensaje, 
            wait_time=15, 
            tab_close=True,
            close_time=5
        )
        
        logger.info(f"Mensaje de WhatsApp enviado exitosamente a {numero_destino}")
        return True
        
    except Exception as e:
        logger.error(f"Error al enviar WhatsApp a {numero_destino}: {e}")
        return False

def _crear_mensaje_sin_resultados(producto):
    """Crea un mensaje cuando no se encontraron resultados."""
    return (
        f"🔍 *Búsqueda: {producto}*\n\n"
        "😔 Lo sentimos, no encontramos ofertas para este producto en este momento.\n\n"
        "💡 *Sugerencias:*\n"
        "• Intenta con palabras clave más generales\n"
        "• Revisa la ortografía\n"
        "• Prueba en unos minutos más\n\n"
        "¡Seguimos buscando las mejores ofertas para ti! 🛒✨"
    )

def _crear_mensaje_con_resultados(producto, resultados):
    """Crea un mensaje con los resultados encontrados."""
    # Ordenar por precio y tomar los mejores
    mejores_ofertas = sorted(resultados, key=lambda x: x['precio'])[:3]
    mejor_oferta = mejores_ofertas[0]
    
    mensaje = f"🎉 *¡Ofertas encontradas para: {producto}!*\n\n"
    
    # Mostrar la mejor oferta destacada
    mensaje += "🏆 *MEJOR OFERTA:*\n"
    mensaje += f"📦 {mejor_oferta['nombre'][:60]}{'...' if len(mejor_oferta['nombre']) > 60 else ''}\n"
    mensaje += f"💰 *S/ {mejor_oferta['precio']:.2f}*\n"
    mensaje += f"🏪 {mejor_oferta['tienda'].title()}\n"
    
    if mejor_oferta.get('descuento'):
        mensaje += f"🔥 ¡{mejor_oferta['descuento']}% de descuento!\n"
    
    mensaje += f"🔗 {mejor_oferta['link']}\n\n"
    
    # Mostrar otras ofertas si hay más
    if len(mejores_ofertas) > 1:
        mensaje += "📋 *Otras ofertas destacadas:*\n"
        for i, oferta in enumerate(mejores_ofertas[1:], 2):
            mensaje += f"{i}. S/ {oferta['precio']:.2f} - {oferta['tienda'].title()}\n"
        mensaje += "\n"
      # Estadísticas
    mensaje += "📊 *Resumen:*\n"
    mensaje += f"• {len(resultados)} productos encontrados\n"
    
    if len(resultados) > 1:
        precio_max = max(resultados, key=lambda x: x['precio'])['precio']
        ahorro = precio_max - mejor_oferta['precio']
        if ahorro > 0:
            mensaje += f"• Ahorras hasta S/ {ahorro:.2f} eligiendo la mejor oferta\n"
    
    mensaje += "\n¡Aprovecha estas ofertas antes de que se agoten! 🛒⚡"
    
    return mensaje

def enviar_notificacion_async(numero_destino, producto, resultados):
    """
    Envía la notificación en un hilo separado para no bloquear la aplicación.
    
    Args:
        numero_destino (str): Número de teléfono
        producto (str): Producto buscado
        resultados (list): Resultados de la búsqueda
    """
    def _enviar():
        time.sleep(2)  # Pequeña espera para asegurar que la respuesta HTTP se envíe primero
        enviar_alerta_whatsapp(numero_destino, producto, resultados)
    
    thread = Thread(target=_enviar, daemon=True)
    thread.start()
    return thread

def validar_numero_telefono(numero):
    """
    Valida que el número de teléfono tenga el formato correcto.
    
    Args:
        numero (str): Número a validar
        
    Returns:
        tuple: (es_valido, numero_limpio, mensaje_error)
    """
    if not numero:
        return False, "", "Número de teléfono requerido"
    
    # Limpiar el número
    numero_limpio = numero.strip().replace(" ", "").replace("-", "")
    
    # Verificar que comience con +
    if not numero_limpio.startswith('+'):
        return False, numero_limpio, "El número debe incluir el código de país (ej: +51987654321)"
    
    # Verificar longitud mínima (+ código país + número)
    if len(numero_limpio) < 10:
        return False, numero_limpio, "El número parece ser muy corto"
    
    # Verificar que después del + solo haya números
    if not numero_limpio[1:].isdigit():
        return False, numero_limpio, "El número solo debe contener dígitos después del +"
    
    return True, numero_limpio, ""


def _crear_mensaje_bajada_precio(producto_info, old_price, new_price, discount_percentage):
    """
    Crea un mensaje específico para una bajada de precio.

    Args:
        producto_info (dict): Información del producto (nombre, tienda, link, etc.).
        old_price (float): Precio anterior del producto.
        new_price (float): Nuevo precio del producto.
        discount_percentage (float): Porcentaje de descuento.
    """
    mensaje = f"🚨📉 *¡ALERTA DE BAJADA DE PRECIO!* 📉🚨\n\n"
    mensaje += f"El producto que sigues ha bajado de precio:\n\n"
    mensaje += f"📦 *Producto:* {producto_info['nombre'][:80]}{'...' if len(producto_info['nombre']) > 80 else ''}\n"
    mensaje += f"🏪 *Tienda:* {producto_info['tienda'].title()}\n\n"
    mensaje += f"💰 *Precio Anterior:* S/ {old_price:.2f}\n"
    mensaje += f"💸 *Nuevo Precio:* S/ {new_price:.2f}\n"
    mensaje += f"🔥 *Descuento:* {discount_percentage:.2f}%\n\n"
    mensaje += f"👉 *Aprovecha la oferta aquí:*\n{producto_info['link']}\n\n"
    mensaje += "¡No te lo pierdas! Estas ofertas pueden ser por tiempo limitado. ⏳"
    return mensaje

def enviar_alerta_whatsapp_bajada_precio(numero_destino, producto_info, old_price, new_price, discount_percentage):
    """
    Envía una notificación por WhatsApp sobre una bajada de precio.
    Misma advertencia sobre pywhatkit que enviar_alerta_whatsapp.
    """
    try:
        if not numero_destino or not numero_destino.startswith('+'):
            logger.error("Error en bajada de precio: El número debe incluir el código de país.")
            return False

        mensaje = _crear_mensaje_bajada_precio(producto_info, old_price, new_price, discount_percentage)

        logger.info(f"Enviando notificación de BAJADA DE PRECIO por WhatsApp a {numero_destino} para {producto_info['nombre']}")

        pywhatkit.sendwhatmsg_instantly(
            numero_destino,
            mensaje,
            wait_time=15,
            tab_close=True,
            close_time=5
        )

        logger.info(f"Mensaje de BAJADA DE PRECIO por WhatsApp enviado exitosamente a {numero_destino}")
        return True

    except Exception as e:
        logger.error(f"Error al enviar WhatsApp de BAJADA DE PRECIO a {numero_destino}: {e}")
        return False

def enviar_notificacion_bajada_precio_async(user_identifier: str, producto_info: dict, old_price: float, new_price: float, discount_percentage: float, notification_channel: str = 'whatsapp'):
    """
    Envía la notificación de bajada de precio en un hilo separado, choosing the channel.

    Args:
        user_identifier (str): Phone number for WhatsApp, Chat ID for Telegram.
        producto_info (dict): Information about the product.
        old_price (float): The old price.
        new_price (float): The new price.
        discount_percentage (float): The discount percentage.
        notification_channel (str): 'whatsapp' or 'telegram'.
    """
    def _enviar():
        time.sleep(2) # Pequeña espera para que la respuesta HTTP se envíe si es aplicable

        if notification_channel.lower() == 'whatsapp':
            logger.info(f"Attempting to send price drop alert via WhatsApp to {user_identifier} for {producto_info.get('nombre', 'N/A')}")
            enviar_alerta_whatsapp_bajada_precio(user_identifier, producto_info, old_price, new_price, discount_percentage)

        elif notification_channel.lower() == 'telegram':
            if send_price_drop_alert_telegram and TELEGRAM_BOT_TOKEN:
                logger.info(f"Attempting to send price drop alert via Telegram to {user_identifier} for {producto_info.get('nombre', 'N/A')}")
                try:
                    # Need to run the async function in a way that works from a sync thread
                    # asyncio.run() creates a new event loop.
                    # If an event loop is already running in this thread (unlikely for a new thread),
                    # this could be an issue. For simple threaded tasks, it's often fine.
                    asyncio.run(send_price_drop_alert_telegram(user_identifier, producto_info, old_price, new_price, discount_percentage))
                except Exception as e:
                    logger.error(f"Error running async Telegram notification from thread: {e}", exc_info=True)
            else:
                logger.warning(f"Telegram notifications are not configured or send_price_drop_alert_telegram is None. Cannot send to {user_identifier}.")
        else:
            logger.error(f"Unknown notification channel: {notification_channel} for user {user_identifier}")

    thread = Thread(target=_enviar, daemon=True)
    thread.start()
    logger.info(f"Programada notificación de bajada de precio para {producto_info.get('nombre', 'N/A')} a {user_identifier} via {notification_channel}")
    return thread

# Función para testing (solo para desarrollo)
def test_notificacion():
    """Función de prueba - NO USAR EN PRODUCCIÓN"""
    productos_prueba = [
        {
            'nombre': 'Laptop HP Pavilion 15.6" Intel Core i5',
            'precio': 2499.00,
            'tienda': 'ripley',
            'link': 'https://simple.ripley.com.pe/laptop-hp-test',
            'descuento': 15
        },
        {
            'nombre': 'Laptop Lenovo IdeaPad 14" Intel Core i3',
            'precio': 1899.00,
            'tienda': 'falabella',
            'link': 'https://falabella.com.pe/laptop-lenovo-test',
            'descuento': None
        }
    ]
    
    print("=== MENSAJE DE PRUEBA ===")
    mensaje = _crear_mensaje_con_resultados("laptop", productos_prueba)
    print(mensaje)
    print("=" * 50)

    print("=== MENSAJE DE BAJADA DE PRECIO PRUEBA ===")
    producto_bajada_prueba = {
        'nombre': 'Smart TV Samsung 55" Crystal UHD 4K',
        'precio': 1799.00, # Este sería el nuevo precio
        'tienda': 'Oechsle',
        'link': 'https://www.oechsle.pe/smart-tv-samsung-test',
        'descuento': 25 # Este es el descuento calculado sobre el precio anterior
    }
    mensaje_bajada = _crear_mensaje_bajada_precio(producto_bajada_prueba, 2399.00, 1799.00, 25.01)
    print(mensaje_bajada)
    print("=" * 50)


if __name__ == '__main__':
    # Ejecutar test
    test_notificacion()

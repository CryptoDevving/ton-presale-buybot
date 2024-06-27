import os
import requests
import asyncio
from datetime import datetime, timedelta
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAnimation
from pycoingecko import CoinGeckoAPI
from pymongo import MongoClient
from cachetools import TTLCache

# Configuración del bot y la dirección de TON
bot_token = '7485087081:AAHLD5oAYytiYmgQlOBYRg7dDOMkEKDZylQ'  # Reemplaza con tu token
ton_address = 'UQB1W1ooB95ZXfWFY-lbj29bVC0L7RCpuQ1vn5VRVvGBNwMF'  # Reemplaza con tu dirección de TON
mongo_uri = 'mongodb+srv://rain:mellamoleonel@presale-buy-bot.n3nxa6m.mongodb.net/presale-buy-bot?retryWrites=true&w=majority'  # Reemplaza con tu URI de MongoDB
gif_url = 'http://zyneteq.com/rain-token/wp-content/uploads/2024/06/icegif-442-1.gif'  # URL del GIF

# Chainbase API Configuration
chainbase_api_key = '2iSlPrev0qcJaPVMold1a1neOxo'  # Replace with your Chainbase API key
chainbase_base_url = f"https://ton-mainnet.s.chainbase.online/{chainbase_api_key}/v1/getTransactions"

bot = Bot(token=bot_token)
cg = CoinGeckoAPI()

# Configuración de MongoDB
client = MongoClient(mongo_uri)
db = client.get_default_database()
collection = db['transactions']

# Cache para el precio de TON
price_cache = TTLCache(maxsize=1, ttl=60)  # Cache con TTL de 60 segundos

# Función para obtener las transacciones de TON usando Chainbase API
async def get_latest_transactions(address):
    try:
        url = f"{chainbase_base_url}?address={address}&limit=10&lt=1&to_lt=1"
        headers = {
            'accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            print("Transacciones obtenidas correctamente.")
            return response.json().get('result', [])
        else:
            print(f"Error al obtener transacciones de TON: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error al realizar la solicitud HTTP: {e}")
        return None

# Función para obtener el precio actual de TON en USD desde CoinGecko
def get_ton_price():
    try:
        if 'ton_price' in price_cache:
            return price_cache['ton_price']
        
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "the-open-network",
            "vs_currencies": "usd"
        }
        headers = {
            "accept": "application/json"
        }
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'the-open-network' in data and 'usd' in data['the-open-network']:
                ton_price = data['the-open-network']['usd']
                price_cache['ton_price'] = ton_price
                return ton_price
            else:
                print("No se pudo encontrar el precio de TON en la respuesta de CoinGecko.")
                return None
        else:
            print(f"Error al obtener el precio de TON desde CoinGecko: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error al obtener el precio de TON desde CoinGecko: {e}")
        return None

# Función para obtener el total recaudado en USD y TON
def get_total_raised():
    try:
        url = f"https://ton-mainnet.s.chainbase.online/{chainbase_api_key}/v1/getAddressBalance?address={ton_address}"
        headers = {
            'accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'ok' in data and data['ok'] and 'result' in data:
                total_balance = int(data['result']) / 1e9  # Convertir a TON desde nanoTON
                ton_price = get_ton_price()
                if ton_price:
                    total_usd = total_balance * ton_price
                    return total_usd, total_balance
                else:
                    print("No se pudo obtener el precio de TON para calcular el total en USD.")
                    return None, None
            else:
                print(f"Error al obtener el saldo de la dirección TON: {data}")
                return None, None
        else:
            print(f"Error al obtener el saldo de la dirección TON: {response.status_code} - {response.text}")
            return None, None
    except Exception as e:
        print(f"Error al obtener el saldo de la dirección TON: {e}")
        return None, None

async def send_message_to_groups(amount_ton, amount_rain, spent_usd, ton_price, tx_id, source):
    # Redondear el monto de RAIN a dos decimales
    amount_rain_rounded = round(amount_rain, 2)
    
    try:
        # Verificar si el tx_id ya existe en MongoDB
        existing_transaction = collection.find_one({'tx_id': tx_id})
        if existing_transaction:
            print(f"El mensaje para la transacción {tx_id} ya ha sido enviado anteriormente.")
            return
        
        # Obtener total recaudado
        total_usd, total_ton = get_total_raised()
        if total_usd is not None and total_ton is not None:
            total_raised_message = f"\n💲 Total raised: ${total_usd:.2f} / {total_ton:.2f} TON"
        else:
            total_raised_message = "\nTotal raised: Not available at the moment"

        message = (f"🌧💧 *NEW PRE-SALE BUY* 🌧💧\n\n"
                   f"🏷 From Wallet: [View on Explorer](https://tonscan.com/{source})\n"
                   f"💰 Spent: ${spent_usd:.2f} ({amount_ton:.2f} TON)\n"
                   f"🌧️ Got: {amount_rain_rounded} $RAIN\n"
                   f"💲 TON Price: ${ton_price:.4f}\n"
                   f"📊 TX Id: [View on Explorer](https://tonscan.com/transactions/{tx_id})" 
                   f"{total_raised_message}")
        
        # Crear botones
        keyboard = [
            [InlineKeyboardButton("Website 🌐", url="https://zyneteq.com/rain-token"),
             InlineKeyboardButton("$RAIN News 🗞", url="https://t.me/rain_token_news")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)  # Crear el markup de los botones

        # Obtener todos los chats donde el bot es administrador
        admin_chats = get_admin_chats()
        if not admin_chats:
            print("No se encontraron chats administrados.")
            return

        for chat_id in admin_chats:
            print(f"Enviando mensaje al chat {chat_id}")
            
            # Construir la URL del GIF
            gif_url = 'https://zyneteq.com/rain-token/wp-content/uploads/2024/06/icegif-442.gif'
            
            # Enviar mensaje con GIF y botones
            await bot.send_animation(chat_id=chat_id, animation=gif_url, caption=message, parse_mode='Markdown', reply_markup=reply_markup)
            
            # Guardar detalles en MongoDB junto con 'source'
            transaction_data = {
                'amount_ton': amount_ton,
                'amount_rain': amount_rain,
                'spent_usd': spent_usd,
                'ton_price': ton_price,
                'date': datetime.now(),
                'tx_id': tx_id,
                'chat_id': chat_id,
                'source': source  # Agregar el campo 'source' al documento
            }
            collection.insert_one(transaction_data)
        
            print(f"Mensaje enviado a Telegram para la transacción {tx_id} en el chat {chat_id}")

    except Exception as e:
        print(f"Error al enviar mensaje a Telegram o guardar en MongoDB: {e}")

# Función para obtener todos los chats donde el bot es administrador
def get_admin_chats():
    try:
        admin_chats = [-1002209350662]  # Ejemplo de IDs de chat administrados
        print(f"Chats administrados por el bot: {admin_chats}")
        return admin_chats
    except Exception as e:
        print(f"Error al obtener chats administrados por el bot: {e}")
        return []

# Función principal para monitorear y enviar notificaciones de transacciones
async def monitor_transactions():
    while True:
        try:
            transactions = await get_latest_transactions(ton_address)
            if not transactions:
                continue

            for tx in transactions:
                tx_id = tx['transaction_id']['hash']
                
                # Verificar si el tx_id ya existe en MongoDB
                existing_transaction = collection.find_one({'tx_id': tx_id})
                if existing_transaction:
                    print(f"La transacción {tx_id} ya ha sido procesada anteriormente.")
                    continue
                
                in_msg = tx.get('in_msg', {})
                if 'source' not in in_msg:
                    print(f"No se encontró el campo 'source' en el mensaje de entrada (in_msg) para tx_id {tx_id}")
                    continue
                
                source = in_msg['source']
                amount_ton = int(in_msg['value']) / 1e9  # Suponiendo que el valor está en nanoTON
                ton_price = get_ton_price()
                if ton_price is None:
                    print("No se pudo obtener el precio de TON. Abortando envío de mensaje.")
                    continue
                
                amount_rain = amount_ton * 15000  # Cálculo del monto en RAIN
                spent_usd = amount_ton * ton_price
                await send_message_to_groups(amount_ton, amount_rain, spent_usd, ton_price, tx_id, source)

            await asyncio.sleep(5)  # Revisar cada 5 segundos

        except Exception as e:
            print(f"Error en el bucle principal: {e}")
            await asyncio.sleep(60)  # Esperar un minuto antes de reintentar

# Ejecutar el monitor de transacciones
async def main():
    await monitor_transactions()

# Iniciar el bot (simulación)
print("Bot is running...")
asyncio.run(main())

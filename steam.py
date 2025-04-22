import logging
import ssl
from datetime import datetime, timedelta
import asyncio

import aiohttp

import db
from poll_state import poll_state

# Configure logging
logger = logging.getLogger(__name__)

async def verify_steam_id(steam_id, steam_api_key):
    """Verify Steam ID by checking if it exists in Steam API."""
    if not steam_api_key:
        logger.warning("Steam API key not set, cannot verify Steam ID")
        return None
    
    try:
        # Create SSL context with certificate verification disabled
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={steam_api_key}&steamids={steam_id}"
            logger.info(f"Verifying Steam ID: {steam_id}")
            
            # Добавляем механизм повторных попыток для обработки ошибки 429
            max_retries = 3
            for retry in range(max_retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 429:  # Too Many Requests
                            logger.warning(f"Steam API rate limit (429) hit when verifying Steam ID {steam_id}, retry {retry+1}/{max_retries}")
                            if retry < max_retries - 1:
                                wait_time = (retry + 1) * 5  # Увеличиваем время ожидания с каждой попыткой
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"Max retries reached for Steam API request when verifying Steam ID {steam_id}")
                                return None
                                
                        if response.status != 200:
                            logger.warning(f"Steam API returned status {response.status}")
                            return None
                        
                        data = await response.json()
                        players = data.get('response', {}).get('players', [])
                        
                        if not players:
                            logger.warning(f"No player found with Steam ID: {steam_id}")
                            return None
                        
                        player_info = players[0]
                        profile_data = {
                            'steam_id': player_info.get('steamid'),
                            'username': player_info.get('personaname', 'Unknown'),
                            'profile_url': player_info.get('profileurl', ''),
                            'avatar': player_info.get('avatar', ''),
                            'status': player_info.get('personastate', 0),  # 0 = offline, 1 = online
                            'real_name': player_info.get('realname', ''),
                            'visibility': player_info.get('communityvisibilitystate', 1),  # 1 = private, 3 = public
                        }
                        
                        logger.info(f"Successfully verified Steam ID: {steam_id}, username: {profile_data['username']}")
                        return profile_data
                        
                        # Успешно получили данные, выходим из цикла
                        break
                except Exception as e:
                    logger.error(f"Error in Steam API request when verifying Steam ID {steam_id}: {e}")
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 5
                        await asyncio.sleep(wait_time)
                    else:
                        return None
    except Exception as e:
        logger.error(f"Error verifying Steam ID {steam_id}: {e}")
        return None

async def check_verification_code(steam_id, verification_code, steam_api_key):
    """
    Проверяет наличие кода верификации в имени пользователя Steam.
    Возвращает True, если код найден, иначе False.
    """
    if not steam_api_key:
        logger.warning("Steam API key not set, cannot check verification code")
        return False
    
    try:
        # Create SSL context with certificate verification disabled
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={steam_api_key}&steamids={steam_id}"
            logger.info(f"Checking verification code for Steam ID: {steam_id}")
            
            # Добавляем механизм повторных попыток для обработки ошибки 429
            max_retries = 3
            for retry in range(max_retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 429:  # Too Many Requests
                            logger.warning(f"Steam API rate limit (429) hit when checking verification code for Steam ID {steam_id}, retry {retry+1}/{max_retries}")
                            if retry < max_retries - 1:
                                wait_time = (retry + 1) * 5  # Увеличиваем время ожидания с каждой попыткой
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"Max retries reached for Steam API request when checking verification code for Steam ID {steam_id}")
                                return False
                                
                        if response.status != 200:
                            logger.warning(f"Steam API returned status {response.status}")
                            return False
                        
                        data = await response.json()
                        players = data.get('response', {}).get('players', [])
                        
                        if not players:
                            logger.warning(f"No player found with Steam ID: {steam_id}")
                            return False
                        
                        player_info = players[0]
                        username = player_info.get('personaname', '')
                        
                        # Проверяем, содержится ли код верификации в имени пользователя
                        if verification_code in username:
                            logger.info(f"Verification code '{verification_code}' found in username '{username}'")
                            return True
                        else:
                            logger.info(f"Verification code '{verification_code}' NOT found in username '{username}'")
                            return False
                            
                        # Успешно получили данные, выходим из цикла
                        break
                except Exception as e:
                    logger.error(f"Error in Steam API request when checking verification code for Steam ID {steam_id}: {e}")
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 5
                        await asyncio.sleep(wait_time)
                    else:
                        return False
    except Exception as e:
        logger.error(f"Error checking verification code for Steam ID {steam_id}: {e}")
        return False

async def check_steam_status(context, steam_api_key, send_poll_func):
    """Check if users are playing Dota 2 and notify the chat."""
    if not steam_api_key:
        logger.warning("Steam API key not set, skipping Steam status check")
        return
    
    logger.info("Starting Steam status check...")
    
    try:
        # Get Steam users from database
        steam_users, last_activities = await db.get_steam_users()
        
        logger.info(f"Found {len(steam_users)} users with Steam IDs")
        
        # Debug: Print all users with Steam IDs
        for telegram_id, steam_id, first_name, chat_id in steam_users:
            logger.info(f"User: {first_name}, Steam ID: {steam_id}, Chat ID: {chat_id}")
        
        logger.info(f"Last activities: {last_activities}")

        # Group by chat_id
        chat_users = {}
        for telegram_id, steam_id, first_name, chat_id in steam_users:
            if not chat_id:  # Skip if no chat_id
                logger.warning(f"Skipping user {first_name} because no chat_id is associated")
                continue
            
            # Проверяем, привязан ли Steam ID конкретно к этому чату
            is_linked = await db.is_steam_id_linked_to_chat(telegram_id, chat_id)
            if not is_linked:
                logger.warning(f"Skipping user {first_name} because Steam ID not linked to chat {chat_id}")
                continue
                
            if chat_id not in chat_users:
                chat_users[chat_id] = []

            last_poll_end = None
            if chat_id in last_activities:
                last_poll_end = datetime.fromisoformat(last_activities[chat_id]) if last_activities[chat_id] else None
                logger.info(f"Last poll end for chat {chat_id}: {last_poll_end}")

            chat_users[chat_id].append({
                'telegram_id': telegram_id,
                'steam_id': steam_id,
                'first_name': first_name,
                'last_poll_end': last_poll_end
            })

        logger.info(f"Checking {len(chat_users)} chats for players")
        
        # Check each chat
        for chat_id, users in chat_users.items():
            # Skip if there's already an active poll
            if poll_state.is_active(chat_id):
                logger.info(f"Skipping chat {chat_id} because there's an active poll")
                continue

            logger.info(f"Checking {len(users)} users in chat {chat_id}")
            
            # Get users who might be playing Dota 2
            dota_players = []

            for user in users:
                # Skip if last poll end was less than 2 hours ago
                if user['last_poll_end'] and datetime.now() - user['last_poll_end'] < timedelta(hours=2):
                    logger.info(f"Skipping user {user['first_name']} because last poll was less than 2 hours ago")
                    continue

                # Check Steam status
                steam_id = user['steam_id']
                logger.info(f"Checking Steam status for {user['first_name']} (Steam ID: {steam_id})")

                try:
                    # Create SSL context with certificate verification disabled
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    
                    # Добавляем задержку между запросами, чтобы избежать ограничений API
                    await asyncio.sleep(2)
                    
                    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={steam_api_key}&steamids={steam_id}"
                        
                        # Добавляем механизм повторных попыток для обработки ошибки 429
                        max_retries = 3
                        for retry in range(max_retries):
                            try:
                                async with session.get(url) as response:
                                    if response.status == 429:  # Too Many Requests
                                        logger.warning(f"Steam API rate limit (429) hit for user {user['first_name']}, retry {retry+1}/{max_retries}")
                                        if retry < max_retries - 1:
                                            wait_time = (retry + 1) * 5  # Увеличиваем время ожидания с каждой попыткой
                                            await asyncio.sleep(wait_time)
                                            continue
                                        else:
                                            logger.error(f"Max retries reached for Steam API request for user {user['first_name']}")
                                            break
                                            
                                    if response.status != 200:
                                        logger.error(f"Steam API returned status {response.status} for user {user['first_name']}")
                                        break
                                        
                                    data = await response.json()
                                    logger.info(f"Steam API response for {user['first_name']}: {data}")
                                    
                                    players = data.get('response', {}).get('players', [])
                                    if players:
                                        player = players[0]
                                        logger.info(f"Player {user['first_name']} status: {player.get('gameextrainfo', 'Not in game')} (Game ID: {player.get('gameid', 'None')})")
                                        
                                        # Check if playing Dota 2 (game ID 570)
                                        if player.get('gameid') == "570":
                                            logger.info(f"User {user['first_name']} is playing Dota 2!")
                                            dota_players.append(user['first_name'])
                                    else:
                                        logger.warning(f"No player data found for Steam ID: {steam_id}")
                                        
                                    # Успешно получили данные, выходим из цикла
                                    break
                            except Exception as e:
                                logger.error(f"Error in Steam API request for {user['first_name']}: {e}")
                                if retry < max_retries - 1:
                                    wait_time = (retry + 1) * 5
                                    await asyncio.sleep(wait_time)
                                else:
                                    break
                except Exception as e:
                    logger.error(f"Error checking Steam status for {steam_id}: {e}")

            # If at least one person is playing Dota 2, send notification
            if dota_players:
                logger.info(f"Found Dota 2 players in chat {chat_id}: {dota_players}")
                
                # Формируем сообщение в зависимости от количества игроков
                if len(dota_players) == 1:
                    message = f"{dota_players[0]} уже вовсю начал сасать в Дотке, присоединяйтесь!"
                elif len(dota_players) >= 2:
                    # Для 2 и более игроков
                    players_list = ", ".join(dota_players[:-1]) + " и " + dota_players[-1]
                    message = f"{players_list} уже вовсю начали сасать в Дотке, присоединяйтесь!"
                
                # Отправляем сообщение вместо опроса
                await context.bot.send_message(chat_id=chat_id, text=message)
            else:
                logger.info(f"No Dota 2 players found in chat {chat_id}")

        logger.info("Steam status check completed")

    except Exception as e:
        logger.error(f"Error in Steam status checker: {e}")
        import traceback
        logger.error(traceback.format_exc())

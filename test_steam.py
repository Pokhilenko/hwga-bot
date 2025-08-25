import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

import steam


class TestSteam(unittest.TestCase):
    @patch("steam.aiohttp.ClientSession")
    async def test_send_steam_request_success(self, mock_session):
        """Test successful Steam API request"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"response": {"players": [{"steamid": "123"}]}}

        mock_session.return_value.__aenter__.return_value.get.return_value = mock_response

        result = await steam._send_steam_request("123", "test_api_key", "test action")

        self.assertEqual(result, {"response": {"players": [{"steamid": "123"}]}})

    @patch("steam.aiohttp.ClientSession")
    async def test_send_steam_request_rate_limit(self, mock_session):
        """Test Steam API rate limit handling"""
        mock_response_429 = AsyncMock()
        mock_response_429.status = 429

        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json.return_value = {"response": {"players": [{"steamid": "123"}]}}

        # Simulate one rate limit error, then a success
        mock_session.return_value.__aenter__.return_value.get.side_effect = [
            mock_response_429,
            mock_response_200,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await steam._send_steam_request(
                "123", "test_api_key", "test action"
            )

        self.assertEqual(result, {"response": {"players": [{"steamid": "123"}]}})

    @patch("steam._send_steam_request")
    async def test_verify_steam_id_success(self, mock_send_request):
        """Test successful Steam ID verification"""
        mock_send_request.return_value = {
            "response": {
                "players": [
                    {
                        "steamid": "123",
                        "personaname": "test_user",
                        "profileurl": "test_url",
                        "avatar": "test_avatar",
                        "personastate": 1,
                        "realname": "test_real_name",
                        "communityvisibilitystate": 3,
                    }
                ]
            }
        }

        result = await steam.verify_steam_id("123", "test_api_key")

        self.assertEqual(result["steam_id"], "123")
        self.assertEqual(result["username"], "test_user")

    @patch("steam._send_steam_request")
    async def test_check_verification_code_success(self, mock_send_request):
        """Test successful verification code check"""
        mock_send_request.return_value = {
            "response": {"players": [{"personaname": "test_user_12345"}]}
        }

        result = await steam.check_verification_code("123", "12345", "test_api_key")

        self.assertTrue(result)

    @patch("steam.db.get_steam_users")
    @patch("steam.db.is_steam_id_linked_to_chat")
    @patch("steam.poll_state.is_active")
    @patch("steam.aiohttp.ClientSession")
    async def test_check_steam_status(
        self, mock_session, mock_is_active, mock_is_linked, mock_get_users
    ):
        """Test the check_steam_status function"""
        mock_get_users.return_value = ([
            ("user1", "steam1", "name1", "chat1"),
            ("user2", "steam2", "name2", "chat1"),
        ], {})
        mock_is_linked.return_value = True
        mock_is_active.return_value = False

        mock_response1 = AsyncMock()
        mock_response1.status = 200
        mock_response1.json.return_value = {
            "response": {"players": [{"gameid": "570", "gameextrainfo": "Dota 2"}]}
        }

        mock_response2 = AsyncMock()
        mock_response2.status = 200
        mock_response2.json.return_value = {"response": {"players": [{}]}}

        mock_session.return_value.__aenter__.return_value.get.side_effect = [
            mock_response1,
            mock_response2,
        ]

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await steam.check_steam_status(mock_context, "test_api_key", AsyncMock())

        mock_context.bot.send_message.assert_called_once()

    @patch("steam.db.safe_db_connect")
    @patch("steam.aiohttp.ClientSession")
    async def test_get_steam_player_statuses(self, mock_session, mock_db_connect):
        """Test the get_steam_player_statuses function"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("user1", "steam1", "name1")]
        mock_db_connect.return_value.__enter__.return_value.cursor.return_value = (
            mock_cursor
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "response": {"players": [{"gameid": "570", "gameextrainfo": "Dota 2"}]}
        }
        mock_session.return_value.__aenter__.return_value.get.return_value = mock_response

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await steam.get_steam_player_statuses("chat1", "test_api_key")

        self.assertIn("В Dota 2:", result)


if __name__ == "__main__":
    unittest.main()
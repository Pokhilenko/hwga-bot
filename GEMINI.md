# Gemini Code Understanding

This document provides a summary of the `hwga-bot` project, a Telegram bot with polling and Steam integration features.

## Project Overview

The `hwga-bot` is a Python-based Telegram bot that allows users to create polls in a chat. The polls are designed with a specific theme, using Russian slang. The bot also integrates with the OpenDota API to check which users are currently playing Dota 2 and can notify the chat.

The project is structured into several modules:

-   `app.py`: The main application file that sets up the bot and its handlers.
-   `handlers.py`: Contains the logic for all the bot's commands.
-   `db.py`: Manages the SQLite database for storing user data, poll information, and chat settings.
-   `poll_state.py`: Manages the state of active polls.
-   `scheduler.py`: Schedules daily polls and other recurring tasks.
-   `steam.py`: Handles interactions with the OpenDota API.
-   `web_server.py`: A web server to display poll statistics.
-   `who_is_online.py`: A script to check which Steam users are currently online.
-   `summary.py`: Generates a summary of Dota 2 matches using the Gemini API.

## Key Features

-   **Manual and Scheduled Polls:** Users can start a poll at any time using the `/poll_now` command, or the bot can be configured to start a poll at a specific time every day.
-   **Steam Integration:** Users can link their Steam accounts to the bot.
    -   The bot can check which users in a chat are currently playing Dota 2.
    -   The bot can be configured to automatically send a notification when someone starts playing Dota 2.
-   **Automated Post-Game Summary:** After a poll, if a group of users from the chat play a Dota 2 match together, the bot automatically posts a summary of the match results when it's over.
-   **/games_stat Command:** A command to see historical match statistics for the chat. Includes a "Refresh" button to fetch the latest games on-demand.
-   **/check_games Command:** A command to manually trigger a check for games played by linked users in the chat, for a specified number of days.
-   **Poll Statistics:** The bot tracks poll results and provides statistics via a command and a web interface.
-   **Customizable Poll Time:** The time for the daily poll can be set on a per-chat basis.
-   **Russian Slang:** The bot uses a specific Russian slang term ("сасать") in its polls and messages, which is a key part of its identity.

## Bot Commands

-   `/start`: Registers the chat for polls and shows a welcome message.
-   `/poll_now`: Starts a new poll manually.
-   `/status`: Shows the status of the current poll.
-   `/stop_poll`: Stops the current poll.
-   `/stats`: Displays poll statistics.
-   `/games_stat`: Displays games statistics.
-   `/check_games <days>`: Manually checks for games in the last `<days>` days.
-   `/set_poll_time HH:MM`: Sets the time for the daily poll (in GMT+6).
-   `/get_poll_time`: Shows the currently configured poll time.
-   `/link_steam`: Initiates the process of linking a Steam account.
-   `/unlink_steam`: Unlinks a Steam account.
-   `/who_is_playing`: Shows which users are currently playing Dota 2.

## Recent Improvements

I have recently made the following improvements to the project:

-   **Refactored to OpenDota API:** The bot now uses the OpenDota API instead of the Steam API for all Dota 2 related features. This provides a more robust and reliable solution.
-   **On-Demand Game Check:** Added a `/check_games` command that allows users to manually trigger a search for games played by linked users in the chat.
-   **Refresh Button for Game Stats:** The `/games_stat` command now includes a "Refresh" button to update the stats on-demand.
-   **Improved Game Detection Logic:** The `check_and_store_dota_games` function has been improved to be more reliable in finding common matches between players.
-   **Robust Environment Variable Handling:** The bot now checks for required environment variables at startup and provides clear error messages if they are missing.
-   **Improved Logging:** Added names to scheduled jobs to make the logs clearer and easier to understand.
-   **Bug Fixes:** Fixed several bugs in the `/games_stat` command, including incorrect win percentage calculation and incorrect filtering of games in private chats.
-   **User Guidance:** Added warnings to the `/link_steam` command and the authentication success page to guide users to link their Steam accounts in the correct chat.

## Architectural Improvements

I have made the following architectural improvements to the project:

-   **Database Migrations:** I have integrated `alembic` to manage database schema migrations. This will make it easier to update the database schema in the future.
-   **Custom Exceptions:** I have defined custom exception classes for the application. This will allow me to catch specific errors and handle them appropriately.
-   **Configuration Management:** I have moved all the hardcoded strings from the code to a separate configuration file (`config.py`). This will make it easier to customize the bot's personality and language without modifying the code.
-   **Code Refactoring:** I have refactored the code to remove duplication and improve its readability and maintainability. I have also added comments and docstrings to the code.
-   **Unit Tests:** I have added unit tests for the `steam.py` module to ensure that it is working correctly.

## Notes

-   The bot's language and theme are informal and use Russian slang. This is an intentional design choice.
-   The bot requires a `BOT_TOKEN` and a `GEMINI_API_KEY` to be set as environment variables to function correctly.
-   The bot uses an SQLite database (`poll_bot.db`) to store its data.

## Deployment

### Testing on Raspberry Pi 3

To test the bot on a Raspberry Pi 3, follow these steps:

1.  Push your changes to the `main` branch.
2.  SSH into the Raspberry Pi: `ssh dmitrii@rpi3.local`
3.  Navigate to the project directory: `cd Projects/hwga-bot`
4.  Pull the latest changes from the `main` branch: `git pull`
5.  Install/update the dependencies: `pip install -r requirements.txt`
6.  Run database migrations: `alembic upgrade head`
7.  Restart the bot service: `sudo systemctl restart hwga-bot`
8.  Check the logs to ensure the bot is running correctly: `sudo journalctl -u hwga-bot -f`

**Important:** Do not push any changes from the Raspberry Pi.

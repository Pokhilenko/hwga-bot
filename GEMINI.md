# Gemini Code Understanding

This document provides a summary of the `hwga-bot` project, a Telegram bot with polling and Steam integration features.

## Project Overview

The `hwga-bot` is a Python-based Telegram bot that allows users to create polls in a chat. The polls are designed with a specific theme, using Russian slang. The bot also integrates with Steam to check which users are currently playing Dota 2 and can notify the chat.

The project is structured into several modules:

-   `app.py`: The main application file that sets up the bot and its handlers.
-   `handlers.py`: Contains the logic for all the bot's commands.
-   `db.py`: Manages the SQLite database for storing user data, poll information, and chat settings.
-   `poll_state.py`: Manages the state of active polls.
-   `scheduler.py`: Schedules daily polls and other recurring tasks.
-   `steam.py`: Handles interactions with the Steam API.
-   `web_server.py`: A web server to display poll statistics.
-   `who_is_online.py`: A script to check which Steam users are currently online.

## Key Features

-   **Manual and Scheduled Polls:** Users can start a poll at any time using the `/pol_now` command, or the bot can be configured to start a poll at a specific time every day.
-   **Steam Integration:** Users can link their Steam accounts to the bot.
    -   The bot can check which users in a chat are currently playing Dota 2.
    -   The bot can be configured to automatically send a notification when someone starts playing Dota 2.
-   **Poll Statistics:** The bot tracks poll results and provides statistics via a command and a web interface.
-   **Customizable Poll Time:** The time for the daily poll can be set on a per-chat basis.
-   **Russian Slang:** The bot uses a specific Russian slang term ("сасать") in its polls and messages, which is a key part of its identity.

## Bot Commands

-   `/start`: Registers the chat for polls and shows a welcome message.
-   `/pol_now`: Starts a new poll manually.
-   `/status`: Shows the status of the current poll.
-   `/stop_poll`: Stops the current poll.
-   `/stats`: Displays poll statistics.
-   `/set_poll_time HH:MM`: Sets the time for the daily poll (in GMT+6).
-   `/get_poll_time`: Shows the currently configured poll time.
-   `/link_steam`: Initiates the process of linking a Steam account.
-   `/unlink_steam`: Unlinks a Steam account.
-   `/who_is_playing`: Shows which users are currently playing Dota 2.

## Architectural Improvements

I have made the following architectural improvements to the project:

-   **Database Migrations:** I have integrated `alembic` to manage database schema migrations. This will make it easier to update the database schema in the future.
-   **Custom Exceptions:** I have defined custom exception classes for the application. This will allow me to catch specific errors and handle them appropriately.
-   **Configuration Management:** I have moved all the hardcoded strings from the code to a separate configuration file (`config.py`). This will make it easier to customize the bot's personality and language without modifying the code.
-   **Code Refactoring:** I have refactored the code to remove duplication and improve its readability and maintainability. I have also added comments and docstrings to the code.
-   **Unit Tests:** I have added unit tests for the `steam.py` module to ensure that it is working correctly.

## Notes

-   The bot's language and theme are informal and use Russian slang. This is an intentional design choice.
-   The bot requires a `BOT_TOKEN` and a `STEAM_API_KEY` to be set as environment variables to function correctly.
-   The bot uses an SQLite database (`poll_bot.db`) to store its data.
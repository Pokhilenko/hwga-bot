import logging
import os
import json
import asyncio
from datetime import datetime
from aiohttp import web
import socket
import sqlite3
import pathlib
import secrets
import re
import aiohttp
import ssl

import db
from db import DB_FILE  # Import DB_FILE constant

# Configure logging
logger = logging.getLogger(__name__)

# Настройки сервера
DEV_MODE = os.environ.get('BOT_ENV', 'dev') == 'dev'
DEV_HOST = '0.0.0.0'
DEV_PORT = 8081
PROD_HOST = os.environ.get('PROD_HOST', socket.gethostbyname(socket.gethostname()))
PROD_PORT = int(os.environ.get('PROD_PORT', 8081))

HOST = DEV_HOST if DEV_MODE else PROD_HOST
PORT = DEV_PORT if DEV_MODE else PROD_PORT

# Steam OpenID configuration
STEAM_OPENID_URL = 'https://steamcommunity.com/openid/login'
STEAM_API_KEY = os.environ.get('STEAM_API_KEY', '')

# Хранение временных состояний и связок telegram_id <-> код сессии
steam_auth_sessions = {}  # session_id -> (telegram_id, chat_id)
telegram_auth_requests = {}  # telegram_id -> session_id

# Database file
DATABASE = DB_FILE

# Путь к статическим файлам
STATIC_DIR = pathlib.Path(__file__).parent / 'static'
os.makedirs(STATIC_DIR, exist_ok=True)

# Шаблон для HTML-страницы
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Статистика опросов</title>
    <style>
        :root {{
            --primary-color: #5865F2;
            --secondary-color: #4752C4;
            --text-color: #F2F3F5;
            --bg-color: #36393F;
            --card-bg: #2F3136;
            --accent-color: #FFCC4D;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            color: var(--accent-color);
        }}
        .stats-card {{
            background-color: var(--card-bg);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        }}
        .stats-title {{
            font-size: 1.5em;
            margin-bottom: 15px;
            color: var(--primary-color);
            border-bottom: 2px solid var(--primary-color);
            padding-bottom: 5px;
        }}
        .stats-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            padding: 10px;
            border-bottom: 1px solid #444;
        }}
        .stats-label {{
            font-weight: bold;
        }}
        .stats-value {{
            color: var(--accent-color);
        }}
        .chart-container {{
            margin-top: 30px;
            height: 300px;
        }}
        .poll-history {{
            margin-top: 30px;
        }}
        .poll-item {{
            background-color: var(--card-bg);
            border-left: 4px solid var(--primary-color);
            padding: 10px 15px;
            margin-bottom: 10px;
            border-radius: 0 5px 5px 0;
        }}
        .poll-time {{
            color: var(--accent-color);
            font-size: 0.9em;
        }}
        .poll-votes {{
            margin-top: 5px;
            font-style: italic;
        }}
        .option-bar {{
            height: 20px;
            background-color: var(--primary-color);
            margin: 5px 0;
            border-radius: 3px;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            border-top: 1px solid #444;
            font-size: 0.9em;
            color: #999;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Статистика опросов Хатим сасать!?!?!</h1>
            <p>Чат: {{chat_name}}</p>
        </div>
        
        <div class="stats-card">
            <div class="stats-title">Общая статистика</div>
            <div class="stats-row">
                <span class="stats-label">Всего опросов:</span>
                <span class="stats-value">{{total_polls}}</span>
            </div>
            <div class="stats-row">
                <span class="stats-label">Среднее время запуска:</span>
                <span class="stats-value">{{avg_time}}</span>
            </div>
            <div class="stats-row">
                <span class="stats-label">Самый популярный ответ:</span>
                <span class="stats-value">{{most_popular}}</span>
            </div>
            <div class="stats-row">
                <span class="stats-label">Всего голосов:</span>
                <span class="stats-value">{{total_votes}}</span>
            </div>
        </div>
        
        <div class="stats-card">
            <div class="stats-title">Распределение ответов</div>
            <div class="chart-container">
                <canvas id="optionsChart"></canvas>
            </div>
        </div>
        
        <div class="stats-card poll-history">
            <div class="stats-title">История последних опросов</div>
            {{poll_history}}
        </div>
        
        <div class="footer">
            <p>Сгенерировано {{generation_time}}</p>
        </div>
    </div>
    
    <script>
        const ctx = document.getElementById('optionsChart').getContext('2d');
        const optionsChart = new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {{options_labels}},
                datasets: [{{
                    label: 'Количество голосов',
                    data: {{options_data}},
                    backgroundColor: [
                        '#5865F2',
                        '#57F287',
                        '#ED4245',
                        '#FEE75C', 
                        '#EB459E'
                    ],
                    borderColor: [
                        '#4752C4',
                        '#45C16C',
                        '#D63037',
                        '#EDD04A',
                        '#CF3B89'
                    ],
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            color: '#F2F3F5'
                        }},
                        grid: {{
                            color: '#444'
                        }}
                    }},
                    x: {{
                        ticks: {{
                            color: '#F2F3F5'
                        }},
                        grid: {{
                            color: '#444'
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        labels: {{
                            color: '#F2F3F5'
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

async def get_detailed_poll_stats(chat_id, poll_options):
    """Получает детальную статистику по опросам для конкретного чата"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Получаем имя чата (если есть)
        chat_name = ""
        c.execute("SELECT chat_name FROM chat_settings WHERE chat_id = ?", (chat_id,))
        result = c.fetchone()
        if result:
            chat_name = result["chat_name"]
        
        # Общее количество опросов
        c.execute("SELECT COUNT(*) FROM polls WHERE chat_id = ?", (chat_id,))
        total_polls = c.fetchone()[0]
        
        # Общее количество голосов
        c.execute("""
            SELECT COUNT(*) FROM votes v
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ?
        """, (chat_id,))
        total_votes = c.fetchone()[0]
        
        # Среднее количество голосов на опрос
        avg_votes_per_poll = total_votes / total_polls if total_polls > 0 else 0
        
        # Популярность ответов
        option_votes = [0] * len(poll_options)
        c.execute("""
            SELECT option_index, COUNT(*) as count FROM votes v
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ? 
            GROUP BY option_index
            ORDER BY option_index
        """, (chat_id,))
        for row in c.fetchall():
            option_index = row["option_index"]
            if 0 <= option_index < len(option_votes):
                option_votes[option_index] = row["count"]
        
        # Активные пользователи
        c.execute("""
            SELECT u.first_name || ' ' || COALESCE(u.last_name, '') as name FROM users u
            JOIN votes v ON u.telegram_id = v.user_id
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ?
            GROUP BY u.telegram_id
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """, (chat_id,))
        active_users = [row["name"].strip() for row in c.fetchall()]
        
        # Среднее время голосования
        c.execute("""
            SELECT AVG(strftime('%s', v.response_time) - strftime('%s', p.trigger_time)) as avg_time
            FROM votes v
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ?
        """, (chat_id,))
        avg_seconds = c.fetchone()[0] or 0
        avg_minutes = int(avg_seconds / 60)
        avg_vote_time = f"{avg_minutes} мин"
        
        # Последние опросы
        c.execute("""
            SELECT p.id, p.trigger_time 
            FROM polls p 
            WHERE p.chat_id = ? 
            ORDER BY p.trigger_time DESC 
            LIMIT 5
        """, (chat_id,))
        recent_polls = []
        
        for row in c.fetchall():
            poll_id = row["id"]
            poll_time = datetime.fromisoformat(row["trigger_time"]).strftime("%d.%m.%Y %H:%M")
            
            # Голоса для каждого опроса
            c.execute("""
                SELECT option_index, COUNT(*) as count
                FROM votes
                WHERE poll_id = ?
                GROUP BY option_index
                ORDER BY option_index
            """, (poll_id,))
            
            poll_votes = [0] * len(poll_options)
            for vote in c.fetchall():
                option_index = vote["option_index"]
                if 0 <= option_index < len(poll_votes):
                    poll_votes[option_index] = vote["count"]
            
            recent_polls.append({
                "time": poll_time,
                "votes": poll_votes
            })
        
        # Данные для таблицы голосов по пользователям
        c.execute("""
            SELECT 
                u.telegram_id, 
                u.first_name || ' ' || COALESCE(u.last_name, '') as name,
                v.option_index,
                COUNT(*) as vote_count
            FROM users u
            JOIN votes v ON u.telegram_id = v.user_id
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ?
            GROUP BY u.telegram_id, v.option_index
            ORDER BY u.telegram_id, v.option_index
        """, (chat_id,))
        
        user_votes_data = {}
        for row in c.fetchall():
            user_id = row["telegram_id"]
            user_name = row["name"].strip()
            option_index = row["option_index"]
            vote_count = row["vote_count"]
            
            if user_name not in user_votes_data:
                user_votes_data[user_name] = [0] * len(poll_options)
            
            if 0 <= option_index < len(poll_options):
                user_votes_data[user_name][option_index] = vote_count
        
        # Данные для таблицы голосов по дням недели
        c.execute("""
            SELECT 
                strftime('%w', p.trigger_time) as weekday,
                v.option_index,
                COUNT(*) as vote_count
            FROM votes v
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ?
            GROUP BY weekday, v.option_index
            ORDER BY weekday, v.option_index
        """, (chat_id,))
        
        weekday_votes_data = {}
        weekday_names = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        
        for row in c.fetchall():
            weekday_idx = int(row["weekday"])
            weekday = weekday_names[weekday_idx]
            option_index = row["option_index"]
            vote_count = row["vote_count"]
            
            if weekday not in weekday_votes_data:
                weekday_votes_data[weekday] = [0] * len(poll_options)
            
            if 0 <= option_index < len(poll_options):
                weekday_votes_data[weekday][option_index] = vote_count
        
        # Данные для таблицы голосов по времени суток
        c.execute("""
            SELECT 
                CASE
                    WHEN strftime('%H', p.trigger_time) BETWEEN '06' AND '11' THEN 'Утро'
                    WHEN strftime('%H', p.trigger_time) BETWEEN '12' AND '17' THEN 'День'
                    WHEN strftime('%H', p.trigger_time) BETWEEN '18' AND '23' THEN 'Вечер'
                    ELSE 'Ночь'
                END as time_of_day,
                v.option_index,
                COUNT(*) as vote_count
            FROM votes v
            JOIN polls p ON v.poll_id = p.id
            WHERE p.chat_id = ?
            GROUP BY time_of_day, v.option_index
            ORDER BY 
                CASE time_of_day
                    WHEN 'Утро' THEN 1
                    WHEN 'День' THEN 2
                    WHEN 'Вечер' THEN 3
                    WHEN 'Ночь' THEN 4
                END, v.option_index
        """, (chat_id,))
        
        time_votes_data = {}
        for row in c.fetchall():
            time_of_day = row["time_of_day"]
            option_index = row["option_index"]
            vote_count = row["vote_count"]
            
            if time_of_day not in time_votes_data:
                time_votes_data[time_of_day] = [0] * len(poll_options)
            
            if 0 <= option_index < len(poll_options):
                time_votes_data[time_of_day][option_index] = vote_count
        
        # Формируем итоговую структуру данных
        stats_data = {
            "chat_id": chat_id,
            "chat_name": chat_name,
            "total_polls": total_polls,
            "total_votes": total_votes,
            "avg_votes_per_poll": avg_votes_per_poll,
            "active_users": active_users,
            "poll_options": poll_options,
            "option_votes": option_votes,
            "avg_vote_time": avg_vote_time,
            "recent_polls": recent_polls,
            "user_votes_data": user_votes_data,
            "weekday_votes_data": weekday_votes_data,
            "time_votes_data": time_votes_data
        }
        
        return stats_data
    
    except Exception as e:
        logger.error(f"Error in get_detailed_poll_stats: {e}", exc_info=True)
        raise
    finally:
        conn.close()

def format_poll_history(poll_history, poll_options):
    """Форматирует историю опросов в HTML"""
    if not poll_history:
        return "<p>История опросов отсутствует</p>"
    
    html = ""
    for poll in poll_history:
        html += f"""
        <div class="poll-item">
            <div class="poll-time">{poll['time']}</div>
            <div class="poll-votes">Всего голосов: {sum(poll['votes'])}</div>
        """
        
        for i, option in enumerate(poll_options):
            votes = poll['votes'][i]
            max_votes = max(poll['votes']) if any(poll['votes']) else 1
            percentage = (votes / max_votes) * 100 if max_votes > 0 else 0
            
            html += f"""
            <div style="margin-top: 8px;">
                <div>{option}: {votes}</div>
                <div class="option-bar" style="width: {percentage}%"></div>
            </div>
            """
        
        html += "</div>"
    
    return html

def generate_stats_html(stats_data):
    """Генерирует HTML-страницу со статистикой"""
    try:
        chat_id = stats_data["chat_id"]
        chat_name = stats_data["chat_name"]
        total_polls = stats_data["total_polls"]
        total_votes = stats_data["total_votes"] 
        avg_votes_per_poll = stats_data["avg_votes_per_poll"]
        active_users = stats_data["active_users"]
        poll_options = stats_data["poll_options"]
        option_votes = stats_data["option_votes"]
        avg_vote_time = stats_data["avg_vote_time"]
        recent_polls = stats_data["recent_polls"]
        user_votes_data = stats_data["user_votes_data"]
        weekday_votes_data = stats_data["weekday_votes_data"]
        time_votes_data = stats_data["time_votes_data"]

        # Определяем название чата для отображения
        display_chat_name = chat_name if chat_name else f"Чат {chat_id}"
        
        # Начало HTML документа с нашим CSS
        html = f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Статистика опросов - {display_chat_name}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f5f5f5;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                header {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 20px 0;
                    text-align: center;
                    margin-bottom: 30px;
                    border-radius: 5px;
                    position: relative;
                }}
                .refresh-button {{
                    position: absolute;
                    top: 20px;
                    right: 20px;
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    font-size: 18px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: background-color 0.3s;
                }}
                .refresh-button:hover {{
                    background-color: #2980b9;
                }}
                h1, h2, h3 {{
                    margin-top: 0;
                }}
                .stats-card {{
                    background-color: white;
                    border-radius: 5px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    padding: 20px;
                    margin-bottom: 30px;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .stat-box {{
                    background-color: #e8f4fc;
                    border-radius: 5px;
                    padding: 15px;
                    text-align: center;
                }}
                .stat-number {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2980b9;
                    margin: 10px 0;
                }}
                .options-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                .options-table th, .options-table td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                .options-table th {{
                    background-color: #f2f2f2;
                }}
                .options-table tr:hover {{
                    background-color: #f9f9f9;
                }}
                .bar-container {{
                    width: 100%;
                    background-color: #f1f1f1;
                    border-radius: 4px;
                    margin-top: 5px;
                }}
                .bar {{
                    height: 20px;
                    border-radius: 4px;
                    background-color: #4CAF50;
                }}
                .poll-history {{
                    margin-top: 30px;
                }}
                .poll-item {{
                    background-color: white;
                    border-radius: 5px;
                    padding: 15px;
                    margin-bottom: 15px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                }}
                .poll-time {{
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                .poll-option {{
                    display: flex;
                    align-items: center;
                    margin-bottom: 8px;
                }}
                .option-label {{
                    width: 150px;
                    flex-shrink: 0;
                }}
                .option-votes {{
                    margin-left: 10px;
                    font-weight: bold;
                }}
                .option-bar {{
                    height: 20px;
                    background-color: #3498db;
                    border-radius: 3px;
                }}
                .section-tabs {{
                    display: flex;
                    margin-bottom: 20px;
                    overflow-x: auto;
                }}
                .tab {{
                    padding: 10px 20px;
                    background-color: #f1f1f1;
                    border: 1px solid #ddd;
                    cursor: pointer;
                    transition: 0.3s;
                    text-align: center;
                    flex: 1;
                }}
                .tab:hover {{
                    background-color: #ddd;
                }}
                .tab.active {{
                    background-color: #2c3e50;
                    color: white;
                }}
                .section-content {{
                    display: none;
                }}
                .section-content.active {{
                    display: block;
                }}
                @media (max-width: 768px) {{
                    .stats-grid {{
                        grid-template-columns: 1fr;
                    }}
                    .section-tabs {{
                        flex-direction: column;
                    }}
                    .tab {{
                        margin-bottom: 5px;
                    }}
                }}
            </style>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>Статистика опросов</h1>
                    <h2>{display_chat_name}</h2>
                    <button class="refresh-button" title="Обновить статистику" onclick="window.location.reload()">
                        ↻
                    </button>
                </div>
            </header>
            
            <div class="container">
                <div class="stats-card">
                    <h2>Общая статистика</h2>
                    <div class="stats-grid">
                        <div class="stat-box">
                            <div>Всего опросов</div>
                            <div class="stat-number">{total_polls}</div>
                        </div>
                        <div class="stat-box">
                            <div>Всего голосов</div>
                            <div class="stat-number">{total_votes}</div>
                        </div>
                        <div class="stat-box">
                            <div>Среднее голосов на опрос</div>
                            <div class="stat-number">{round(avg_votes_per_poll, 1)}</div>
                        </div>
                        <div class="stat-box">
                            <div>Среднее время голосования</div>
                            <div class="stat-number">{avg_vote_time}</div>
                        </div>
                    </div>
                </div>
                
                <div class="stats-card">
                    <h2>Популярные ответы</h2>
                    <table class="options-table">
                        <thead>
                            <tr>
                                <th>Ответ</th>
                                <th>Голосов</th>
                                <th>Процент</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        # Добавляем строки для каждого варианта ответа
        max_votes = max(option_votes) if option_votes else 1
        for i, option in enumerate(poll_options):
            votes = option_votes[i]
            percentage = (votes / total_votes) * 100 if total_votes > 0 else 0
            bar_percentage = (votes / max_votes) * 100 if max_votes > 0 else 0
            
            html += f"""
                <tr>
                    <td>{option}</td>
                    <td>{votes}</td>
                    <td>{percentage:.1f}%</td>
                    <td>
                        <div class="bar-container">
                            <div class="bar" style="width: {bar_percentage}%"></div>
                        </div>
                    </td>
                </tr>
            """
        
        html += """
                        </tbody>
                    </table>
                </div>
                
                <div class="stats-card">
                    <div class="section-tabs">
                        <div class="tab active" onclick="openTab(event, 'user-votes')">Голоса по пользователям</div>
                        <div class="tab" onclick="openTab(event, 'weekday-votes')">Голоса по дням недели</div>
                        <div class="tab" onclick="openTab(event, 'time-votes')">Голоса по времени суток</div>
                    </div>
                    
                    <div id="user-votes" class="section-content active">
                        <h3>Голоса по пользователям</h3>
                        <table class="options-table">
                            <thead>
                                <tr>
                                    <th>Пользователь</th>
        """
        
        # Добавляем заголовки для каждого варианта
        for option in poll_options:
            html += f"<th>{option}</th>"
        
        html += """
                                    <th>Всего</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        # Добавляем данные по пользователям
        for user_name, votes_array in user_votes_data.items():
            total_user_votes = sum(votes_array)
            html += f"<tr><td>{user_name}</td>"
            
            for votes in votes_array:
                html += f"<td>{votes}</td>"
            
            html += f"<td>{total_user_votes}</td></tr>"
        
        html += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div id="weekday-votes" class="section-content">
                        <h3>Голоса по дням недели</h3>
                        <table class="options-table">
                            <thead>
                                <tr>
                                    <th>День недели</th>
        """
        
        # Добавляем заголовки для каждого варианта
        for option in poll_options:
            html += f"<th>{option}</th>"
        
        html += """
                                    <th>Всего</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        # Порядок дней недели для отображения
        weekday_order = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        
        # Добавляем данные по дням недели
        for weekday in weekday_order:
            if weekday in weekday_votes_data:
                votes_array = weekday_votes_data[weekday]
                total_weekday_votes = sum(votes_array)
                html += f"<tr><td>{weekday}</td>"
                
                for votes in votes_array:
                    html += f"<td>{votes}</td>"
                
                html += f"<td>{total_weekday_votes}</td></tr>"
            else:
                # Если нет данных для этого дня недели
                html += f"<tr><td>{weekday}</td>"
                for _ in poll_options:
                    html += "<td>0</td>"
                html += "<td>0</td></tr>"
        
        html += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div id="time-votes" class="section-content">
                        <h3>Голоса по времени суток</h3>
                        <table class="options-table">
                            <thead>
                                <tr>
                                    <th>Время суток</th>
        """
        
        # Добавляем заголовки для каждого варианта
        for option in poll_options:
            html += f"<th>{option}</th>"
        
        html += """
                                    <th>Всего</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        # Порядок времени суток для отображения
        time_order = ['Утро', 'День', 'Вечер', 'Ночь']
        
        # Добавляем данные по времени суток
        for time_of_day in time_order:
            if time_of_day in time_votes_data:
                votes_array = time_votes_data[time_of_day]
                total_time_votes = sum(votes_array)
                html += f"<tr><td>{time_of_day}</td>"
                
                for votes in votes_array:
                    html += f"<td>{votes}</td>"
                
                html += f"<td>{total_time_votes}</td></tr>"
            else:
                # Если нет данных для этого времени суток
                html += f"<tr><td>{time_of_day}</td>"
                for _ in poll_options:
                    html += "<td>0</td>"
                html += "<td>0</td></tr>"
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <div class="stats-card">
                    <h2>История опросов</h2>
                    <div class="poll-history">
        """
        
        # Добавляем историю опросов
        for poll in recent_polls:
            html += f"""
            <div class="poll-item">
                <div class="poll-time">{poll['time']}</div>
                <div class="poll-votes">Всего голосов: {sum(poll['votes'])}</div>
            """
            
            for i, option in enumerate(poll_options):
                votes = poll['votes'][i]
                max_votes = max(poll['votes']) if any(poll['votes']) else 1
                percentage = (votes / max_votes) * 100 if max_votes > 0 else 0
                
                html += f"""
                <div class="poll-option">
                    <div class="option-label">{option}</div>
                    <div class="option-bar" style="width: {percentage}%;"></div>
                    <div class="option-votes">{votes}</div>
                </div>
                """
            
            html += "</div>"
        
        html += """
                    </div>
                </div>
            </div>
            
            <script>
                function openTab(evt, tabName) {
                    var i, tabcontent, tablinks;
                    
                    // Скрываем все содержимое вкладок
                    tabcontent = document.getElementsByClassName("section-content");
                    for (i = 0; i < tabcontent.length; i++) {
                        tabcontent[i].classList.remove("active");
                    }
                    
                    // Удаляем активный класс у всех вкладок
                    tablinks = document.getElementsByClassName("tab");
                    for (i = 0; i < tablinks.length; i++) {
                        tablinks[i].classList.remove("active");
                    }
                    
                    // Показываем текущую вкладку и добавляем "active" класс
                    document.getElementById(tabName).classList.add("active");
                    evt.currentTarget.classList.add("active");
                }
            </script>
        </body>
        </html>
        """
        
        return html
    except Exception as e:
        logger.error(f"Error in generate_stats_html: {e}", exc_info=True)
        return f"<html><body><h1>Ошибка при создании статистики</h1><p>{str(e)}</p></body></html>"

async def get_stats_handler(request):
    """Обработчик GET-запроса для получения статистики"""
    chat_id = request.match_info.get('chat_id', '')
    
    if not chat_id:
        return web.Response(text="Не указан ID чата", status=400)
    
    try:
        # Получаем опции опроса из запроса (или используем дефолтные)
        poll_options = request.query.get('options', '').split(',')
        if not poll_options or len(poll_options) < 2:
            # Дефолтные опции
            poll_options = [
                "Конечно, нахуй, да!",
                "А когда не сасать?!",
                "Со вчерашнего рот болит",
                "5-10 минут и готов сасать",
                "Полчасика и буду пасасэо"
            ]
        
        # Генерируем HTML
        stats = await get_detailed_poll_stats(chat_id, poll_options)
        html = generate_stats_html(stats)
        
        # Сохраняем HTML в файл
        filename = f"stats_{chat_id}.html"
        filepath = STATIC_DIR / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Перенаправляем на созданный файл
        return web.HTTPFound(f'/static/{filename}')
    
    except Exception as e:
        logger.error(f"Error generating stats: {e}")
        return web.Response(text=f"Ошибка при генерации статистики: {str(e)}", status=500)

def get_stats_url(chat_id):
    """Получить URL для статистики"""
    # Используем домен вместо IP-адреса
    host = os.environ.get('DOMAIN_NAME', 'hwga.pokhilen.co')
    base_url = f"https://{host}"
    return f"{base_url}/stats/{chat_id}"

async def start_web_server():
    """Запускает веб-сервер"""
    app = web.Application()
    
    # Маршруты для статистики
    app.router.add_get('/stats/{chat_id}', get_stats_handler)
    
    # Маршруты для Steam OpenID авторизации
    app.router.add_get('/auth/steam/login/{telegram_id}', steam_login_handler)
    app.router.add_get('/auth/steam/callback', steam_callback_handler)
    app.router.add_get('/auth/steam/success', steam_success_handler)
    app.router.add_get('/auth/steam/cancel', steam_cancel_handler)
    
    # Тестовый маршрут
    app.router.add_get('/', lambda request: web.Response(text='HWGA Bot Web Server is running!'))
    
    app.router.add_static('/static/', path=STATIC_DIR, name='static')
    
    # Запуск сервера
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Запускаем HTTP сервер на основном порту
    http_site = web.TCPSite(runner, HOST, PORT)
    await http_site.start()
    logger.info(f"HTTP web server started at http://{HOST}:{PORT}")
    
    # Пути к SSL сертификатам
    ssl_cert = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cert', 'cert.pem')
    ssl_key = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cert', 'key.pem')
    
    # Проверяем наличие SSL сертификатов
    if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        # Создаем SSL контекст
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(ssl_cert, ssl_key)
        
        # Запускаем HTTPS сервер на стандартном порту 443
        try:
            https_site = web.TCPSite(runner, HOST, 443, ssl_context=ssl_context)
            await https_site.start()
            logger.info(f"HTTPS web server started at https://{HOST}")
        except OSError as e:
            # Если нет прав на порт 443, пробуем альтернативный порт из env
            alt_port = int(os.environ.get('PROD_PORT', 8444))
            logger.warning(f"Failed to start HTTPS server on port 443: {e}. Trying port {alt_port}...")
            https_site = web.TCPSite(runner, HOST, alt_port, ssl_context=ssl_context)
            await https_site.start()
            logger.info(f"HTTPS web server started at https://{HOST}:{alt_port}")
    else:
        logger.warning(f"SSL certificates not found at {ssl_cert} and {ssl_key}. HTTPS server not started.")
    
    return runner

def format_user_votes_table(user_votes_data, poll_options):
    """Форматирует таблицу с голосами пользователей"""
    if not user_votes_data:
        return "<p>Нет данных о голосах пользователей</p>"
    
    html = """
    <div class="stats-card">
        <div class="stats-title">Распределение ответов по пользователям</div>
        <table class="votes-table">
            <thead>
                <tr>
                    <th>Пользователь</th>
    """
    
    # Добавляем заголовки столбцов с вариантами ответов
    for option in poll_options:
        html += f"<th>{option}</th>"
    
    html += """
                    <th>Всего</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Сортируем пользователей по общему количеству голосов (по убыванию)
    sorted_users = sorted(
        user_votes_data.items(),
        key=lambda x: sum(x[1]),
        reverse=True
    )
    
    # Добавляем строки для каждого пользователя
    for user_name, votes in sorted_users:
        total_votes = sum(votes)
        if total_votes == 0:
            continue  # Пропускаем пользователей без голосов
            
        html += f"<tr><td>{user_name}</td>"
        
        # Добавляем ячейки для каждого варианта ответа
        for vote_count in votes:
            # Выделяем ячейку с максимальным значением
            is_max = vote_count == max(votes) and vote_count > 0
            style = ' class="max-value"' if is_max else ''
            html += f"<td{style}>{vote_count}</td>"
        
        html += f"<td>{total_votes}</td></tr>"
    
    html += """
            </tbody>
        </table>
    </div>
    """
    
    return html

def format_weekday_votes_table(weekday_votes_data, poll_options):
    """Форматирует таблицу с голосами по дням недели"""
    if not weekday_votes_data:
        return "<p>Нет данных о голосах по дням недели</p>"
    
    html = """
    <div class="stats-card">
        <div class="stats-title">Распределение ответов по дням недели</div>
        <table class="votes-table">
            <thead>
                <tr>
                    <th>День недели</th>
    """
    
    # Добавляем заголовки столбцов с вариантами ответов
    for option in poll_options:
        html += f"<th>{option}</th>"
    
    html += """
                    <th>Всего</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Порядок дней недели
    weekday_order = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    # Добавляем строки для каждого дня недели
    for day in weekday_order:
        if day in weekday_votes_data:
            votes = weekday_votes_data[day]
            total_votes = sum(votes)
            if total_votes == 0:
                continue  # Пропускаем дни без голосов
                
            html += f"<tr><td>{day}</td>"
            
            # Добавляем ячейки для каждого варианта ответа
            for vote_count in votes:
                # Выделяем ячейку с максимальным значением
                is_max = vote_count == max(votes) and vote_count > 0
                style = ' class="max-value"' if is_max else ''
                html += f"<td{style}>{vote_count}</td>"
            
            html += f"<td>{total_votes}</td></tr>"
    
    html += """
            </tbody>
        </table>
    </div>
    """
    
    return html

def format_time_votes_table(time_votes_data, poll_options):
    """Форматирует таблицу с голосами по времени суток"""
    if not time_votes_data:
        return "<p>Нет данных о голосах по времени суток</p>"
    
    html = """
    <div class="stats-card">
        <div class="stats-title">Распределение ответов по времени суток</div>
        <table class="votes-table">
            <thead>
                <tr>
                    <th>Время суток</th>
    """
    
    # Добавляем заголовки столбцов с вариантами ответов
    for option in poll_options:
        html += f"<th>{option}</th>"
    
    html += """
                    <th>Всего</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Порядок периодов времени
    time_order = ["Утро (6-12)", "День (12-18)", "Вечер (18-0)", "Ночь (0-6)"]
    
    # Добавляем строки для каждого периода времени
    for period in time_order:
        if period in time_votes_data:
            votes = time_votes_data[period]
            total_votes = sum(votes)
            if total_votes == 0:
                continue  # Пропускаем периоды без голосов
                
            html += f"<tr><td>{period}</td>"
            
            # Добавляем ячейки для каждого варианта ответа
            for vote_count in votes:
                # Выделяем ячейку с максимальным значением
                is_max = vote_count == max(votes) and vote_count > 0
                style = ' class="max-value"' if is_max else ''
                html += f"<td{style}>{vote_count}</td>"
            
            html += f"<td>{total_votes}</td></tr>"
    
    html += """
            </tbody>
        </table>
    </div>
    """
    
    return html

# Steam OpenID Authentication Handlers

def get_base_url():
    """Get the base URL for callbacks"""
    # Используем домен вместо IP-адреса
    host = os.environ.get('DOMAIN_NAME', 'hwga.pokhilen.co')
    base_url = f"https://{host}"
    return base_url

async def steam_login_handler(request):
    """Handles the initial Steam login request"""
    telegram_id = request.match_info.get('telegram_id', '')
    chat_id = request.query.get('chat_id', '')
    
    if not telegram_id:
        return web.Response(text="Не указан ID пользователя Telegram", status=400)
    
    try:
        # Проверяем, привязан ли уже Steam ID к данному чату
        if chat_id:
            is_linked = await db.is_steam_id_linked_to_chat(telegram_id, chat_id)
            
            if is_linked:
                # Получаем информацию о пользователе
                user_info = await db.get_user_info(telegram_id)
                if user_info and user_info['steam_id']:
                    # Получаем название чата
                    chat_name = await db.get_chat_name_by_id(chat_id) or "неизвестный чат"
                    
                    # Перенаправляем на страницу успешной авторизации
                    redirect_url = f"/auth/steam/success?telegram_id={telegram_id}&steam_id={user_info['steam_id']}&chat_id={chat_id}&already_linked=true"
                    return web.HTTPFound(redirect_url)
        
        # Generate a unique session ID
        session_id = secrets.token_hex(16)
        
        # Store the session mapping with chat_id
        steam_auth_sessions[session_id] = (telegram_id, chat_id)
        telegram_auth_requests[telegram_id] = session_id
        
        # Generate Steam OpenID parameters
        return_url = f"{get_base_url()}/auth/steam/callback"
        
        params = {
            'openid.ns': 'http://specs.openid.net/auth/2.0',
            'openid.mode': 'checkid_setup',
            'openid.return_to': return_url,
            'openid.realm': get_base_url(),
            'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
        }
        
        # Construct the Steam OpenID URL
        url = STEAM_OPENID_URL + '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
        
        # Redirect the user to Steam
        return web.HTTPFound(url)
    
    except Exception as e:
        logger.error(f"Error in steam_login_handler: {e}")
        return web.Response(text=f"Ошибка при авторизации через Steam: {str(e)}", status=500)

async def steam_callback_handler(request):
    """Handles the callback from Steam OpenID"""
    try:
        # Validate the response from Steam
        params = request.query
        
        if 'openid.mode' not in params or params['openid.mode'] != 'id_res':
            return web.HTTPFound('/auth/steam/cancel')
        
        # Extract the Steam ID
        claimed_id = params.get('openid.claimed_id', '')
        steam_id_match = re.search(r'/openid/id/(\d+)$', claimed_id)
        
        if not steam_id_match:
            logger.error(f"Invalid claimed_id format: {claimed_id}")
            return web.HTTPFound('/auth/steam/cancel')
        
        steam_id = steam_id_match.group(1)
        logger.info(f"Successfully authenticated Steam ID: {steam_id}")
        
        # Verify the response with Steam
        verification_params = dict(params)
        verification_params['openid.mode'] = 'check_authentication'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(STEAM_OPENID_URL, data=verification_params) as resp:
                verification_result = await resp.text()
                
                if 'is_valid:true' not in verification_result:
                    logger.error(f"Steam OpenID verification failed: {verification_result}")
                    return web.HTTPFound('/auth/steam/cancel')
        
        # Get user info from Steam API
        if STEAM_API_KEY:
            try:
                async with aiohttp.ClientSession() as session:
                    api_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}"
                    async with session.get(api_url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            players = data.get('response', {}).get('players', [])
                            if players:
                                player = players[0]
                                steam_username = player.get('personaname', 'Unknown')
                                logger.info(f"Steam user: {steam_username}, ID: {steam_id}")
            except Exception as e:
                logger.error(f"Error getting Steam user info: {e}")
        
        # Find the associated Telegram ID
        # Since we can't store session in the browser easily for this use case,
        # we'll check all pending authentications to find a match
        for session_id, session_data in list(steam_auth_sessions.items()):
            telegram_id, chat_id = session_data
            
            # Update the user's Steam ID in the database
            if chat_id:
                # Link to specific chat
                await db.update_user_steam_id(telegram_id, steam_id, chat_id)
                logger.info(f"Updated Steam ID for Telegram user {telegram_id} in chat {chat_id}: {steam_id}")
            else:
                # Just update global Steam ID
                await db.update_user_steam_id(telegram_id, steam_id)
                logger.info(f"Updated global Steam ID for Telegram user {telegram_id}: {steam_id}")
            
            # Clean up the auth session
            del steam_auth_sessions[session_id]
            if telegram_id in telegram_auth_requests:
                del telegram_auth_requests[telegram_id]
            
            # Redirect to success page showing the steam_id and telegram_id
            success_url = f"/auth/steam/success?telegram_id={telegram_id}&steam_id={steam_id}&chat_id={chat_id}"
            return web.HTTPFound(success_url)
        
        # If no matching session was found
        return web.Response(text="Не удалось найти сессию аутентификации. Пожалуйста, попробуйте снова.", status=400)
    
    except Exception as e:
        logger.error(f"Error in steam_callback_handler: {e}")
        return web.Response(text=f"Ошибка при обработке ответа от Steam: {str(e)}", status=500)

async def steam_success_handler(request):
    """Shows a success page"""
    telegram_id = request.query.get('telegram_id', '')
    steam_id = request.query.get('steam_id', '')
    chat_id = request.query.get('chat_id', '')
    already_linked = request.query.get('already_linked', '') == 'true'
    
    chat_name = "неизвестный чат"
    if chat_id:
        chat_name_result = await db.get_chat_name_by_id(chat_id)
        if chat_name_result:
            chat_name = chat_name_result
    
    if already_linked:
        # Если аккаунт уже был привязан ранее
        success_message = "Аккаунт Steam уже привязан!"
        description = f"Ваш аккаунт Steam уже привязан к чату \"{chat_name}\". Вам не нужно привязывать его повторно."
        icon_color = "#3498db"  # Синий цвет для информационного сообщения
    else:
        # Стандартное сообщение для новой привязки
        success_message = "Аккаунт Steam успешно привязан!"
        description = f"Вы успешно привязали свой аккаунт Steam к чату \"{chat_name}\". Теперь бот сможет отслеживать, когда вы играете в Dota 2, и автоматически предлагать опрос для вашей группы."
        icon_color = "#4CAF50"  # Зеленый цвет для успешной привязки
    
    chat_info = f" к чату \"{chat_name}\"" if chat_id else ""
    
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Привязка Steam ID</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f0f2f5;
            }}
            .card {{
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                padding: 30px;
                text-align: center;
                max-width: 500px;
            }}
            .success-icon {{
                font-size: 64px;
                color: {icon_color};
                margin-bottom: 20px;
            }}
            h1 {{
                color: {icon_color};
                margin-bottom: 20px;
            }}
            p {{
                color: #333;
                line-height: 1.5;
                margin-bottom: 20px;
            }}
            .steam-id {{
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                font-family: monospace;
                margin: 10px 0;
            }}
            .button {{
                display: inline-block;
                background-color: #171a21;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                text-decoration: none;
                margin-top: 20px;
                transition: background-color 0.3s;
            }}
            .button:hover {{
                background-color: #2a475e;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="success-icon">{'ℹ' if already_linked else '✓'}</div>
            <h1>{success_message}</h1>
            <p>{description}</p>
            <p>Steam ID:</p>
            <div class="steam-id">{steam_id}</div>
            <p>Можете закрыть эту страницу и вернуться в Telegram.</p>
            <a href="https://t.me/hwga_sausage_bot" class="button">Вернуться к боту</a>
        </div>
    </body>
    </html>
    """
    
    return web.Response(text=html, content_type='text/html')

async def steam_cancel_handler(request):
    """Shows a cancel page"""
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Отмена привязки Steam ID</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f0f2f5;
            }
            .card {
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                padding: 30px;
                text-align: center;
                max-width: 500px;
            }
            .cancel-icon {
                font-size: 64px;
                color: #f44336;
                margin-bottom: 20px;
            }
            h1 {
                color: #f44336;
                margin-bottom: 20px;
            }
            p {
                color: #333;
                line-height: 1.5;
                margin-bottom: 20px;
            }
            .button {
                display: inline-block;
                background-color: #171a21;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                text-decoration: none;
                margin-top: 20px;
                transition: background-color 0.3s;
            }
            .button:hover {
                background-color: #2a475e;
            }
            .warning {
                color: #e74c3c;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="cancel-icon">✕</div>
            <h1>Привязка отменена</h1>
            <p>Вы отменили привязку аккаунта Steam к боту или произошла ошибка в процессе авторизации.</p>
            <p>Вы можете попробовать снова, выполнив команду /link_steam в том чате, где вы хотите использовать бота.</p>
            <p class="warning">ВАЖНО: Команду /link_steam необходимо запускать внутри нужного группового чата, а не в личных сообщениях с ботом!</p>
            <a href="https://t.me/hwga_sausage_bot" class="button">Вернуться к боту</a>
        </div>
    </body>
    </html>
    """
    
    return web.Response(text=html, content_type='text/html')

def get_steam_auth_url(telegram_id, chat_id=None):
    """Получить URL для авторизации через Steam"""
    base_url = get_base_url()
    chat_param = f"?chat_id={chat_id}" if chat_id else ""
    return f"{base_url}/auth/steam/login/{telegram_id}{chat_param}"

from __future__ import annotations
import os
import json
import re
import random
import string
import threading
import asyncio
import logging
import time as _time
import math
import requests as http_requests
from flask import Flask, render_template, request, jsonify, g, redirect
from db_compat import connect_db, init_db as _init_database, DB_TYPE

# aiogram — optional (not available on PythonAnywhere WSGI)
try:
    from aiogram import Bot, Dispatcher, types
    from aiogram.filters import Command
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    HAS_AIOGRAM = True
except ImportError:
    HAS_AIOGRAM = False
    # Stubs so decorated bot handlers don't crash at import time
    class _Stub:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Stub()
        def __getattr__(self, name): return _Stub()
    Bot = _Stub
    Dispatcher = _Stub
    types = _Stub()
    Command = _Stub
    InlineKeyboardMarkup = _Stub
    InlineKeyboardButton = _Stub
    WebAppInfo = _Stub

# ============ CONFIG ============
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'luna-gifts-secret-key-change-me')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files

ADMIN_IDS = [5257227756, 7589153715]
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8338591585:AAH8ezZ8xO7Y9KlU9GQe4Sj5nhdCIyOaXnE')
WEBAPP_URL = os.environ.get('WEBAPP_URL', 'https://lunagifts.onrender.com')
MIN_WITHDRAW = 15

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ============ AUTH KEYS (in-memory) ============
# {key: {telegram_id, username, first_name, last_name, photo_url} or None if pending}
auth_keys = {}


@app.after_request
def add_cache_headers(response):
    """Set aggressive caching for static assets (GIFs, images, CSS, JS)."""
    if request.path.startswith('/static/'):
        if request.path.endswith('.gif'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif request.path.endswith(('.png', '.jpg', '.jpeg', '.webp', '.svg')):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif request.path.endswith(('.css', '.js')):
            response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


# ============ MAINTENANCE MODE ============

_settings_path_maint = None  # will use load_settings

@app.before_request
def ensure_background_threads():
    """Ensure background threads are running (called once)."""
    start_background_threads()


@app.before_request
def check_maintenance():
    """Block non-admin users when maintenance mode is enabled."""
    # Skip for static files and admin/maintenance endpoints
    if request.path.startswith('/static/') or request.path == '/api/admin/maintenance':
        return None
    if request.path.startswith('/api/admin/') or request.path == '/admin':
        return None
    # Lazy import — load_settings may not be defined yet at decoration time, but it will be at call time
    settings = load_settings()
    if not settings.get('maintenance_enabled', False):
        return None
    # Allow admins through: check query/json param
    try:
        admin_id = request.args.get('admin_id', type=int)
        if not admin_id and request.is_json and request.json:
            admin_id = request.json.get('admin_id')
        if admin_id and is_admin(admin_id):
            return None
    except Exception:
        pass
    # Check Telegram initData for admin
    try:
        init_data = request.args.get('initData', '') or request.headers.get('X-Init-Data', '')
        if init_data:
            from urllib.parse import parse_qs
            params = parse_qs(init_data)
            user_str = params.get('user', [''])[0]
            if user_str:
                user_data = json.loads(user_str)
                if is_admin(user_data.get('id', 0)):
                    return None
    except Exception:
        pass
    # If API — JSON error
    if request.path.startswith('/api/'):
        return jsonify({'error': 'maintenance', 'message': 'Ведутся технические работы'}), 503
    # Otherwise show maintenance page
    end_time = settings.get('maintenance_end_time', '')
    return _render_maintenance_page(end_time), 503


def _render_maintenance_page(end_time=''):
    """Return a simple maintenance HTML page."""
    time_msg = ''
    if end_time:
        time_msg = f'<p style="font-size:14px;color:rgba(255,255,255,0.5);margin-top:12px;">Примерное время окончания: <b style="color:#FFD74A;">{end_time}</b></p>'
    return f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>Luna Gifts — Тех. работы</title>
<link rel="icon" href="/static/img/logo.png" type="image/png">
<style>
*{{box-sizing:border-box;}}body{{margin:0;padding:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0e0e1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#fff;text-align:center;padding:24px;}}
.maint-box{{max-width:400px;padding:40px 32px;border-radius:24px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);backdrop-filter:blur(20px);}}
.maint-icon{{font-size:64px;margin-bottom:16px;}}
h1{{font-size:24px;font-weight:900;margin:0 0 8px;}}
p{{margin:0;font-size:15px;color:rgba(255,255,255,0.6);line-height:1.5;}}
</style></head><body>
<div class="maint-box">
<div class="maint-icon">🔧</div>
<h1>Технические работы</h1>
<p>Мы проводим обновление сервиса.<br>Пожалуйста, зайдите позже.</p>
{time_msg}
</div></body></html>'''


# ============ CRASH GAME ENGINE (server-side multiplayer) ============

_crash_cache = {
    'game_id': 0,
    'status': 'waiting',       # waiting | counting | flying | crashed
    'multiplier': 1.00,
    'target_multiplier': 1.00,
    'countdown': 0,
    'start_time': 0,
    'crash_profit_balance': 0,  # running site profit for multiplier generation
}
_crash_lock = threading.Lock()


def get_crash_cache():
    with _crash_lock:
        return dict(_crash_cache)


def update_crash_cache(**kwargs):
    with _crash_lock:
        _crash_cache.update(kwargs)


def generate_crash_multiplier():
    """Generate a crash multiplier with ~5% house edge, considering profit balance."""
    profit = _crash_cache.get('crash_profit_balance', 0)

    r = random.random()

    # Adjust probabilities based on site profit
    if profit < -500:
        # Site is losing — more low crashes
        if r < 0.15:
            return 1.00
        if r < 0.40:
            return round(random.uniform(1.01, 1.5), 2)
        return round(max(1.01, 0.99 / r), 2)
    elif profit > 500:
        # Site is profiting — allow bigger multipliers
        if r < 0.03:
            return 1.00
        return round(max(1.01, 0.97 / r), 2)
    else:
        # Normal
        if r < 0.05:
            return 1.00
        return round(max(1.01, 0.95 / r), 2)


def start_crash_loop():
    """Background thread running the crash game loop."""
    logging.info("Crash game loop started")

    while True:
        try:
            db = connect_db()

            # --- Create new game ---
            target = generate_crash_multiplier()
            now = _time.time()
            db.execute(
                "INSERT INTO crash_games (status, target_multiplier, current_multiplier, start_time) "
                "VALUES (?, ?, ?, ?)",
                ('waiting', target, 1.00, now)
            )
            db.commit()
            game = db.execute("SELECT * FROM crash_games ORDER BY id DESC LIMIT 1").fetchone()
            game_id = game['id']

            update_crash_cache(
                game_id=game_id, status='waiting', multiplier=1.00,
                target_multiplier=target, countdown=0, start_time=now
            )
            logging.info(f"Crash game #{game_id} created, target={target}")

            # --- Waiting phase (3s) ---
            _time.sleep(3.0)

            # --- Counting phase (3s countdown) ---
            db.execute("UPDATE crash_games SET status='counting' WHERE id=?", (game_id,))
            db.commit()
            update_crash_cache(status='counting', countdown=3.0)

            for i in range(6):
                remaining = 3.0 - i * 0.5
                update_crash_cache(countdown=max(0, remaining))
                _time.sleep(0.5)

            # --- Flying phase ---
            db.execute("UPDATE crash_games SET status='flying', start_time=? WHERE id=?", (_time.time(), game_id))
            db.commit()
            update_crash_cache(status='flying', multiplier=1.00, start_time=_time.time())

            current = 1.00
            while current < target:
                _time.sleep(0.08)

                # Increment speed depends on current multiplier
                if current < 1.5:
                    inc = random.uniform(0.01, 0.03)
                elif current < 3.0:
                    inc = random.uniform(0.02, 0.06)
                elif current < 10.0:
                    inc = random.uniform(0.04, 0.15)
                else:
                    inc = random.uniform(0.10, 0.40)

                current = round(current + inc, 2)
                if current >= target:
                    current = target
                    break

                db.execute("UPDATE crash_games SET current_multiplier=? WHERE id=?", (current, game_id))
                db.commit()
                update_crash_cache(multiplier=current)

            # --- Crashed ---
            db.execute(
                "UPDATE crash_games SET status='crashed', current_multiplier=? WHERE id=?",
                (target, game_id)
            )

            # Mark all playing bets as lost
            playing_bets = db.execute(
                "SELECT id, bet_amount FROM crash_bets WHERE game_id=? AND status='playing'",
                (game_id,)
            ).fetchall()
            for bet in playing_bets:
                db.execute("UPDATE crash_bets SET status='lost' WHERE id=?", (bet['id'],))
                update_crash_cache(
                    crash_profit_balance=_crash_cache.get('crash_profit_balance', 0) + bet['bet_amount']
                )

            # Add to history
            db.execute(
                "INSERT INTO crash_history (game_id, final_multiplier) VALUES (?, ?)",
                (game_id, target)
            )
            db.commit()

            update_crash_cache(status='crashed', multiplier=target)
            logging.info(f"Crash game #{game_id} crashed at {target}x")

            db.close()

            # Show crashed state for 3s
            _time.sleep(3.0)

        except Exception as e:
            logging.error(f"Crash loop error: {e}")
            _time.sleep(2)


# ============ PVP WHEEL GAME ENGINE ============

PVP_COLORS = ['#FF6B35', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
              '#BB8FCE', '#85C1E9', '#F0B27A', '#82E0AA', '#F1948A', '#AED6F1', '#D5F5E3', '#FADBD8']

_pvp_cache = {
    'game_id': 0,
    'status': 'waiting',       # waiting | betting | countdown | spinning | result
    'players': [],              # [{telegram_id, username, first_name, photo_url, amount, color, chance}]
    'total_pot': 0,
    'countdown': 0,             # seconds remaining
    'countdown_max': 30,
    'winner': None,             # {telegram_id, username, ...}
    'spin_angle': 0,            # final angle
    'hash': '',
    'currency': 'stars',
}
_pvp_lock = threading.Lock()


def get_pvp_cache():
    with _pvp_lock:
        return dict(_pvp_cache)


def update_pvp_cache(**kwargs):
    with _pvp_lock:
        _pvp_cache.update(kwargs)


def _pvp_compute_chances(players):
    """Compute chance percentages for all players based on their bets."""
    total = sum(p['amount'] for p in players)
    if total == 0:
        return players
    for p in players:
        p['chance'] = round((p['amount'] / total) * 100, 2)
    return players


def _pvp_pick_winner(players):
    """Pick a random winner weighted by bet amounts. Returns (winner, angle_degrees)."""
    total = sum(p['amount'] for p in players)
    if total == 0:
        return None, 0
    r = random.random() * total
    cumulative = 0
    winner = players[0]
    winner_start = 0
    for p in players:
        if cumulative + p['amount'] >= r:
            winner = p
            winner_start = cumulative
            break
        cumulative += p['amount']
    # Calculate angle within the winner's slice
    slice_start_angle = (winner_start / total) * 360
    slice_size_angle = (winner['amount'] / total) * 360
    # Random angle within the winner's slice (avoid edges)
    margin = min(slice_size_angle * 0.15, 10)
    angle_in_slice = slice_start_angle + margin + random.random() * max(1, slice_size_angle - 2 * margin)
    # Invert angle so wheel rotation brings this position under the pointer (top)
    # Wheel starts drawing from top, rotates clockwise
    target_angle = 360 - angle_in_slice
    return winner, target_angle


def _pvp_generate_hash():
    """Generate a provably fair game hash."""
    import hashlib
    seed = f"{_time.time()}{random.random()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


def start_pvp_loop():
    """Background thread running the PVP wheel game loop."""
    logging.info("PVP game loop started")
    
    # Clean up any stuck games from previous runs
    try:
        db = connect_db()
        db.execute("UPDATE pvp_games SET status='cancelled' WHERE status IN ('waiting', 'betting', 'countdown', 'spinning')")
        db.commit()
        db.close()
        logging.info("Cleaned up stuck PVP games")
    except Exception as e:
        logging.error(f"Error cleaning up PVP games: {e}")

    while True:
        try:
            db = connect_db()

            # Create new game
            game_hash = _pvp_generate_hash()
            game_id = db.insert_returning_id(
                'pvp_games',
                ['status', 'total_pot', 'hash'],
                ('waiting', 0, game_hash)
            )
            db.commit()

            update_pvp_cache(
                game_id=game_id, status='waiting', players=[], total_pot=0,
                countdown=0, winner=None, spin_angle=0, hash=game_hash
            )
            logging.info(f"PVP game #{game_id} created, hash={game_hash}")

            # Wait for at least 2 players
            while True:
                _time.sleep(0.5)
                with _pvp_lock:
                    player_count = len(_pvp_cache['players'])
                    status = _pvp_cache['status']
                # api_pvp_bet may have already flipped status to 'countdown'
                if status == 'countdown':
                    break
                if player_count >= 2 and status == 'betting':
                    break

            # Start countdown (only if not already started by api_pvp_bet)
            with _pvp_lock:
                if _pvp_cache['status'] != 'countdown':
                    _pvp_cache['status'] = 'countdown'
                    _pvp_cache['countdown'] = 30
            db.execute("UPDATE pvp_games SET status='countdown' WHERE id=?", (game_id,))
            db.commit()
            logging.info(f"PVP game #{game_id} countdown started")

            for i in range(60):  # 30 seconds, check every 0.5s
                _time.sleep(0.5)
                remaining = 30 - (i + 1) * 0.5
                update_pvp_cache(countdown=max(0, remaining))
                if remaining <= 0:
                    break

            # Spin phase
            with _pvp_lock:
                players = list(_pvp_cache['players'])
                total_pot = _pvp_cache['total_pot']

            if len(players) < 2:
                # Not enough players, refund and restart
                for p in players:
                    db.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                               (p['amount'], p['telegram_id']))
                db.execute("UPDATE pvp_games SET status='cancelled' WHERE id=?", (game_id,))
                db.commit()
                db.close()
                update_pvp_cache(status='waiting')
                _time.sleep(2)
                continue

            winner, target_angle = _pvp_pick_winner(players)
            # Spin angle = multiple full rotations + target
            spin_angle = 360 * random.randint(5, 8) + target_angle

            update_pvp_cache(status='spinning', spin_angle=spin_angle, winner=winner)
            db.execute("UPDATE pvp_games SET status='spinning', winner_id=?, winner_angle=? WHERE id=?",
                       (winner['telegram_id'], spin_angle, game_id))
            db.commit()
            logging.info(f"PVP game #{game_id} spinning, winner={winner['username']}, angle={spin_angle}")

            # Wait for spin animation (6 seconds)
            _time.sleep(6.5)

            # Result phase — give winnings to winner
            win_amount = total_pot
            db.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                       (win_amount, winner['telegram_id']))
            db.execute("UPDATE pvp_games SET status='result', total_pot=? WHERE id=?",
                       (total_pot, game_id))
            db.commit()

            update_pvp_cache(status='result')
            logging.info(f"PVP game #{game_id} result: {winner['username']} won {win_amount}")

            # Show result for 5 seconds
            _time.sleep(5)

            db.close()

        except Exception as e:
            logging.error(f"PVP loop error: {e}")
            import traceback
            traceback.print_exc()
            _time.sleep(3)


# ============ BOT SETUP ============
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Handle referral: /start ref_XXXXXXXX
    args = message.text.strip().split(maxsplit=1)
    ref_code = ''
    if len(args) > 1 and args[1].startswith('ref_'):
        ref_code = args[1][4:].upper()

    user_id = message.from_user.id

    # Process referral
    if ref_code:
        db = connect_db()
        referrer = db.execute('SELECT telegram_id FROM users WHERE referral_code = ?', (ref_code,)).fetchone()
        if referrer and referrer['telegram_id'] != user_id:
            # Check user not already referred
            existing = db.execute('SELECT id FROM referrals WHERE referred_id = ?', (user_id,)).fetchone()
            if not existing:
                # Create referred user first
                own_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                db.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name, photo_url, referral_code, referred_by)
                              VALUES (?, ?, ?, ?, ?, ?, ?)''',
                           (user_id, message.from_user.username or '', message.from_user.first_name or '',
                            message.from_user.last_name or '', '', own_code, referrer['telegram_id']))
                db.execute('UPDATE users SET referred_by = ? WHERE telegram_id = ? AND referred_by = 0',
                           (referrer['telegram_id'], user_id))
                db.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
                           (referrer['telegram_id'], user_id))
                # Give 2 stars to referrer
                db.execute('UPDATE users SET balance = balance + 2 WHERE telegram_id = ?',
                           (referrer['telegram_id'],))
                db.commit()
                try:
                    await bot.send_message(
                        referrer['telegram_id'],
                        f"🎉 Новый реферал! <b>{message.from_user.first_name}</b> присоединился по вашей ссылке.\n"
                        f"+2 ⭐ зачислено на баланс!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
        db.close()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Открыть Luna Gifts",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )],
        [InlineKeyboardButton(
            text="Кейсы",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/cases")
        ),
        InlineKeyboardButton(
            text="Маркет",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/market")
        )],
        [InlineKeyboardButton(
            text="Инвентарь",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/inventory")
        )]
    ])

    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "Добро пожаловать в <b>Luna Gifts</b>!\n\n"
        "Выполняй задания и получай звёзды\n"
        "Покупай NFT подарки в маркете\n"
        "Открывай кейсы и испытай удачу\n\n"
        "Нажми кнопку ниже, чтобы начать",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.message(Command("auth"))
async def cmd_auth(message: types.Message):
    """Авторизация по ключу из браузера"""
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Введите ключ авторизации:\n"
            "<code>/auth ВАШ_КЛЮЧ</code>\n\n"
            "Ключ можно получить на сайте Luna Gifts при входе через браузер.",
            parse_mode="HTML"
        )
        return

    key = parts[1].strip().upper()

    if key not in auth_keys:
        await message.answer("Ключ не найден или истёк. Сгенерируйте новый на сайте.")
        return

    if auth_keys[key] is not None:
        await message.answer("Этот ключ уже был использован.")
        return

    user = message.from_user
    photo_url = ''
    try:
        photos = await bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file = await bot.get_file(photos.photos[0][-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    except Exception:
        pass

    # Сохраняем данные пользователя в ключ
    auth_keys[key] = {
        'telegram_id': user.id,
        'username': user.username or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'photo_url': photo_url
    }

    # Создаём/обновляем пользователя в БД
    db = connect_db()
    db.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name, photo_url)
                  VALUES (?, ?, ?, ?, ?)''',
               (user.id, user.username or '', user.first_name or '', user.last_name or '', photo_url))
    db.execute('''UPDATE users SET username=?, first_name=?, last_name=?, photo_url=? WHERE telegram_id=?''',
               (user.username or '', user.first_name or '', user.last_name or '', photo_url, user.id))
    db.commit()
    db.close()

    await message.answer(
        f"Авторизация успешна!\n"
        f"Вернитесь на сайт — вход произойдёт автоматически.",
        parse_mode="HTML"
    )


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к админ панели.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Админ панель",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/admin")
        )]
    ])

    await message.answer(
        "<b>Админ панель</b>\n\nНажмите кнопку для управления:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Посмотреть баланс",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])
    await message.answer("Откройте приложение чтобы увидеть ваш баланс:", reply_markup=keyboard)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "<b>Luna Gifts — Помощь</b>\n\n"
        "/start — Открыть приложение\n"
        "/auth КЛЮЧ — Авторизация через браузер\n"
        "/ref — Реферальная ссылка\n"
        "/balance — Посмотреть баланс\n"
        "/help — Помощь\n\n"
        "<b>Как заработать звёзды?</b>\n"
        "• Выполняйте задания на главной странице\n"
        "• Приглашайте друзей (+2 ⭐ за каждого)\n"
        "• Получайте 5% с пополнений друзей\n"
        "• Открывайте кейсы\n\n"
        "<b>Что делать со звёздами?</b>\n"
        "• Покупайте NFT подарки в маркете\n"
        "• Открывайте кейсы для шанса выиграть больше",
        parse_mode="HTML"
    )


@dp.message(Command("ref"))
async def cmd_ref(message: types.Message):
    """Показать реферальную ссылку"""
    user_id = message.from_user.id
    db = connect_db()
    user = db.execute('SELECT referral_code FROM users WHERE telegram_id = ?', (user_id,)).fetchone()

    if not user or not user['referral_code']:
        # Create user with referral code
        ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        db.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name, referral_code)
                      VALUES (?, ?, ?, ?)''',
                   (user_id, message.from_user.username or '', message.from_user.first_name or '', ref_code))
        if user:
            db.execute('UPDATE users SET referral_code=? WHERE telegram_id=?', (ref_code, user_id))
        db.commit()
    else:
        ref_code = user['referral_code']

    referrals = db.execute('SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?', (user_id,)).fetchone()
    count = referrals['cnt'] if referrals else 0
    db.close()

    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"

    await message.answer(
        f"<b>Реферальная программа</b>\n\n"
        f"Ваша ссылка:\n<code>{ref_link}</code>\n\n"
        f"<b>Ваши рефералы:</b> {count}\n"
        f"<b>Бонус:</b> +2 ⭐ за каждого друга\n"
        f"<b>Комиссия:</b> 5% от пополнений друзей\n\n"
        f"Делитесь ссылкой и получайте награды!",
        parse_mode="HTML"
    )


# ============ STARS PAYMENT HANDLERS ============

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    """Always approve pre-checkout for Stars payments"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(lambda m: m.successful_payment is not None)
async def successful_payment_handler(message: types.Message):
    """Handle successful Stars payment — credit balance"""
    payment = message.successful_payment
    try:
        payload = json.loads(payment.invoice_payload)
        telegram_id = payload.get('telegram_id', message.from_user.id)
        amount = payload.get('amount', payment.total_amount)
    except (json.JSONDecodeError, AttributeError):
        telegram_id = message.from_user.id
        amount = payment.total_amount

    charge_id = getattr(payment, 'telegram_payment_charge_id', '') or ''

    # Credit balance + deposited_balance + total_topup
    db = connect_db()
    db.execute('UPDATE users SET balance = balance + ?, deposited_balance = deposited_balance + ?, total_topup = total_topup + ? WHERE telegram_id = ?', (amount, amount, amount, telegram_id))

    # Save transaction for refund
    if charge_id:
        db.execute('INSERT OR IGNORE INTO star_transactions (telegram_id, charge_id, amount) VALUES (?, ?, ?)',
                   (telegram_id, charge_id, amount))

    # 5% referral commission
    user = db.execute('SELECT referred_by FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if user and user['referred_by'] and user['referred_by'] > 0:
        commission = amount * 0.05
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?',
                   (commission, user['referred_by']))

    db.commit()
    db.close()

    logging.info(f"Stars payment: user {telegram_id} credited {amount} stars, charge_id={charge_id}")

    await message.answer(
        f"Оплата прошла успешно!\n\n"
        f"+{amount} ⭐ зачислено на баланс Luna Gifts!",
        parse_mode="HTML"
    )


def run_bot():
    """Запуск бота в отдельном потоке"""
    if not HAS_AIOGRAM:
        logging.warning("aiogram not installed — bot disabled")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logging.info("Telegram bot starting...")
    loop.run_until_complete(dp.start_polling(bot))


# ============ DATABASE ============

def get_db():
    if 'db' not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    _init_database()


# ============ HELPERS ============

def load_gifts():
    """Загрузка подарков из gifts.json, поддержка обоих форматов"""
    path = os.path.join(os.path.dirname(__file__), 'data', 'gifts.json')
    with open(path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    # Поддержка формата {"gifts": [...]} и просто [...]
    if isinstance(data, dict) and 'gifts' in data:
        gifts_list = data['gifts']
    elif isinstance(data, list):
        gifts_list = data
    else:
        gifts_list = []

    # Нормализация: value -> price если price отсутствует
    for g in gifts_list:
        if 'price' not in g and 'value' in g:
            g['price'] = g['value']
        if 'price' not in g:
            g['price'] = 0

    return gifts_list


def save_gifts(gifts):
    path = os.path.join(os.path.dirname(__file__), 'data', 'gifts.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(gifts, f, ensure_ascii=False, indent=4)


def load_cases():
    path = os.path.join(os.path.dirname(__file__), 'data', 'cases.json')
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_cases(cases):
    path = os.path.join(os.path.dirname(__file__), 'data', 'cases.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cases, f, ensure_ascii=False, indent=4)


def load_scratches():
    path = os.path.join(os.path.dirname(__file__), 'data', 'scratch.json')
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_scratches(scratches):
    path = os.path.join(os.path.dirname(__file__), 'data', 'scratch.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(scratches, f, ensure_ascii=False, indent=4)


def generate_referral_code():
    """Generate unique 8-char referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ============ FRAGMENT IMAGE CACHE ============

FRAGMENT_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'fragment_models.json')
fragment_cache = {}  # {slug: {models: [url,...], backdrops: [url,...], symbols: [url,...]}}


def load_fragment_cache():
    """Load cached Fragment asset URLs from file"""
    global fragment_cache
    try:
        if os.path.exists(FRAGMENT_CACHE_FILE):
            with open(FRAGMENT_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Migrate old format: {slug: [urls]} -> {slug: {models: [...], ...}}
            if data and isinstance(next(iter(data.values()), None), list):
                fragment_cache = {slug: {'models': urls, 'backdrops': [], 'symbols': []} for slug, urls in data.items()}
                save_fragment_cache()
            else:
                fragment_cache = data
            logging.info(f"Loaded Fragment cache: {len(fragment_cache)} gifts")
    except Exception as e:
        logging.error(f"Error loading Fragment cache: {e}")
        fragment_cache = {}


def save_fragment_cache():
    """Save Fragment asset URLs cache to file"""
    try:
        with open(FRAGMENT_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(fragment_cache, f, ensure_ascii=False)
        logging.info(f"Saved Fragment cache: {len(fragment_cache)} gifts")
    except Exception as e:
        logging.error(f"Error saving Fragment cache: {e}")


def scrape_fragment_assets(slug):
    """Scrape Fragment.com for model, backdrop, and symbol URLs of a given gift slug"""
    try:
        url = f"https://fragment.com/gifts/{slug}"
        resp = http_requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        if resp.status_code != 200:
            logging.warning(f"Fragment returned {resp.status_code} for {slug}")
            return {}

        escaped = re.escape(slug)
        # Extract model URLs: /file/gifts/{slug}/model.{hash}.webp
        model_pattern = rf'/file/gifts/{escaped}/model\.[A-Za-z0-9_\-]+\.webp'
        models = list(set(f"https://fragment.com{m}" for m in re.findall(model_pattern, resp.text)))

        # Extract backdrop URLs: /file/gifts/{slug}/backdrop.{hash}.svg
        backdrop_pattern = rf'/file/gifts/{escaped}/backdrop\.[A-Za-z0-9_\-]+\.svg'
        backdrops = list(set(f"https://fragment.com{m}" for m in re.findall(backdrop_pattern, resp.text)))

        # Extract symbol URLs: /file/gifts/{slug}/symbol.{hash}.webp
        symbol_pattern = rf'/file/gifts/{escaped}/symbol\.[A-Za-z0-9_\-]+\.webp'
        symbols = list(set(f"https://fragment.com{m}" for m in re.findall(symbol_pattern, resp.text)))

        result = {'models': models, 'backdrops': backdrops, 'symbols': symbols}
        if models or backdrops or symbols:
            fragment_cache[slug] = result
            logging.info(f"Scraped {slug}: {len(models)} models, {len(backdrops)} backdrops, {len(symbols)} symbols")
        return result
    except Exception as e:
        logging.error(f"Error scraping Fragment for {slug}: {e}")
        return {}


def scrape_all_gifts_background():
    """Background thread: scrape Fragment for all gift slugs"""
    import time
    logging.info("Starting background Fragment scraping...")
    gifts = load_gifts()
    slugs = [g.get('slug') for g in gifts if g.get('slug')]
    scraped = 0
    for slug in slugs:
        cached = fragment_cache.get(slug, {})
        if isinstance(cached, dict) and cached.get('models') and cached.get('backdrops') and cached.get('symbols'):
            continue  # Already fully cached
        scrape_fragment_assets(slug)
        scraped += 1
        time.sleep(1.5)  # Rate limit: 1 request per 1.5s
    if scraped > 0:
        save_fragment_cache()
    logging.info(f"Fragment scraping done. Scraped {scraped} new gifts.")


def get_random_fragment_image(slug):
    """Get a random Fragment model image URL for a gift slug"""
    cached = fragment_cache.get(slug, {})
    if isinstance(cached, list):
        # Old format compatibility
        return random.choice(cached) if cached else None
    urls = cached.get('models', [])
    return random.choice(urls) if urls else None


def get_random_fragment_symbol(slug):
    """Get a random Fragment symbol image URL for a gift slug"""
    cached = fragment_cache.get(slug, {})
    if isinstance(cached, dict):
        urls = cached.get('symbols', [])
        return random.choice(urls) if urls else None
    return None


def get_fragment_assets(slug):
    """Get random model and symbol for a gift slug (backdrop is generated client-side)"""
    return {
        'fragment_image': get_random_fragment_image(slug),
        'fragment_symbol': get_random_fragment_symbol(slug),
    }


# Initialize database on module import (needed for PythonAnywhere WSGI)
init_db()

# Load cache on module import
load_fragment_cache()

# Start background Fragment scraping (works in both WSGI and __main__ modes)
_fragment_thread = threading.Thread(target=scrape_all_gifts_background, daemon=True)
_fragment_thread.start()
logging.info("Fragment scraping thread started (module level)")

def get_or_create_user(telegram_id, username='', first_name='', last_name='', photo_url=''):
    db = get_db()
    import time
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        ref_code = generate_referral_code()
        db.execute(
            'INSERT INTO users (telegram_id, username, first_name, last_name, photo_url, referral_code) VALUES (?, ?, ?, ?, ?, ?)',
            (telegram_id, username, first_name, last_name, photo_url, ref_code)
        )
        db.commit()
        user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    else:
        # Generate referral code if missing
        if not user['referral_code']:
            ref_code = generate_referral_code()
            db.execute('UPDATE users SET referral_code=? WHERE telegram_id=?', (ref_code, telegram_id))
        db.execute(
            'UPDATE users SET username=?, first_name=?, last_name=?, photo_url=? WHERE telegram_id=?',
            (username, first_name, last_name, photo_url, telegram_id)
        )
        db.commit()
        user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    # Update last_active timestamp
    try:
        db.execute('UPDATE users SET last_active=? WHERE telegram_id=?', (time.time(), telegram_id))
        db.commit()
    except Exception:
        try:
            db.execute('ALTER TABLE users ADD COLUMN last_active REAL DEFAULT 0')
            db.execute('UPDATE users SET last_active=? WHERE telegram_id=?', (time.time(), telegram_id))
            db.commit()
        except Exception:
            pass
    return user


def is_admin(telegram_id):
    return int(telegram_id) in ADMIN_IDS


# ============ AUTH API ============

@app.route('/api/auth/generate', methods=['POST'])
def api_auth_generate():
    """Генерация ключа авторизации для входа через браузер"""
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    auth_keys[key] = None  # None = ожидание подтверждения
    return jsonify({'key': key})


@app.route('/api/auth/check/<key>')
def api_auth_check(key):
    """Проверка статуса ключа авторизации"""
    key = key.upper()
    if key not in auth_keys:
        return jsonify({'status': 'not_found'}), 404

    user_data = auth_keys[key]
    if user_data is None:
        return jsonify({'status': 'pending'})

    # Ключ подтверждён — инициализируем пользователя
    user = get_or_create_user(
        user_data['telegram_id'],
        user_data['username'],
        user_data['first_name'],
        user_data['last_name'],
        user_data['photo_url']
    )

    # Удаляем использованный ключ
    del auth_keys[key]

    return jsonify({
        'status': 'confirmed',
        'user': {
            'telegram_id': user['telegram_id'],
            'username': user['username'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'photo_url': user['photo_url'],
            'balance': user['balance'],
            'is_admin': is_admin(user['telegram_id']),
            'referral_code': user['referral_code']
        }
    })


# ============ USER API ============

@app.route('/api/init', methods=['POST'])
def api_init():
    """Initialize user from Telegram WebApp data"""
    data = request.json
    telegram_id = data.get('telegram_id')
    username = data.get('username', '')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    photo_url = data.get('photo_url', '')
    ref_code = data.get('ref_code', '')

    if not telegram_id:
        return jsonify({'error': 'No telegram_id'}), 400

    user = get_or_create_user(telegram_id, username, first_name, last_name, photo_url)

    # Process referral if new user and ref_code provided
    if ref_code and not user['referred_by']:
        db = get_db()
        referrer = db.execute('SELECT * FROM users WHERE referral_code = ?', (ref_code,)).fetchone()
        if referrer and referrer['telegram_id'] != telegram_id:
            # Check not already referred
            existing = db.execute('SELECT id FROM referrals WHERE referred_id = ?', (telegram_id,)).fetchone()
            if not existing:
                db.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
                           (referrer['telegram_id'], telegram_id))
                db.execute('UPDATE users SET referred_by = ? WHERE telegram_id = ?',
                           (referrer['telegram_id'], telegram_id))
                # Give 2 stars bonus to referrer
                db.execute('UPDATE users SET balance = balance + 2 WHERE telegram_id = ?',
                           (referrer['telegram_id'],))
                db.commit()

    deposited = user['deposited_balance'] if user['deposited_balance'] else 0
    return jsonify({
        'telegram_id': user['telegram_id'],
        'username': user['username'],
        'first_name': user['first_name'],
        'last_name': user['last_name'],
        'photo_url': user['photo_url'],
        'balance': user['balance'],
        'deposited_balance': deposited,
        'earned_balance': user['balance'] - deposited,
        'is_admin': is_admin(telegram_id),
        'referral_code': user['referral_code']
    })


@app.route('/api/balance/<int:telegram_id>')
def api_balance(telegram_id):
    db = get_db()
    user = db.execute('SELECT balance, deposited_balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if user:
        deposited = user['deposited_balance'] if user['deposited_balance'] else 0
        return jsonify({'balance': user['balance'], 'deposited_balance': deposited, 'earned_balance': user['balance'] - deposited, 'is_admin': is_admin(telegram_id)})
    return jsonify({'error': 'User not found'}), 404


# ============ ONLINE COUNT ============
@app.route('/api/online')
def api_online():
    db = get_db()
    import time
    cutoff = time.time() - 300  # 5 minutes
    settings = load_settings()
    boost = int(settings.get('online_boost', 0))
    try:
        count = db.execute('SELECT COUNT(*) as cnt FROM users WHERE last_active > ?', (cutoff,)).fetchone()
        real = count['cnt'] if count else 0
        return jsonify({'count': real + boost})
    except Exception:
        # last_active column may not exist
        count = db.execute('SELECT COUNT(*) as cnt FROM users').fetchone()
        online = min(count['cnt'] if count else 0, max(1, (count['cnt'] if count else 0) // 10))
        return jsonify({'count': online + boost})


@app.route('/api/banners')
def api_banners():
    import os as _os
    allowed = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    result = []
    for dirname in ('banners', 'baners'):
        banners_dir = _os.path.join(app.static_folder, 'img', dirname)
        if not _os.path.isdir(banners_dir):
            continue
        for f in sorted(_os.listdir(banners_dir)):
            if f.lower().endswith(allowed):
                result.append(f'/static/img/{dirname}/{f}')
    return jsonify(result)


# ============ RECENT WINS ============
@app.route('/api/cases/recent-wins')
def api_recent_wins():
    db = get_db()
    try:
        wins = db.execute('''
            SELECT i.gift_name, i.gift_image, i.acquired_at,
                   u.username, u.first_name, u.photo_url
            FROM inventory i
            JOIN users u ON i.user_id = u.telegram_id
            ORDER BY i.id DESC LIMIT 15
        ''').fetchall()
        result = []
        for w in wins:
            result.append({
                'gift_name': w['gift_name'] or 'Gift',
                'gift_image': w['gift_image'] or '',
                'username': w['first_name'] or w['username'] or 'User',
                'photo_url': w['photo_url'] or ''
            })
        return jsonify(result)
    except Exception:
        return jsonify([])


# ============ REFERRAL API ============

@app.route('/api/referral/stats/<int:telegram_id>')
def api_referral_stats(telegram_id):
    db = get_db()
    user = db.execute('SELECT referral_code FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    referrals = db.execute('SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?', (telegram_id,)).fetchone()
    total_earned = referrals['cnt'] * 2  # 2 stars per referral sign-up bonus

    return jsonify({
        'referral_code': user['referral_code'],
        'referral_count': referrals['cnt'],
        'total_earned': total_earned
    })


# ============ TOP-UP API ============

@app.route('/api/topup/stars', methods=['POST'])
def api_topup_stars():
    """Create Telegram Stars invoice for top-up"""
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount', 0)

    if not telegram_id or amount <= 0:
        return jsonify({'error': 'Invalid data'}), 400

    # Stars amounts: user pays X Stars → gets X balance
    if amount < 1 or amount > 100000:
        return jsonify({'error': 'Amount must be between 1 and 100000'}), 400

    return jsonify({
        'success': True,
        'amount': int(amount),
        'telegram_id': telegram_id
    })


@app.route('/api/topup/create-invoice', methods=['POST'])
def api_topup_create_invoice():
    """Create a real Telegram Stars invoice link via Bot API"""
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount', 0)

    if not telegram_id or amount <= 0 or amount > 100000:
        return jsonify({'error': 'Invalid data'}), 400

    amount = int(amount)

    # Create invoice link via Bot API
    try:
        resp = http_requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink',
            json={
                'title': f'Пополнение {amount} ⭐',
                'description': f'Пополнение баланса Luna Gifts на {amount} звёзд',
                'payload': json.dumps({'telegram_id': telegram_id, 'amount': amount}),
                'currency': 'XTR',
                'prices': [{'label': f'{amount} Stars', 'amount': amount}]
            }
        )
        result = resp.json()
        if result.get('ok') and result.get('result'):
            return jsonify({'success': True, 'invoice_url': result['result']})
        else:
            logging.error(f"Invoice creation failed: {result}")
            return jsonify({'error': 'Failed to create invoice'}), 500
    except Exception as e:
        logging.error(f"Invoice creation error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/topup/confirm', methods=['POST'])
def api_topup_confirm():
    """Confirm top-up and credit balance (called after successful payment)"""
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount', 0)

    if not telegram_id or amount <= 0:
        return jsonify({'error': 'Invalid data'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Credit balance + deposited_balance + total_topup
    db.execute('UPDATE users SET balance = balance + ?, deposited_balance = deposited_balance + ?, total_topup = total_topup + ? WHERE telegram_id = ?', (amount, amount, amount, telegram_id))

    # 5% referral commission (goes to earned balance only, NOT deposited)
    if user['referred_by'] and user['referred_by'] > 0:
        commission = amount * 0.05
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?',
                   (commission, user['referred_by']))

    db.commit()

    updated_user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({'success': True, 'new_balance': updated_user['balance']})


# ============ TON ↔ STARS EXCHANGE ============

@app.route('/api/exchange', methods=['POST'])
def api_exchange():
    data = request.json
    telegram_id = data.get('telegram_id')
    direction = data.get('direction')  # 'ton_to_stars' or 'stars_to_ton'
    amount = data.get('amount', 0)

    if not telegram_id or not direction or not amount or amount <= 0:
        return jsonify({'error': 'Invalid data'}), 400

    RATE = 100  # 1 TON = 100 Stars

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if direction == 'ton_to_stars':
        # Convert TON to Stars (user sends TON-equivalent, gets Stars)
        stars_amount = int(amount * RATE)
        if stars_amount < 1:
            return jsonify({'error': 'Минимум 0.01 TON'}), 400
        # TON balance is tracked as Stars internally, so add stars_amount
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (stars_amount, telegram_id))
        db.commit()
        updated = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        return jsonify({'success': True, 'new_balance': updated['balance'], 'message': f'+{stars_amount} ⭐ зачислено!'})

    elif direction == 'stars_to_ton':
        stars_amount = int(amount)
        if stars_amount < 100:
            return jsonify({'error': 'Минимум 100 Stars'}), 400
        if user['balance'] < stars_amount:
            return jsonify({'error': 'Недостаточно Stars'}), 400
        ton_amount = stars_amount / RATE
        db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (stars_amount, telegram_id))
        db.commit()
        updated = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        return jsonify({'success': True, 'new_balance': updated['balance'], 'message': f'Обменяно на {ton_amount:.2f} TON'})

    return jsonify({'error': 'Unknown direction'}), 400


# ============ WITHDRAWAL API (Telethon — отправка подарков с аккаунта) ============

_settings_path = os.path.join(os.path.dirname(__file__), 'data', 'settings.json')

def load_settings():
    try:
        if os.path.exists(_settings_path):
            with open(_settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_settings(data):
    try:
        with open(_settings_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"save_settings error: {e}")


# ---------- Telethon relay (Render.com) ----------
# All Telethon/MTProto operations run on a separate Render.com service.
# This PA app communicates with it via HTTPS (allowed on PA free tier).

def _get_relay_config():
    """Get relay URL and secret from settings."""
    settings = load_settings()
    return settings.get('relay_url', ''), settings.get('relay_secret', '')


def _relay_call(endpoint, data=None, timeout=90):
    """Make an HTTP POST call to the Telethon relay service.

    Supports two modes:
    1. Direct relay: relay_url + endpoint (e.g. https://relay.onrender.com/send-code)
    2. GAS proxy:   all requests go to one URL, endpoint is sent in payload['_path']
       Detected when relay_url contains 'script.google.com' or 'script.googleusercontent.com'
    """
    relay_url, relay_secret = _get_relay_config()
    if not relay_url:
        return None, 'Relay URL не настроен. Укажите URL в настройках.'
    payload = dict(data or {})
    payload['relay_secret'] = relay_secret

    # Google Apps Script proxy — single URL, path in payload
    is_gas = ('script.google.com' in relay_url
              or 'script.googleusercontent.com' in relay_url)
    if is_gas:
        payload['_path'] = endpoint
        url = relay_url
    else:
        url = relay_url.rstrip('/') + endpoint

    try:
        if is_gas:
            # GAS web apps redirect POST→302→GET; handle manually
            resp = http_requests.post(url, json=payload, timeout=timeout,
                                      allow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                redir = resp.headers.get('Location', '')
                if redir:
                    resp = http_requests.get(redir, timeout=timeout)
            # If still not JSON, try text
            try:
                return resp.json(), None
            except ValueError:
                preview = resp.text[:300] if resp.text else '(empty)'
                return None, (f'GAS ответ не JSON (status={resp.status_code}, '
                              f'len={len(resp.text)}, redir={is_gas}, '
                              f'body={preview})')
        else:
            resp = http_requests.post(url, json=payload, timeout=timeout)
            try:
                return resp.json(), None
            except ValueError:
                preview = resp.text[:300] if resp.text else '(empty)'
                return None, f'Ответ relay не JSON (status={resp.status_code}, len={len(resp.text)}, body={preview})'
    except http_requests.exceptions.Timeout:
        return None, 'Таймаут соединения с relay сервером'
    except http_requests.exceptions.ConnectionError:
        return None, 'Не удалось подключиться к relay серверу'
    except Exception as e:
        return None, f'Ошибка relay: {e}'


def _relay_is_configured():
    """Check if relay URL is set."""
    url, _ = _get_relay_config()
    return bool(url)


# ---------- Telethon relay API endpoints ----------

@app.route('/api/admin/telethon/relay-config', methods=['GET', 'POST'])
def api_telethon_relay_config():
    """Get or set relay URL and secret."""
    admin_id = request.args.get('admin_id', type=int) or (request.json or {}).get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    if request.method == 'POST':
        data = request.json or {}
        settings = load_settings()
        relay_url = str(data.get('relay_url', '')).strip().rstrip('/')
        relay_secret = str(data.get('relay_secret', '')).strip()
        settings['relay_url'] = relay_url
        settings['relay_secret'] = relay_secret
        save_settings(settings)
        return jsonify({'success': True})
    else:
        settings = load_settings()
        return jsonify({
            'relay_url': settings.get('relay_url', ''),
            'relay_secret': settings.get('relay_secret', ''),
        })


_relay_backup_path = os.path.join(os.path.dirname(__file__), 'data', 'relay_session_backup.json')

@app.route('/api/relay-session-backup', methods=['POST'])
def api_relay_session_backup():
    """Store / retrieve relay session backup so Render restarts don't lose auth."""
    body = request.json or {}
    secret = body.get('relay_secret', '')
    _, relay_secret = _get_relay_config()
    if not relay_secret or secret != relay_secret:
        return jsonify({'error': 'Unauthorized'}), 403

    action = body.get('action', 'save')

    if action == 'get':
        try:
            if os.path.exists(_relay_backup_path):
                with open(_relay_backup_path, 'r', encoding='utf-8') as f:
                    return jsonify({'session_data': json.load(f)})
        except Exception:
            pass
        return jsonify({'session_data': None})

    # save
    session_data = body.get('session_data')
    if session_data and isinstance(session_data, dict):
        try:
            os.makedirs(os.path.dirname(_relay_backup_path), exist_ok=True)
            with open(_relay_backup_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'No session_data'}), 400


@app.route('/api/admin/telethon/status')
def api_telethon_status():
    admin_id = request.args.get('admin_id', type=int)
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    if not _relay_is_configured():
        return jsonify({'available': False, 'connected': False,
                        'error': 'Relay сервер не настроен. Укажите URL и Secret.'})

    settings = load_settings()
    api_id = settings.get('telethon_api_id', '')
    api_hash = settings.get('telethon_api_hash', '')
    phone = settings.get('telethon_phone', '')

    # Ask the relay for session status
    resp, err = _relay_call('/status', {
        'api_id': api_id,
        'api_hash': api_hash,
    })

    if err:
        return jsonify({'available': True, 'connected': False,
                        'relay_error': err,
                        'api_id': api_id, 'api_hash': api_hash, 'phone': phone})

    connected = resp.get('connected', False)
    result = {
        'available': True,
        'connected': connected,
        'api_id': api_id,
        'api_hash': api_hash,
        'phone': phone,
    }
    if connected:
        result['account_name'] = resp.get('account_name', '')
        result['account_id'] = resp.get('account_id', '')
        result['username'] = resp.get('username', '')
        if resp.get('star_balance') is not None:
            result['star_balance'] = resp['star_balance']
    return jsonify(result)


@app.route('/api/admin/telethon/send-code', methods=['POST'])
def api_telethon_send_code():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    if not _relay_is_configured():
        return jsonify({'error': 'Relay сервер не настроен'}), 400

    api_id = str(data.get('api_id', '')).strip()
    api_hash = str(data.get('api_hash', '')).strip()
    phone = str(data.get('phone', '')).strip()

    if not api_id or not api_hash or not phone:
        return jsonify({'error': 'Заполните API ID, API Hash и номер телефона'}), 400

    try:
        int(api_id)
    except ValueError:
        return jsonify({'error': 'API ID должен быть числом'}), 400

    # Save credentials locally
    settings = load_settings()
    settings['telethon_api_id'] = api_id
    settings['telethon_api_hash'] = api_hash
    settings['telethon_phone'] = phone
    save_settings(settings)

    # Wake up relay before sending (Render free tier cold-start)
    try:
        _relay_call('/health', {}, timeout=30)
    except Exception:
        pass

    # Forward to relay
    payload = {
        'api_id': api_id,
        'api_hash': api_hash,
        'phone': phone,
    }
    if data.get('force_sms'):
        payload['force_sms'] = True

    resp, err = _relay_call('/send-code', payload)

    if err:
        return jsonify({'error': err}), 400
    if resp.get('error'):
        return jsonify({'error': resp['error']}), 400

    code_type = resp.get('code_type', '')
    msg = resp.get('message', 'Код отправлен в Telegram')
    return jsonify({'success': True, 'message': msg, 'code_type': code_type})


@app.route('/api/admin/telethon/sign-in', methods=['POST'])
def api_telethon_sign_in():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    code = str(data.get('code', '')).strip()
    password = str(data.get('password', '')).strip()

    settings = load_settings()
    api_id = settings.get('telethon_api_id', '')
    api_hash = settings.get('telethon_api_hash', '')
    phone = settings.get('telethon_phone', '')

    # Forward to relay
    resp, err = _relay_call('/sign-in', {
        'api_id': api_id,
        'api_hash': api_hash,
        'phone': phone,
        'code': code,
        'password': password,
    })

    if err:
        return jsonify({'error': err}), 400
    if resp.get('error'):
        return jsonify({'error': resp['error']}), 400

    if resp.get('need_2fa'):
        return jsonify({'need_2fa': True, 'message': 'Требуется пароль двухфакторной аутентификации'})

    if resp.get('success'):
        # Mark as connected locally (relay manages the session itself)
        settings = load_settings()
        settings['telethon_session'] = 'relay-managed'  # marker that session is active on relay
        settings.pop('telethon_temp_session', None)
        settings.pop('telethon_phone_code_hash', None)
        save_settings(settings)
        return jsonify({
            'success': True,
            'account_name': resp.get('account_name', ''),
            'account_id': resp.get('account_id', ''),
            'username': resp.get('username', ''),
        })

    return jsonify({'error': 'Неизвестная ошибка'}), 400


@app.route('/api/admin/telethon/disconnect', methods=['POST'])
def api_telethon_disconnect():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    # Tell relay to disconnect
    _relay_call('/disconnect', {})

    # Clear local session marker
    settings = load_settings()
    settings.pop('telethon_session', None)
    save_settings(settings)
    return jsonify({'success': True})


@app.route('/api/admin/telethon/import-session', methods=['POST'])
def api_telethon_import_session():
    """Import a pre-generated Telethon StringSession."""
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    if not _relay_is_configured():
        return jsonify({'error': 'Relay сервер не настроен'}), 400

    session_string = str(data.get('session_string', '')).strip()
    api_id = str(data.get('api_id', '')).strip()
    api_hash = str(data.get('api_hash', '')).strip()

    if not session_string:
        return jsonify({'error': 'Вставьте строку сессии'}), 400
    if not api_id or not api_hash:
        return jsonify({'error': 'Заполните API ID и API Hash'}), 400

    try:
        int(api_id)
    except ValueError:
        return jsonify({'error': 'API ID должен быть числом'}), 400

    # Save credentials locally
    settings = load_settings()
    settings['telethon_api_id'] = api_id
    settings['telethon_api_hash'] = api_hash
    save_settings(settings)

    # Wake up relay before import (Render free tier cold-start)
    try:
        _relay_call('/health', {}, timeout=45)
    except Exception:
        pass

    # Forward to relay for validation
    resp, err = _relay_call('/import-session', {
        'session_string': session_string,
        'api_id': api_id,
        'api_hash': api_hash,
    }, timeout=60)

    if err:
        return jsonify({'error': err}), 400
    if resp.get('error'):
        return jsonify({'error': resp['error']}), 400

    if resp.get('success'):
        settings = load_settings()
        settings['telethon_session'] = 'relay-managed'
        settings['telethon_phone'] = resp.get('phone', settings.get('telethon_phone', ''))
        settings.pop('telethon_temp_session', None)
        settings.pop('telethon_phone_code_hash', None)
        save_settings(settings)
        return jsonify({
            'success': True,
            'account_name': resp.get('account_name', ''),
            'account_id': resp.get('account_id', ''),
            'username': resp.get('username', ''),
        })

    return jsonify({'error': 'Неизвестная ошибка'}), 400


# ---------- QR Login via relay ----------

@app.route('/api/admin/telethon/qr-start', methods=['POST'])
def api_telethon_qr_start():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    if not _relay_is_configured():
        return jsonify({'error': 'Relay сервер не настроен'}), 400

    api_id = str(data.get('api_id', '')).strip()
    api_hash = str(data.get('api_hash', '')).strip()
    if not api_id or not api_hash:
        return jsonify({'error': 'Заполните API ID и API Hash'}), 400

    settings = load_settings()
    settings['telethon_api_id'] = api_id
    settings['telethon_api_hash'] = api_hash
    save_settings(settings)

    # Wake up relay before QR login (Render free tier cold-start)
    try:
        _relay_call('/health', {}, timeout=45)
    except Exception:
        pass

    resp, err = _relay_call('/qr-login/start', {'api_id': api_id, 'api_hash': api_hash}, timeout=60)
    if err:
        return jsonify({'error': err}), 400
    if resp.get('error'):
        return jsonify({'error': resp['error']}), 400
    return jsonify(resp)


@app.route('/api/admin/telethon/qr-check', methods=['POST'])
def api_telethon_qr_check():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    resp, err = _relay_call('/qr-login/check', {}, timeout=15)
    if err:
        return jsonify({'error': err}), 400
    if resp.get('error'):
        return jsonify({'error': resp['error']}), 400

    if resp.get('success'):
        settings = load_settings()
        settings['telethon_session'] = 'relay-managed'
        if resp.get('phone'):
            settings['telethon_phone'] = resp['phone']
        settings.pop('telethon_temp_session', None)
        settings.pop('telethon_phone_code_hash', None)
        save_settings(settings)

    return jsonify(resp)


@app.route('/api/admin/telethon/qr-2fa', methods=['POST'])
def api_telethon_qr_2fa():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    password = str(data.get('password', '')).strip()
    if not password:
        return jsonify({'error': 'Введите пароль'}), 400

    resp, err = _relay_call('/qr-login/2fa', {'password': password})
    if err:
        return jsonify({'error': err}), 400
    if resp.get('error'):
        return jsonify({'error': resp['error']}), 400

    if resp.get('success'):
        settings = load_settings()
        settings['telethon_session'] = 'relay-managed'
        if resp.get('phone'):
            settings['telethon_phone'] = resp['phone']
        settings.pop('telethon_temp_session', None)
        settings.pop('telethon_phone_code_hash', None)
        save_settings(settings)

    return jsonify(resp)


# ---------- Telegram Star Gifts catalog ----------

@app.route('/api/admin/telethon/star-gifts', methods=['POST'])
def api_admin_star_gifts():
    """Fetch available Telegram star gifts via relay."""
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    resp, err = _relay_call('/get-star-gifts', {}, timeout=30)
    if err:
        return jsonify({'error': err}), 400
    return jsonify(resp)


# ---------- Gift sending via relay ----------

def send_gift_telethon(user_id, gift_id):
    """Send a gift via the Telethon relay service."""
    if not _relay_is_configured():
        return False, 'Relay не настроен'

    resp, err = _relay_call('/send-gift', {
        'user_id': int(user_id),
        'gift_id': str(gift_id),
    }, timeout=25)

    if err:
        logging.error(f"Relay send_gift error user={user_id} gift={gift_id}: {err}")
        return False, err
    if resp.get('error'):
        logging.error(f"Relay send_gift failed user={user_id} gift={gift_id}: {resp['error']}")
        return False, resp['error']
    if resp.get('ok') or resp.get('success'):
        return True, ''
    return False, 'Неизвестная ошибка relay'


def send_telegram_gift_bot_api(bot_token, user_id, gift_id):
    """Fallback: send gift via Bot API sendGift (from bot, not account)."""
    try:
        payload = {'user_id': int(user_id), 'gift_id': str(gift_id)}
        resp = http_requests.post(
            f'https://api.telegram.org/bot{bot_token}/sendGift',
            json=payload, timeout=15)
        result = resp.json()
        if result.get('ok'):
            return True, ''
        err = result.get('description', 'Unknown error')
        logging.error(f"sendGift (bot API) failed user={user_id} gift={gift_id}: {err}")
        return False, err
    except Exception as e:
        logging.error(f"sendGift (bot API) exception: {e}")
        return False, str(e)


def send_telegram_gift(bot_token, user_id, gift_id):
    """Send gift via Telethon relay only (from user account, not bot)."""
    settings = load_settings()
    if _relay_is_configured() and settings.get('telethon_session'):
        return send_gift_telethon(user_id, gift_id)
    return False, 'Telethon сессия не настроена. Авторизуйтесь в админке (QR/код/сессия).'


def notify_admins_withdrawal(withdrawal_id, user_id, username, gifts_desc, total_amount, status):
    """Send Telegram notification to all admins about a new withdrawal request."""
    def _send():
        status_emoji = {'completed': '✅', 'queued': '⏳', 'pending': '🕐', 'partial': '⚠️', 'failed': '❌'}.get(status, '🔔')
        status_text = {'completed': 'Выполнен', 'queued': 'В очереди', 'pending': 'Ожидает', 'partial': 'Частично', 'failed': 'Ошибка'}.get(status, status)
        text = (
            f"🔔 Новый вывод!\n\n"
            f"ID: #{withdrawal_id}\n"
            f"👤 {username} ({user_id})\n"
            f"💰 {int(total_amount)} ⭐\n"
            f"🎁 {gifts_desc}\n"
            f"{status_emoji} Статус: {status_text}"
        )
        for aid in ADMIN_IDS:
            try:
                http_requests.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                    json={'chat_id': aid, 'text': text, 'parse_mode': 'HTML'},
                    timeout=5)
            except Exception:
                pass
    threading.Thread(target=_send, daemon=True).start()


def _is_balance_error(msg):
    low = msg.lower()
    # STARGIFT_INVALID is a gift-ID error, NOT a balance error
    if 'stargift_invalid' in low:
        return False
    return any(k in low for k in (
        'not enough', 'balance_too_low', 'insufficient',
        'pay_stars_required', 'not_enough_stars',
        'gift_send_failed', 'not enough stars',
    ))


def _is_gift_invalid_error(msg):
    low = msg.lower()
    return 'stargift_invalid' in low


def process_withdrawal_auto(withdrawal_id):
    """Auto-send gifts for a withdrawal."""
    db = connect_db()
    try:
        w = db.execute('SELECT * FROM withdrawals WHERE id = ?', (withdrawal_id,)).fetchone()
        if not w or w['status'] in ('completed', 'rejected'):
            return

        # Check retry count — stop after 10 attempts for balance errors
        retry_count = w['retry_count'] if 'retry_count' in w.keys() else 0
        if retry_count >= 10:
            db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                       ('failed', 'Превышен лимит попыток (10). Обработайте вручную.', withdrawal_id))
            db.commit()
            return

        # Need either Telethon relay session or bot token
        settings = load_settings()
        has_telethon_sess = _relay_is_configured() and bool(settings.get('telethon_session'))
        bot_token = BOT_TOKEN

        if not has_telethon_sess and not bot_token:
            db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                       ('pending', 'Автовывод не настроен', withdrawal_id))
            db.commit()
            return

        selected_gifts = json.loads(w['gifts_json'])
        user_id = w['user_id']
        success_count = 0
        fail_count = 0
        last_error = ''

        for gift in selected_gifts:
            qty = gift.get('qty', 1)
            tg_gift_id = gift.get('telegram_gift_id', '')
            if not tg_gift_id:
                fail_count += qty
                last_error = 'telegram_gift_id не установлен'
                continue
            for _ in range(qty):
                ok, err = send_telegram_gift(bot_token, user_id, tg_gift_id)
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                    last_error = err
                import time; time.sleep(1)

        total = success_count + fail_count
        if fail_count == 0 and success_count > 0:
            db.execute('UPDATE withdrawals SET status=?, processed_at=CURRENT_TIMESTAMP, error_msg=? WHERE id=?',
                       ('completed', '', withdrawal_id))
            db.commit()
            try:
                http_requests.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                    json={'chat_id': user_id,
                          'text': f'✅ Ваш вывод #{withdrawal_id} на {int(w["amount"])} ⭐ выполнен! Подарки отправлены.'},
                    timeout=5)
            except Exception:
                pass
        elif success_count > 0:
            db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                       ('partial', f'Отправлено {success_count}/{total}. Ошибка: {last_error}', withdrawal_id))
            db.commit()
        else:
            if _is_gift_invalid_error(last_error):
                # Gift ID is invalid/stale — don't retry, it won't help
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('failed', 'Подарок не найден в каталоге Telegram. Проверьте ID подарка в админке.', withdrawal_id))
            elif _is_balance_error(last_error):
                new_retry = retry_count + 1
                if new_retry >= 10:
                    db.execute('UPDATE withdrawals SET status=?, error_msg=?, retry_count=? WHERE id=?',
                               ('failed', f'Временная ошибка вывода (попытка {new_retry}/10). Обратитесь в поддержку.', new_retry, withdrawal_id))
                else:
                    db.execute('UPDATE withdrawals SET status=?, error_msg=?, retry_count=? WHERE id=?',
                               ('queued', f'Вывод в обработке (попытка {new_retry}/10). Следующая через 5 мин...', new_retry, withdrawal_id))
            else:
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('failed', 'Ошибка вывода. Обратитесь в поддержку.', withdrawal_id))
            db.commit()
    except Exception as e:
        logging.error(f"process_withdrawal_auto error #{withdrawal_id}: {e}")
    finally:
        db.close()


# Background retry — every 5 min for queued, every 30s for pending
_withdraw_retry_running = False

def _withdraw_retry_loop():
    global _withdraw_retry_running
    import time
    # Ensure retry_count column exists
    try:
        dbc = connect_db()
        dbc.execute('ALTER TABLE withdrawals ADD COLUMN retry_count INTEGER DEFAULT 0')
        dbc.commit()
        dbc.close()
    except Exception:
        pass  # column already exists

    # Wait 30s before first retry so site can serve requests first
    for _ in range(30):
        if not _withdraw_retry_running:
            return
        time.sleep(1)

    while _withdraw_retry_running:
        try:
            settings = load_settings()
            has_sender = (_relay_is_configured() and settings.get('telethon_session')) or BOT_TOKEN
            if has_sender:
                db = connect_db()
                rows = db.execute(
                    "SELECT id FROM withdrawals WHERE status IN ('pending') ORDER BY created_at ASC"
                ).fetchall()
                db.close()
                for row in rows:
                    if not _withdraw_retry_running:
                        break
                    process_withdrawal_auto(row['id'])
                    time.sleep(3)
        except Exception as e:
            logging.error(f"Withdraw retry error: {e}")
        # Sleep 30s for pending items
        for _ in range(30):
            if not _withdraw_retry_running:
                break
            time.sleep(1)

        # Also retry queued (balance errors) less frequently — every 5 min (10 iterations of 30s)
        try:
            db = connect_db()
            queued = db.execute(
                "SELECT id FROM withdrawals WHERE status = 'queued' ORDER BY created_at ASC"
            ).fetchall()
            db.close()
            if queued:
                for row in queued:
                    if not _withdraw_retry_running:
                        break
                    process_withdrawal_auto(row['id'])
                    time.sleep(3)
                # After processing queued, wait 5 min before next cycle
                for _ in range(270):
                    if not _withdraw_retry_running:
                        break
                    time.sleep(1)
        except Exception as e:
            logging.error(f"Withdraw queued retry error: {e}")

def start_withdraw_retry_thread():
    global _withdraw_retry_running
    if _withdraw_retry_running:
        return
    _withdraw_retry_running = True
    t = threading.Thread(target=_withdraw_retry_loop, daemon=True)
    t.start()
    logging.info("Withdrawal retry thread started")

# One-time fix: mark all queued/pending STARGIFT_INVALID withdrawals as failed
try:
    _fixdb = connect_db()
    _stuck = _fixdb.execute("SELECT id, status, error_msg FROM withdrawals WHERE status IN ('queued', 'pending')").fetchall()
    for _sw in _stuck:
        _emsg = _sw['error_msg'] or ''
        if 'STARGIFT_INVALID' in _emsg or 'звёзд' in _emsg.lower() or 'GetPaymentFormRequest' in _emsg:
            _fixdb.execute("UPDATE withdrawals SET status='failed', error_msg=? WHERE id=?",
                           (f"Авто-исправлено: {_emsg}", _sw['id']))
            logging.info(f"Fixed stuck withdrawal #{_sw['id']}: {_sw['status']} -> failed")
    _fixdb.commit()
    _fixdb.close()
except Exception as _fe:
    logging.warning(f"Stuck withdrawal fix error: {_fe}")

start_withdraw_retry_thread()


# ------ Admin settings (kept minimal for backward compat) ------

@app.route('/api/admin/settings', methods=['GET', 'POST'])
def api_admin_settings():
    admin_id = request.args.get('admin_id', type=int) or (request.json or {}).get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    if request.method == 'POST':
        # Legacy — no-op, kept for compat
        return jsonify({'success': True})
    else:
        # Return Telethon relay status for admin
        settings = load_settings()
        connected = _relay_is_configured() and bool(settings.get('telethon_session'))
        return jsonify({
            'telethon_connected': connected,
            'telethon_phone': settings.get('telethon_phone', ''),
            'online_boost': settings.get('online_boost', 0),
        })


@app.route('/api/admin/online-boost', methods=['POST'])
def api_admin_online_boost():
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    boost = int(data.get('boost', 0))
    settings = load_settings()
    settings['online_boost'] = boost
    save_settings(settings)
    return jsonify({'success': True, 'online_boost': boost})


@app.route('/api/admin/pvp/reset', methods=['POST'])
def api_admin_pvp_reset():
    """Reset all PVP games and start fresh."""
    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    
    db = get_db()
    # Cancel all non-finished games
    db.execute("UPDATE pvp_games SET status='cancelled' WHERE status IN ('waiting', 'betting', 'countdown', 'spinning')")
    db.commit()
    
    # Reset cache
    with _pvp_lock:
        _pvp_cache['game_id'] = 0
        _pvp_cache['status'] = 'waiting'
        _pvp_cache['players'] = []
        _pvp_cache['total_pot'] = 0
        _pvp_cache['countdown'] = 0
        _pvp_cache['winner'] = None
        _pvp_cache['spin_angle'] = 0
    
    return jsonify({'success': True, 'message': 'PVP games reset'})


@app.route('/api/admin/pvp/debug')
def api_admin_pvp_debug():
    """Debug endpoint to view PVP cache and recent games."""
    db = get_db()
    # Get last 5 games from DB
    games = db.execute(
        "SELECT id, status, total_pot, hash, winner_id, created_at FROM pvp_games ORDER BY id DESC LIMIT 5"
    ).fetchall()
    
    with _pvp_lock:
        cache_copy = dict(_pvp_cache)
    
    return jsonify({
        'cache': cache_copy,
        'recent_games': [dict(g) for g in games],
        'threads_started': _threads_started
    })


@app.route('/api/admin/maintenance', methods=['GET', 'POST'])
def api_admin_maintenance():
    """Toggle maintenance mode on/off."""
    if request.method == 'GET':
        settings = load_settings()
        return jsonify({
            'enabled': settings.get('maintenance_enabled', False),
            'end_time': settings.get('maintenance_end_time', ''),
        })

    data = request.json or {}
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    settings = load_settings()
    settings['maintenance_enabled'] = bool(data.get('enabled', False))
    settings['maintenance_end_time'] = data.get('end_time', '')
    save_settings(settings)
    logging.info(f"Maintenance mode {'ENABLED' if settings['maintenance_enabled'] else 'DISABLED'} by admin {admin_id}")
    return jsonify({
        'success': True,
        'enabled': settings['maintenance_enabled'],
        'end_time': settings['maintenance_end_time'],
    })


# ---------- Telegram catalog cache ----------
_tg_catalog_cache = {'gifts': [], 'balance': None, 'ts': 0}
_TG_CATALOG_TTL = 300  # 5 min cache

def _fetch_telegram_catalog(force=False):
    """Fetch star gifts catalog from Telegram via relay, with caching."""
    import time as _time
    now = _time.time()
    if not force and _tg_catalog_cache['gifts'] and (now - _tg_catalog_cache['ts']) < _TG_CATALOG_TTL:
        return _tg_catalog_cache['gifts'], _tg_catalog_cache['balance'], None

    if not _relay_is_configured():
        return [], None, 'Relay не настроен'

    settings = load_settings()
    if not settings.get('telethon_session'):
        return [], None, 'Сессия не настроена'

    resp, err = _relay_call('/get-star-gifts', {'include_thumbs': True}, timeout=45)
    if err:
        # Return stale cache if available
        if _tg_catalog_cache['gifts']:
            return _tg_catalog_cache['gifts'], _tg_catalog_cache['balance'], None
        return [], None, err

    if not resp or not resp.get('ok'):
        error_msg = resp.get('error', 'Unknown') if resp else 'Empty response'
        if _tg_catalog_cache['gifts']:
            return _tg_catalog_cache['gifts'], _tg_catalog_cache['balance'], None
        return [], None, error_msg

    gifts = resp.get('gifts', [])
    balance = resp.get('star_balance')
    _tg_catalog_cache['gifts'] = gifts
    _tg_catalog_cache['balance'] = balance
    _tg_catalog_cache['ts'] = now
    return gifts, balance, None


@app.route('/api/telegram-catalog')
def api_telegram_catalog():
    """Public endpoint: returns available Telegram star gifts for withdrawal."""
    gifts, balance, err = _fetch_telegram_catalog()
    if err and not gifts:
        return jsonify({'ok': False, 'error': err, 'gifts': []}), 400
    result = []
    for g in gifts:
        if g.get('sold_out'):
            continue
        result.append({
            'id': g['id'],
            'name': g.get('title') or f"Gift {g['stars']}⭐",
            'stars': g['stars'],
            'telegram_gift_id': str(g['id']),
            'limited': g.get('limited', False),
            'availability_remains': g.get('availability_remains'),
            'availability_total': g.get('availability_total'),
            'thumb_b64': g.get('thumb_b64', ''),
            'thumb_mime': g.get('thumb_mime', ''),
        })
    result.sort(key=lambda x: x['stars'])
    return jsonify({'ok': True, 'gifts': result, 'star_balance': balance})


@app.route('/api/withdraw/gifts')
def api_withdraw_gifts():
    """Return available gifts for withdrawal — fetched from Telegram catalog."""
    gifts, balance, err = _fetch_telegram_catalog()

    result = []
    if gifts:
        for g in gifts:
            if g.get('sold_out'):
                continue
            result.append({
                'id': g['id'],
                'name': g.get('title') or f"Gift {g['stars']}⭐",
                'image': '',
                'star_count': g['stars'],
                'bg_color': '',
                'telegram_gift_id': str(g['id']),
                'available': True,
                'thumb_b64': g.get('thumb_b64', ''),
                'thumb_mime': g.get('thumb_mime', ''),
            })
    else:
        # Fallback: use manually configured gifts from gifts.json
        all_gifts = load_gifts()
        withdrawable = [g for g in all_gifts if g.get('withdrawable')]
        for wg in withdrawable:
            result.append({
                'id': wg['id'],
                'name': wg.get('name', ''),
                'image': wg.get('image', ''),
                'star_count': wg.get('price', wg.get('value', 0)),
                'bg_color': wg.get('bg_color', ''),
                'telegram_gift_id': wg.get('telegram_gift_id', ''),
                'available': True,
                'thumb_b64': '',
                'thumb_mime': '',
            })

    result.sort(key=lambda x: x['star_count'])
    return jsonify({'gifts': result, 'min_withdraw': MIN_WITHDRAW, 'star_balance': balance})


@app.route('/api/withdraw/request', methods=['POST'])
def api_withdraw_request():
    data = request.json
    telegram_id = data.get('telegram_id')
    selected_gifts = data.get('gifts', [])

    if not telegram_id or not selected_gifts:
        return jsonify({'error': 'Некорректные данные'}), 400

    total_amount = sum(g.get('star_count', 0) * g.get('qty', 1) for g in selected_gifts)
    if total_amount < MIN_WITHDRAW:
        return jsonify({'error': f'Минимальная сумма вывода: {MIN_WITHDRAW} ⭐'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'Пользователь не найден'}), 404
    if user['balance'] < total_amount:
        return jsonify({'error': 'Недостаточно звёзд на балансе'}), 400

    db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (total_amount, telegram_id))
    db.execute(
        'INSERT INTO withdrawals (user_id, amount, gifts_json, status) VALUES (?, ?, ?, ?)',
        (telegram_id, total_amount, json.dumps(selected_gifts, ensure_ascii=False), 'pending')
    )
    withdrawal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.commit()

    # Prepare notification info
    uname = user['username'] or user['first_name'] or str(telegram_id)
    gift_desc = ', '.join(f"{g.get('qty',1)}x {g.get('name','Gift')} ({g.get('star_count',0)}⭐)" for g in selected_gifts)

    # Check if auto-withdrawal is available (Telethon session or Bot API)
    settings = load_settings()
    can_auto = (_relay_is_configured() and settings.get('telethon_session')) or bool(BOT_TOKEN)
    if can_auto:
        success_count = 0
        fail_count = 0
        last_error = ''

        for gift in selected_gifts:
            qty = gift.get('qty', 1)
            tg_gift_id = gift.get('telegram_gift_id', '')
            if not tg_gift_id:
                fail_count += qty
                last_error = 'No telegram_gift_id'
                continue
            for _ in range(qty):
                ok, err = send_telegram_gift(BOT_TOKEN, telegram_id, tg_gift_id)
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                    last_error = err

        updated_user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()

        if fail_count == 0 and success_count > 0:
            db.execute('UPDATE withdrawals SET status=?, processed_at=CURRENT_TIMESTAMP WHERE id=?',
                       ('completed', withdrawal_id))
            db.commit()
            notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gift_desc, total_amount, 'completed')
            return jsonify({'success': True, 'status': 'completed',
                            'message': 'Подарки успешно отправлены! ✅',
                            'new_balance': updated_user['balance']})
        elif success_count > 0:
            db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                       ('partial', f'Отправлено {success_count}/{success_count+fail_count}', withdrawal_id))
            db.commit()
            notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gift_desc, total_amount, 'partial')
            return jsonify({'success': True, 'status': 'partial',
                            'message': f'Частично отправлено ({success_count}/{success_count+fail_count}). Остальное автоматически.',
                            'new_balance': updated_user['balance']})
        else:
            if _is_gift_invalid_error(last_error):
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('failed', 'Подарок не найден в каталоге Telegram. Проверьте ID подарка в админке.', withdrawal_id))
                db.commit()
                notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gift_desc, total_amount, 'failed')
                return jsonify({'success': True, 'status': 'failed',
                                'message': 'Ошибка вывода. Обратитесь в поддержку.',
                                'new_balance': updated_user['balance']})
            elif _is_balance_error(last_error):
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('queued', 'Вывод в обработке. Автоповтор...', withdrawal_id))
                db.commit()
                notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gift_desc, total_amount, 'queued')
                return jsonify({'success': True, 'status': 'queued',
                                'message': 'Вывод в обработке. Ожидайте — подарки будут отправлены автоматически.',
                                'new_balance': updated_user['balance']})
            else:
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('queued', 'Ошибка вывода. Автоповтор...', withdrawal_id))
                db.commit()
                notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gift_desc, total_amount, 'queued')
                return jsonify({'success': True, 'status': 'queued',
                                'message': 'Вывод в обработке. Ожидайте — система повторит автоматически.',
                                'new_balance': updated_user['balance']})
    else:
        db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                   ('pending', 'Автовывод не настроен', withdrawal_id))
        db.commit()
        updated_user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gift_desc, total_amount, 'pending')
        return jsonify({'success': True, 'status': 'pending',
                        'message': f'Заявка #{withdrawal_id} создана. Ожидайте.',
                        'new_balance': updated_user['balance']})


# ============ TASKS API ============

@app.route('/api/tasks')
def api_tasks():
    db = get_db()
    tasks = db.execute('SELECT * FROM tasks WHERE is_active = 1 ORDER BY created_at DESC').fetchall()
    result = []
    for t in tasks:
        td = dict(t)
        # Attach gift info if reward_type is 'gift'
        if td.get('reward_type') == 'gift' and td.get('reward_gift_id'):
            gifts = load_gifts()
            g = next((x for x in gifts if x.get('id') == int(td['reward_gift_id'])), None)
            if g:
                slug = g.get('slug', '')
                assets = get_fragment_assets(slug) if slug else {}
                td['reward_gift'] = {
                    'id': g['id'],
                    'name': g.get('name', ''),
                    'image': g.get('image', ''),
                    'price': g.get('price', 0),
                    'slug': slug,
                    'item_count': g.get('item_count', 0),
                }
                td['gift_name'] = g.get('name', '')
                td['gift_image'] = g.get('image', '')
        result.append(td)
    return jsonify(result)


@app.route('/api/tasks/progress/<int:telegram_id>')
def api_task_progress(telegram_id):
    """Return progress for goal-based tasks (topup, referral, earn_stars)"""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({})
    ref_count = db.execute('SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?', (telegram_id,)).fetchone()['cnt']
    return jsonify({
        'total_topup': user['total_topup'] if 'total_topup' in user.keys() else 0,
        'total_earned': user['total_earned'] if 'total_earned' in user.keys() else 0,
        'referral_count': ref_count,
    })


@app.route('/api/tasks/completed/<int:telegram_id>')
def api_completed_tasks(telegram_id):
    db = get_db()
    completed = db.execute('SELECT task_id FROM completed_tasks WHERE user_id = ?', (telegram_id,)).fetchall()
    return jsonify([c['task_id'] for c in completed])


@app.route('/api/tasks/complete', methods=['POST'])
def api_complete_task():
    data = request.json
    telegram_id = data.get('telegram_id')
    task_id = data.get('task_id')

    if not telegram_id or not task_id:
        return jsonify({'error': 'Missing data'}), 400

    db = get_db()

    existing = db.execute(
        'SELECT id FROM completed_tasks WHERE user_id = ? AND task_id = ?',
        (telegram_id, task_id)
    ).fetchone()
    if existing:
        return jsonify({'error': 'Task already completed'}), 400

    task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # Check progress for goal-based tasks
    goal_type = task['goal_type'] if 'goal_type' in task.keys() else ''
    goal_amount = float(task['goal_amount']) if 'goal_amount' in task.keys() else 0

    if goal_type and goal_amount > 0:
        user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if goal_type == 'topup':
            current = float(user['total_topup']) if 'total_topup' in user.keys() else 0
            if current < goal_amount:
                return jsonify({'error': f'Нужно пополнить ещё {int(goal_amount - current)} ⭐'}), 400
        elif goal_type == 'referral':
            ref_count = db.execute('SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?', (telegram_id,)).fetchone()['cnt']
            if ref_count < goal_amount:
                return jsonify({'error': f'Нужно ещё {int(goal_amount - ref_count)} рефералов'}), 400
        elif goal_type == 'earn_stars':
            current = float(user['total_earned']) if 'total_earned' in user.keys() else 0
            if current < goal_amount:
                return jsonify({'error': f'Нужно заработать ещё {int(goal_amount - current)} ⭐'}), 400

    db.execute('INSERT INTO completed_tasks (user_id, task_id) VALUES (?, ?)', (telegram_id, task_id))

    # Handle reward
    reward_type = task['reward_type'] if 'reward_type' in task.keys() else 'stars'
    reward_data = {'type': reward_type}

    if reward_type == 'gift':
        gift_id = int(task['reward_gift_id']) if 'reward_gift_id' in task.keys() else 0
        if gift_id:
            gifts = load_gifts()
            gift = next((g for g in gifts if g.get('id') == gift_id), None)
            if gift:
                db.execute(
                    'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price) VALUES (?, ?, ?, ?, ?)',
                    (telegram_id, gift_id, gift['name'], gift.get('image', ''), gift.get('price', 0))
                )
                reward_data['gift_name'] = gift['name']
                reward_data['gift_image'] = gift.get('image', '')
        # Also give star reward if set
        if task['reward'] > 0:
            db.execute('UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE telegram_id = ?', (task['reward'], task['reward'], telegram_id))
    else:
        db.execute('UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE telegram_id = ?', (task['reward'], task['reward'], telegram_id))

    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    reward_data['reward'] = task['reward']
    reward_data['new_balance'] = user['balance']
    reward_data['success'] = True
    return jsonify(reward_data)


# ============ MARKET API ============

@app.route('/api/gifts')
def api_gifts():
    gifts = load_gifts()
    gifts.sort(key=lambda x: x.get('price', 0))
    return jsonify(gifts)


# ============ CRASH GAME API (server-side multiplayer) ============

@app.route('/api/crash/status')
def api_crash_status():
    """Polled every 800ms by clients to get current game state."""
    c = get_crash_cache()
    return jsonify({
        'success': True,
        'game_id': c['game_id'],
        'status': c['status'],
        'multiplier': c['multiplier'],
        'countdown': c.get('countdown', 0),
    })


@app.route('/api/crash/bet', methods=['POST'])
def api_crash_bet():
    data = request.json
    telegram_id = data.get('telegram_id')
    bet = data.get('bet', 0)
    if not telegram_id or not bet or bet < 1:
        return jsonify({'error': 'Invalid bet'}), 400

    c = get_crash_cache()
    game_id = c['game_id']
    status = c['status']

    # Allow bets during waiting or counting phase
    if status not in ('waiting', 'counting'):
        return jsonify({'error': 'Ставки закрыты'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user['balance'] < bet:
        return jsonify({'error': 'Недостаточно средств'}), 400

    # Check if already bet this game
    existing = db.execute(
        'SELECT id FROM crash_bets WHERE game_id = ? AND user_id = ?',
        (game_id, telegram_id)
    ).fetchone()
    if existing:
        return jsonify({'error': 'Вы уже сделали ставку'}), 400

    db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (bet, telegram_id))
    db.execute(
        'INSERT INTO crash_bets (game_id, user_id, bet_amount, status, first_name, photo_url) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (game_id, telegram_id, bet, 'playing',
         user['first_name'] or user['username'] or '',
         user['photo_url'] or '')
    )
    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({'success': True, 'new_balance': user['balance'], 'game_id': game_id})


@app.route('/api/crash/cashout', methods=['POST'])
def api_crash_cashout():
    data = request.json
    telegram_id = data.get('telegram_id')
    game_id = data.get('game_id')
    if not telegram_id or not game_id:
        return jsonify({'error': 'Invalid data'}), 400

    c = get_crash_cache()
    if c['status'] != 'flying' or c['game_id'] != game_id:
        return jsonify({'error': 'Невозможно забрать'}), 400

    # Use the max of DB multiplier and cache multiplier for fairness
    mult = c['multiplier']
    if mult < 1.01:
        mult = 1.01

    db = get_db()
    bet = db.execute(
        "SELECT * FROM crash_bets WHERE game_id = ? AND user_id = ? AND status = 'playing'",
        (game_id, telegram_id)
    ).fetchone()
    if not bet:
        return jsonify({'error': 'Ставка не найдена'}), 404

    winnings = round(bet['bet_amount'] * mult)
    profit = bet['bet_amount'] - winnings
    update_crash_cache(
        crash_profit_balance=_crash_cache.get('crash_profit_balance', 0) + profit
    )

    db.execute(
        "UPDATE crash_bets SET status='won', cashout_multiplier=?, win_amount=? WHERE id=?",
        (mult, winnings, bet['id'])
    )
    db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (winnings, telegram_id))
    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({
        'success': True,
        'new_balance': user['balance'],
        'winnings': winnings,
        'multiplier': mult
    })


@app.route('/api/crash/history')
def api_crash_history():
    db = get_db()
    rows = db.execute(
        "SELECT final_multiplier FROM crash_history ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return jsonify({
        'success': True,
        'history': [{'multiplier': r['final_multiplier']} for r in rows]
    })


@app.route('/api/crash/bets')
def api_crash_bets():
    c = get_crash_cache()
    game_id = c['game_id']
    if not game_id:
        return jsonify({'success': True, 'bets': []})
    db = get_db()
    rows = db.execute(
        "SELECT * FROM crash_bets WHERE game_id = ? ORDER BY id DESC LIMIT 50",
        (game_id,)
    ).fetchall()
    bets = []
    for r in rows:
        bets.append({
            'user_id': r['user_id'],
            'first_name': r['first_name'] or 'Игрок',
            'photo_url': r['photo_url'] or '',
            'bet_amount': r['bet_amount'],
            'status': r['status'],
            'cashout_mult': r['cashout_multiplier'] or 0,
            'win_amount': r['win_amount'] or 0,
        })
    return jsonify({'success': True, 'bets': bets})


# ============ PVP WHEEL API ============

@app.route('/api/pvp/state')
def api_pvp_state():
    """Polled by clients to get current PVP game state."""
    c = get_pvp_cache()
    # If no game created yet (cold start), indicate loading state
    if c['game_id'] == 0:
        return jsonify({
            'success': True,
            'game_id': 0,
            'status': 'loading',
            'players': [],
            'total_pot': 0,
            'countdown': 0,
            'winner': None,
            'spin_angle': 0,
            'hash': '',
        })
    return jsonify({
        'success': True,
        'game_id': c['game_id'],
        'status': c['status'],
        'players': c['players'],
        'total_pot': c['total_pot'],
        'countdown': c.get('countdown', 0),
        'winner': c.get('winner'),
        'spin_angle': c.get('spin_angle', 0),
        'hash': c.get('hash', ''),
    })


@app.route('/api/pvp/bet', methods=['POST'])
def api_pvp_bet():
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount', 0)
    if not telegram_id or not amount or amount < 1:
        return jsonify({'error': 'Invalid bet'}), 400

    # Get state atomically with the lock to prevent race conditions
    with _pvp_lock:
        game_id = _pvp_cache['game_id']
        status = _pvp_cache['status']

    # No game running yet (cold start)
    if game_id == 0:
        return jsonify({'error': 'Игра загружается, подождите...'}), 503

    # Allow bets during waiting, betting, or countdown
    if status not in ('waiting', 'betting', 'countdown'):
        return jsonify({'error': 'Ставки закрыты'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user['balance'] < amount:
        return jsonify({'error': 'Недостаточно звёзд'}), 400

    # Deduct balance
    db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (amount, telegram_id))

    # Check if player already in this game — add to their bet
    # Re-acquire lock and verify game_id hasn't changed
    with _pvp_lock:
        # Double-check game hasn't changed while we were fetching user data
        if _pvp_cache['game_id'] != game_id:
            db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, telegram_id))
            db.commit()
            return jsonify({'error': 'Игра изменилась, повторите ставку'}), 409
        existing_idx = None
        for i, p in enumerate(_pvp_cache['players']):
            if p['telegram_id'] == telegram_id:
                existing_idx = i
                break

        if existing_idx is not None:
            _pvp_cache['players'][existing_idx]['amount'] += amount
            _pvp_cache['total_pot'] += amount
            _pvp_cache['players'] = _pvp_compute_chances(_pvp_cache['players'])
            # Update DB
            db.execute(
                "UPDATE pvp_bets SET amount = amount + ? WHERE game_id = ? AND user_id = ?",
                (amount, game_id, telegram_id)
            )
        else:
            color_idx = len(_pvp_cache['players']) % len(PVP_COLORS)
            player = {
                'telegram_id': telegram_id,
                'username': user['username'] or '',
                'first_name': user['first_name'] or user['username'] or 'Player',
                'photo_url': user['photo_url'] or '',
                'amount': amount,
                'color': PVP_COLORS[color_idx],
                'chance': 0,
            }
            _pvp_cache['players'].append(player)
            _pvp_cache['total_pot'] += amount
            _pvp_cache['players'] = _pvp_compute_chances(_pvp_cache['players'])

            db.execute(
                "INSERT INTO pvp_bets (game_id, user_id, username, first_name, photo_url, amount, color) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (game_id, telegram_id, player['username'], player['first_name'],
                 player['photo_url'], amount, player['color'])
            )

        # Update game status
        if len(_pvp_cache['players']) >= 2 and _pvp_cache['status'] == 'betting':
            _pvp_cache['status'] = 'countdown'
            _pvp_cache['countdown'] = 30
        elif _pvp_cache['status'] == 'waiting':
            _pvp_cache['status'] = 'betting'

    db.execute("UPDATE pvp_games SET total_pot = total_pot + ? WHERE id = ?", (amount, game_id))
    db.commit()

    updated_user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({
        'success': True,
        'new_balance': updated_user['balance'],
        'game_id': game_id
    })


@app.route('/api/pvp/history')
def api_pvp_history():
    db = get_db()
    rows = db.execute(
        "SELECT g.id, g.total_pot, g.winner_id, g.created_at, "
        "b.username as winner_name, b.photo_url as winner_photo "
        "FROM pvp_games g LEFT JOIN pvp_bets b ON g.winner_id = b.user_id AND g.id = b.game_id "
        "WHERE g.status = 'result' ORDER BY g.id DESC LIMIT 10"
    ).fetchall()
    history = []
    for r in rows:
        history.append({
            'game_id': r['id'],
            'total_pot': r['total_pot'],
            'winner_name': r['winner_name'] or 'Unknown',
            'winner_photo': r['winner_photo'] or '',
        })
    return jsonify({'success': True, 'history': history})


@app.route('/api/buy', methods=['POST'])
def api_buy():
    data = request.json
    telegram_id = data.get('telegram_id')
    gift_id = data.get('gift_id')

    if not telegram_id or gift_id is None:
        return jsonify({'error': 'Missing data'}), 400

    gifts = load_gifts()
    gift = next((g for g in gifts if g['id'] == gift_id), None)
    if not gift:
        return jsonify({'error': 'Gift not found'}), 404

    price = gift.get('price', 0)
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Allow spending full balance (including deposited) on market
    if user['balance'] < price:
        return jsonify({'error': 'Недостаточно средств'}), 400

    db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (price, telegram_id))
    db.execute(
        'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price) VALUES (?, ?, ?, ?, ?)',
        (telegram_id, gift['id'], gift['name'], gift.get('image', ''), price)
    )
    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({'success': True, 'new_balance': user['balance'], 'gift': gift})


# ============ CASES API ============

@app.route('/api/cases')
def api_cases():
    cases = load_cases()
    show_hidden = request.args.get('show_hidden', '0') == '1'
    if not show_hidden:
        cases = [c for c in cases if not c.get('hidden', False)]
    return jsonify(cases)


@app.route('/api/cases/open', methods=['POST'])
def api_open_case():
    data = request.json
    telegram_id = data.get('telegram_id')
    case_id = data.get('case_id')
    use_discount = data.get('use_discount', False)
    inventory_id = data.get('inventory_id')  # If opening from inventory — free

    if not telegram_id or case_id is None:
        return jsonify({'error': 'Missing data'}), 400

    cases = load_cases()
    case = next((c for c in cases if c['id'] == case_id), None)
    if not case:
        return jsonify({'error': 'Case not found'}), 404

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    from_inventory = False
    if inventory_id:
        # Validate the inventory item belongs to user and is a case
        inv_item = db.execute(
            'SELECT * FROM inventory WHERE id = ? AND user_id = ? AND item_type = ?',
            (inventory_id, telegram_id, 'case')
        ).fetchone()
        if inv_item:
            from_inventory = True
        else:
            return jsonify({'error': 'Предмет не найден в инвентаре'}), 404

    actual_price = 0 if from_inventory else case['price']

    # Check for active case discount promo (only when not from inventory)
    if not from_inventory and use_discount:
        # Find unused case_discount promo for this user and case
        promo = db.execute('''
            SELECT pc.* FROM promo_codes pc
            JOIN promo_uses pu ON pc.id = pu.promo_id
            WHERE pu.user_id = ? AND pc.type = 'case_discount' AND (pc.case_id = ? OR pc.case_id = 0) AND pc.is_active = 1
            ORDER BY pc.value DESC LIMIT 1
        ''', (telegram_id, case_id)).fetchone()
        if promo:
            discount = promo['value']
            actual_price = max(0, round(case['price'] * (1 - discount / 100)))

    if not from_inventory and user['balance'] < actual_price:
        return jsonify({'error': 'Недостаточно средств'}), 400

    if not from_inventory:
        db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (actual_price, telegram_id))

    # Remove case from inventory if opened from there
    if from_inventory:
        db.execute('DELETE FROM inventory WHERE id = ? AND user_id = ?', (inventory_id, telegram_id))

    # Roll drop
    drops = case['drops']
    total_chance = sum(d['chance'] for d in drops)
    roll = random.uniform(0, total_chance)
    cumulative = 0
    won_drop = drops[0]

    for drop in drops:
        cumulative += drop['chance']
        if roll <= cumulative:
            won_drop = drop
            break

    result = {}
    if won_drop['type'] == 'stars':
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (won_drop['amount'], telegram_id))
        result = {'type': 'stars', 'amount': won_drop['amount']}
    elif won_drop['type'] == 'gift':
        gifts = load_gifts()
        gift = next((gi for gi in gifts if gi['id'] == won_drop['gift_id']), None)
        if gift:
            price = gift.get('price', 0)
            db.execute(
                'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price, item_type) VALUES (?, ?, ?, ?, ?, ?)',
                (telegram_id, gift['id'], gift['name'], gift.get('image', ''), price, 'gift')
            )
            # Add Fragment assets + ensure slug/item_count
            slug = gift.get('slug', '')
            gift['item_count'] = gift.get('item_count', 1000)
            if slug:
                assets = get_fragment_assets(slug)
                gift.update({k: v for k, v in assets.items() if v})
            result = {'type': 'gift', 'gift': gift}

    db.commit()
    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    result['new_balance'] = user['balance']
    return jsonify(result)


@app.route('/api/cases/drops/<int:case_id>')
def api_case_drops(case_id):
    cases = load_cases()
    case = next((c for c in cases if c['id'] == case_id), None)
    if not case:
        return jsonify({'error': 'Case not found'}), 404

    gifts = load_gifts()
    drops_info = []
    for drop in case['drops']:
        if drop['type'] == 'stars':
            drops_info.append({
                'type': 'stars',
                'name': f"{drop['amount']} Stars",
                'amount': drop['amount'],
                'chance': drop['chance'],
                'image': '/static/img/star.png',
                'price': drop['amount']
            })
        elif drop['type'] == 'gift':
            gift = next((gi for gi in gifts if gi['id'] == drop['gift_id']), None)
            if gift:
                slug = gift.get('slug', '')
                assets = get_fragment_assets(slug) if slug else {}
                drop_info = {
                    'type': 'gift',
                    'name': gift['name'],
                    'chance': drop['chance'],
                    'image': gift.get('image', ''),
                    'price': gift.get('price', 0),
                    'slug': slug,
                    'item_count': gift.get('item_count', 1000)
                }
                drop_info.update({k: v for k, v in assets.items() if v})
                drops_info.append(drop_info)

    drops_info.sort(key=lambda x: x['price'], reverse=True)
    return jsonify(drops_info)


# ============ SCRATCH API ============

@app.route('/api/scratch')
def api_scratch():
    scratches = load_scratches()
    return jsonify(scratches)


@app.route('/api/scratch/free-check/<int:telegram_id>')
def api_scratch_free_check(telegram_id):
    """Check if user has free first scratch available"""
    db = get_db()
    user = db.execute('SELECT free_scratch_used FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'has_free': False})
    return jsonify({'has_free': not user['free_scratch_used']})


@app.route('/api/scratch/discount-check/<int:telegram_id>')
def api_scratch_discount_check(telegram_id):
    """Check if user has an available scratch discount promo (not yet applied)"""
    db = get_db()
    promo = db.execute('''
        SELECT pc.value, pc.scratch_id FROM promo_codes pc
        JOIN promo_uses pu ON pc.id = pu.promo_id
        WHERE pu.user_id = ? AND pc.type = 'scratch_discount'
        AND pc.is_active = 1 AND pu.discount_applied = 0
        ORDER BY pc.value DESC LIMIT 1
    ''', (telegram_id,)).fetchone()
    if promo:
        return jsonify({'has_discount': True, 'percent': promo['value'], 'scratch_id': promo['scratch_id']})
    return jsonify({'has_discount': False})


@app.route('/api/scratch/play', methods=['POST'])
def api_scratch_play():
    data = request.json
    telegram_id = data.get('telegram_id')
    scratch_id = data.get('scratch_id')

    if not telegram_id or not scratch_id:
        return jsonify({'error': 'Missing parameters'}), 400

    scratches = load_scratches()
    scratch = next((s for s in scratches if s['id'] == scratch_id), None)
    if not scratch:
        return jsonify({'error': 'Scratch not found'}), 404

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    price = scratch['price']
    is_free = False
    discount_promo_id = None

    # Free first scratch for new users
    if data.get('use_free') and not user['free_scratch_used']:
        is_free = True
        db.execute('UPDATE users SET free_scratch_used = 1 WHERE telegram_id = ?', (telegram_id,))
    else:
        # Check for scratch discount promo (one-time use)
        if data.get('use_scratch_discount'):
            promo = db.execute('''
                SELECT pc.id, pc.value, pc.scratch_id FROM promo_codes pc
                JOIN promo_uses pu ON pc.id = pu.promo_id
                WHERE pu.user_id = ? AND pc.type = 'scratch_discount'
                AND (pc.scratch_id = ? OR pc.scratch_id = 0)
                AND pc.is_active = 1 AND pu.discount_applied = 0
                ORDER BY pc.value DESC LIMIT 1
            ''', (telegram_id, scratch_id)).fetchone()
            if promo:
                discount_percent = promo['value']
                price = max(0, round(scratch['price'] * (1 - discount_percent / 100)))
                discount_promo_id = promo['id']

        if user['balance'] < price:
            return jsonify({'error': 'Недостаточно звёзд'}), 400

    # Deduct balance (skip if free)
    if not is_free:
        db.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (price, telegram_id))
        # Mark discount as applied so it can't be used again
        if discount_promo_id:
            db.execute('UPDATE promo_uses SET discount_applied = 1 WHERE user_id = ? AND promo_id = ?',
                       (telegram_id, discount_promo_id))

    picks = scratch.get('picks', 1)
    drops = scratch['drops']
    gifts_data = load_gifts()

    def roll_prize():
        roll = random.random() * 100
        cumulative = 0
        for drop in drops:
            cumulative += drop['chance']
            if roll <= cumulative:
                return drop
        return drops[-1]

    def process_prize(prize_drop):
        r = {}
        if prize_drop['type'] == 'stars':
            db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (prize_drop['amount'], telegram_id))
            r['prize_type'] = 'stars'
            r['prize_amount'] = prize_drop['amount']
            r['prize_name'] = f"+{prize_drop['amount']} Stars"
            r['prize_image'] = '/static/img/star.png'
        elif prize_drop['type'] == 'gift':
            gift = next((g for g in gifts_data if g['id'] == prize_drop['gift_id']), None)
            if gift:
                price_val = gift.get('price', 0)
                image_url = gift.get('image', '')
                db.execute(
                    'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price) VALUES (?, ?, ?, ?, ?)',
                    (telegram_id, gift['id'], gift['name'], image_url, price_val)
                )
                slug = gift.get('slug', '')
                gift['item_count'] = gift.get('item_count', 1000)
                if slug:
                    assets = get_fragment_assets(slug)
                    gift.update({k: v for k, v in assets.items() if v})
                r['prize_type'] = 'gift'
                r['prize_name'] = gift['name']
                r['prize_image'] = image_url
                r['prize_slug'] = gift.get('slug', '')
                r['prize_item_count'] = gift.get('item_count', 1000)
            else:
                db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (price, telegram_id))
                r['prize_type'] = 'stars'
                r['prize_amount'] = price
                r['prize_name'] = f"+{price} Stars"
                r['prize_image'] = '/static/img/star.png'
        return r

    if picks <= 1:
        # Single pick — original behavior, flat response
        prize = roll_prize()
        result = process_prize(prize)
    else:
        # Multi-pick — return array of prizes
        prizes = []
        for _ in range(picks):
            prize = roll_prize()
            prizes.append(process_prize(prize))
        result = {'picks': picks, 'prizes': prizes}

    db.commit()
    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    result['new_balance'] = user['balance']
    return jsonify(result)


# ============ INVENTORY API ============

@app.route('/api/inventory/<int:telegram_id>')
def api_inventory(telegram_id):
    db = get_db()
    items = db.execute(
        'SELECT * FROM inventory WHERE user_id = ? ORDER BY acquired_at DESC',
        (telegram_id,)
    ).fetchall()
    gifts = load_gifts()
    gift_map = {g['id']: g for g in gifts}
    cases = load_cases()
    case_map = {c['id']: c for c in cases}
    result = []
    for i in items:
        item = dict(i)
        item_type = item.get('item_type', 'gift')
        # Add frontend-friendly aliases
        item['type'] = item_type
        item['name'] = item.get('gift_name', '')
        item['image'] = item.get('gift_image', '')
        item['price'] = item.get('gift_price', 0)
        if item_type == 'case':
            cs = case_map.get(item.get('case_id', 0))
            if cs:
                item['case_data'] = cs
                item['name'] = cs.get('name', item['name'])
                item['image'] = cs.get('image', item['image'])
        else:
            gift = gift_map.get(item.get('gift_id'))
            if gift:
                slug = gift.get('slug', '')
                item['slug'] = slug
                item['name'] = gift.get('name', item['name'])
                item['price'] = gift.get('price', gift.get('value', item['price']))
                item['image'] = gift.get('image', item['image'])
                item['item_count'] = gift.get('item_count', 1000)
                item['withdrawable'] = gift.get('withdrawable', False)
                item['telegram_gift_id'] = gift.get('telegram_gift_id', '')
                item['star_count'] = gift.get('value', 0)
                item['bg_color'] = gift.get('bg_color', '')
                if slug:
                    assets = get_fragment_assets(slug)
                    item.update({k: v for k, v in assets.items() if v})
        result.append(item)
    return jsonify(result)


@app.route('/api/inventory/open-case', methods=['POST'])
def api_inventory_open_case():
    """Open a case item from inventory"""
    data = request.json
    telegram_id = data.get('telegram_id')
    inventory_id = data.get('inventory_id')

    if not telegram_id or not inventory_id:
        return jsonify({'error': 'Missing data'}), 400

    db = get_db()
    item = db.execute('SELECT * FROM inventory WHERE id = ? AND user_id = ?', (inventory_id, telegram_id)).fetchone()
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    item_type = item['item_type'] if 'item_type' in item.keys() else 'gift'
    if item_type != 'case':
        return jsonify({'error': 'Not a case item'}), 400

    case_id = item['case_id'] if 'case_id' in item.keys() else 0
    cases = load_cases()
    case = next((c for c in cases if c['id'] == case_id), None)
    if not case:
        return jsonify({'error': 'Case data not found'}), 404

    # Remove case from inventory
    db.execute('DELETE FROM inventory WHERE id = ?', (inventory_id,))

    # Roll drop
    drops = case['drops']
    total_chance = sum(d['chance'] for d in drops)
    roll = random.uniform(0, total_chance)
    cumulative = 0
    won_drop = drops[0]
    for drop in drops:
        cumulative += drop['chance']
        if roll <= cumulative:
            won_drop = drop
            break

    result = {}
    if won_drop['type'] == 'stars':
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (won_drop['amount'], telegram_id))
        result = {'type': 'stars', 'amount': won_drop['amount']}
    elif won_drop['type'] == 'gift':
        gifts = load_gifts()
        gift = next((gi for gi in gifts if gi['id'] == won_drop['gift_id']), None)
        if gift:
            price = gift.get('price', 0)
            db.execute(
                'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price, item_type) VALUES (?, ?, ?, ?, ?, ?)',
                (telegram_id, gift['id'], gift['name'], gift.get('image', ''), price, 'gift')
            )
            slug = gift.get('slug', '')
            gift['item_count'] = gift.get('item_count', 1000)
            if slug:
                assets = get_fragment_assets(slug)
                gift.update({k: v for k, v in assets.items() if v})
            result = {'type': 'gift', 'gift': gift}

    db.commit()
    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    result['new_balance'] = user['balance']
    return jsonify(result)


@app.route('/api/inventory/withdraw', methods=['POST'])
def api_inventory_withdraw():
    """Withdraw a gift from inventory — sends it as a Telegram star gift."""
    data = request.json
    telegram_id = data.get('telegram_id')
    inventory_id = data.get('inventory_id')

    if not telegram_id or not inventory_id:
        return jsonify({'error': 'Некорректные данные'}), 400

    db = get_db()
    item = db.execute('SELECT * FROM inventory WHERE id = ? AND user_id = ?', (inventory_id, telegram_id)).fetchone()
    if not item:
        return jsonify({'error': 'Предмет не найден'}), 404

    # Look up the gift to get telegram_gift_id
    gifts = load_gifts()
    gift = next((g for g in gifts if g['id'] == item['gift_id']), None)
    if not gift or not gift.get('withdrawable'):
        return jsonify({'error': 'Этот подарок нельзя вывести'}), 400

    # NFT gifts without telegram_gift_id — just create notification
    if not gift.get('telegram_gift_id'):
        # Check if this is the user's first withdrawal
        prior_withdrawals = db.execute(
            'SELECT COUNT(*) as cnt FROM withdrawals WHERE user_id = ?', (telegram_id,)
        ).fetchone()['cnt']
        is_first_withdrawal = (prior_withdrawals == 0)

        star_count = gift.get('value', gift.get('price', 0))

        # Create withdrawal record as pending (manual)
        db.execute(
            'INSERT INTO withdrawals (user_id, amount, gifts_json, status, error_msg) VALUES (?, ?, ?, ?, ?)',
            (telegram_id, star_count,
             json.dumps([{'name': gift.get('name', ''), 'star_count': star_count, 'qty': 1, 'type': 'nft'}], ensure_ascii=False),
             'pending', 'NFT — ручной вывод')
        )
        withdrawal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Remove from inventory
        db.execute('DELETE FROM inventory WHERE id = ?', (inventory_id,))
        db.commit()

        # Notify admins
        usr = db.execute('SELECT username, first_name FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        uname = (usr['username'] or usr['first_name'] or str(telegram_id)) if usr else str(telegram_id)
        gifts_desc = f"1x {gift.get('name', 'NFT Gift')} (NFT)"
        notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gifts_desc, star_count, 'pending')

        # Notify user via Telegram
        def _notify_user():
            try:
                text = f"📦 Ваша заявка на вывод NFT подарка <b>{gift.get('name', '')}</b> принята!\n\nЗаявка #{withdrawal_id}. Ожидайте отправки."
                http_requests.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                    json={'chat_id': telegram_id, 'text': text, 'parse_mode': 'HTML'},
                    timeout=5)
            except Exception:
                pass
        threading.Thread(target=_notify_user, daemon=True).start()

        user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        return jsonify({'success': True, 'status': 'pending',
                        'message': f'Заявка #{withdrawal_id} на вывод NFT принята! Вам придёт уведомление.',
                        'new_balance': user['balance'],
                        'is_first_withdrawal': is_first_withdrawal})

    tg_gift_id = gift['telegram_gift_id']
    star_count = gift.get('value', gift.get('price', 0))

    # Check if this is the user's first withdrawal
    prior_withdrawals = db.execute(
        'SELECT COUNT(*) as cnt FROM withdrawals WHERE user_id = ?', (telegram_id,)
    ).fetchone()['cnt']
    is_first_withdrawal = (prior_withdrawals == 0)

    # Create withdrawal record
    db.execute(
        'INSERT INTO withdrawals (user_id, amount, gifts_json, status) VALUES (?, ?, ?, ?)',
        (telegram_id, star_count,
         json.dumps([{'telegram_gift_id': tg_gift_id, 'star_count': star_count, 'qty': 1, 'name': gift.get('name', '')}], ensure_ascii=False),
         'pending')
    )
    withdrawal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # Remove from inventory
    db.execute('DELETE FROM inventory WHERE id = ?', (inventory_id,))
    db.commit()

    # Get user info for admin notification
    usr = db.execute('SELECT username, first_name FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    uname = (usr['username'] or usr['first_name'] or str(telegram_id)) if usr else str(telegram_id)
    gifts_desc = f"1x {gift.get('name', 'Gift')} ({int(star_count)}⭐)"

    # Try auto-send
    settings = load_settings()
    can_auto = (_relay_is_configured() and settings.get('telethon_session')) or bool(BOT_TOKEN)
    if can_auto:
        ok, err = send_telegram_gift(BOT_TOKEN, telegram_id, tg_gift_id)
        if ok:
            db.execute('UPDATE withdrawals SET status=?, processed_at=CURRENT_TIMESTAMP WHERE id=?',
                       ('completed', withdrawal_id))
            db.commit()
            notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gifts_desc, star_count, 'completed')
            user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
            return jsonify({'success': True, 'status': 'completed',
                            'message': 'Подарок отправлен! Проверьте Telegram',
                            'new_balance': user['balance'],
                            'is_first_withdrawal': is_first_withdrawal})
        else:
            final_status = 'failed' if _is_gift_invalid_error(err) else 'queued'
            if _is_gift_invalid_error(err):
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('failed', 'Подарок не найден в каталоге Telegram.', withdrawal_id))
            else:
                db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                           ('queued', 'Вывод в обработке. Автоповтор...', withdrawal_id))
            db.commit()
            notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gifts_desc, star_count, final_status)
            user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
            return jsonify({'success': True, 'status': 'queued',
                            'message': 'Вывод в обработке. Подарок будет отправлен автоматически.',
                            'new_balance': user['balance'],
                            'is_first_withdrawal': is_first_withdrawal})
    else:
        db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                   ('pending', 'Автовывод не настроен', withdrawal_id))
        db.commit()
        notify_admins_withdrawal(withdrawal_id, telegram_id, uname, gifts_desc, star_count, 'pending')
        user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        return jsonify({'success': True, 'status': 'pending',
                        'message': f'Заявка #{withdrawal_id} создана. Ожидайте.',
                        'new_balance': user['balance'],
                        'is_first_withdrawal': is_first_withdrawal})


@app.route('/api/inventory/sell', methods=['POST'])
def api_sell():
    data = request.json
    telegram_id = data.get('telegram_id')
    inventory_id = data.get('inventory_id')

    if not telegram_id or not inventory_id:
        return jsonify({'error': 'Missing data'}), 400

    db = get_db()
    item = db.execute('SELECT * FROM inventory WHERE id = ? AND user_id = ?', (inventory_id, telegram_id)).fetchone()
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    sell_price = item['gift_price']
    db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (sell_price, telegram_id))
    db.execute('DELETE FROM inventory WHERE id = ?', (inventory_id,))
    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({'success': True, 'sell_price': sell_price, 'new_balance': user['balance']})


@app.route('/api/inventory/sell-all', methods=['POST'])
def api_sell_all():
    data = request.json
    telegram_id = data.get('telegram_id')
    if not telegram_id:
        return jsonify({'error': 'Missing data'}), 400

    db = get_db()
    items = db.execute("SELECT * FROM inventory WHERE user_id = ? AND (item_type IS NULL OR item_type != 'case')", (telegram_id,)).fetchall()
    if not items:
        return jsonify({'error': 'Нет предметов для продажи'}), 400

    total_price = sum(item['gift_price'] for item in items)
    sold_count = len(items)
    db.execute("DELETE FROM inventory WHERE user_id = ? AND (item_type IS NULL OR item_type != 'case')", (telegram_id,))
    db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (total_price, telegram_id))
    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    return jsonify({'success': True, 'total_price': total_price, 'sold_count': sold_count, 'new_balance': user['balance']})


@app.route('/api/inventory/withdraw-all', methods=['POST'])
def api_inventory_withdraw_all():
    """Withdraw all eligible NFT gifts from inventory at once."""
    data = request.json
    telegram_id = data.get('telegram_id')
    if not telegram_id:
        return jsonify({'error': 'Некорректные данные'}), 400

    db = get_db()
    items = db.execute(
        "SELECT * FROM inventory WHERE user_id = ? AND (item_type IS NULL OR item_type != 'case')",
        (telegram_id,)
    ).fetchall()
    if not items:
        return jsonify({'error': 'Нет предметов для вывода'}), 400

    gifts = load_gifts()
    eligible = []
    for item in items:
        gift = next((g for g in gifts if g['id'] == item['gift_id']), None)
        if gift and gift.get('withdrawable') and gift.get('telegram_gift_id'):
            eligible.append((item, gift))

    if not eligible:
        return jsonify({'error': 'Нет подарков, доступных для вывода в Telegram'}), 400

    # Check if this is the user's first withdrawal
    prior = db.execute('SELECT COUNT(*) as cnt FROM withdrawals WHERE user_id = ?', (telegram_id,)).fetchone()['cnt']
    is_first = (prior == 0)

    usr = db.execute('SELECT username, first_name FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    uname = (usr['username'] or usr['first_name'] or str(telegram_id)) if usr else str(telegram_id)

    settings = load_settings()
    can_auto = (_relay_is_configured() and settings.get('telethon_session')) or bool(BOT_TOKEN)

    results = []
    total_success = 0
    total_fail = 0

    for item, gift in eligible:
        tg_gift_id = gift['telegram_gift_id']
        star_count = gift.get('value', gift.get('price', 0))
        gift_name = gift.get('name', '')

        # Create withdrawal record
        db.execute(
            'INSERT INTO withdrawals (user_id, amount, gifts_json, status) VALUES (?, ?, ?, ?)',
            (telegram_id, star_count,
             json.dumps([{'telegram_gift_id': tg_gift_id, 'star_count': star_count, 'qty': 1, 'name': gift_name}], ensure_ascii=False),
             'pending')
        )
        wid = db.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Remove from inventory
        db.execute('DELETE FROM inventory WHERE id = ?', (item['id'],))
        db.commit()

        status = 'pending'
        if can_auto:
            ok, err = send_telegram_gift(BOT_TOKEN, telegram_id, tg_gift_id)
            if ok:
                db.execute('UPDATE withdrawals SET status=?, processed_at=CURRENT_TIMESTAMP WHERE id=?',
                           ('completed', wid))
                status = 'completed'
                total_success += 1
            else:
                if _is_gift_invalid_error(err):
                    db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                               ('failed', 'Подарок не найден в каталоге Telegram.', wid))
                    status = 'failed'
                else:
                    db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                               ('queued', 'Вывод в обработке. Автоповтор...', wid))
                    status = 'queued'
                total_fail += 1
            db.commit()
        else:
            db.execute('UPDATE withdrawals SET status=?, error_msg=? WHERE id=?',
                       ('pending', 'Автовывод не настроен', wid))
            db.commit()
            total_fail += 1

        # Notify admins per withdrawal
        desc = f"1x {gift_name} ({int(star_count)}⭐)"
        notify_admins_withdrawal(wid, telegram_id, uname, desc, star_count, status)

        results.append({'name': gift_name, 'status': status})
        import time; time.sleep(0.5)

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    total = len(eligible)
    if total_success == total:
        msg = f'Все {total} подарков отправлены! Проверьте Telegram ✅'
    elif total_success > 0:
        msg = f'Отправлено {total_success}/{total}. Остальные в обработке.'
    else:
        msg = f'Вывод {total} подарков в обработке. Ожидайте.'

    return jsonify({
        'success': True,
        'total': total,
        'sent': total_success,
        'queued': total_fail,
        'message': msg,
        'new_balance': user['balance'],
        'is_first_withdrawal': is_first,
        'results': results
    })


# ============ ADMIN API ============

@app.route('/api/admin/tasks', methods=['GET'])
def api_admin_get_tasks():
    db = get_db()
    tasks = db.execute('SELECT * FROM tasks ORDER BY created_at DESC').fetchall()
    result = []
    gifts = load_gifts()
    for t in tasks:
        td = dict(t)
        if td.get('reward_type') == 'gift' and td.get('reward_gift_id'):
            g = next((x for x in gifts if x.get('id') == int(td['reward_gift_id'])), None)
            if g:
                td['gift_name'] = g.get('name', '')
        result.append(td)
    return jsonify(result)


@app.route('/api/admin/tasks', methods=['POST'])
def api_admin_create_task():
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    db = get_db()
    db.execute(
        '''INSERT INTO tasks (type, title, description, reward, link, channel_id, reward_type, reward_gift_id, goal_type, goal_amount)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['type'], data['title'], data.get('description', ''),
         data.get('reward', 0), data.get('link', ''), data.get('channel_id', ''),
         data.get('reward_type', 'stars'), int(data.get('reward_gift_id', 0)),
         data.get('goal_type', ''), float(data.get('goal_amount', 0)))
    )
    db.commit()
    return jsonify({'success': True})


@app.route('/api/admin/tasks/<int:task_id>', methods=['DELETE'])
def api_admin_delete_task(task_id):
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/admin/tasks/<int:task_id>/toggle', methods=['POST'])
def api_admin_toggle_task(task_id):
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    db = get_db()
    task = db.execute('SELECT is_active FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if task:
        new_status = 0 if task['is_active'] else 1
        db.execute('UPDATE tasks SET is_active = ? WHERE id = ?', (new_status, task_id))
        db.commit()
    return jsonify({'success': True})


@app.route('/api/admin/cases', methods=['POST'])
def api_admin_save_cases():
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    cases = data.get('cases', [])
    save_cases(cases)
    return jsonify({'success': True})


# ============ ADMIN SCRATCH API ============

@app.route('/api/admin/scratches', methods=['GET'])
def api_admin_scratches():
    admin_id = request.args.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(load_scratches())


@app.route('/api/admin/scratches/update', methods=['POST'])
def api_admin_update_scratch():
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    scratch = data.get('scratch')
    if not scratch or not scratch.get('name') or not scratch.get('price'):
        return jsonify({'error': 'Invalid scratch data'}), 400

    scratches = load_scratches()
    sid = scratch.get('id')
    if sid:
        idx = next((i for i, s in enumerate(scratches) if s['id'] == sid), None)
        if idx is not None:
            scratches[idx] = scratch
        else:
            scratches.append(scratch)
    else:
        scratch['id'] = max((s['id'] for s in scratches), default=0) + 1
        scratches.append(scratch)

    save_scratches(scratches)
    return jsonify({'success': True, 'id': scratch['id']})


@app.route('/api/admin/scratches/delete', methods=['POST'])
def api_admin_delete_scratch():
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    scratch_id = data.get('scratch_id')
    scratches = load_scratches()
    scratches = [s for s in scratches if s['id'] != scratch_id]
    save_scratches(scratches)
    return jsonify({'success': True})


@app.route('/api/admin/gifts', methods=['POST'])
def api_admin_save_gifts():
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    gifts = data.get('gifts', [])
    save_gifts(gifts)
    return jsonify({'success': True})


@app.route('/api/admin/balance', methods=['POST'])
def api_admin_set_balance():
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    target_id = data.get('target_id')
    amount = data.get('amount', 0)

    db = get_db()
    db.execute('UPDATE users SET balance = ? WHERE telegram_id = ?', (amount, target_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/admin/clear-inventory', methods=['POST'])
def api_admin_clear_inventory():
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    target_id = data.get('target_id')
    if not target_id:
        return jsonify({'error': 'Missing target_id'}), 400
    db = get_db()
    deleted = db.execute('DELETE FROM inventory WHERE user_id = ?', (target_id,)).rowcount
    db.commit()
    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/admin/stats')
def api_admin_stats():
    """Dashboard statistics for admin panel"""
    admin_id = request.args.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    total_users = db.execute('SELECT COUNT(*) as cnt FROM users').fetchone()['cnt']
    total_balance = db.execute('SELECT COALESCE(SUM(balance),0) as s FROM users').fetchone()['s']
    total_deposited = db.execute('SELECT COALESCE(SUM(deposited_balance),0) as s FROM users').fetchone()['s']
    total_inventory = db.execute('SELECT COUNT(*) as cnt FROM inventory').fetchone()['cnt']
    total_tasks = db.execute('SELECT COUNT(*) as cnt FROM tasks WHERE is_active=1').fetchone()['cnt']
    total_referrals = db.execute('SELECT COUNT(*) as cnt FROM referrals').fetchone()['cnt']

    # Enhanced stats
    total_withdrawals = 0
    completed_withdrawals = 0
    pending_withdrawals = 0
    try:
        total_withdrawals = db.execute('SELECT COUNT(*) as cnt FROM withdrawals').fetchone()['cnt']
        completed_withdrawals = db.execute("SELECT COUNT(*) as cnt FROM withdrawals WHERE status='completed'").fetchone()['cnt']
        pending_withdrawals = db.execute("SELECT COUNT(*) as cnt FROM withdrawals WHERE status IN ('pending','queued','manual')").fetchone()['cnt']
    except Exception:
        pass

    # Users registered today / this week
    users_today = 0
    users_week = 0
    try:
        users_today = db.execute("SELECT COUNT(*) as cnt FROM users WHERE date(created_at)=date('now')").fetchone()['cnt']
        users_week = db.execute("SELECT COUNT(*) as cnt FROM users WHERE created_at >= datetime('now','-7 days')").fetchone()['cnt']
    except Exception:
        pass

    # Task completion stats
    task_stats = []
    try:
        tasks = db.execute('SELECT id, title, is_active FROM tasks ORDER BY id').fetchall()
        for t in tasks:
            completed_count = db.execute('SELECT COUNT(*) as cnt FROM user_tasks WHERE task_id=? AND completed=1', (t['id'],)).fetchone()['cnt']
            task_stats.append({
                'id': t['id'],
                'title': t['title'],
                'is_active': bool(t['is_active']),
                'completed_count': completed_count
            })
    except Exception:
        pass

    # Top users by balance
    top_users = []
    try:
        rows = db.execute('SELECT telegram_id, username, first_name, balance FROM users ORDER BY balance DESC LIMIT 10').fetchall()
        for r in rows:
            top_users.append({
                'telegram_id': r['telegram_id'],
                'name': r['first_name'] or r['username'] or str(r['telegram_id']),
                'balance': round(r['balance'], 1)
            })
    except Exception:
        pass

    return jsonify({
        'total_users': total_users,
        'total_balance': round(total_balance, 1),
        'total_deposited': round(total_deposited, 1),
        'total_inventory': total_inventory,
        'active_tasks': total_tasks,
        'total_referrals': total_referrals,
        'total_withdrawals': total_withdrawals,
        'completed_withdrawals': completed_withdrawals,
        'pending_withdrawals': pending_withdrawals,
        'users_today': users_today,
        'users_week': users_week,
        'task_stats': task_stats,
        'top_users': top_users
    })


@app.route('/api/admin/users')
def api_admin_users():
    """List all users for admin panel"""
    admin_id = request.args.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    users = db.execute('SELECT telegram_id, username, first_name, last_name, balance, deposited_balance, referral_code, referred_by, created_at, photo_url FROM users ORDER BY created_at DESC').fetchall()
    result = []
    for u in users:
        inv_count = db.execute('SELECT COUNT(*) as cnt FROM inventory WHERE user_id=?', (u['telegram_id'],)).fetchone()['cnt']
        ref_count = db.execute('SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id=?', (u['telegram_id'],)).fetchone()['cnt']
        result.append({
            'telegram_id': u['telegram_id'],
            'username': u['username'],
            'first_name': u['first_name'],
            'last_name': u['last_name'],
            'balance': u['balance'],
            'deposited_balance': u['deposited_balance'] or 0,
            'referral_code': u['referral_code'],
            'referred_by': u['referred_by'],
            'created_at': u['created_at'],
            'photo_url': u['photo_url'] if 'photo_url' in u.keys() else '',
            'inventory_count': inv_count,
            'referral_count': ref_count,
        })
    return jsonify(result)


@app.route('/api/admin/cases/update', methods=['POST'])
def api_admin_update_case():
    """Update a single case by id"""
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    cases = load_cases()
    updated = data.get('case')
    if not updated:
        return jsonify({'error': 'No case data'}), 400
    idx = next((i for i, c in enumerate(cases) if c['id'] == updated['id']), None)
    if idx is not None:
        cases[idx] = updated
    else:
        cases.append(updated)
    save_cases(cases)
    return jsonify({'success': True})


@app.route('/api/admin/cases/delete', methods=['POST'])
def api_admin_delete_case():
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    case_id = data.get('case_id')
    cases = load_cases()
    cases = [c for c in cases if c['id'] != case_id]
    save_cases(cases)
    return jsonify({'success': True})


@app.route('/api/admin/gifts/update', methods=['POST'])
def api_admin_update_gift():
    """Update a single gift by id"""
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    gift = data.get('gift')
    if not gift:
        return jsonify({'error': 'No gift data'}), 400
    gifts = load_gifts()
    idx = next((i for i, g in enumerate(gifts) if g['id'] == gift['id']), None)
    if idx is not None:
        gifts[idx] = gift
    else:
        gifts.append(gift)
    save_gifts(gifts)
    return jsonify({'success': True})


@app.route('/api/admin/gifts/delete', methods=['POST'])
def api_admin_delete_gift():
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    gift_id = data.get('gift_id')
    gifts = load_gifts()
    gifts = [g for g in gifts if g['id'] != gift_id]
    save_gifts(gifts)
    return jsonify({'success': True})


# ============ PROMO CODES API ============

@app.route('/api/admin/promos')
def api_admin_list_promos():
    admin_id = request.args.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    promos = db.execute('SELECT * FROM promo_codes ORDER BY created_at DESC').fetchall()
    return jsonify([dict(p) for p in promos])


@app.route('/api/admin/promos', methods=['POST'])
def api_admin_create_promo():
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    code = data.get('code', '').strip().upper()
    promo_type = data.get('type', '')
    value = float(data.get('value', 0))
    case_id = int(data.get('case_id', 0))
    gift_id = int(data.get('gift_id', 0))
    scratch_id = int(data.get('scratch_id', 0))
    max_uses = int(data.get('max_uses', 1))

    if not code or not promo_type:
        return jsonify({'error': 'Code and type required'}), 400

    valid_types = ['stars', 'topup_percent', 'case_discount', 'gift_discount', 'case_to_inventory', 'gift_to_inventory', 'scratch_discount']
    if promo_type not in valid_types:
        return jsonify({'error': f'Invalid type. Valid: {valid_types}'}), 400

    db = get_db()
    try:
        db.execute(
            'INSERT INTO promo_codes (code, type, value, case_id, gift_id, scratch_id, max_uses) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (code, promo_type, value, case_id, gift_id, scratch_id, max_uses)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as _e:
        if 'unique' in str(_e).lower() or 'duplicate' in str(_e).lower() or 'IntegrityError' in type(_e).__name__:
            return jsonify({'error': 'Promo code already exists'}), 400
        raise


@app.route('/api/admin/promos/<int:promo_id>', methods=['DELETE'])
def api_admin_delete_promo(promo_id):
    data = request.json
    admin_id = data.get('admin_id')
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    db = get_db()
    db.execute('DELETE FROM promo_codes WHERE id = ?', (promo_id,))
    db.execute('DELETE FROM promo_uses WHERE promo_id = ?', (promo_id,))
    db.commit()
    return jsonify({'success': True})


# ============ ADMIN WITHDRAWALS ============

@app.route('/api/admin/withdrawals')
def api_admin_withdrawals():
    admin_id = request.args.get('admin_id', type=int)
    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    db = get_db()
    rows = db.execute('''
        SELECT w.*, u.username, u.first_name
        FROM withdrawals w
        LEFT JOIN users u ON w.user_id = u.telegram_id
        ORDER BY w.created_at DESC LIMIT 100
    ''').fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['gifts'] = json.loads(d.get('gifts_json', '[]'))
        result.append(d)
    return jsonify(result)


@app.route('/api/admin/withdrawals/<int:wid>/process', methods=['POST'])
def api_admin_process_withdrawal(wid):
    data = request.json
    admin_id = data.get('admin_id')
    action = data.get('action')  # 'complete' or 'reject'

    if not admin_id or not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    db = get_db()
    w = db.execute('SELECT * FROM withdrawals WHERE id = ?', (wid,)).fetchone()
    if not w:
        return jsonify({'error': 'Not found'}), 404

    if action == 'complete':
        db.execute('UPDATE withdrawals SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?',
                   ('completed', wid))
        db.commit()
        return jsonify({'success': True, 'status': 'completed'})
    elif action == 'reject':
        # Refund balance
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?',
                   (w['amount'], w['user_id']))
        db.execute('UPDATE withdrawals SET status = ?, error_msg = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?',
                   ('rejected', 'Отклонено администратором', wid))
        db.commit()
        return jsonify({'success': True, 'status': 'rejected'})
    else:
        return jsonify({'error': 'Invalid action'}), 400


@app.route('/api/promo/redeem', methods=['POST'])
def api_promo_redeem():
    """Redeem a promo code"""
    data = request.json
    telegram_id = data.get('telegram_id')
    code = (data.get('code') or '').strip().upper()

    if not telegram_id or not code:
        return jsonify({'error': 'Введите промокод'}), 400

    db = get_db()
    promo = db.execute('SELECT * FROM promo_codes WHERE code = ? AND is_active = 1', (code,)).fetchone()
    if not promo:
        return jsonify({'error': 'Промокод не найден или неактивен'}), 404

    if promo['max_uses'] > 0 and promo['used_count'] >= promo['max_uses']:
        return jsonify({'error': 'Промокод больше не действителен'}), 400

    # Check if user already used this promo
    used = db.execute('SELECT id FROM promo_uses WHERE user_id = ? AND promo_id = ?',
                      (telegram_id, promo['id'])).fetchone()
    if used:
        return jsonify({'error': 'Вы уже использовали этот промокод'}), 400

    promo_type = promo['type']
    value = promo['value']
    result = {'type': promo_type, 'value': value}

    if promo_type == 'stars':
        # Direct stars bonus
        db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (value, telegram_id))
        result['message'] = f'+{int(value)} ⭐ зачислено!'

    elif promo_type == 'topup_percent':
        # Store as pending bonus - will be applied on next topup
        # We store it as a user attribute temporarily
        result['message'] = f'Бонус +{int(value)}% к следующему пополнению активирован!'
        result['topup_bonus_percent'] = value

    elif promo_type == 'case_discount':
        try:
            case_id_promo = promo['case_id']
        except (KeyError, IndexError):
            case_id_promo = 0
        result['message'] = f'Скидка {int(value)}% на кейс активирована!'
        result['case_discount_percent'] = value
        result['case_id'] = case_id_promo

    elif promo_type == 'gift_discount':
        result['message'] = f'Скидка {int(value)}% на подарки в маркете активирована!'
        result['gift_discount_percent'] = value

    elif promo_type == 'case_to_inventory':
        # Give a case directly to inventory
        case_id = promo['case_id']
        cases = load_cases()
        cs = next((c for c in cases if c['id'] == case_id), None)
        if not cs:
            return jsonify({'error': 'Кейс промокода не найден'}), 400
        db.execute(
            'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price, item_type, case_id) VALUES (?, 0, ?, ?, 0, ?, ?)',
            (telegram_id, cs['name'], cs.get('image', ''), 'case', case_id)
        )
        result['message'] = f'Кейс "{cs["name"]}" добавлен в инвентарь!'
        result['case'] = cs

    elif promo_type == 'gift_to_inventory':
        # Give a gift directly to inventory
        try:
            gift_id_promo = promo['gift_id']
        except (KeyError, IndexError):
            gift_id_promo = 0
        gifts = load_gifts()
        gift = next((g for g in gifts if g['id'] == gift_id_promo), None)
        if not gift:
            return jsonify({'error': 'Подарок промокода не найден'}), 400
        price_val = gift.get('price', 0)
        db.execute(
            'INSERT INTO inventory (user_id, gift_id, gift_name, gift_image, gift_price) VALUES (?, ?, ?, ?, ?)',
            (telegram_id, gift['id'], gift['name'], gift.get('image', ''), price_val)
        )
        result['message'] = f'Подарок "{gift["name"]}" добавлен в инвентарь!'
        result['gift'] = {'name': gift['name'], 'image': gift.get('image', ''), 'price': price_val}

    elif promo_type == 'scratch_discount':
        # Discount on specific scratch
        try:
            scratch_id_promo = promo['scratch_id']
        except (KeyError, IndexError):
            scratch_id_promo = 0
        result['message'] = f'Скидка {int(value)}% на скретч активирована!'
        result['scratch_discount_percent'] = value
        result['scratch_id'] = scratch_id_promo

    # Mark promo as used
    db.execute('INSERT INTO promo_uses (user_id, promo_id) VALUES (?, ?)', (telegram_id, promo['id']))
    db.execute('UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?', (promo['id'],))
    db.commit()

    user = db.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    result['new_balance'] = user['balance']
    result['success'] = True
    return jsonify(result)


# ============ BOT WEBHOOK (sync — no aiogram) ============

def tg_api(method, params=None):
    """Call Telegram Bot API synchronously"""
    try:
        resp = http_requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/{method}',
            json=params or {},
            timeout=10
        )
        return resp.json()
    except Exception as e:
        logging.error(f"TG API error ({method}): {e}")
        return {}


def tg_send(chat_id, text, reply_markup=None, parse_mode='HTML'):
    """Send a message via Telegram Bot API"""
    params = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    if reply_markup:
        params['reply_markup'] = reply_markup
    return tg_api('sendMessage', params)


@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram webhook updates — pure sync, no aiogram"""
    data = request.json
    if not data:
        return jsonify({'ok': True})

    try:
        # Pre-checkout query (Stars payment)
        if 'pre_checkout_query' in data:
            pcq = data['pre_checkout_query']
            tg_api('answerPreCheckoutQuery', {
                'pre_checkout_query_id': pcq['id'],
                'ok': True
            })
            return jsonify({'ok': True})

        # Message updates
        msg = data.get('message')
        if not msg:
            return jsonify({'ok': True})

        chat_id = msg['chat']['id']
        user = msg.get('from', {})
        user_id = user.get('id', 0)
        text = msg.get('text', '')

        # Successful payment
        if 'successful_payment' in msg:
            payment = msg['successful_payment']
            charge_id = payment.get('telegram_payment_charge_id', '')
            try:
                payload = json.loads(payment.get('invoice_payload', '{}'))
                tid = payload.get('telegram_id', user_id)
                amount = payload.get('amount', payment.get('total_amount', 0))
            except (json.JSONDecodeError, AttributeError):
                tid = user_id
                amount = payment.get('total_amount', 0)

            db = get_db()
            db.execute('UPDATE users SET balance = balance + ?, deposited_balance = deposited_balance + ? WHERE telegram_id = ?',
                       (amount, amount, tid))
            # Save transaction for refund
            if charge_id:
                db.execute('INSERT OR IGNORE INTO star_transactions (telegram_id, charge_id, amount) VALUES (?, ?, ?)',
                           (tid, charge_id, amount))
            # 5% referral commission
            ref_user = db.execute('SELECT referred_by FROM users WHERE telegram_id = ?', (tid,)).fetchone()
            if ref_user and ref_user['referred_by'] and ref_user['referred_by'] > 0:
                commission = amount * 0.05
                db.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?',
                           (commission, ref_user['referred_by']))
            db.commit()
            tg_send(chat_id, f"✅ Оплата прошла! +{amount} ⭐ зачислено на баланс.")
            return jsonify({'ok': True})

        # /start command
        if text.startswith('/start'):
            args = text.strip().split(maxsplit=1)
            ref_code = ''
            if len(args) > 1 and args[1].startswith('ref_'):
                ref_code = args[1][4:].upper()

            # Process referral
            if ref_code:
                db = get_db()
                referrer = db.execute('SELECT telegram_id FROM users WHERE referral_code = ?', (ref_code,)).fetchone()
                if referrer and referrer['telegram_id'] != user_id:
                    existing = db.execute('SELECT id FROM referrals WHERE referred_id = ?', (user_id,)).fetchone()
                    if not existing:
                        own_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                        db.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name, photo_url, referral_code, referred_by)
                                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                   (user_id, user.get('username', ''), user.get('first_name', ''),
                                    user.get('last_name', ''), '', own_code, referrer['telegram_id']))
                        db.execute('UPDATE users SET referred_by = ? WHERE telegram_id = ? AND referred_by = 0',
                                   (referrer['telegram_id'], user_id))
                        db.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
                                   (referrer['telegram_id'], user_id))
                        db.execute('UPDATE users SET balance = balance + 2 WHERE telegram_id = ?',
                                   (referrer['telegram_id'],))
                        db.commit()
                        tg_send(referrer['telegram_id'],
                                f"🎉 Новый реферал! <b>{user.get('first_name', '')}</b> присоединился по вашей ссылке.\n+2 ⭐ зачислено на баланс!")

            keyboard = {
                'inline_keyboard': [
                    [{'text': 'Открыть Luna Gifts', 'web_app': {'url': WEBAPP_URL}}],
                    [{'text': 'Кейсы', 'web_app': {'url': f'{WEBAPP_URL}/cases'}},
                     {'text': 'Маркет', 'web_app': {'url': f'{WEBAPP_URL}/market'}}],
                    [{'text': 'Инвентарь', 'web_app': {'url': f'{WEBAPP_URL}/inventory'}}]
                ]
            }
            tg_send(chat_id,
                     f"Привет, <b>{user.get('first_name', '')}</b>!\n\n"
                     "Добро пожаловать в <b>Luna Gifts</b>!\n\n"
                     "Выполняй задания и получай звёзды\n"
                     "Покупай NFT подарки в маркете\n"
                     "Открывай кейсы и испытай удачу\n\n"
                     "Нажми кнопку ниже, чтобы начать",
                     reply_markup=keyboard)

        elif text == '/help':
            tg_send(chat_id,
                     "<b>Luna Gifts — Помощь</b>\n\n"
                     "/start — Открыть приложение\n"
                     "/auth КЛЮЧ — Авторизация через браузер\n"
                     "/ref — Реферальная ссылка\n"
                     "/balance — Посмотреть баланс\n"
                     "/help — Помощь\n\n"
                     "<b>Как заработать звёзды?</b>\n"
                     "• Выполняйте задания на главной странице\n"
                     "• Приглашайте друзей (+2 ⭐ за каждого)\n"
                     "• Получайте 5% с пополнений друзей\n"
                     "• Открывайте кейсы\n\n"
                     "<b>Что делать со звёздами?</b>\n"
                     "• Покупайте NFT подарки в маркете\n"
                     "• Открывайте кейсы для шанса выиграть больше")

        elif text == '/balance':
            keyboard = {
                'inline_keyboard': [
                    [{'text': 'Посмотреть баланс', 'web_app': {'url': WEBAPP_URL}}]
                ]
            }
            tg_send(chat_id, "Откройте приложение чтобы увидеть ваш баланс:", reply_markup=keyboard)

        elif text.startswith('/auth'):
            parts = text.strip().split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                tg_send(chat_id,
                         "Введите ключ авторизации:\n"
                         "<code>/auth ВАШ_КЛЮЧ</code>\n\n"
                         "Ключ можно получить на сайте Luna Gifts при входе через браузер.")
            else:
                key = parts[1].strip().upper()
                if key not in auth_keys:
                    tg_send(chat_id, "Ключ не найден или истёк. Сгенерируйте новый на сайте.")
                elif auth_keys[key] is not None:
                    tg_send(chat_id, "Этот ключ уже был использован.")
                else:
                    photo_url = ''
                    try:
                        photos_resp = tg_api('getUserProfilePhotos', {'user_id': user_id, 'limit': 1})
                        if photos_resp.get('ok') and photos_resp['result']['total_count'] > 0:
                            file_id = photos_resp['result']['photos'][0][-1]['file_id']
                            file_resp = tg_api('getFile', {'file_id': file_id})
                            if file_resp.get('ok'):
                                photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_resp['result']['file_path']}"
                    except Exception:
                        pass

                    auth_keys[key] = {
                        'telegram_id': user_id,
                        'username': user.get('username', ''),
                        'first_name': user.get('first_name', ''),
                        'last_name': user.get('last_name', ''),
                        'photo_url': photo_url
                    }

                    db = get_db()
                    db.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name, photo_url)
                                  VALUES (?, ?, ?, ?, ?)''',
                               (user_id, user.get('username', ''), user.get('first_name', ''), user.get('last_name', ''), photo_url))
                    db.execute('''UPDATE users SET username=?, first_name=?, last_name=?, photo_url=? WHERE telegram_id=?''',
                               (user.get('username', ''), user.get('first_name', ''), user.get('last_name', ''), photo_url, user_id))
                    db.commit()
                    tg_send(chat_id, "✅ Авторизация успешна!\nВернитесь на сайт — вход произойдёт автоматически.")

        elif text == '/admin':
            if user_id not in ADMIN_IDS:
                tg_send(chat_id, "У вас нет доступа к админ панели.")
            else:
                keyboard = {
                    'inline_keyboard': [
                        [{'text': 'Админ панель', 'web_app': {'url': f'{WEBAPP_URL}/admin'}}]
                    ]
                }
                tg_send(chat_id, "<b>Админ панель</b>\n\nНажмите кнопку для управления:", reply_markup=keyboard)

        elif text.startswith('/refund'):
            # /refund <user_id> <charge_id> — admin only, refund Stars via TG API directly
            if user_id not in ADMIN_IDS:
                tg_send(chat_id, "❌ У вас нет доступа к этой команде.")
            else:
                parts = text.strip().split()
                if len(parts) < 3:
                    tg_send(chat_id,
                             "<b>Возврат звёзд</b>\n\n"
                             "Использование:\n<code>/refund USER_ID CHARGE_ID</code>\n\n"
                             "• <b>USER_ID</b> — Telegram ID пользователя\n"
                             "• <b>CHARGE_ID</b> — <code>telegram_payment_charge_id</code> из платежа")
                else:
                    target_uid = parts[1].strip()
                    cid = parts[2].strip()
                    # Validate user_id is numeric
                    if not target_uid.isdigit():
                        tg_send(chat_id, "❌ USER_ID должен быть числом.")
                    else:
                        target_uid = int(target_uid)
                        result = tg_api('refundStarPayment', {
                            'user_id': target_uid,
                            'telegram_payment_charge_id': cid
                        })
                        if result.get('ok'):
                            tg_send(chat_id,
                                     f"✅ Возврат выполнен!\n\n"
                                     f"Пользователь: <code>{target_uid}</code>\n"
                                     f"Charge ID: <code>{cid}</code>")
                            # Notify user
                            try:
                                tg_send(target_uid,
                                         "💫 Возврат средств\n\n"
                                         "Вам возвращены Telegram Stars.\n"
                                         "Баланс Luna Gifts скорректирован.")
                            except Exception:
                                pass
                        else:
                            err = result.get('description', 'Неизвестная ошибка')
                            tg_send(chat_id, f"❌ Ошибка возврата:\n<code>{err}</code>")

        elif text.startswith('/ref'):
            db = get_db()
            u = db.execute('SELECT referral_code FROM users WHERE telegram_id = ?', (user_id,)).fetchone()
            if not u or not u['referral_code']:
                ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                db.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name, referral_code)
                              VALUES (?, ?, ?, ?)''',
                           (user_id, user.get('username', ''), user.get('first_name', ''), ref_code))
                if u:
                    db.execute('UPDATE users SET referral_code=? WHERE telegram_id=?', (ref_code, user_id))
                db.commit()
            else:
                ref_code = u['referral_code']

            referrals = db.execute('SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?', (user_id,)).fetchone()
            count = referrals['cnt'] if referrals else 0

            me_resp = tg_api('getMe')
            bot_username = me_resp.get('result', {}).get('username', 'lunagifts_robot')
            ref_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"

            tg_send(chat_id,
                     f"<b>Реферальная программа</b>\n\n"
                     f"Ваша ссылка:\n<code>{ref_link}</code>\n\n"
                     f"<b>Ваши рефералы:</b> {count}\n"
                     f"<b>Бонус:</b> +2 ⭐ за каждого друга\n"
                     f"<b>Комиссия:</b> 5% от пополнений друзей\n\n"
                     f"Делитесь ссылкой и получайте награды!")

    except Exception as e:
        logging.error(f"Webhook error: {e}")

    return jsonify({'ok': True})


@app.route('/api/bot/setup-webhook', methods=['POST'])
def api_setup_webhook():
    """Set Telegram webhook to point to our server"""
    data = request.json or {}
    admin_id = data.get('admin_id')
    if admin_id and not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized'}), 403

    webhook_url = f"{WEBAPP_URL}/webhook"
    try:
        resp = http_requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook',
            json={
                'url': webhook_url,
                'allowed_updates': [
                    'message', 'callback_query', 'pre_checkout_query',
                    'successful_payment', 'business_connection',
                ],
            }
        )
        result = resp.json()
        logging.info(f"Webhook setup: {result}")
        return jsonify(result)
    except Exception as e:
        logging.error(f"Webhook setup error: {e}")
        return jsonify({'error': str(e)}), 500


# ============ PAGE ROUTES ============

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/tonconnect-manifest.json')
def tonconnect_manifest():
    response = app.send_static_file('tonconnect-manifest.json')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@app.route('/market')
def market():
    return render_template('market.html')


@app.route('/cases')
def cases():
    return render_template('cases.html')


@app.route('/games')
def games():
    return render_template('games.html')


@app.route('/crash')
def crash():
    return redirect('/games')


@app.route('/pvp')
def pvp():
    return render_template('pvp.html')


@app.route('/scratch')
def scratch():
    return render_template('scratch.html')


@app.route('/topup')
def topup():
    return render_template('topup.html')


@app.route('/inventory')
def inventory():
    return render_template('inventory.html')


@app.route('/referral')
def referral_page():
    return render_template('referral.html')


@app.route('/admin')
def admin():
    return render_template('admin.html')


# ============ DATA MIGRATION (one-time) ============

@app.route('/api/admin/migrate-seed', methods=['POST'])
def migrate_seed():
    """Run seed_data.json to populate DB from SQLite dump. One-time use."""
    import os as _os
    seed_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'seed_data.json')
    if not _os.path.exists(seed_path):
        return jsonify({'error': 'seed_data.json not found'}), 404
    
    import json as _json
    with open(seed_path, 'r', encoding='utf-8') as f:
        seed = _json.load(f)
    
    # Conflict columns for ON CONFLICT DO NOTHING
    conflict_map = {
        "users": "telegram_id",
        "completed_tasks": "user_id, task_id",
        "referrals": "referred_id",
        "promo_codes": "code",
        "promo_uses": "user_id, promo_id",
    }
    
    db = connect_db()
    results = {}
    for table, info in seed.items():
        cols = info.get("cols", [])
        rows = info.get("rows", [])
        if not rows or not cols:
            results[table] = {"ok": 0, "total": 0}
            continue
        
        col_str = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        conflict = conflict_map.get(table)
        if conflict:
            sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) ON CONFLICT ({conflict}) DO NOTHING"
        else:
            sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
        
        ok = 0
        errors = []
        for row in rows:
            try:
                db.execute(sql, row)
                db.commit()
                ok += 1
            except Exception as e:
                try:
                    db.rollback()
                except:
                    pass
                errors.append(str(e)[:120])
        
        # Reset sequence
        try:
            db.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))")
            db.commit()
        except:
            try:
                db.rollback()
            except:
                pass
        
        results[table] = {"ok": ok, "total": len(rows), "errors": errors[:3] if errors else []}
    
    db.close()
    return jsonify(results)


# ============ BACKGROUND THREADS INIT (for gunicorn) ============
# Start background game loops at module level so they run when gunicorn workers start

_threads_started = False
_threads_lock = threading.Lock()

def start_background_threads():
    global _threads_started
    with _threads_lock:
        if _threads_started:
            return
        _threads_started = True
    
    logging.info("Starting background threads...")
    
    # Start PVP game loop
    pvp_thread = threading.Thread(target=start_pvp_loop, daemon=True)
    pvp_thread.start()
    logging.info("PVP game loop thread started")
    
    # Start crash game loop
    crash_thread = threading.Thread(target=start_crash_loop, daemon=True)
    crash_thread.start()
    logging.info("Crash game loop thread started (gunicorn)")

# Auto-start threads when module is imported
start_background_threads()


# ============ INIT & RUN ============

if __name__ == '__main__':
    # Background threads already started at module level via start_background_threads()
    
    # Запуск бота в отдельном потоке
    if HAS_AIOGRAM:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logging.info("Bot thread started")

    # Запуск Flask
    app.run(debug=False, host='0.0.0.0', port=5000)

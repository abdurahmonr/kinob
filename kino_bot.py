#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 MUKAMMAL KINO BOT — TO'LIQ VERSIYA
Kod tizimi + Sevimlilar + Seriyalar + Referal + Avto-e'lon
"""

import logging
import sqlite3
import requests
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ============================================================
# ⚙️ SOZLAMALAR
# ============================================================
BOT_TOKEN         = "8871541413:AAEVT_GV5VZbPJ2Hw5ZTapEBl2LRaWyp43Q"
ADMIN_USERNAME    = "raximovabdurahmon"
CHANNEL_USERNAME  = "@kinovaauz"          # majburiy obuna kanali
POST_CHANNEL      = "@kinovaauz"          # yangi kino e'lon qilinadigan kanal (None = o'chirilgan)
OMDB_API_KEY      = "YOUR_OMDB_API_KEY"   # bepul: omdbapi.com/apikey.aspx
BOT_USERNAME      = "kinovaabot"          # referal link uchun, @ siz
REFERAL_BONUS     = 3                      # har referal uchun beriladigan ball
# ============================================================

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

EMOJI_GENRE = {
    "action": "💥", "jangari": "💥",
    "comedy": "😂", "komediya": "😂",
    "drama": "🎭",
    "horror": "👻", "qo'rqinch": "👻",
    "romance": "❤️", "sevgi": "❤️",
    "sci-fi": "🚀", "ilmiy": "🚀",
    "animation": "🎨", "multfilm": "🎨",
    "thriller": "😱", "triller": "😱",
    "crime": "🔍", "jinoyat": "🔍",
    "fantasy": "🧙", "fantastika": "🧙",
    "adventure": "🗺️", "sarguzasht": "🗺️",
    "family": "👨‍👩‍👧", "oilaviy": "👨‍👩‍👧",
    "biography": "📖", "tarixiy": "📖",
}

# ============================================================
# 🗄️ DATABASE
# ============================================================
def init_db():
    conn = sqlite3.connect('kino_bot.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS movies (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        code         TEXT UNIQUE,
        title        TEXT NOT NULL,
        description  TEXT,
        genre        TEXT,
        year         INTEGER,
        imdb_rating  TEXT,
        poster_url   TEXT,
        file_id      TEXT NOT NULL,
        file_type    TEXT DEFAULT 'video',
        series_group TEXT,
        episode_num  INTEGER DEFAULT 0,
        added_by     INTEGER,
        added_date   TEXT,
        views        INTEGER DEFAULT 0,
        avg_rating   REAL DEFAULT 0.0,
        rating_count INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY,
        username      TEXT,
        full_name     TEXT,
        joined_date   TEXT,
        last_active   TEXT,
        total_watched INTEGER DEFAULT 0,
        points        INTEGER DEFAULT 0,
        referred_by   INTEGER,
        ref_count     INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id  INTEGER,
        movie_id INTEGER,
        rating   INTEGER,
        UNIQUE(user_id, movie_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS watch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER,
        movie_id     INTEGER,
        watched_date TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id  INTEGER,
        movie_id INTEGER,
        added_date TEXT,
        UNIQUE(user_id, movie_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id    INTEGER PRIMARY KEY,
        username   TEXT,
        added_date TEXT
    )''')

    conn.commit()
    conn.close()

def db():
    return sqlite3.connect('kino_bot.db')

# ============================================================
# 🔧 YORDAMCHI FUNKSIYALAR
# ============================================================
def is_admin(user_id, username=None):
    conn = db(); c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
    r = c.fetchone(); conn.close()
    if r:
        return True
    if username and username.lower() == ADMIN_USERNAME.lower():
        add_admin(user_id, username)
        return True
    return False

def add_admin(user_id, username):
    conn = db(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins VALUES (?,?,?)",
              (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit(); conn.close()

def register_user(user, referred_by=None):
    conn = db(); c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    exists = c.fetchone()
    if not exists:
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,0,0,?,0)",
                  (user.id, user.username or '', user.full_name, now, now, referred_by))
        if referred_by and referred_by != user.id:
            c.execute("UPDATE users SET points = points + ?, ref_count = ref_count + 1 WHERE user_id=?",
                      (REFERAL_BONUS, referred_by))
    c.execute("UPDATE users SET last_active=?, username=?, full_name=? WHERE user_id=?",
              (now, user.username or '', user.full_name, user.id))
    conn.commit(); conn.close()
    return not exists

async def check_sub(user_id, context):
    if not CHANNEL_USERNAME:
        return True
    try:
        m = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return m.status not in ['left', 'kicked']
    except Exception:
        return True

def genre_emoji(g):
    if not g:
        return "🎬"
    g_low = g.lower()
    for key, emoji in EMOJI_GENRE.items():
        if key in g_low:
            return emoji
    return "🎬"

def get_omdb(title):
    if OMDB_API_KEY == "YOUR_OMDB_API_KEY":
        return None
    try:
        r = requests.get(f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}", timeout=5)
        d = r.json()
        return d if d.get("Response") == "True" else None
    except Exception:
        return None

def update_rating(movie_id):
    conn = db(); c = conn.cursor()
    c.execute("SELECT AVG(rating), COUNT(*) FROM ratings WHERE movie_id=?", (movie_id,))
    avg, cnt = c.fetchone()
    c.execute("UPDATE movies SET avg_rating=?, rating_count=? WHERE id=?",
              (round(avg or 0, 1), cnt or 0, movie_id))
    conn.commit(); conn.close()

def gen_random_code(length=5):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        conn = db(); c = conn.cursor()
        c.execute("SELECT id FROM movies WHERE code=?", (code,))
        if not c.fetchone():
            conn.close()
            return code
        conn.close()

def progress_bar(value, max_value=10, length=10):
    filled = int((value / max_value) * length) if max_value else 0
    filled = max(0, min(length, filled))
    return "🟩" * filled + "⬜" * (length - filled)

# ============================================================
# 📋 ASOSIY MENYU
# ============================================================
def main_menu_kb(is_adm):
    kb = [
        [InlineKeyboardButton("🔍 Qidirish", callback_data="search"),
         InlineKeyboardButton("🎲 Tasodifiy", callback_data="random")],
        [InlineKeyboardButton("🎭 Janrlar", callback_data="genres"),
         InlineKeyboardButton("⭐ Top kinolar", callback_data="top")],
        [InlineKeyboardButton("📈 Yangi kinolar", callback_data="new"),
         InlineKeyboardButton("💡 Tavsiyalar", callback_data="recommend")],
        [InlineKeyboardButton("❤️ Sevimlilarim", callback_data="favorites"),
         InlineKeyboardButton("📜 Tariximi", callback_data="history")],
        [InlineKeyboardButton("👤 Profilim", callback_data="profile"),
         InlineKeyboardButton("ℹ️ Yordam", callback_data="help")],
    ]
    if is_adm:
        kb.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)

def welcome_text(user):
    return (
        f"🎬 <b>KINO BOT</b> ✨\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Assalomu alaykum, <b>{user.first_name}</b>! 👋\n\n"
        f"🔑 Kino kodini yuboring — kino keladi!\n"
        f"📝 Yoki nomi bilan qidiring\n\n"
        f"Quyidagi menyudan foydalaning 👇"
    )

async def send_main_menu(chat_id, user, context, edit_msg=None):
    adm = is_admin(user.id, user.username)
    text = welcome_text(user)
    kb = main_menu_kb(adm)
    if edit_msg:
        try:
            await edit_msg.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass
    await context.bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ============================================================
# 🚀 START (referal qo'llab-quvvatlash bilan)
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None

    if context.args:
        arg = context.args[0]
        if arg.startswith("ref"):
            try:
                ref_id = int(arg.replace("ref", ""))
                if ref_id != user.id:
                    referred_by = ref_id
            except ValueError:
                pass

    is_new = register_user(user, referred_by)

    if user.username and user.username.lower() == ADMIN_USERNAME.lower():
        add_admin(user.id, user.username)

    if is_new and referred_by:
        try:
            await context.bot.send_message(
                referred_by,
                f"🎉 <b>{user.first_name}</b> sizning taklifingiz orqali botga qo'shildi!\n"
                f"+{REFERAL_BONUS} ball qo'shildi! 🎁",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    if not await check_sub(user.id, context):
        kb = [
            [InlineKeyboardButton("📢 Kanalga obuna bo'lish",
                                  url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            f"👋 Salom <b>{user.first_name}</b>!\n\n"
            f"🔒 Botdan foydalanish uchun avval <b>{CHANNEL_USERNAME}</b> kanaliga obuna bo'ling!\n\n"
            f"Obuna bo'lgach tugmani bosing 👇",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML
        )
        return

    await send_main_menu(update.effective_chat.id, user, context)

# ============================================================
# 🎬 KINO KARTASI
# ============================================================
async def show_movie_card(message, movie, edit=False, user_rating=None, back="main_menu", is_fav=False):
    (mid, code, title, desc, genre, year, imdb, poster, fid, ftype,
     series_group, ep_num, _, _, views, avg, rcnt) = movie

    series_line = ""
    if series_group:
        conn = db(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM movies WHERE series_group=?", (series_group,))
        total_ep = c.fetchone()[0]
        conn.close()
        series_line = f"📺 <b>Qism:</b> {ep_num}/{total_ep}\n"

    genre_display = genre if genre else "Noma'lum"
    text = (
        f"🎬 <b>{title}</b>\n"
        f"🔑 Kod: <code>{code}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{series_line}"
        f"{genre_emoji(genre)} <b>Janr:</b> {genre_display}\n"
        f"📅 <b>Yil:</b> {year or '?'}\n"
        f"⭐ <b>IMDb:</b> {imdb or '-'}\n"
        f"{progress_bar(avg)} <b>{avg}/10</b> ({rcnt} ovoz)\n"
        f"👁 <b>Ko'rishlar:</b> {views}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📖 {(desc or 'Tarif kiritilmagan.')[:280]}"
    )

    rate_row = [InlineKeyboardButton(
        f"{'✅' if user_rating == i else i}",
        callback_data=f"rate_{mid}_{i}"
    ) for i in range(2, 12, 2)]

    rows = [[InlineKeyboardButton("▶️ Kinoni ko'rish", callback_data=f"watch_{mid}")]]

    if series_group:
        rows.append([InlineKeyboardButton("📺 Boshqa qismlar", callback_data=f"series_{series_group}")])

    fav_label = "💔 Sevimlilardan olib tashlash" if is_fav else "❤️ Sevimlilarga qo'shish"
    rows.append([InlineKeyboardButton(fav_label, callback_data=f"fav_{mid}")])
    rows.append(rate_row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=back)])

    kb = InlineKeyboardMarkup(rows)
    try:
        if edit:
            await message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ============================================================
# 📩 XABAR HANDLER — KOD QIDIRISH
# ============================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    text = update.message.text.strip()

    if context.user_data.get('wait_broadcast') and is_admin(user.id, user.username):
        context.user_data.pop('wait_broadcast')
        await do_broadcast(update, context, text)
        return

    state = context.user_data.get('admin_state')
    if state and is_admin(user.id, user.username):
        await handle_admin_input(update, context, state, text)
        return

    if not await check_sub(user.id, context):
        kb = [
            [InlineKeyboardButton("📢 Kanalga obuna bo'lish",
                                  url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            f"🔒 Avval <b>{CHANNEL_USERNAME}</b> kanaliga obuna bo'ling!",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML
        )
        return

    # Kod orqali qidirish
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM movies WHERE LOWER(code)=LOWER(?)", (text,))
    movie = c.fetchone()
    conn.close()

    if movie:
        await send_movie_by_code(update, context, movie)
        return

    if context.user_data.get('wait_search'):
        context.user_data.pop('wait_search')

    await search_movies(update, context, text)

async def send_movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE, movie):
    user = update.effective_user
    mid, code, title = movie[0], movie[1], movie[2]
    genre, year = movie[4], movie[5]
    file_id, file_type = movie[8], movie[9]
    views = movie[14]

    conn = db(); c = conn.cursor()
    c.execute("UPDATE movies SET views=? WHERE id=?", (views + 1, mid))
    c.execute("INSERT INTO watch_history VALUES (NULL,?,?,?)",
              (user.id, mid, datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute("UPDATE users SET total_watched=total_watched+1 WHERE user_id=?", (user.id,))
    conn.commit(); conn.close()

    bot_username = (await context.bot.get_me()).username
    caption = (
        f"🎬 <b>{title}</b>\n"
        f"🔑 Kod: <code>{code}</code>\n"
        f"📅 {year or ''} | {genre_emoji(genre)} {genre or ''}\n\n"
        f"🤖 @{bot_username}"
    )
    try:
        if file_type == 'video':
            await update.message.reply_video(video=file_id, caption=caption, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_document(document=file_id, caption=caption, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")

    # Agar seriyaning bir qismi bo'lsa — keyingi qism tugmasi
    series_group = movie[10]
    if series_group:
        conn = db(); c = conn.cursor()
        c.execute("SELECT id, code, episode_num FROM movies WHERE series_group=? ORDER BY episode_num",
                  (series_group,))
        eps = c.fetchall()
        conn.close()
        kb = [[InlineKeyboardButton(f"📺 {ep[2]}-qism: {ep[1]}", callback_data=f"movie_{ep[0]}")]
              for ep in eps if ep[0] != mid]
        if kb:
            await update.message.reply_text(
                "📺 <b>Boshqa qismlar:</b>",
                reply_markup=InlineKeyboardMarkup(kb[:10]),
                parse_mode=ParseMode.HTML
            )

# ============================================================
# 🎬 KINO YUBORISH (tugma orqali)
# ============================================================
async def send_movie_file(update: Update, context: ContextTypes.DEFAULT_TYPE, movie_id: int):
    query = update.callback_query
    user = query.from_user

    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM movies WHERE id=?", (movie_id,))
    movie = c.fetchone()
    conn.close()

    if not movie:
        await query.answer("❌ Kino topilmadi!", show_alert=True)
        return

    mid, code, title = movie[0], movie[1], movie[2]
    genre, year = movie[4], movie[5]
    file_id, file_type = movie[8], movie[9]
    views = movie[14]

    conn = db(); c = conn.cursor()
    c.execute("UPDATE movies SET views=? WHERE id=?", (views + 1, mid))
    c.execute("INSERT INTO watch_history VALUES (NULL,?,?,?)",
              (user.id, mid, datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute("UPDATE users SET total_watched=total_watched+1 WHERE user_id=?", (user.id,))
    conn.commit(); conn.close()

    await query.answer(f"🎬 {title} yuklanmoqda...")
    bot_username = (await context.bot.get_me()).username
    caption = (
        f"🎬 <b>{title}</b>\n"
        f"🔑 Kod: <code>{code}</code>\n"
        f"📅 {year or ''} | {genre_emoji(genre)} {genre or ''}\n\n"
        f"🤖 @{bot_username}"
    )
    try:
        if file_type == 'video':
            await context.bot.send_video(query.message.chat_id, video=file_id,
                                         caption=caption, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_document(query.message.chat_id, document=file_id,
                                            caption=caption, parse_mode=ParseMode.HTML)
    except Exception as e:
        await context.bot.send_message(query.message.chat_id, f"❌ Xato: {e}")

# ============================================================
# 🔍 QIDIRISH
# ============================================================
async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    conn = db(); c = conn.cursor()
    c.execute("""SELECT id, code, title, year, avg_rating, genre FROM movies
                 WHERE title LIKE ? OR code LIKE ? OR description LIKE ?
                 ORDER BY avg_rating DESC LIMIT 10""",
              (f'%{query_text}%',) * 3)
    movies = c.fetchall()
    conn.close()

    if not movies:
        await update.message.reply_text(
            f"🔍 <b>{query_text}</b> bo'yicha hech narsa topilmadi.\n\n"
            f"💡 Kino kodini to'g'ri yozing yoki boshqa nom bilan qidiring.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Bosh menyu", callback_data="main_menu")]
            ]), parse_mode=ParseMode.HTML
        )
        return

    kb = []
    for m in movies:
        mid, code, title, year, avg, genre = m
        kb.append([InlineKeyboardButton(
            f"{genre_emoji(genre)} {title} ({year or '?'}) | 🔑{code}",
            callback_data=f"movie_{mid}"
        )])
    kb.append([InlineKeyboardButton("⬅️ Bosh menyu", callback_data="main_menu")])
    await update.message.reply_text(
        f"🔍 <b>{query_text}</b> natijalari:",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML
    )

# ============================================================
# 📁 FAYL HANDLER (admin)
# ============================================================
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id, user.username):
        return

    state = context.user_data.get('admin_state')
    if state not in ('wait_file', 'wait_series_file'):
        return

    msg = update.message
    if msg.video:
        file_id, file_type = msg.video.file_id, 'video'
    elif msg.document:
        file_id, file_type = msg.document.file_id, 'document'
    else:
        await update.message.reply_text("❌ Faqat video yoki fayl yuboring.")
        return

    context.user_data['movie_file_id'] = file_id
    context.user_data['movie_file_type'] = file_type

    if state == 'wait_series_file':
        # Seriyaga avtomatik kod va qism raqami beriladi
        sd = context.user_data['series_data']
        sd['episode'] += 1
        code = f"{sd['base_code']}{sd['episode']}"
        d = {
            'code': code,
            'title': f"{sd['title']} - {sd['episode']}-qism",
            'genre': sd.get('genre', ''),
            'year': sd.get('year'),
            'desc': sd.get('desc', ''),
            'series_group': sd['base_code'],
            'episode_num': sd['episode']
        }
        movie_id = save_movie_to_db(d, file_id, file_type, user.id)
        await update.message.reply_text(
            f"✅ <b>{sd['episode']}-qism</b> qo'shildi!\n🔑 Kod: <code>{code}</code>\n\n"
            f"➡️ Keyingi qism faylini yuboring yoki tugatish uchun /done yozing.",
            parse_mode=ParseMode.HTML
        )
        if POST_CHANNEL:
            await announce_to_channel(context, d['title'], code, d.get('genre'), d.get('year'))
        return

    context.user_data['admin_state'] = 'wait_code'
    await update.message.reply_text(
        "✅ Fayl qabul qilindi!\n\n"
        "🔑 Kino kodini yozing (masalan: <code>AVATAR2</code>)\n"
        "Yoki avtomatik kod uchun /auto yozing:",
        parse_mode=ParseMode.HTML
    )

# ============================================================
# 📺 SERIYA TUGATISH
# ============================================================
async def done_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id, user.username):
        return
    if context.user_data.get('admin_state') == 'wait_series_file':
        sd = context.user_data.get('series_data', {})
        for k in ['admin_state', 'series_data', 'movie_file_id', 'movie_file_type']:
            context.user_data.pop(k, None)
        await update.message.reply_text(
            f"✅ Seriya tugatildi! Jami <b>{sd.get('episode', 0)}</b> qism qo'shildi.\n"
            f"🔑 Asosiy kod: <code>{sd.get('base_code')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]),
            parse_mode=ParseMode.HTML
        )

# ============================================================
# 👑 ADMIN INPUT HANDLER (oddiy kino qo'shish)
# ============================================================
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str, text: str):
    # Seriya holatlari
    if state in ('wait_series_title', 'wait_series_genre', 'wait_series_desc'):
        await handle_series_setup(update, context, state, text)
        return

    if state == 'wait_code':
        if text == '/auto':
            code = gen_random_code()
        else:
            code = text.upper().replace(' ', '')
            conn = db(); c = conn.cursor()
            c.execute("SELECT id FROM movies WHERE LOWER(code)=LOWER(?)", (code,))
            exists = c.fetchone(); conn.close()
            if exists:
                await update.message.reply_text(
                    f"❌ <b>{code}</b> kodi allaqachon mavjud! Boshqa kod yozing yoki /auto yozing:",
                    parse_mode=ParseMode.HTML
                )
                return

        context.user_data['new_movie'] = {'code': code}
        context.user_data['admin_state'] = 'wait_title'
        await update.message.reply_text(
            f"✅ Kod: <code>{code}</code>\n\n📝 Kino nomini yozing:",
            parse_mode=ParseMode.HTML
        )

    elif state == 'wait_title':
        context.user_data['new_movie']['title'] = text
        context.user_data['admin_state'] = 'wait_desc'
        imdb = get_omdb(text)
        if imdb:
            context.user_data['new_movie']['imdb'] = imdb
            await update.message.reply_text(
                f"✅ IMDb topildi: <b>{imdb['Title']} ({imdb['Year']})</b>\n"
                f"⭐ {imdb['imdbRating']} | 🎭 {imdb['Genre']}\n\n"
                f"📝 Ta'rif yozing yoki /skip:",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text("📝 Qisqacha ta'rif yozing yoki /skip:")

    elif state == 'wait_desc':
        if text != '/skip':
            context.user_data['new_movie']['desc'] = text
        context.user_data['admin_state'] = 'wait_genre'
        genres = ["Jangari", "Komediya", "Drama", "Qo'rqinchli", "Sevgi",
                  "Fantastika", "Multfilm", "Triller", "Jinoyat", "Sarguzasht"]
        kb = [[InlineKeyboardButton(f"{genre_emoji(g)} {g}", callback_data=f"set_genre_{g}")] for g in genres]
        await update.message.reply_text("🎭 Janrni tanlang yoki o'zingiz yozing:",
                                        reply_markup=InlineKeyboardMarkup(kb))

    elif state == 'wait_genre':
        context.user_data['new_movie']['genre'] = text
        context.user_data['admin_state'] = 'wait_year'
        await update.message.reply_text("📅 Yilni kiriting (masalan: 2023) yoki /skip:")

    elif state == 'wait_year':
        if text != '/skip':
            try:
                context.user_data['new_movie']['year'] = int(text)
            except ValueError:
                pass
        await finalize_movie(update, context)

async def finalize_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data.get('new_movie', {})
    file_id = context.user_data.get('movie_file_id')
    file_type = context.user_data.get('movie_file_type', 'video')

    try:
        movie_id = save_movie_to_db(d, file_id, file_type, update.effective_user.id)
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ Bu kod allaqachon mavjud! Qaytadan urinib ko'ring.")
        return

    for k in ['admin_state', 'new_movie', 'movie_file_id', 'movie_file_type']:
        context.user_data.pop(k, None)

    await update.message.reply_text(
        f"✅ <b>{d.get('title')}</b> muvaffaqiyatli qo'shildi!\n\n"
        f"🔑 Kino kodi: <code>{d.get('code')}</code>\n"
        f"👥 Foydalanuvchilar shu kodni yozsa kino chiqadi!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel"),
             InlineKeyboardButton("🎬 Ko'rish", callback_data=f"movie_{movie_id}")]
        ]), parse_mode=ParseMode.HTML
    )

    if POST_CHANNEL:
        await announce_to_channel(context, d.get('title'), d.get('code'), d.get('genre'), d.get('year'))

def save_movie_to_db(d, file_id, file_type, added_by):
    imdb = d.get('imdb', {})
    conn = db(); c = conn.cursor()
    c.execute("""INSERT INTO movies
        (code,title,description,genre,year,imdb_rating,poster_url,file_id,file_type,
         series_group,episode_num,added_by,added_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        d.get('code'),
        d.get('title', 'Nomsiz'),
        d.get('desc') or imdb.get('Plot', ''),
        d.get('genre') or imdb.get('Genre', ''),
        d.get('year') or (int(imdb['Year'][:4]) if imdb.get('Year') else None),
        imdb.get('imdbRating'),
        imdb.get('Poster'),
        file_id, file_type,
        d.get('series_group'), d.get('episode_num', 0),
        added_by,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))
    movie_id = c.lastrowid
    conn.commit(); conn.close()
    return movie_id

async def announce_to_channel(context, title, code, genre, year):
    try:
        text = (
            f"🆕 <b>YANGI KINO!</b>\n\n"
            f"🎬 <b>{title}</b>\n"
            f"{genre_emoji(genre)} {genre or ''} | 📅 {year or ''}\n\n"
            f"🔑 Kod: <code>{code}</code>\n\n"
            f"👇 Botga kirib shu kodni yuboring:\n"
            f"@{BOT_USERNAME}"
        )
        await context.bot.send_message(POST_CHANNEL, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"Kanalga e'lon yuborilmadi: {e}")

# ============================================================
# 📺 SERIYA QO'SHISH BOSHLASH (admin)
# ============================================================
async def start_add_series(update_or_query, context: ContextTypes.DEFAULT_TYPE, message):
    context.user_data['admin_state'] = 'wait_series_title'
    await message.edit_text(
        "📺 <b>Yangi seriya qo'shish</b>\n\n"
        "1️⃣ Seriya nomini yozing (masalan: <i>Money Heist</i>):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor", callback_data="admin_panel")]]),
        parse_mode=ParseMode.HTML
    )

async def handle_series_setup(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str, text: str):
    if state == 'wait_series_title':
        base_code = ''.join(text.upper().split())[:8] or gen_random_code(4)
        context.user_data['series_data'] = {
            'title': text, 'base_code': base_code, 'episode': 0
        }
        context.user_data['admin_state'] = 'wait_series_genre'
        genres = ["Jangari", "Komediya", "Drama", "Qo'rqinchli", "Triller", "Jinoyat", "Fantastika"]
        kb = [[InlineKeyboardButton(f"{genre_emoji(g)} {g}", callback_data=f"set_sgenre_{g}")] for g in genres]
        await update.message.reply_text(
            f"✅ Seriya: <b>{text}</b>\n🔑 Asosiy kod: <code>{base_code}</code>\n\n🎭 Janrni tanlang:",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML
        )

    elif state == 'wait_series_genre':
        context.user_data['series_data']['genre'] = text
        context.user_data['admin_state'] = 'wait_series_desc'
        await update.message.reply_text("📝 Qisqacha ta'rif yozing yoki /skip:")

    elif state == 'wait_series_desc':
        if text != '/skip':
            context.user_data['series_data']['desc'] = text
        context.user_data['admin_state'] = 'wait_series_file'
        await update.message.reply_text(
            "✅ Tayyor!\n\n"
            "🎬 Endi <b>1-qism</b> videosini yuboring.\n"
            "Har video yuborganingizda avtomatik keyingi qism sifatida qo'shiladi.\n\n"
            "✅ Tugatish uchun /done yozing.",
            parse_mode=ParseMode.HTML
        )

# ============================================================
# 🖱️ BUTTON HANDLER
# ============================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    register_user(user)
    data = query.data

    # ---------- Obuna ----------
    if data == "check_sub":
        if await check_sub(user.id, context):
            await query.answer("✅ Obuna tasdiqlandi!", show_alert=False)
            try:
                await query.message.delete()
            except Exception:
                pass
            await send_main_menu(query.message.chat_id, user, context)
        else:
            kb = [
                [InlineKeyboardButton("📢 Kanalga obuna bo'lish",
                                      url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
                [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
            ]
            try:
                await query.message.edit_text(
                    f"❌ Siz hali <b>{CHANNEL_USERNAME}</b> kanaliga obuna bo'lmagansiz!\n\n"
                    f"Obuna bo'lib qaytadan tekshiring 👇",
                    reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        return

    # ---------- Admin: janr tanlash (oddiy kino) ----------
    if data.startswith("set_genre_"):
        if is_admin(user.id, user.username):
            genre = data.replace("set_genre_", "")
            context.user_data['new_movie']['genre'] = genre
            context.user_data['admin_state'] = 'wait_year'
            await query.answer(f"✅ {genre}")
            await query.message.edit_text(f"✅ Janr: {genre}\n\n📅 Yilni kiriting yoki /skip:")
        return

    # ---------- Admin: janr tanlash (seriya) ----------
    if data.startswith("set_sgenre_"):
        if is_admin(user.id, user.username):
            genre = data.replace("set_sgenre_", "")
            context.user_data['series_data']['genre'] = genre
            context.user_data['admin_state'] = 'wait_series_desc'
            await query.answer(f"✅ {genre}")
            await query.message.edit_text(f"✅ Janr: {genre}\n\n📝 Ta'rif yozing yoki /skip:")
        return

    if data == "main_menu":
        await send_main_menu(query.message.chat_id, user, context, edit_msg=query.message)
        return

    if data == "search":
        await query.message.edit_text(
            "🔍 <b>Kino qidirish</b>\n\nKino nomi yoki kodini yozing:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]),
            parse_mode=ParseMode.HTML
        )
        context.user_data['wait_search'] = True
        return

    if data == "random":
        conn = db(); c = conn.cursor()
        c.execute("SELECT * FROM movies ORDER BY RANDOM() LIMIT 1")
        movie = c.fetchone(); conn.close()
        if movie:
            await show_movie_card(query.message, movie, edit=True)
        else:
            await query.message.edit_text("📭 Hozircha kinolar yo'q.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]))
        return

    if data == "genres":
        conn = db(); c = conn.cursor()
        c.execute("SELECT DISTINCT genre FROM movies WHERE genre IS NOT NULL AND genre != ''")
        genres = [r[0] for r in c.fetchall()]
        conn.close()
        if not genres:
            await query.message.edit_text("📭 Hozircha kinolar yo'q.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]))
            return
        kb = [[InlineKeyboardButton(f"{genre_emoji(g)} {g}", callback_data=f"genre_{g}")] for g in genres]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text("🎭 <b>Janrlar</b>\n\nQaysi janrni tanlaysiz?",
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return

    if data.startswith("genre_"):
        genre = data.replace("genre_", "")
        conn = db(); c = conn.cursor()
        c.execute("SELECT id, code, title, year, avg_rating FROM movies WHERE genre=? ORDER BY avg_rating DESC",
                  (genre,))
        movies = c.fetchall(); conn.close()
        kb = [[InlineKeyboardButton(f"🎬 {m[2]} ({m[3] or '?'}) | 🔑{m[1]}", callback_data=f"movie_{m[0]}")]
              for m in movies]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="genres")])
        await query.message.edit_text(f"{genre_emoji(genre)} <b>{genre}</b> kinolari:",
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return

    if data == "top":
        conn = db(); c = conn.cursor()
        c.execute("SELECT id, code, title, year, avg_rating FROM movies ORDER BY avg_rating DESC, views DESC LIMIT 10")
        movies = c.fetchall(); conn.close()
        kb = [[InlineKeyboardButton(f"#{i} {m[2]} ⭐{m[4]} | 🔑{m[1]}", callback_data=f"movie_{m[0]}")]
              for i, m in enumerate(movies, 1)]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text("⭐ <b>Top Kinolar</b>", reply_markup=InlineKeyboardMarkup(kb),
                                      parse_mode=ParseMode.HTML)
        return

    if data == "new":
        conn = db(); c = conn.cursor()
        c.execute("SELECT id, code, title, year FROM movies ORDER BY id DESC LIMIT 10")
        movies = c.fetchall(); conn.close()
        kb = [[InlineKeyboardButton(f"🆕 {m[2]} ({m[3] or '?'}) | 🔑{m[1]}", callback_data=f"movie_{m[0]}")]
              for m in movies]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text("📈 <b>Yangi Kinolar</b>", reply_markup=InlineKeyboardMarkup(kb),
                                      parse_mode=ParseMode.HTML)
        return

    if data == "recommend":
        conn = db(); c = conn.cursor()
        c.execute("""SELECT m.genre FROM watch_history wh JOIN movies m ON wh.movie_id=m.id
                     WHERE wh.user_id=? AND m.genre IS NOT NULL
                     GROUP BY m.genre ORDER BY COUNT(*) DESC LIMIT 2""", (user.id,))
        genres = [r[0] for r in c.fetchall()]
        if genres:
            ph = ','.join('?' * len(genres))
            c.execute(f"""SELECT id,code,title,year,genre FROM movies WHERE genre IN ({ph})
                         AND id NOT IN (SELECT movie_id FROM watch_history WHERE user_id=?)
                         ORDER BY avg_rating DESC LIMIT 8""", genres + [user.id])
        else:
            c.execute("SELECT id,code,title,year,genre FROM movies ORDER BY avg_rating DESC LIMIT 8")
        movies = c.fetchall(); conn.close()
        if not movies:
            await query.message.edit_text("💡 Avval bir nechta kino ko'ring, keyin tavsiya beraman!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]))
            return
        kb = [[InlineKeyboardButton(f"{genre_emoji(m[4])} {m[2]} | 🔑{m[1]}", callback_data=f"movie_{m[0]}")]
              for m in movies]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text("💡 <b>Siz uchun tavsiyalar</b>",
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return

    if data == "history":
        conn = db(); c = conn.cursor()
        c.execute("""SELECT m.id, m.code, m.title, m.year FROM watch_history wh
                     JOIN movies m ON wh.movie_id=m.id WHERE wh.user_id=?
                     ORDER BY wh.id DESC LIMIT 10""", (user.id,))
        history = c.fetchall(); conn.close()
        if not history:
            await query.message.edit_text("📜 Hali hech qanday kino ko'rmagansiz.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]))
            return
        kb = [[InlineKeyboardButton(f"🎬 {h[2]} | 🔑{h[1]}", callback_data=f"movie_{h[0]}")] for h in history]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text("📜 <b>Ko'rgan kinolarim</b>",
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return

    # ---------- Sevimlilar ----------
    if data == "favorites":
        conn = db(); c = conn.cursor()
        c.execute("""SELECT m.id, m.code, m.title, m.year FROM favorites f
                     JOIN movies m ON f.movie_id=m.id WHERE f.user_id=?
                     ORDER BY f.id DESC""", (user.id,))
        favs = c.fetchall(); conn.close()
        if not favs:
            await query.message.edit_text(
                "❤️ Sevimlilar ro'yxati bo'sh.\n\nKino kartasida ❤️ tugmasini bosib qo'shing!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]))
            return
        kb = [[InlineKeyboardButton(f"❤️ {f[2]} | 🔑{f[1]}", callback_data=f"movie_{f[0]}")] for f in favs]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text("❤️ <b>Sevimli kinolarim</b>",
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return

    if data.startswith("fav_"):
        movie_id = int(data.replace("fav_", ""))
        conn = db(); c = conn.cursor()
        c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user.id, movie_id))
        exists = c.fetchone()
        if exists:
            c.execute("DELETE FROM favorites WHERE user_id=? AND movie_id=?", (user.id, movie_id))
            conn.commit(); conn.close()
            await query.answer("💔 Sevimlilardan olib tashlandi", show_alert=False)
            is_fav = False
        else:
            c.execute("INSERT INTO favorites VALUES (NULL,?,?,?)",
                      (user.id, movie_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit(); conn.close()
            await query.answer("❤️ Sevimlilarga qo'shildi!", show_alert=False)
            is_fav = True
        conn = db(); c = conn.cursor()
        c.execute("SELECT * FROM movies WHERE id=?", (movie_id,))
        movie = c.fetchone()
        c.execute("SELECT rating FROM ratings WHERE user_id=? AND movie_id=?", (user.id, movie_id))
        ur = c.fetchone(); conn.close()
        if movie:
            await show_movie_card(query.message, movie, edit=True,
                                  user_rating=ur[0] if ur else None, is_fav=is_fav)
        return

    # ---------- Seriya boshqa qismlar ----------
    if data.startswith("series_"):
        series_group = data.replace("series_", "")
        conn = db(); c = conn.cursor()
        c.execute("SELECT id, code, episode_num, title FROM movies WHERE series_group=? ORDER BY episode_num",
                  (series_group,))
        eps = c.fetchall(); conn.close()
        kb = [[InlineKeyboardButton(f"📺 {e[2]}-qism | 🔑{e[1]}", callback_data=f"movie_{e[0]}")] for e in eps]
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")])
        await query.message.edit_text(f"📺 <b>Barcha qismlar</b> ({len(eps)} ta):",
                                      reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        return

    # ---------- Profil ----------
    if data == "profile":
        conn = db(); c = conn.cursor()
        c.execute("SELECT points, ref_count, total_watched, joined_date FROM users WHERE user_id=?", (user.id,))
        urow = c.fetchone(); conn.close()
        points, ref_count, watched, joined = urow if urow else (0, 0, 0, '-')
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref{user.id}"
        text = (
            f"👤 <b>Profilim</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"📅 Qo'shilgan: {joined}\n"
            f"👁 Ko'rgan kinolar: {watched}\n"
            f"🎁 Ballarim: {points}\n"
            f"👥 Taklif qilganlar: {ref_count}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 <b>Referal havolangiz:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"Har bir do'stingiz botga shu havola orqali qo'shilsa — sizga "
            f"<b>+{REFERAL_BONUS} ball</b> beriladi! 🎉"
        )
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]),
            parse_mode=ParseMode.HTML
        )
        return

    if data == "help":
        await query.message.edit_text(
            "ℹ️ <b>Yordam</b>\n\n"
            "🔑 <b>Kod orqali kino olish:</b>\n"
            "   Bot ga kino kodini yozing → kino keladi!\n\n"
            "🔍 <b>Qidirish</b> — nom bo'yicha qidirish\n"
            "🎲 <b>Tasodifiy</b> — tasodifiy kino\n"
            "🎭 <b>Janrlar</b> — janr bo'yicha tanlash\n"
            "⭐ <b>Top</b> — eng yaxshi kinolar\n"
            "📈 <b>Yangi</b> — oxirgi qo'shilganlar\n"
            "💡 <b>Tavsiya</b> — sizga mos kinolar\n"
            "❤️ <b>Sevimlilar</b> — saqlangan kinolar\n"
            "👤 <b>Profil</b> — referal havola va ballar\n\n"
            f"📞 Admin: @{ADMIN_USERNAME}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]]),
            parse_mode=ParseMode.HTML
        )
        return

    if data.startswith("movie_"):
        movie_id = int(data.replace("movie_", ""))
        conn = db(); c = conn.cursor()
        c.execute("SELECT * FROM movies WHERE id=?", (movie_id,))
        movie = c.fetchone()
        c.execute("SELECT rating FROM ratings WHERE user_id=? AND movie_id=?", (user.id, movie_id))
        ur = c.fetchone()
        c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user.id, movie_id))
        is_fav = bool(c.fetchone())
        conn.close()
        if movie:
            await show_movie_card(query.message, movie, edit=True,
                                  user_rating=ur[0] if ur else None, is_fav=is_fav)
        return

    if data.startswith("watch_"):
        movie_id = int(data.replace("watch_", ""))
        await send_movie_file(update, context, movie_id)
        return

    if data.startswith("rate_"):
        parts = data.split("_")
        movie_id, rating = int(parts[1]), int(parts[2])
        conn = db(); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO ratings VALUES (NULL,?,?,?)", (user.id, movie_id, rating))
        conn.commit(); conn.close()
        update_rating(movie_id)
        await query.answer(f"✅ {rating}⭐ baho berdingiz!")
        conn = db(); c = conn.cursor()
        c.execute("SELECT * FROM movies WHERE id=?", (movie_id,))
        movie = c.fetchone()
        c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user.id, movie_id))
        is_fav = bool(c.fetchone())
        conn.close()
        if movie:
            await show_movie_card(query.message, movie, edit=True, user_rating=rating, is_fav=is_fav)
        return

    # ========== ADMIN ==========
    if data == "admin_panel":
        if not is_admin(user.id, user.username):
            await query.answer("❌ Ruxsat yo'q!", show_alert=True)
            return
        await show_admin_panel(query)
        return

    if data == "admin_add":
        if not is_admin(user.id, user.username):
            return
        context.user_data['admin_state'] = 'wait_file'
        context.user_data['new_movie'] = {}
        await query.message.edit_text(
            "➕ <b>Yangi kino qo'shish</b>\n\n1️⃣ Kino faylini yuboring (video yoki document):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor", callback_data="admin_panel")]]),
            parse_mode=ParseMode.HTML
        )
        return

    if data == "admin_add_series":
        if not is_admin(user.id, user.username):
            return
        await start_add_series(query, context, query.message)
        return

    if data == "admin_list":
        if not is_admin(user.id, user.username):
            return
        await render_admin_movie_list(query)
        return

    if data.startswith("del_"):
        if not is_admin(user.id, user.username):
            return
        movie_id = int(data.replace("del_", ""))
        conn = db(); c = conn.cursor()
        c.execute("SELECT title, code FROM movies WHERE id=?", (movie_id,))
        m = c.fetchone()
        if m:
            c.execute("DELETE FROM movies WHERE id=?", (movie_id,))
            c.execute("DELETE FROM ratings WHERE movie_id=?", (movie_id,))
            c.execute("DELETE FROM watch_history WHERE movie_id=?", (movie_id,))
            c.execute("DELETE FROM favorites WHERE movie_id=?", (movie_id,))
            conn.commit()
            await query.answer(f"✅ '{m[0]}' (kod: {m[1]}) o'chirildi!", show_alert=True)
        conn.close()
        await render_admin_movie_list(query)
        return

    if data == "admin_stats":
        if not is_admin(user.id, user.username):
            return
        conn = db(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM movies"); mc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users"); uc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM watch_history"); wc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM favorites"); fc = c.fetchone()[0]
        c.execute("SELECT title, code, views FROM movies ORDER BY views DESC LIMIT 5")
        top5 = c.fetchall()
        c.execute("SELECT COUNT(*) FROM users WHERE last_active >= date('now','-7 days')")
        active_week = c.fetchone()[0]
        conn.close()
        top_text = "\n".join([f"  {i+1}. {m[0]} (🔑{m[1]}) — {m[2]} ko'rish" for i, m in enumerate(top5)])
        await query.message.edit_text(
            f"📊 <b>Statistika</b>\n\n"
            f"🎬 Kinolar: {mc}\n"
            f"👥 Foydalanuvchilar: {uc}\n"
            f"📈 Haftalik faol: {active_week}\n"
            f"👁 Jami ko'rishlar: {wc}\n"
            f"❤️ Sevimlilar soni: {fc}\n\n"
            f"🏆 Top 5 kino:\n{top_text or 'Hozircha yo`q'}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")]]),
            parse_mode=ParseMode.HTML
        )
        return

    if data == "admin_broadcast":
        if not is_admin(user.id, user.username):
            return
        await query.message.edit_text(
            "📢 <b>Xabar yuborish</b>\n\nBarcha foydalanuvchilarga yuboriladigan xabarni yozing:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor", callback_data="admin_panel")]]),
            parse_mode=ParseMode.HTML
        )
        context.user_data['wait_broadcast'] = True
        return

async def render_admin_movie_list(query):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, code, title, views, avg_rating FROM movies ORDER BY id DESC LIMIT 20")
    movies = c.fetchall(); conn.close()
    kb = []
    for m in movies:
        kb.append([
            InlineKeyboardButton(f"🎬 {m[2]} | 🔑{m[1]} | 👁{m[3]}", callback_data=f"movie_{m[0]}"),
            InlineKeyboardButton("🗑", callback_data=f"del_{m[0]}")
        ])
    kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")])
    await query.message.edit_text("🎬 <b>Barcha kinolar</b> (oxirgi 20 ta):",
                                  reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def show_admin_panel(query):
    conn = db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM movies"); mc = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users"); uc = c.fetchone()[0]
    conn.close()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Kino qo'shish", callback_data="admin_add"),
         InlineKeyboardButton("📺 Seriya qo'shish", callback_data="admin_add_series")],
        [InlineKeyboardButton("🎬 Kinolar ro'yxati", callback_data="admin_list"),
         InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⬅️ Bosh menyu", callback_data="main_menu")]
    ])
    await query.message.edit_text(
        f"👑 <b>Admin Panel</b>\n\n🎬 Kinolar: {mc}\n👥 Foydalanuvchilar: {uc}",
        reply_markup=kb, parse_mode=ParseMode.HTML
    )

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    conn = db(); c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall(); conn.close()
    ok, fail = 0, 0
    for u in users:
        try:
            await context.bot.send_message(u[0], f"📢 {text}", parse_mode=ParseMode.HTML)
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(
        f"✅ Yuborildi: {ok}\n❌ Xato: {fail}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]])
    )

# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done_series))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🎬 Kino Bot ishga tushdi!")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print(f"📢 Kanal: {CHANNEL_USERNAME}")
    print(f"📺 E'lon kanali: {POST_CHANNEL}")
    print("🔑 Kod tizimi: YOQILGAN | ❤️ Sevimlilar | 📺 Seriyalar | 🎁 Referal")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

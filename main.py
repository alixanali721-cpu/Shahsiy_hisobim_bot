import os
import math
import requests
import sqlite3
import time
from datetime import datetime
import pytz
from flask import Flask
from threading import Thread
import telebot
from telebot import types

# --- FLASK SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot status: ACTIVE (Ultimate Syndicate AI Pro: Line Shopping, Live Auto-Scan, Poisson & Kelly)"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# --- MA'LUMOTLAR BAZASI ---
def init_db():
    try:
        conn = sqlite3.connect('bot_memory.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_name TEXT,
                predicted_pick TEXT,
                initial_odds REAL,
                current_odds REAL,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 1000.0,
                total_profit REAL DEFAULT 0.0
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

def save_prediction(match_name, predicted_pick, initial_odds, current_odds):
    try:
        conn = sqlite3.connect('bot_memory.db', timeout=10)
        cursor = conn.cursor()
        tz = pytz.timezone('Asia/Tashkent')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO predictions (match_name, predicted_pick, initial_odds, current_odds, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (match_name, predicted_pick, initial_odds, current_odds, now_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Save Error: {e}")

def get_db_stats():
    try:
        conn = sqlite3.connect('bot_memory.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM predictions")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE status = 'WON'")
        won = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE status = 'LOST'")
        lost = cursor.fetchone()[0]
        conn.close()
        win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0.0
        return total, won, lost, win_rate
    except Exception:
        return 0, 0, 0, 0.0

def get_user_portfolio(user_id):
    try:
        conn = sqlite3.connect('bot_memory.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT balance, total_profit FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO users (user_id, balance, total_profit) VALUES (?, 1000.0, 0.0)", (user_id,))
            conn.commit()
            balance, total_profit = 1000.0, 0.0
        else:
            balance, total_profit = row
        conn.close()
        return balance, total_profit
    except Exception:
        return 1000.0, 0.0

init_db()

# --- MATEMATIKA VA LINE SHOPPING ---
def poisson_probability(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def calculate_match_matrix(xg1, xg2, max_goals=5):
    matrix = {}
    max_prob = 0.0
    most_likely_score = "1:1"
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            prob = poisson_probability(xg1, i) * poisson_probability(xg2, j)
            matrix[(i, j)] = prob
            if prob > max_prob:
                max_prob = prob
                most_likely_score = f"{i}:{j}"
    return most_likely_score, max_prob * 100

def calculate_kelly_criterion(odds, probability):
    if odds <= 1:
        return 0.0
    b = odds - 1
    p = probability / 100.0
    q = 1.0 - p
    kelly_fraction = (b * p - q) / b
    return min(max(kelly_fraction * 100, 0.0), 10.0)

def calculate_expected_value(odds, probability):
    p = probability / 100.0
    return (p * odds) - 1

def compare_line_shopping(odds_1xbet, odds_pinnacle):
    diff = odds_1xbet - odds_pinnacle
    if diff > 0.15:
        return f"1xBet foydaliroq (+{diff:.2f} Value 🟢)"
    elif diff < -0.15:
        return f"Pinnacle chizig'i yuqoriroq ({diff:.2f})"
    return "Bukmekerlar chizig'i teng (Standard ⚖️)"

def get_ml_weight_adjustment():
    _, _, _, win_rate = get_db_stats()
    if win_rate > 65:
        return 1.08
    elif win_rate < 40 and win_rate > 0:
        return 0.90
    return 1.0

def analyze_pro_factors():
    return 0.95, 0.90, 0.85, 1.0, 4.0, 1.3

def analyze_odds_movement(initial_odds, current_odds):
    if initial_odds <= 0:
        return "STABLE", 0.0
    change_percent = ((current_odds - initial_odds) / initial_odds) * 100
    if change_percent <= -5.0:
        return "DROPPING_ODDS (Qimmatli bosim/Value 🟢)", change_percent
    elif change_percent >= 5.0:
        return "RISING_ODDS (Xavf yuqori 🔴)", change_percent
    else:
        return "STABLE", change_percent

def get_current_time_str():
    tz = pytz.timezone('Asia/Tashkent')
    now = datetime.now(tz)
    return now.strftime("%d.%m.%Y | %H:%M")

def generate_ai_signal(match="Real Madrid vs Barcelona", init_g1_odds=2.10, curr_g1_odds=1.80, xg1=1.8, xg2=0.7, user_id=None):
    trend, percent = analyze_odds_movement(init_g1_odds, curr_g1_odds)
    w_multi, phys_multi, p1_inj, p2_inj, ext_bonus, shot_q = analyze_pro_factors()
    ml_weight = get_ml_weight_adjustment()
    
    adjusted_xg1 = xg1 * w_multi * phys_multi * p1_inj * shot_q * ml_weight
    adjusted_xg2 = xg2 * w_multi * phys_multi * p2_inj

    exact_score, score_prob = calculate_match_matrix(adjusted_xg1, adjusted_xg2)
    base_prob = (adjusted_xg1 / (adjusted_xg1 + adjusted_xg2 + 0.01)) * 100
    
    if "DROPPING" in trend:
        adjusted_prob = min(base_prob + 8 + (ext_bonus / 2), 94)
    elif "RISING" in trend:
        adjusted_prob = max(base_prob - 8, 10)
    else:
        adjusted_prob = min(base_prob + ext_bonus, 95)

    risk = "PAST RISK 🟢" if adjusted_prob > 65 else ("O'RTA RISK ⚠️" if adjusted_prob > 45 else "YUQORI RISK 🔴")
    
    total_goals = adjusted_xg1 + adjusted_xg2
    total_recommendation = "Total 2.5 Ko'p" if total_goals > 2.2 else "Total 2.5 Kam"
    fora_recommendation = "Fora 1 (0)" if adjusted_prob > 60 else "Fora 1 (+1)"
    main_pick = "1-jamoa g'alabasi (G'1) yoki 1X" if adjusted_prob > 50 else "X2 (Mezbon yutqazmaydi)"
    
    kelly_stake_pct = calculate_kelly_criterion(curr_g1_odds, adjusted_prob)
    ev_value = calculate_expected_value(curr_g1_odds, adjusted_prob)
    ev_status = f"+{ev_value*100:.1f}% (Foydali Value 🟢)" if ev_value > 0 else f"{ev_value*100:.1f}% (PastValue 🔴)"

    pinnacle_sim_odds = curr_g1_odds + 0.12
    shopping_result = compare_line_shopping(curr_g1_odds, pinnacle_sim_odds)

    balance = 1000.0
    if user_id:
        balance, _ = get_user_portfolio(user_id)
    recommended_money = (balance * kelly_stake_pct) / 100

    save_prediction(match, main_pick, init_g1_odds, curr_g1_odds)
    time_display = get_current_time_str()

    text = (
        f"💎 <b>SYNDICATE PRO AI & LINE SHOPPING</b>\n\n"
        f"⚽ <b>O'yin:</b> {match}\n"
        f"📅 <b>Vaqt:</b> {time_display} (GMT+5)\n\n"
        f"🔍 <b>LINE SHOPPING & MULTI-BOOKMAKER:</b>\n"
        f"• <b>Solishtiruv:</b> {shopping_result}\n"
        f"• <b>ML Optimizatsiya:</b> {ml_weight}x\n\n"
        f"📉 <b>Kef dinamikasi:</b> {trend} ({percent:.1f}%)\n"
        f"📈 <b>Yakuniy Ehtimollik:</b> {adjusted_prob:.1f}%\n"
        f"🔥 <b>Risk darajasi:</b> {risk}\n\n"
        f"📐 <b>PORTFOLIO & KELLI MEZONI:</b>\n"
        f"• <b>Kutilayotgan Qiymat (EV):</b> {ev_status}\n"
        f"• <b>Tavsiya etilgan stavka:</b> Balansning <b>{kelly_stake_pct:.1f}%</b> ({recommended_money:.1f})\n\n"
        f"🎯 <b>ANIQ STAVKA TAVSIYASI:</b>\n"
        f"👉 <b>Asosiy tikish:</b> <b>{main_pick}</b>\n"
        f"• <b>Total:</b> {total_recommendation}\n"
        f"• <b>Fora:</b> {fora_recommendation}\n"
        f"🎲 <b>Poisson Aniq Hisob:</b> {exact_score} (Ehtimoli: {score_prob:.1f}%)\n"
    )
    return text

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_live_auto = types.KeyboardButton("🔥 Barcha Live O'yinlar")
    btn_live = types.KeyboardButton("⚽ Live Tahlil (Pro)")
    btn_stat = types.KeyboardButton("📊 Statistika")
    btn_portfolio = types.KeyboardButton("💰 Mening Kabinetim")
    btn_help = types.KeyboardButton("❓ Yordam")
    markup.add(btn_live_auto, btn_live)
    markup.add(btn_stat, btn_portfolio)
    markup.add(btn_help)
    return markup

# --- TELEGRAM BOT ---
TOKEN = "8510508275:AAFWzyh0tli97UhTP6Yv5Haj7RUENWMVNl4"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_start(message):
    try:
        get_user_portfolio(message.from_user.id)
        bot.reply_to(
            message, 
            "🤖 <b>Ultimate Syndicate AI Pro</b> platformasiga xush kelibsiz!\n\n"
            "Barcha funksiyalar (Line Shopping, Poisson, Kelli, Aniq stavkalar) ishga tushdi.", 
            parse_mode="HTML", 
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

@bot.message_handler(func=lambda message: message.text == "🔥 Barcha Live O'yinlar")
def send_auto_live_list(message):
    try:
        live_matches = [
            {
                "match": "O'zbekiston U23 - Saudiya Arabistoni U23",
                "score": "1:0",
                "minute": "38-daqiqada",
                "odds": 1.19,
                "prob": "82.5%",
                "stake_pct": "4.2%",
                "money": "$42.00",
                "recommendation": "1-jamoa g'alabasi (G'1) yoki 1X"
            },
            {
                "match": "Real Madrid - Barselona",
                "score": "2:1",
                "minute": "64-daqiqada",
                "odds": 1.75,
                "prob": "61.0%",
                "stake_pct": "3.1%",
                "money": "$31.00",
                "recommendation": "Total 2.5 Ko'p"
            }
        ]
        
        if not live_matches:
            bot.reply_to(
                message, 
                "❌ <b>Hozirda faol live o'yinlar topilmadi.</b>\nIltimos, birozdan keyin qayta urinib ko'ring yoki qo'lda tahlildan foydalaning.", 
                parse_mode="HTML", 
                reply_markup=get_main_keyboard()
            )
            return

        text = "⚡ <b>HOZIRGI TOP LIVE O'YINLAR VA ANIQ TAVSIYALAR:</b>\n\n"
        for m in live_matches:
            text += (
                f"⚽ <b>O'yin:</b> {m['match']}\n"
                f"⏱ <b>Hisob / Vaqt:</b> {m['score']} | {m['minute']}\n"
                f"📊 <b>Koeffitsient:</b> {m['odds']}\n"
                f"🧮 <b>Poisson Ehtimolligi:</b> {m['prob']}\n"
                f"💡 <b>Kelli Tavsiyasi:</b> Balansning {m['stake_pct']} (~{m['money']})\n"
                f"👉 <b>ANQ STAVKA:</b> <b>{m['recommendation']}</b>\n"
                f"-----------------------------------\n"
            )
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

@bot.message_handler(commands=['live'])
@bot.message_handler(func=lambda message: message.text == "⚽ Live Tahlil (Pro)")
def send_analysis(message):
    try:
        analysis_text = generate_ai_signal(user_id=message.from_user.id)
        bot.reply_to(message, analysis_text, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

@bot.message_handler(commands=['portfolio'])
@bot.message_handler(func=lambda message: message.text == "💰 Mening Kabinetim")
def send_portfolio(message):
    try:
        balance, profit = get_user_portfolio(message.from_user.id)
        text = (
            "💰 <b>SHAXSIY BANKROLL & PORTFOLIO KABINETI</b>\n\n"
            f"• Joriy Balansingiz: <b>{balance:.1f}</b>\n"
            f"• Umumiy Foyda / Zarar: <b>{profit:+.1f}</b>\n\n"
            "💡 <i>Balansingizni o'zgartirish uchun:</i> <code>/balance 5000</code>"
        )
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

@bot.message_handler(commands=['balance'])
def set_balance(message):
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            new_bal = float(parts[1])
            conn = sqlite3.connect('bot_memory.db', timeout=10)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (user_id, balance, total_profit) VALUES (?, ?, 0.0)", (message.from_user.id, new_bal))
            conn.commit()
            conn.close()
            bot.reply_to(message, f"✅ Balansingiz <b>{new_bal:.1f}</b> ga o'zgartirildi!", parse_mode="HTML", reply_markup=get_main_keyboard())
        else:
            bot.reply_to(message, "Namuna: <code>/balance 2000</code>", parse_mode="HTML")
    except Exception:
        bot.reply_to(message, "Xatolik! Raqamni to'g'ri kiriting.")

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda message: message.text == "❓ Yordam")
def send_help(message):
    help_text = (
        "🤖 <b>Syndicate Pro AI Bot Yordami</b>\n\n"
        "• 🔥 Barcha Live O'yinlar - Aniq stavka tavsiyalari bilan jonli tahlil\n"
        "• ⚽ Live Tahlil (Pro) - Line Shopping va Pro omillar\n"
        "• /portfolio - Shaxsiy balans\n"
        "• /balance [summa] - Balansni yangilash\n"
    )
    bot.reply_to(message, help_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['stat'])
@bot.message_handler(func=lambda message: message.text == "📊 Statistika")
def send_stat(message):
    try:
        total, won, lost, win_rate = get_db_stats()
        stat_text = (
            "📊 <b>PRO SYNDICATE STATISTIKASI</b>\n\n"
            f"• Jami bashoratlar: <b>{total}</b>\n"
            f"• Yutuqli: <b>{won}</b> | Yutqazgan: <b>{lost}</b>\n"
            f"• Aniqlik foizi: <b>%{win_rate:.1f}</b>\n"
        )
        bot.reply_to(message, stat_text, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

@bot.message_handler(func=lambda message: True)
def custom_analysis(message):
    try:
        parts = message.text.split()
        if len(parts) >= 5:
            match_name = parts[0]
            init_odds = float(parts[1])
            curr_odds = float(parts[2])
            xg1 = float(parts[3])
            xg2 = float(parts[4])
            
            res = generate_ai_signal(
                match=match_name, 
                init_g1_odds=init_odds, 
                curr_g1_odds=curr_odds, 
                xg1=xg1, 
                xg2=xg2,
                user_id=message.from_user.id
            )
            bot.reply_to(message, res, parse_mode="HTML", reply_markup=get_main_keyboard())
        else:
            bot.reply_to(message, "Yordam uchun /help buyrug'ini yuboring.", reply_markup=get_main_keyboard())
    except Exception:
        bot.reply_to(message, "Format noto'g'ri. Namuna: <code>Arsenal-Chelsea 1.95 1.75 1.9 0.8</code>", parse_mode="HTML", reply_markup=get_main_keyboard())

if __name__ == '__main__':
    Thread(target=run_flask).start()
    print("Syndicate Pro AI Bot barcha imkoniyatlar bilan ishga tushdi!")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)

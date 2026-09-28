"""
Serverless Telegram-бот магазина одежды (webhook).

Telegram сам вызывает эту функцию при каждом сообщении, процесс
постоянно держать не нужно. Состояние диалога хранится в callback_data
inline-кнопок, поэтому база данных не нужна.

Переменные окружения:
  BOT_TOKEN       — токен от @BotFather (обязательно)
  WEBHOOK_SECRET  — секрет для проверки, что запрос пришёл от Telegram (рекомендуется)
  ADMIN_CHAT_ID   — chat id, куда присылать готовые заказы (необязательно)
"""
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

TOKEN = os.environ.get("BOT_TOKEN", "")
SECRET = os.environ.get("WEBHOOK_SECRET", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

MANAGER_PHONE = "+7 707 729 0612"
DELIVERY_PRICE = 2000


# ==================================================
# 📦 ДАННЫЕ
# ==================================================

PRODUCTS = {
    "h": {
        "name": "🧥 Худи",
        "price": 15000,
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["⚫ Чёрный", "⚪ Белый", "🩶 Серый"],
        "words": ["худи"],
    },
    "t": {
        "name": "👕 Футболка",
        "price": 7000,
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "colors": ["⚫ Чёрный", "⚪ Белый", "🔵 Синий", "🔴 Красный"],
        "words": ["футбол"],
    },
    "c": {
        "name": "👖 Карго",
        "price": 18000,
        "sizes": ["S", "M", "L"],
        "colors": ["🟢 Хаки", "⚫ Чёрный", "🟤 Бежевый"],
        "words": ["карго"],
    },
}

CITIES = [
    "Алматы", "Астана", "Шымкент",
    "Караганда", "Актобе", "Тараз",
    "Павлодар", "Семей", "Костанай",
    "Атырау", "Актау", "Туркестан",
    "Кокшетау",
]

CITY_STEMS = [
    "алмат", "астан", "шымкент", "караган", "актоб", "тараз", "павлодар",
    "семей", "костанай", "атырау", "актау", "туркестан", "кокшетау",
]

MAIN_KB = {
    "keyboard": [
        [{"text": "🛍 Товары"}, {"text": "💰 Цены"}],
        [{"text": "📏 Размеры"}, {"text": "🎨 Цвета"}],
        [{"text": "🚚 Доставка"}, {"text": "🛒 Заказать"}],
    ],
    "resize_keyboard": True,
}


# ==================================================
# 🔧 УТИЛИТЫ
# ==================================================

def money(n):
    return f"{n:,}".replace(",", " ") + " ₸"


def size_range(p):
    s = p["sizes"]
    return s[0] if len(s) == 1 else f"{s[0]}–{s[-1]}"


def ikb(rows):
    """rows: [[(текст, callback_data), ...], ...] -> inline-клавиатура."""
    return {
        "inline_keyboard": [
            [{"text": t, "callback_data": d} for t, d in row] for row in rows
        ]
    }


def tg(method, **params):
    """Вызов Telegram Bot API без внешних библиотек."""
    params = {k: v for k, v in params.items() if v is not None}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print("TG error", method, e.read()[:300])
    except Exception as e:  # noqa: BLE001
        print("TG error", method, repr(e))
    return None


def send(chat_id, text, markup=None):
    return tg("sendMessage", chat_id=chat_id, text=text, reply_markup=markup)


# ==================================================
# 📝 ТЕКСТЫ
# ==================================================

def text_products():
    lines = [f"{p['name']} — {money(p['price'])}" for p in PRODUCTS.values()]
    return "🛍 НАШИ ТОВАРЫ\n\n" + "\n".join(lines)


def text_sizes():
    lines = [f"{p['name']}: {size_range(p)}" for p in PRODUCTS.values()]
    return "📏 РАЗМЕРЫ\n\n" + "\n".join(lines)


GREETING = (
    "Здравствуйте! 👋\n\n"
    "Я бот магазина одежды.\n"
    "Выберите нужный раздел ниже или напишите свой вопрос."
)


# ==================================================
# 🧭 ЭКРАНЫ (текст + inline-кнопки)
# ==================================================

def v_home():
    return "🏠 Выберите раздел в меню ниже 👇", {"inline_keyboard": []}


# ---- цены ----
def v_price_menu():
    rows = [[(p["name"], f"pr:{k}")] for k, p in PRODUCTS.items()]
    rows.append([("🏠 В меню", "m")])
    return "💰 О каком товаре подсказать цену?", ikb(rows)


def v_price(k):
    p = PRODUCTS[k]
    return (
        f"💰 {p['name']}\nЦена: {money(p['price'])}",
        ikb([[("⬅️ Другой товар", "p")], [("🏠 В меню", "m")]]),
    )


# ---- цвета ----
def v_color_menu():
    rows = [[(p["name"], f"cr:{k}")] for k, p in PRODUCTS.items()]
    rows.append([("🏠 В меню", "m")])
    return "🎨 Для какого товара показать доступные цвета?", ikb(rows)


def v_colors_info(k):
    p = PRODUCTS[k]
    return (
        f"🎨 {p['name']}\nДоступные цвета:\n" + "\n".join(p["colors"]),
        ikb([[("⬅️ Другой товар", "c")], [("🏠 В меню", "m")]]),
    )


# ---- заказ / доставка ----
def v_cities():
    rows, row = [], []
    for i, city in enumerate(CITIES):
        row.append((city, f"dc:{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("🏠 В меню", "m")])
    return (
        "🚚 ДОСТАВКА\n\n"
        "Доставляем по всему Казахстану 🇰🇿\n"
        f"Стоимость — {money(DELIVERY_PRICE)}.\n\n"
        "Выберите город:",
        ikb(rows),
    )


def v_products(i):
    rows = [
        [(f"{p['name']} — {money(p['price'])}", f"dp:{i}:{k}")]
        for k, p in PRODUCTS.items()
    ]
    rows.append([("⬅️ Другой город", "d")])
    return (
        f"🏙 Город: {CITIES[i]}\n"
        f"🚚 Доставка — {money(DELIVERY_PRICE)}\n\n"
        "Выберите товар:",
        ikb(rows),
    )


def v_sizes(i, k):
    p = PRODUCTS[k]
    rows = [[(s, f"ds:{i}:{k}:{si}") for si, s in enumerate(p["sizes"])]]
    rows.append([("⬅️ Другой товар", f"dc:{i}")])
    return f"{p['name']} — {money(p['price'])}\n\nВыберите размер:", ikb(rows)


def v_colors(i, k, si):
    p = PRODUCTS[k]
    rows = [[(c, f"dk:{i}:{k}:{si}:{ci}")] for ci, c in enumerate(p["colors"])]
    rows.append([("⬅️ Другой размер", f"dp:{i}:{k}")])
    return (
        f"{p['name']}, размер {p['sizes'][si]}\n\nВыберите цвет:",
        ikb(rows),
    )


def order_lines(i, k, si, ci):
    p = PRODUCTS[k]
    total = p["price"] + DELIVERY_PRICE
    return (
        f"Товар: {p['name']}\n"
        f"Размер: {p['sizes'][si]}\n"
        f"Цвет: {p['colors'][ci]}\n"
        f"Город: {CITIES[i]}\n\n"
        f"Цена: {money(p['price'])}\n"
        f"Доставка: {money(DELIVERY_PRICE)}\n"
        f"Итого: {money(total)}"
    )


def v_confirm(i, k, si, ci):
    return (
        "🛒 ПРОВЕРЬТЕ ЗАКАЗ\n\n" + order_lines(i, k, si, ci),
        ikb([
            [("✅ Подтвердить заказ", f"ok:{i}:{k}:{si}:{ci}")],
            [("⬅️ Изменить цвет", f"ds:{i}:{k}:{si}")],
            [("❌ Отмена", "m")],
        ]),
    )


def v_done(i, k, si, ci, order_no):
    return (
        f"✅ ЗАКАЗ №{order_no} ОФОРМЛЕН\n\n"
        + order_lines(i, k, si, ci)
        + "\n\nДля подтверждения заказа напишите нашему менеджеру:\n"
        f"📞 {MANAGER_PHONE}",
        {"inline_keyboard": []},
    )


# ==================================================
# 🔀 МАРШРУТИЗАЦИЯ КНОПОК
# ==================================================

def route(data, user):
    """Возвращает (текст, клавиатура) или None."""
    parts = data.split(":")
    a = parts[0]

    if a == "m":
        return v_home()
    if a == "p":
        return v_price_menu()
    if a == "pr":
        return v_price(parts[1])
    if a == "c":
        return v_color_menu()
    if a == "cr":
        return v_colors_info(parts[1])
    if a == "d":
        return v_cities()
    if a == "dc":
        return v_products(int(parts[1]))
    if a == "dp":
        return v_sizes(int(parts[1]), parts[2])
    if a == "ds":
        return v_colors(int(parts[1]), parts[2], int(parts[3]))
    if a == "dk":
        return v_confirm(*_order_args(parts))
    if a == "ok":
        i, k, si, ci = _order_args(parts)
        order_no = str(int(time.time()))[-6:]
        notify_admin(user, order_no, i, k, si, ci)
        return v_done(i, k, si, ci, order_no)
    return None


def _order_args(parts):
    i, k, si, ci = int(parts[1]), parts[2], int(parts[3]), int(parts[4])
    # проверка границ — защита от подделанных callback_data
    CITIES[i]
    p = PRODUCTS[k]
    p["sizes"][si]
    p["colors"][ci]
    return i, k, si, ci


def notify_admin(user, order_no, i, k, si, ci):
    if not ADMIN_CHAT_ID:
        return
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
    uname = f"@{user['username']}" if user.get("username") else "без username"
    send(
        ADMIN_CHAT_ID,
        f"🔔 НОВЫЙ ЗАКАЗ №{order_no}\n\n"
        f"Клиент: {name} ({uname})\n"
        f"ID: {user.get('id')}\n\n" + order_lines(i, k, si, ci),
    )


# ==================================================
# 🤖 СВОБОДНЫЙ ТЕКСТ
# ==================================================

def has(q, *words):
    return any(w in q for w in words)


def free_text(text):
    q = text.lower()
    k = next((key for key, p in PRODUCTS.items() if has(q, *p["words"])), None)

    if has(q, "привет", "здрав", "салам", "здаров", "хай", "hello",
           "ассаламу", "асаламу", "салем", "сәлем", "добрый"):
        return "Здравствуйте! 👋\nЧем могу помочь?"

    if k and has(q, "цен", "сто", "сколько", "почем"):
        p = PRODUCTS[k]
        return (
            f"{p['name']} — {money(p['price'])}\n"
            f"🚚 С доставкой — {money(p['price'] + DELIVERY_PRICE)}"
        )

    if k and has(q, "цвет"):
        p = PRODUCTS[k]
        return f"🎨 {p['name']}, цвета:\n" + "\n".join(p["colors"])

    if k and has(q, "размер", "разм"):
        p = PRODUCTS[k]
        return f"📏 {p['name']}: {size_range(p)}"

    if has(q, "товар", "вещ", "одежд", "налич", "каталог", "ассортимент"):
        return text_products()

    if has(q, "цен", "стоим", "сколько", "почем"):
        lines = [f"{p['name']} — {money(p['price'])}" for p in PRODUCTS.values()]
        return "💰 ЦЕНЫ:\n\n" + "\n".join(lines)

    if has(q, "цвет"):
        return "🎨 Нажмите «🎨 Цвета» в меню и выберите товар — покажу цвета именно для него."

    if has(q, "размер", "разм"):
        return text_sizes()

    if has(q, *CITY_STEMS):
        return f"🚚 Доставка в ваш город есть!\nСтоимость — {money(DELIVERY_PRICE)}."

    if has(q, "достав", "привез", "отправ"):
        return "🚚 Нажмите «🚚 Доставка» в меню — помогу оформить заказ с выбором города, товара, размера и цвета."

    if has(q, "купить", "заказ", "оформ"):
        return "🛒 Нажмите «🛒 Заказать» в меню — оформим заказ за пару нажатий."

    return (
        "🤔 Извините, я пока не знаю ответа.\n\n"
        "Попробуйте спросить:\n"
        "🛍 о товарах\n💰 о ценах\n📏 о размерах\n"
        "🎨 о цветах\n🚚 о доставке\n🛒 о заказе"
    )


# ==================================================
# 📨 ОБРАБОТКА ОБНОВЛЕНИЙ
# ==================================================

def on_message(m):
    chat_id = m["chat"]["id"]
    text = (m.get("text") or "").strip()

    if text.startswith("/start") or text.startswith("/menu"):
        send(chat_id, GREETING, MAIN_KB)
    elif text == "🛍 Товары":
        send(chat_id, text_products(), MAIN_KB)
    elif text == "📏 Размеры":
        send(chat_id, text_sizes(), MAIN_KB)
    elif text == "💰 Цены":
        send(chat_id, *v_price_menu())
    elif text == "🎨 Цвета":
        send(chat_id, *v_color_menu())
    elif text in ("🚚 Доставка", "🛒 Заказать"):
        send(chat_id, *v_cities())
    else:
        send(chat_id, free_text(text), MAIN_KB)


def on_callback(cq):
    tg("answerCallbackQuery", callback_query_id=cq["id"])
    msg = cq.get("message")
    if not msg:
        return
    try:
        result = route(cq.get("data", ""), cq.get("from", {}))
    except (ValueError, IndexError, KeyError):
        result = None
    if result is None:
        return
    text, markup = result
    tg(
        "editMessageText",
        chat_id=msg["chat"]["id"],
        message_id=msg["message_id"],
        text=text,
        reply_markup=markup,
    )


def handle_update(update):
    if "callback_query" in update:
        on_callback(update["callback_query"])
    elif "message" in update and update["message"].get("text"):
        on_message(update["message"])


# ==================================================
# 🌐 ТОЧКА ВХОДА ДЛЯ VERCEL
# ==================================================

class handler(BaseHTTPRequestHandler):
    def _reply(self, code, body=b"ok"):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, b"Bot is alive")

    def do_POST(self):
        if SECRET and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
            return self._reply(403, b"forbidden")
        try:
            length = int(self.headers.get("Content-Length", 0))
            update = json.loads(self.rfile.read(length) or b"{}")
            handle_update(update)
        except Exception as e:  # noqa: BLE001
            # всегда отвечаем 200, иначе Telegram будет повторять запрос
            print("handler error:", repr(e))
        self._reply(200)

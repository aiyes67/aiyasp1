import os
import re
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs
from contextlib import contextmanager
from datetime import datetime, date, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

# ============================================================
# CONFIG
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
try:
    OWNER_ID = int(os.environ.get("OWNER_ID") or "0")      # 0 = бот для всех
except ValueError:
    OWNER_ID = 0
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")      # необязательно

try:
    TZ = ZoneInfo("Asia/Almaty")
except Exception:
    TZ = timezone(timedelta(hours=5))  # UTC+5, если в системе нет базы часовых поясов

LANGS = {"ru": "Русский", "en": "English", "kk": "Қазақша"}

# ============================================================
# TRANSLATIONS
# ============================================================

T = {
    "ru": {
        "help": (
            "💰 Финансовый помощник\n\n"
            "Нажми ➖ Расход или ➕ Доход, потом напиши сумму и описание, например: кофе 1500.\n"
            "Слова «вчера» и «позавчера» тоже понимаю.\n\n"
            "📊 Неделя / Месяц / Год — отчёты. Прошлые периоды: /lastweek /lastmonth /lastyear\n"
            "🌐 Язык — сменить язык"
        ),
        "menu": {
            "add_expense": "➖ Расход", "add_income": "➕ Доход",
            "week": "📊 Неделя", "month": "📊 Месяц", "year": "📊 Год",
            "lang": "🌐 Язык",
        },
        "prompt_add_expense": "Напиши сумму и описание расхода, например: кофе 1500",
        "prompt_add_income": "Напиши сумму и описание дохода, например: зарплата 400000",
        "no_amount": "Не вижу сумму. Напиши, например: кофе 1500",
        "saved": "✅ Записано:",
        "cat_prompt": "Категория (по желанию):",
        "denied": "Доступ закрыт.",
        "error": "Произошла ошибка при обработке.",
        "lang_prompt": "Выбери язык:",
        "lang_set": "Язык: Русский",
        "income": "Доходы", "expense": "Расходы", "balance": "Баланс", "count": "Операций",
        "top": "Топ расходов по категориям:", "no_category": "Без категории",
        "cats": {"food": "Еда", "transport": "Транспорт", "home": "Жильё", "shopping": "Покупки",
                 "health": "Здоровье", "fun": "Досуг", "other": "Другое",
                 "salary": "Зарплата", "business": "Бизнес"},
        "titles": {
            ("week", False): "Текущая неделя", ("week", True): "Прошлая неделя",
            ("month", False): "Текущий месяц", ("month", True): "Прошлый месяц",
            ("year", False): "Текущий год", ("year", True): "Прошлый год",
        },
    },
    "en": {
        "help": (
            "💰 Finance assistant\n\n"
            "Tap ➖ Expense or ➕ Income, then type the amount and a description, e.g.: coffee 1500.\n"
            "I also understand \"yesterday\".\n\n"
            "📊 Week / Month / Year — reports. Past periods: /lastweek /lastmonth /lastyear\n"
            "🌐 Language — change language"
        ),
        "menu": {
            "add_expense": "➖ Expense", "add_income": "➕ Income",
            "week": "📊 Week", "month": "📊 Month", "year": "📊 Year",
            "lang": "🌐 Language",
        },
        "prompt_add_expense": "Type the amount and a description of the expense, e.g.: coffee 1500",
        "prompt_add_income": "Type the amount and a description of the income, e.g.: salary 400000",
        "no_amount": "I can't see an amount. Try: coffee 1500",
        "saved": "✅ Saved:",
        "cat_prompt": "Category (optional):",
        "denied": "Access denied.",
        "error": "Something went wrong.",
        "lang_prompt": "Choose a language:",
        "lang_set": "Language: English",
        "income": "Income", "expense": "Expenses", "balance": "Balance", "count": "Transactions",
        "top": "Top expense categories:", "no_category": "Uncategorized",
        "cats": {"food": "Food", "transport": "Transport", "home": "Home", "shopping": "Shopping",
                 "health": "Health", "fun": "Fun", "other": "Other",
                 "salary": "Salary", "business": "Business"},
        "titles": {
            ("week", False): "This week", ("week", True): "Last week",
            ("month", False): "This month", ("month", True): "Last month",
            ("year", False): "This year", ("year", True): "Last year",
        },
    },
    "kk": {
        "help": (
            "💰 Қаржылық көмекші\n\n"
            "➖ Шығыс немесе ➕ Кіріс батырмасын басып, соманы және сипаттаманы жаз, мысалы: кофе 1500.\n"
            "«Кеше» деген сөзді де түсінемін.\n\n"
            "📊 Апта / Ай / Жыл — есептер. Өткен кезеңдер: /lastweek /lastmonth /lastyear\n"
            "🌐 Тіл — тілді ауыстыру"
        ),
        "menu": {
            "add_expense": "➖ Шығыс", "add_income": "➕ Кіріс",
            "week": "📊 Апта", "month": "📊 Ай", "year": "📊 Жыл",
            "lang": "🌐 Тіл",
        },
        "prompt_add_expense": "Шығыстың сомасын және сипаттамасын жаз, мысалы: кофе 1500",
        "prompt_add_income": "Кірістің сомасын және сипаттамасын жаз, мысалы: жалақы 400000",
        "no_amount": "Соманы көрмедім. Мысалы: кофе 1500",
        "saved": "✅ Жазылды:",
        "cat_prompt": "Санат (қалауыңша):",
        "denied": "Қолжетімділік жабық.",
        "error": "Өңдеу кезінде қате шықты.",
        "lang_prompt": "Тілді таңда:",
        "lang_set": "Тіл: Қазақша",
        "income": "Кіріс", "expense": "Шығыс", "balance": "Баланс", "count": "Операциялар",
        "top": "Санаттар бойынша шығыстар үздігі:", "no_category": "Санатсыз",
        "cats": {"food": "Тамақ", "transport": "Көлік", "home": "Тұрғын үй", "shopping": "Сатып алу",
                 "health": "Денсаулық", "fun": "Демалыс", "other": "Басқа",
                 "salary": "Жалақы", "business": "Бизнес"},
        "titles": {
            ("week", False): "Осы апта", ("week", True): "Өткен апта",
            ("month", False): "Осы ай", ("month", True): "Өткен ай",
            ("year", False): "Осы жыл", ("year", True): "Өткен жыл",
        },
    },
}

MENU_ORDER = [["add_expense", "add_income"], ["week", "month", "year"], ["lang"]]
LABEL_TO_ACTION = {label: action for lang in T.values() for action, label in lang["menu"].items()}

COMMANDS = {
    "/week": "week", "/month": "month", "/year": "year",
    "/lastweek": "lastweek", "/lastmonth": "lastmonth", "/lastyear": "lastyear",
    "/expense": "add_expense", "/income": "add_income", "/lang": "lang",
}

CATEGORY_KEYS = {
    "add_expense": ["food", "transport", "home", "shopping", "health", "fun", "other"],
    "add_income": ["salary", "business", "other"],
}


def menu_markup(lang):
    return {
        "keyboard": [[{"text": T[lang]["menu"][a]} for a in row] for row in MENU_ORDER],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def cat_label(lang, key):
    if not key:
        return T[lang]["no_category"]
    return T[lang]["cats"].get(key, key)

# ============================================================
# TELEGRAM
# ============================================================

def tg(method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        return urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as e:
        print(f"Telegram {method} failed: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        raise


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    tg("sendMessage", payload)

# ============================================================
# DB
# ============================================================

@contextmanager
def db():
    # В serverless соединение обязательно закрываем сами
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def get_user(user_id):
    """Язык и текущий режим ввода одним запросом. Режим живёт 30 минут."""
    try:
        with db() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT lang FROM user_settings WHERE user_id = %s) AS lang,
                  (SELECT state FROM user_state
                    WHERE user_id = %s AND updated_at > now() - interval '30 minutes') AS state;
                """,
                (user_id, user_id),
            )
            row = cur.fetchone()
        return row["lang"], row["state"]
    except Exception as e:
        print("get_user error:", repr(e))
        return None, None


def set_lang(user_id, lang):
    with db() as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, lang) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang;
            """,
            (user_id, lang),
        )


def set_state(user_id, state):
    with db() as cur:
        if state is None:
            cur.execute("DELETE FROM user_state WHERE user_id = %s", (user_id,))
        else:
            cur.execute(
                """
                INSERT INTO user_state (user_id, state, updated_at) VALUES (%s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET state = EXCLUDED.state, updated_at = now();
                """,
                (user_id, state),
            )


def add_transaction(user_id, tx_type, amount, description, tx_date):
    with db() as cur:
        cur.execute(
            """
            INSERT INTO transactions
            (user_id, type, amount, currency, description, transaction_date)
            VALUES (%s, %s, %s, 'KZT', %s, %s)
            RETURNING id;
            """,
            (user_id, tx_type, amount, description, tx_date),
        )
        return cur.fetchone()["id"]


def set_category(user_id, tx_id, category):
    with db() as cur:
        cur.execute(
            "UPDATE transactions SET category = %s WHERE id = %s AND user_id = %s",
            (category, tx_id, user_id),
        )


def get_report(user_id, start, end):
    """Все суммы считаются в SQL, без лимитов на количество строк."""
    with db() as cur:
        cur.execute(
            """
            SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = %s AND transaction_date BETWEEN %s AND %s
            GROUP BY type;
            """,
            (user_id, start, end),
        )
        totals = {r["type"]: r for r in cur.fetchall()}

        cur.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE user_id = %s AND type = 'expense'
              AND transaction_date BETWEEN %s AND %s
            GROUP BY category ORDER BY 2 DESC LIMIT 5;
            """,
            (user_id, start, end),
        )
        top = cur.fetchall()

    income = float(totals.get("income", {}).get("total", 0))
    expense = float(totals.get("expense", {}).get("total", 0))
    count = sum(r["cnt"] for r in totals.values())
    return {"income": income, "expense": expense, "balance": income - expense,
            "count": count, "top": top}

# ============================================================
# PARSING (без ИИ: сумма = последнее число в сообщении)
# ============================================================

AMOUNT_RE = re.compile(
    r"(\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(миллион\w*|million|млн|тыс\w*|мың|к|k|m)?(?=\s|$|[^\w])",
    re.IGNORECASE,
)

DATE_WORDS = [
    (re.compile(r"\b(?:позавчера|day before yesterday)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(?:вчера|yesterday|кеше)\b", re.IGNORECASE), 1),
    (re.compile(r"\b(?:сегодня|today|бүгін)\b", re.IGNORECASE), 0),
]


def parse_entry(text):
    matches = list(AMOUNT_RE.finditer(text))
    if not matches:
        return None
    m = matches[-1]

    try:
        amount = float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    suffix = (m.group(2) or "").lower()
    if suffix:
        big = suffix.startswith(("миллион", "million", "млн", "m"))
        amount *= 1_000_000 if big else 1000
    if amount <= 0:
        return None

    rest = text[:m.start()] + " " + text[m.end():]
    tx_date = datetime.now(TZ).date()
    for pattern, delta in DATE_WORDS:
        if pattern.search(rest):
            rest = pattern.sub(" ", rest)
            tx_date = tx_date - timedelta(days=delta)
            break

    description = " ".join(rest.split())
    return amount, description, tx_date.isoformat()

# ============================================================
# HELPERS
# ============================================================

def money(val):
    val = float(val)
    text = f"{int(val):,}" if val.is_integer() else f"{val:,.2f}"
    return text.replace(",", " ") + " ₸"


def period_range(period, previous=False):
    today = datetime.now(TZ).date()

    if period == "week":
        start = today - timedelta(days=today.weekday())  # понедельник
        if previous:
            start -= timedelta(days=7)
            return start, start + timedelta(days=6)
        return start, today

    if period == "month":
        start = today.replace(day=1)
        if previous:
            end = start - timedelta(days=1)
            return end.replace(day=1), end
        return start, today

    if previous:
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31)
    return date(today.year, 1, 1), today


def format_report(lang, period, previous, start, end, rep):
    t = T[lang]
    lines = [
        f"📊 {t['titles'][(period, previous)]} ({start:%d.%m.%Y} — {end:%d.%m.%Y})",
        "",
        f"➕ {t['income']}: {money(rep['income'])}",
        f"➖ {t['expense']}: {money(rep['expense'])}",
        f"💼 {t['balance']}: {money(rep['balance'])}",
        f"🧾 {t['count']}: {rep['count']}",
    ]
    if rep["top"]:
        lines += ["", t["top"]]
        lines += [f"• {cat_label(lang, r['category'])}: {money(r['total'])}" for r in rep["top"]]
    return "\n".join(lines)


def send_report(chat_id, user_id, lang, period, previous=False):
    start, end = period_range(period, previous)
    rep = get_report(user_id, start, end)
    send_message(chat_id, format_report(lang, period, previous, start, end, rep))

# ============================================================
# ACTIONS
# ============================================================

def is_allowed(user_id):
    return OWNER_ID == 0 or user_id == OWNER_ID


def run_action(action, chat_id, user_id, lang):
    t = T[lang]

    if action in ("add_expense", "add_income"):
        set_state(user_id, action)
        send_message(chat_id, t[f"prompt_{action}"])

    elif action == "lang":
        set_state(user_id, None)
        keyboard = {"inline_keyboard": [[
            {"text": name, "callback_data": f"lang:{code}"} for code, name in LANGS.items()
        ]]}
        send_message(chat_id, t["lang_prompt"], reply_markup=keyboard)

    elif action in ("week", "month", "year"):
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, action)

    elif action in ("lastweek", "lastmonth", "lastyear"):
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, action[4:], previous=True)


def category_keyboard(state, tx_id, lang):
    buttons = [
        {"text": T[lang]["cats"][k], "callback_data": f"cat:{tx_id}:{k}"}
        for k in CATEGORY_KEYS[state]
    ]
    return {"inline_keyboard": [buttons[i:i + 3] for i in range(0, len(buttons), 3)]}

# ============================================================
# UPDATE PROCESSOR
# ============================================================

def process_callback(cb):
    user_id = cb["from"]["id"]
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    data = cb.get("data", "")
    stored_lang, _ = get_user(user_id)
    lang = stored_lang if stored_lang in LANGS else "ru"

    if not is_allowed(user_id):
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        return

    if data.startswith("lang:") and data[5:] in LANGS:
        lang = data[5:]
        set_lang(user_id, lang)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                      "reply_markup": {"inline_keyboard": []}})
        send_message(chat_id, T[lang]["lang_set"] + "\n\n" + T[lang]["help"], reply_markup=menu_markup(lang))

    elif data.startswith("cat:"):
        _, tx_id, key = data.split(":", 2)
        set_category(user_id, int(tx_id), key)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "✅ " + cat_label(lang, key)})
        tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                      "reply_markup": {"inline_keyboard": []}})
    else:
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})


def process_message(message):
    if not message.get("text"):
        return

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message["text"].strip()
    if not text:
        return

    stored_lang, state = get_user(user_id)
    if stored_lang in LANGS:
        lang = stored_lang
    else:
        lang = {"kk": "kk", "en": "en"}.get((message["from"].get("language_code") or "")[:2], "ru")
    t = T[lang]

    if not is_allowed(user_id):
        send_message(chat_id, t["denied"])
        return

    first = text.split()[0].split("@")[0].lower()

    # 1. Старт и справка
    if first in ("/start", "/help"):
        set_state(user_id, None)
        send_message(chat_id, t["help"], reply_markup=menu_markup(lang))
        return

    # 2. Кнопки панели и команды
    action = LABEL_TO_ACTION.get(text) or COMMANDS.get(first)
    if action:
        run_action(action, chat_id, user_id, lang)
        return

    # 3. Ввод после нажатия кнопки
    if state in ("add_expense", "add_income"):
        entry = parse_entry(text)
        if not entry:
            send_message(chat_id, t["no_amount"])
            return
        amount, description, tx_date = entry
        tx_type = "expense" if state == "add_expense" else "income"
        tx_id = add_transaction(user_id, tx_type, amount, description, tx_date)
        set_state(user_id, None)
        sign = "-" if tx_type == "expense" else "+"
        lines = [t["saved"], f"{sign}{money(amount)}"]
        if description:
            lines.append(description)
        lines += ["", t["cat_prompt"]]
        send_message(chat_id, "\n".join(lines), reply_markup=category_keyboard(state, tx_id, lang))
        return

    # 4. Обычное сообщение вне режима — молчим
    return


def process_update(update):
    if update.get("callback_query"):
        process_callback(update["callback_query"])
    elif update.get("message"):
        process_message(update["message"])

# ============================================================
# VERCEL HANDLER
# ============================================================

def diagnostics():
    """Подробная проверка: таблицы, токен, вебхук. Только по ?key=WEBHOOK_SECRET."""
    lines = []
    try:
        with db() as cur:
            cur.execute(
                """
                SELECT to_regclass('public.transactions') IS NOT NULL AS transactions,
                       to_regclass('public.user_settings') IS NOT NULL AS user_settings,
                       to_regclass('public.user_state') IS NOT NULL AS user_state;
                """
            )
            row = cur.fetchone()
        for name, ok in row.items():
            lines.append(f"Table {name}: {'OK' if ok else 'MISSING (run schema.sql)'}")
    except Exception as e:
        lines.append("Tables check error: " + type(e).__name__)

    for method in ("getMe", "getWebhookInfo"):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
            data = json.loads(urllib.request.urlopen(url, timeout=10).read())["result"]
            if method == "getMe":
                lines.append("Telegram token: OK, bot @" + str(data.get("username")))
            else:
                lines.append("Webhook url: " + (data.get("url") or "NOT SET"))
                lines.append("Webhook pending updates: " + str(data.get("pending_update_count")))
                lines.append("Webhook last error: " + str(data.get("last_error_message") or "none"))
        except urllib.error.HTTPError as e:
            lines.append(f"Telegram {method}: HTTP {e.code} (check TELEGRAM_TOKEN)")
        except Exception as e:
            lines.append(f"Telegram {method} error: " + type(e).__name__)
    return lines


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if WEBHOOK_SECRET and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            self.send_response(403)
            self.end_headers()
            return

        update = {}
        try:
            length = int(self.headers.get("content-length", 0))
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            process_update(update)
        except Exception as e:
            print("Error:", repr(e))
            try:
                msg = update.get("message") or update["callback_query"]["message"]
                user = update["message"]["from"] if update.get("message") else update["callback_query"]["from"]
                lang, _ = get_user(user["id"])
                send_message(msg["chat"]["id"], T[lang if lang in LANGS else "ru"]["error"])
            except Exception:
                pass

        # Всегда 200, иначе Telegram будет бесконечно ретраить апдейт
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        lines = ["Bot is alive!"]
        missing = [n for n in ("TELEGRAM_TOKEN", "DATABASE_URL") if not os.environ.get(n)]
        if missing:
            lines.append("Missing env vars: " + ", ".join(missing))
        else:
            try:
                with db() as cur:
                    cur.execute("SELECT count(*) AS n FROM transactions")
                    cur.fetchone()
                lines.append("Database: OK")
            except Exception as e:
                lines.append("Database error: " + type(e).__name__)
        key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
        if not missing and (not WEBHOOK_SECRET or key == WEBHOOK_SECRET):
            lines += diagnostics()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("\n".join(lines).encode("utf-8"))

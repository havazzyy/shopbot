import os, sqlite3, datetime, asyncio, logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
UPI = os.getenv("UPI_ID", "")
QR = os.getenv("QR_URL", "")
DB = "shop.db"

def q(sql, args=(), one=False):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    cur = c.execute(sql, args); c.commit()
    r = cur.fetchall(); last = cur.lastrowid; c.close()
    if one: return r[0] if r else None
    return last if sql.strip().upper().startswith("INSERT") else r

def init():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,title TEXT,desc TEXT,price INTEGER,stars INTEGER,image TEXT,link TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS bundles(id INTEGER PRIMARY KEY,title TEXT,desc TEXT,price INTEGER,stars INTEGER,image TEXT,links TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,qty INTEGER,amount INTEGER,method TEXT,status TEXT DEFAULT 'pending',shot TEXT,created TEXT, item_type TEXT DEFAULT 'product');
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,referred_by INTEGER,ref_count INTEGER DEFAULT 0);
    """)
    c.commit(); c.close()

class Add(StatesGroup):
    title = State(); price = State(); stars = State(); desc = State(); image = State(); link = State()

class AddBundle(StatesGroup):
    title = State(); price = State(); stars = State(); desc = State(); image = State(); links = State()

class SupportState(StatesGroup):
    message = State()

class EditPriceState(StatesGroup):
    new_price = State()

router = Router()
adm = lambda uid: uid in ADMIN_IDS

@router.message(Command("start"))
async def start(m: Message):
    args = m.text.split()
    user_id = m.from_user.id
    
    existing = q("SELECT * FROM users WHERE id=?", (user_id,), True)
    
    if not existing:
        ref_by = None
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                potential_ref = int(args[1].replace("ref_", ""))
                if potential_ref != user_id:
                    ref_by = potential_ref
            except:
                pass
        
        q("INSERT INTO users(id, name, referred_by, ref_count) VALUES(?,?,?,0)", (user_id, m.from_user.first_name, ref_by))
        
        if ref_by:
            q("UPDATE users SET ref_count = ref_count + 1 WHERE id=?", (ref_by,))
            try:
                await m.bot.send_message(ref_by, f"🎉 <b>New Referral!</b> Someone joined using your invite link.")
            except:
                pass
    
    welcome_text = (
        "✨ <b>WELCOME TO</b>\n"
        "<b>BTW — PREMIUM SUBSCRIPTION STORE</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ <b>EXPLORE THE STORE</b>\n"
        "Browse our available subscriptions and choose the plan that suits you best.\n\n"
        "▸ <b>DISCOUNTS</b>\n"
        "Apply discount coupons or referral discounts to unlock the best available prices.\n\n"
        "▸ <b>HELP & SUPPORT</b>\n"
        "Facing an issue or need assistance? Our support section is here to help.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Thank you for choosing <b>BTW</b>.\n"
        "Enjoy a premium experience. ✦"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Explore the Store", callback_data="shop")
    kb.button(text="🔥 Combo Bundles", callback_data="bundles")
    kb.button(text="🎁 Discounts / Referral", callback_data="referral")
    kb.button(text="📦 My Orders", callback_data="orders")
    kb.button(text="🎧 Help & Support", callback_data="support")
    if adm(user_id): kb.button(text="⚙️ Admin Panel", callback_data="admin")
    kb.adjust(1, 2, 2, 1)
    await m.answer(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "home")
async def home(c: CallbackQuery):
    welcome_text = (
        "✨ <b>WELCOME TO</b>\n"
        "<b>BTW — PREMIUM SUBSCRIPTION STORE</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ <b>EXPLORE THE STORE</b>\n"
        "Browse our available subscriptions and choose the plan that suits you best.\n\n"
        "▸ <b>DISCOUNTS</b>\n"
        "Apply discount coupons or referral discounts to unlock the best available prices.\n\n"
        "▸ <b>HELP & SUPPORT</b>\n"
        "Facing an issue or need assistance? Our support section is here to help.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Thank you for choosing <b>BTW</b>.\n"
        "Enjoy a premium experience. ✦"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Explore the Store", callback_data="shop")
    kb.button(text="🔥 Combo Bundles", callback_data="bundles")
    kb.button(text="🎁 Discounts / Referral", callback_data="referral")
    kb.button(text="📦 My Orders", callback_data="orders")
    kb.button(text="🎧 Help & Support", callback_data="support")
    if adm(c.from_user.id): kb.button(text="⚙️ Admin Panel", callback_data="admin")
    kb.adjust(1, 2, 2, 1)
    await c.message.edit_text(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "support")
async def support_menu(c: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Back to Menu", callback_data="home")
    kb.adjust(1)
    await state.set_state(SupportState.message)
    await c.message.edit_text(
        "🎧 <b>Help & Support Section</b>\n\n"
        "Please type your issue, question, or payment query below as a single message, and our support team will reply to you shortly.",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )

@router.message(SupportState.message)
async def send_support_to_admin(m: Message, state: FSMContext):
    user_id = m.from_user.id
    user_name = m.from_user.full_name
    msg_text = m.text
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Reply to User", callback_data=f"reply:{user_id}")
    kb.adjust(1)
    
    for a in ADMIN_IDS:
        try:
            await m.bot.send_message(
                a,
                f"🚨 <b>New Support Message!</b>\n\n"
                f"👤 <b>From:</b> {user_name} (ID: <code>{user_id}</code>)\n"
                f"💬 <b>Message:</b> {msg_text}",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
        except:
            pass
            
    await state.clear()
    await m.answer("✅ Your message has been sent to our support team! We will get back to you soon.")

@router.callback_query(F.data.startswith("reply:"))
async def admin_reply_prompt(c: CallbackQuery, state: FSMContext):
    if not adm(c.from_user.id): return
    target_user_id = int(c.data.split(":")[1])
    await state.update_data(target_user=target_user_id)
    await state.set_state("admin_reply_wait")
    await c.message.answer(f"✍️ Type your reply message to user ID <code>{target_user_id}</code>:", parse_mode="HTML")

@router.message(StateFilter("admin_reply_wait"))
async def admin_send_reply(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    data = await state.get_data()
    target_user_id = data.get("target_user")
    
    try:
        await m.bot.send_message(
            target_user_id,
            f"👑 <b>Admin Support Reply:</b>\n\n{m.text}",
            parse_mode="HTML"
        )
        await m.answer("✅ Reply sent successfully to the user!")
    except Exception as e:
        await m.answer(f"❌ Failed to send reply: {e}")
    await state.clear()

@router.callback_query(F.data == "referral")
async def referral_menu(c: CallbackQuery):
    user_id = c.from_user.id
    

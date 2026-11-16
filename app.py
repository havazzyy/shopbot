import os, sqlite3, datetime, asyncio, logging
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
    user_data = q("SELECT * FROM users WHERE id=?", (user_id,), True)
    ref_count = user_data["ref_count"] if user_data else 0
    bot_info = await c.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    text = (
        "🎁 <b>Discounts & Referral Program</b>\n\n"
        "Want to get access completely <b>FREE</b>? Share your personal invite link with your friends!\n\n"
        f"👥 <b>Your Referrals:</b> {ref_count} / 3 Friends\n\n"
        f"🔗 <b>Your Invite Link:</b>\n<code>{ref_link}</code>\n\n"
        "<i>Note: Once you successfully invite 3 friends, contact admin with a screenshot to claim your reward!</i>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Back to Menu", callback_data="home")
    kb.adjust(1)
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True)

@router.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    rows = q("SELECT * FROM products WHERE active=1")
    if not rows: return await c.message.edit_text("No groups available at the moment.")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"{r['title']} — ₹{r['price']} | ⭐ {r['stars']}", callback_data=f"p:{r['id']}")
    kb.button(text="🔥 View Combo Bundles", callback_data="bundles")
    kb.button(text="⬅️ Back to Menu", callback_data="home")
    kb.adjust(1)
    await c.message.edit_text("<b>Select an available subscription:</b>", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "bundles")
async def bundles_menu(c: CallbackQuery):
    rows = q("SELECT * FROM bundles WHERE active=1")
    if not rows: return await c.message.edit_text("No combo bundles available right now. Check back soon!")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"🔥 {r['title']} — ₹{r['price']} (Bundle)", callback_data=f"b:{r['id']}")
    kb.button(text="🛍 Individual Subscriptions", callback_data="shop")
    kb.button(text="⬅️ Back to Menu", callback_data="home")
    kb.adjust(1)
    await c.message.edit_text("🔥 <b>Exclusive Combo Bundles (Save More!):</b>\nSelect a bundle pack below:", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("p:"))
async def product(c: CallbackQuery):
    r = q("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),), True)
    if not r: return await c.answer("Subscription not found.", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"💳 Pay UPI ₹{r['price']}", callback_data=f"qty:p:{r['id']}")
    kb.button(text=f"⭐ Pay {r['stars']} Stars (Instant)", callback_data=f"star:p:{r['id']}")
    kb.button(text="⬅️ Back", callback_data="shop")
    kb.adjust(1)
    
    caption = f"<b>{r['title']}</b>\n\n{r['desc'] or ''}\n\n💰 Price: ₹{r['price']}  |  ⭐ Stars: {r['stars']}\n📦 Access: <b>Unlimited Access</b>"
    
    try: await c.message.delete()
    except: pass
        
    if r["image"]:
        await c.bot.send_photo(c.from_user.id, r["image"], caption=caption, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await c.bot.send_message(c.from_user.id, caption, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("b:"))
async def bundle_detail(c: CallbackQuery):
    r = q("SELECT * FROM bundles WHERE id=?", (int(c.data.split(":")[1]),), True)
    if not r: return await c.answer("Bundle not found.", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"💳 Pay UPI ₹{r['price']} (Bundle)", callback_data=f"qty:b:{r['id']}")
    kb.button(text=f"⭐ Pay {r['stars']} Stars (Instant)", callback_data=f"star:b:{r['id']}")
    kb.button(text="⬅️ Back to Bundles", callback_data="bundles")
    kb.adjust(1)
    
    caption = f"🔥 <b>COMBO PACK: {r['title']}</b>\n\n{r['desc'] or ''}\n\n💰 Special Price: ₹{r['price']}  |  ⭐ {r['stars']}\n📦 Includes: <b>Multiple Premium Links Access</b>"
    
    try: await c.message.delete()
    except: pass
        
    if r["image"]:
        await c.bot.send_photo(c.from_user.id, r["image"], caption=caption, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await c.bot.send_message(c.from_user.id, caption, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("qty:"))
async def qty(c: CallbackQuery):
    parts = c.data.split(":")
    item_type = parts[1]
    item_id = int(parts[2])
    
    r = q(f"SELECT * FROM bundles WHERE id=?", (item_id,), True) if item_type == "b" else q(f"SELECT * FROM products WHERE id=?", (item_id,), True)
    
    oid = q("INSERT INTO orders(user_id,product_id,qty,amount,method,created,item_type) VALUES(?,?,?,?,?,?,?)",
            (c.from_user.id, item_id, 1, r["price"], "upi", str(datetime.datetime.now()), item_type))
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ I've Paid — Send Screenshot", callback_data=f"shot:{oid}")
    kb.button(text="❌ Cancel Order", callback_data=f"no:{oid}")
    kb.adjust(1)
    await c.message.answer_photo(QR, caption=f"<b>Order #{oid}</b>\n\nPlease transfer <b>₹{r['price']}</b> to the UPI ID below:\n<code>{UPI}</code>\n\nAfter payment, click the button below and send your payment screenshot.", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("shot:"))
async def shot(c: CallbackQuery, state: FSMContext):
    await state.update_data(oid=int(c.data.split(":")[1]))
    await state.set_state("wait_shot")
    await c.message.answer("Please send your payment screenshot now 👇")

@router.message(StateFilter("wait_shot"), F.photo)
async def got_shot(m: Message, state: FSMContext):
    oid = (await state.get_data())["oid"]
    q("UPDATE orders SET shot=? WHERE id=?", (m.photo[-1].file_id, oid))
    o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"ok:{oid}")
    kb.button(text="❌ Reject", callback_data=f"rno:{oid}")
    kb.adjust(2)
    await m.answer("✅ Screenshot received. Verifying payment...")
    for a in ADMIN_IDS:
        try: await m.bot.send_photo(a, m.photo[-1].file_id, caption=f"🔔 <b>New Payment Verification</b>\nOrder #{oid}\nType: {o['item_type'].upper()}\nUser ID: {m.from_user.id}\nAmount: ₹{o['amount']}", parse_mode="HTML", reply_markup=kb.as_markup())
        except: pass
    await state.clear()

@router.callback_query(F.data.startswith("star:"))
async def stars(c: CallbackQuery):
    parts = c.data.split(":")
    item_type = parts[1]
    item_id = int(parts[2])
    
    r = q(f"SELECT * FROM bundles WHERE id=?", (item_id,), True) if item_type == "b" else q(f"SELECT * FROM products WHERE id=?", (item_id,), True)
    
    await c.bot.send_invoice(c.from_user.id, title=r["title"], description=(r["desc"] or "Access")[:250],
        payload=f"{item_type}:{r['id']}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label=r["title"], amount=r["stars"])])
    await c.answer()

@router.pre_checkout_query()
async def preco(p: PreCheckoutQuery):
    await p.answer(ok=True)

@router.message(F.successful_payment)
async def paid(m: Message):
    payload_parts = m.successful_payment.invoice_payload.split(":")
    item_type = payload_parts[0]
    item_id = int(payload_parts[1])
    
    oid = q("INSERT INTO orders(user_id,product_id,qty,amount,method,status,created,item_type) VALUES(?,?,?,?,?,?,?,?)",
            (m.from_user.id, item_id, 1, m.successful_payment.total_amount, "stars", "paid", str(datetime.datetime.now()), item_type))
    await deliver(m.bot, oid, m.chat.id)

async def deliver(bot, oid, chat_id):
    o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    if o["status"] == "delivered": return
    
    if o["item_type"] == "b":
        item = q("SELECT * FROM bundles WHERE id=?", (o["product_id"],), True)
    else:
        item = q("SELECT * FROM products WHERE id=?", (o["product_id"],), True)
        
    if not item:
        return await bot.send_message(chat_id, f"⚠️ Order #{oid} error. Please contact admin.")
    
    link_to_send = item["links"] if o["item_type"] == "b" else item["link"]

    try:
        await bot.send_message(chat_id, f"🔗 <b>Your Exclusive Access Links:</b>\n\n{link_to_send}", parse_mode="HTML")
    except Exception as e: 
        await bot.send_message(chat_id, f"Error: {e}")
        
    q("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
    await bot.send_message(chat_id, f"✅ Order #{oid} delivered successfully. Enjoy!")

    try:
        alert_text = f"🎉 Customer #{oid} successfully purchased <b>{item['title']}</b> ✅!\n\n🛍 Explore the store below."
        kb_channels = InlineKeyboardBuilder()
        kb_channels.button(text="✨ Explore Store", callback_data="shop")
        kb_channels.button(text="🔥 View Bundles", callback_data="bundles")
        kb_channels.adjust(1)

        users = q("SELECT id FROM users")
        for u in users:
            try:
                if item.get("image"):
                    await bot.send_photo(u["id"], item["image"], caption=alert_text, parse_mode="HTML", reply_markup=kb_channels.as_markup())
                else:
                    await bot.send_message(u["id"], alert_text, parse_mode="HTML", reply_markup=kb_channels.as_markup())
            except:
                pass
    except Exception as e:
        print("Broadcast error:", e)

@router.callback_query(F.data.startswith("ok:"))
async def okk(c: CallbackQuery):
    if not adm(c.from_user.id): return
    oid = int(c.data.split(":")[1]); o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    q("UPDATE orders SET status='paid' WHERE id=?", (oid,))
    await deliver(c.bot, oid, o["user_id"])
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n✅ APPROVED & LINK SENT")

@router.callback_query(F.data.startswith("rno:"))
async def rno(c: CallbackQuery):
    if not adm(c.from_user.id): return
    oid = int(c.data.split(":")[1])
    o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    q("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
    try: await c.bot.send_message(o["user_id"], f"❌ Order #{oid} has been rejected.")
    except: pass
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n❌ REJECTED")

@router.callback_query(F.data.startswith("no:"))
async def cancel(c: CallbackQuery):
    q("UPDATE orders SET status='cancelled' WHERE id=?", (int(c.data.split(":")[1]),))
    await c.message.edit_caption(caption="Order cancelled.")

@router.callback_query(F.data == "orders")
async def myorders(c: CallbackQuery):
    rows = q("SELECT o.* FROM orders o WHERE o.user_id=? ORDER BY o.id DESC LIMIT 10", (c.from_user.id,))
    if not rows: return await c.answer("No orders found.", show_alert=True)
    t = "\n".join(f"#{r['id']} — Amount: ₹{r['amount']} — Status: <b>{r['status']}</b>" for r in rows)
    await c.message.answer(f"<b>Your Recent Orders:</b>\n\n{t}", parse_mode="HTML")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if not adm(c.from_user.id): return
    
    total_sales = q("SELECT COUNT(*) c FROM orders WHERE status IN ('paid','delivered')", (), True)["c"]
    total_revenue = q("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status IN ('paid','delivered')", (), True)["s"]
    total_users = q("SELECT COUNT(*) c FROM users", (), True)["c"]
    
    today = str(datetime.datetime.now().date())
    today_rev = q("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status IN ('paid','delivered') AND created LIKE ?", (today + "%",), True)["s"]

    text = (
        "📊 <b>Automated Sales & Revenue Analytics</b>\n"
        "──────────────────────────\n"
        f"👥 <b>Total Store Users:</b> {total_users}\n"
        f"📦 <b>Total Successful Sales:</b> {total_sales}\n"
        f"💰 <b>Total Revenue:</b> ₹{total_revenue}\n"
        f"📅 <b>Today's Revenue:</b> ₹{today_rev}\n"
        "──────────────────────────\n\n"
        "<b>Admin Commands:</b>\n"
        "/addproduct — Add single subscription\n"
        "/addbundle — Add combo bundle pack\n"
        "/list — View inventory & Manage items\n"
        "/broadcast — Send broadcast message"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Refresh Analytics", callback_data="admin")
    kb.button(text="⬅️ Back to Menu", callback_data="home")
    kb.adjust(1)
    
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.message(Command("addproduct"))
async def addp(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    await state.set_state(Add.title); await m.answer("1/6 Enter Subscription Title:")

@router.message(Add.title)
async def a1(m: Message, state: FSMContext):
    await state.update_data(title=m.text); await state.set_state(Add.price); await m.answer("2/6 Enter Price in INR:")

@router.message(Add.price)
async def a2(m: Message, state: FSMContext):
    await state.update_data(price=int(m.text)); await state.set_state(Add.stars); await m.answer("3/6 Enter Price in Stars:")

@router.message(Add.stars)
async def a3(m: Message, state: FSMContext):
    await state.update_data(stars=int(m.text)); await state.set_state(Add.desc); await m.answer("4/6 Enter Description:")

@router.message(Add.desc)
async def a4(m: Message, state: FSMContext):
    await state.update_data(desc=m.text); await state.set_state(Add.image)
    await m.answer("5/6 Send Demo Photo/Screenshot:", parse_mode="HTML")

@router.message(Add.image, F.photo)
async def a_image(m: Message, state: FSMContext):
    await state.update_data(image=m.photo[-1].file_id)
    await state.set_state(Add.link)
    await m.answer("6/6 Send permanent Invite Link as text:", parse_mode="HTML")

@router.message(Add.link)
async def a6(m: Message, state: FSMContext):
    d = await state.get_data()
    q("INSERT INTO products(title,desc,price,stars,image,link) VALUES(?,?,?,?,?,?)", 
      (d["title"], d["desc"], d["price"], d["stars"], d["image"], m.text))
    await state.clear()
    await m.answer("✅ Subscription added successfully!", parse_mode="HTML")

@router.message(Command("addbundle"))
async def add_bundle(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    await state.set_state(AddBundle.title); await m.answer("🔥 1/6 Enter Combo Bundle Title:")

@router.message(AddBundle.title)
async def b1(m: Message, state: FSMContext):
    await state.update_data(title=m.text); await state.set_state(AddBundle.price); await m.answer("🔥 2/6 Enter Bundle Price in INR:")

@router.message(AddBundle.price)
async def b2(m: Message, state: FSMContext):
    await state.update_data(price=int(m.text)); await state.set_state(AddBundle.stars); await m.answer("🔥 3/6 Enter Bundle Price in Stars:")

@router.message(AddBundle.stars)
async def b3(m: Message, state: FSMContext):
    await state.update_data(stars=int(m.text)); await state.set_state(AddBundle.desc); await m.answer("🔥 4/6 Enter Bundle Description:")

@router.message(AddBundle.desc)
async def b4(m: Message, state: FSMContext):
    await state.update_data(desc=m.text); await state.set_state(AddBundle.image)
    await m.answer("🔥 5/6 Send Bundle Demo Photo:", parse_mode="HTML")

@router.message(AddBundle.image, F.photo)
async def b_image(m: Message, state: FSMContext):
    await state.update_data(image=m.photo[-1].file_id)
    await state.set_state(AddBundle.links)
    await m.answer("🔥 6/6 Send all group links together as text:", parse_mode="HTML")

@router.message(AddBundle.links)
async def b6(m: Message, state: FSMContext):
    d = await state.get_data()
    q("INSERT INTO bundles(title,desc,price,stars,image,links) VALUES(?,?,?,?,?,?)", 
      (d["title"], d["desc"], d["price"], d["stars"], d["image"], m.text))
    await state.clear()
    await m.answer("✅ Combo Bundle Pack created successfully!", parse_mode="HTML")

@router.message(Command("list"))
async def lst(m: Message):
    if not adm(m.from_user.id): return
    rows = q("SELECT * FROM products")
    bundles = q("SELECT * FROM bundles")
    
    await m.answer("📋 <b>Store Inventory & Management:</b>", parse_mode="HTML")
    
    if rows:
        await m.answer("<b>[Subscriptions]</b>", parse_mode="HTML")
        for r in rows:
            kb = InlineKeyboardBuilder()
            kb.button(text="✏️ Edit Price", callback_data=f"edit_p:{r['id']}")
            kb.button(text="🗑 Delete", callback_data=f"del_p:{r['id']}")
            kb.adjust(2)
            await m.answer(f"ID: {r['id']} | <b>{r['title']}</b> — ₹{r['price']} | ⭐ {r['stars']}", parse_mode="HTML", reply_markup=kb.as_markup())
            
    if bundles:
        await m.answer("<b>[Combo Bundles]</b>", parse_mode="HTML")
        for b in bundles:
            kb = InlineKeyboardBuilder()
            kb.button(text="✏️ Edit Price", callback_data=f"edit_b:{b['id']}")
            kb.button(text="🗑 Delete", callback_data=f"del_b:{b['id']}")
            kb.adjust(2)
            await m.answer(f"Bundle ID: {b['id']} | <b>{b['title']}</b> — ₹{b['price']} | ⭐ {b['stars']}", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("del_p:"))
async def delete_product(c: CallbackQuery):
    if not adm(c.from_user.id): return
    pid = int(c.data.split(":")[1])
    q("DELETE FROM products WHERE id=?", (pid,))
    await c.answer("✅ Product deleted successfully!", show_alert=True)
    await c.message.edit_text(c.message.text + "\n\n❌ <b>[DELETED]</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("del_b:"))
async def delete_bundle(c: CallbackQuery):
    if not adm(c.from_user.id): return
    bid = int(c.data.split(":")[1])
    q("DELETE FROM bundles WHERE id=?", (bid,))
    await c.answer("✅ Bundle deleted successfully!", show_alert=True)
    await c.message.edit_text(c.message.text + "\n\n❌ <b>[DELETED]</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_p:"))
async def edit_product_price_prompt(c: CallbackQuery, state: FSMContext):
    if not adm(c.from_user.id): return
    pid = int(c.data.split(":")[1])
    await state.update_data(edit_id=pid, edit_type="product")
    await state.set_state(EditPriceState.new_price)
    await c.message.answer("✏️ Enter the new price (in INR) for this subscription:")

@router.callback_query(F.data.startswith("edit_b:"))
async def edit_bundle_price_prompt(c: CallbackQuery, state: FSMContext):
    if not adm(c.from_user.id): return
    bid = int(c.data.split(":")[1])
    await state.update_data(edit_id=bid, edit_type="bundle")
    await state.set_state(EditPriceState.new_price)
    await c.message.answer("✏️ Enter the new price (in INR) for this combo bundle:")

@router.message(EditPriceState.new_price)
async def save_new_price(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    try:
        new_price = int(m.text)
        data = await state.get_data()
        item_id = data["edit_id"]
        item_type = data["edit_type"]
        
        if item_type == "product":
            q("UPDATE products SET price = ? WHERE id = ?", (new_price, item_id))
        else:
            q("UPDATE bundles SET price = ? WHERE id = ?", (new_price, item_id))
            
        await state.clear()
        await m.answer(f"✅ Price updated successfully to ₹{new_price}!")
    except ValueError:
        await m.save()
        await m.answer("❌ Please enter a valid number for the price.")

@router.message(Command("broadcast"))
async def bc(m: Message):
    if not adm(m.from_user.id): return
    txt = m.text.replace("/broadcast", "").strip(); n = 0
    for u in q("SELECT id FROM users"):
        try: await m.bot.send_message(u["id"], txt); n += 1
        except: pass
    await m.answer(f"Broadcast sent to {n} users.")

async def main():
    init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    
    # Run polling directly as a Background Worker / Polling Bot
    logging.info("Bot started polling successfully!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import os, sqlite3, datetime, asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

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
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,qty INTEGER,amount INTEGER,method TEXT,status TEXT DEFAULT 'pending',shot TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,referred_by INTEGER,ref_count INTEGER DEFAULT 0);
    """)
    c.commit(); c.close()

class Add(StatesGroup):
    title = State(); price = State(); stars = State(); desc = State(); image = State(); link = State()

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
                await m.bot.send_message(ref_by, f"🎉 <b>New Referral!</b> Someone joined using your invite link. Keep going to unlock free rewards!")
            except:
                pass
    
    welcome_text = (
        f"<b>Welcome, {m.from_user.first_name}! 👋</b>\n\n"
        "👑 <b>Welcome to our Exclusive Premium Group Store.</b>\n"
        "• Browse and select available premium groups.\n"
        "• Pay securely via UPI or Telegram Stars.\n"
        "• Invite friends and earn <b>Free Access</b>!\n\n"
        "Please choose an option below 👇"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Browse Groups", callback_data="shop")
    kb.button(text="🎁 Free / Referral", callback_data="referral")
    kb.button(text="📦 My Orders", callback_data="orders")
    if adm(user_id): kb.button(text="⚙️ Admin Panel", callback_data="admin")
    kb.adjust(2)
    await m.answer(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "referral")
async def referral_menu(c: CallbackQuery):
    user_id = c.from_user.id
    user_data = q("SELECT * FROM users WHERE id=?", (user_id,), True)
    ref_count = user_data["ref_count"] if user_data else 0
    bot_info = await c.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    text = (
        "🎁 <b>Free Premium Group Referral Program</b>\n\n"
        "Want to get access completely <b>FREE</b>? Share your personal invite link with your friends!\n\n"
        f"👥 <b>Your Referrals:</b> {ref_count} / 3 Friends\n\n"
        f"🔗 <b>Your Invite Link:</b>\n<code>{ref_link}</code>\n\n"
        "<i>Note: Once you successfully invite 3 friends, contact admin with a screenshot to claim your free group link!</i>"
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
    kb.button(text="⬅️ Back to Menu", callback_data="home")
    kb.adjust(1) # ഓരോ ഗ്രൂപ്പും താഴേക്ക് ഓരോ റോ ആയി (Row-by-Row) വരുന്ന രീതിയിൽ സെറ്റ് ചെയ്തിരിക്കുന്നു
    await c.message.edit_text("<b>Select a group to view details:</b>", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "home")
async def home(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Browse Groups", callback_data="shop")
    kb.button(text="🎁 Free / Referral", callback_data="referral")
    kb.button(text="📦 My Orders", callback_data="orders")
    if adm(c.from_user.id): kb.button(text="⚙️ Admin Panel", callback_data="admin")
    kb.adjust(2)
    
    welcome_text = (
        "👑 <b>Store Menu:</b>\n"
        "Please choose an option below 👇"
    )
    await c.message.edit_text(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("p:"))
async def product(c: CallbackQuery):
    r = q("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),), True)
    if not r: return await c.answer("Group not found.", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"💳 Pay UPI ₹{r['price']}", callback_data=f"qty:{r['id']}")
    kb.button(text=f"⭐ Pay {r['stars']} Stars (Instant)", callback_data=f"star:{r['id']}")
    kb.button(text="⬅️ Back", callback_data="shop")
    kb.adjust(1)
    
    caption = f"<b>{r['title']}</b>\n\n{r['desc'] or ''}\n\n💰 Price: ₹{r['price']}  |  ⭐ Stars: {r['stars']}\n📦 Access: <b>Unlimited (Instant Delivery on Stars)</b>"
    
    try: await c.message.delete()
    except: pass
        
    if r["image"]:
        await c.bot.send_photo(c.from_user.id, r["image"], caption=caption, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await c.bot.send_message(c.from_user.id, caption, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("qty:"))
async def qty(c: CallbackQuery):
    pid = int(c.data.split(":")[1])
    r = q("SELECT * FROM products WHERE id=?", (pid,), True)
    oid = q("INSERT INTO orders(user_id,product_id,qty,amount,method,created) VALUES(?,?,?,?,?,?)",
            (c.from_user.id, pid, 1, r["price"], "upi", str(datetime.datetime.now())))
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
        try: await m.bot.send_photo(a, m.photo[-1].file_id, caption=f"🔔 <b>New Payment Verification</b>\nOrder #{oid}\nUser ID: {m.from_user.id}\nAmount: ₹{o['amount']}", parse_mode="HTML", reply_markup=kb.as_markup())
        except: pass
    await state.clear()

@router.callback_query(F.data.startswith("star:"))
async def stars(c: CallbackQuery):
    r = q("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),), True)
    await c.bot.send_invoice(c.from_user.id, title=r["title"], description=(r["desc"] or "Group Access")[:250],
        payload=f"p:{r['id']}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label=r["title"], amount=r["stars"])])
    await c.answer()

@router.pre_checkout_query()
async def preco(p: PreCheckoutQuery):
    await p.answer(ok=True)

@router.message(F.successful_payment)
async def paid(m: Message):
    pid = int(m.successful_payment.invoice_payload.split(":")[1])
    oid = q("INSERT INTO orders(user_id,product_id,qty,amount,method,status,created) VALUES(?,?,?,?,?,?,?)",
            (m.from_user.id, pid, 1, m.successful_payment.total_amount, "stars", "paid", str(datetime.datetime.now())))
    await deliver(m.bot, oid, m.chat.id)

async def deliver(bot, oid, chat_id):
    o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    if o["status"] == "delivered": return
    
    product = q("SELECT * FROM products WHERE id=?", (o["product_id"],), True)
    if not product:
        return await bot.send_message(chat_id, f"⚠️ Order #{oid} error. Please contact admin.")
    
    link_to_send = product["link"] if product["link"] else "https://t.me/+example"

    try:
        await bot.send_message(chat_id, f"🔗 <b>Your Private Group Invite Link:</b>\n\n{link_to_send}", parse_mode="HTML")
    except Exception as e: 
        await bot.send_message(chat_id, f"Error: {e}")
        
    q("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
    await bot.send_message(chat_id, f"✅ Order #{oid} delivered successfully. Welcome to the group!")

    try:
        alert_text = f"🎉 Customer #{oid} successfully purchased <b>{product['title']}</b> ✅!\n\n🛍 Explore the store and choose your product below."
        kb_channels = InlineKeyboardBuilder()
        kb_channels.button(text="✨ Explore Store", callback_data="shop")
        kb_channels.button(text=f"✨ {product['title']} · ₹{product['price']}", callback_data=f"p:{product['id']}")
        kb_channels.adjust(1)

        users = q("SELECT id FROM users")
        for u in users:
            try:
                if product.get("image"):
                    await bot.send_photo(u["id"], product["image"], caption=alert_text, parse_mode="HTML", reply_markup=kb_channels.as_markup())
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
    try: await c.bot.send_message(o["user_id"], f"❌ Order #{oid} has been rejected by admin.")
    except: pass
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n❌ REJECTED")

@router.callback_query(F.data.startswith("no:"))
async def cancel(c: CallbackQuery):
    q("UPDATE orders SET status='cancelled' WHERE id=?", (int(c.data.split(":")[1]),))
    await c.message.edit_caption(caption="Order cancelled.")

@router.callback_query(F.data == "orders")
async def myorders(c: CallbackQuery):
    rows = q("SELECT o.*, p.title FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? ORDER BY o.id DESC LIMIT 10", (c.from_user.id,))
    if not rows: return await c.answer("No orders found.", show_alert=True)
    t = "\n".join(f"#{r['id']} — {r['title']} — ₹{r['amount']} — <b>{r['status']}</b>" for r in rows)
    await c.message.answer(f"<b>Your Recent Orders:</b>\n\n{t}", parse_mode="HTML")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if not adm(c.from_user.id): return
    total = q("SELECT COUNT(*) c FROM orders WHERE status IN ('paid','delivered')", (), True)["c"]
    rev = q("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status IN ('paid','delivered')", (), True)["s"]
    await c.message.answer(f"<b>Admin Control Panel</b>\nTotal Sales: {total}\nTotal Revenue: ₹{rev}\n\n/addproduct — Add new group\n/list — View all groups (Row by Row)\n/del &lt;id&gt; — Delete group\n/broadcast &lt;msg&gt; — Send broadcast message", parse_mode="HTML")

@router.message(Command("addproduct"))
async def addp(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    await state.set_state(Add.title); await m.answer("1/6 Enter Group Title/Name:")

@router.message(Add.title)
async def a1(m: Message, state: FSMContext):
    await state.update_data(title=m.text); await state.set_state(Add.price); await m.answer("2/6 Enter Price in INR (Number only, e.g., 199):")

@router.message(Add.price)
async def a2(m: Message, state: FSMContext):
    await state.update_data(price=int(m.text)); await state.set_state(Add.stars); await m.answer("3/6 Enter Price in Telegram Stars (Number only):")

@router.message(Add.stars)
async def a3(m: Message, state: FSMContext):
    await state.update_data(stars=int(m.text)); await state.set_state(Add.desc); await m.answer("4/6 Enter Group Description:")

@router.message(Add.desc)
async def a4(m: Message, state: FSMContext):
    await state.update_data(desc=m.text)
    await state.set_state(Add.image)
    await m.answer("5/6 <b>Send Demo Photo / Screenshot</b> for this group:", parse_mode="HTML")

@router.message(Add.image, F.photo)
async def a_image(m: Message, state: FSMContext):
    await state.update_data(image=m.photo[-1].file_id)
    await state.set_state(Add.link)
    await m.answer("6/6 Now send the permanent <b>Group Invite Link</b> as text (this link will be used for unlimited deliveries):", parse_mode="HTML")

@router.message(Add.link)
async def a6(m: Message, state: FSMContext):
    d = await state.get_data()
    q("INSERT INTO products(title,desc,price,stars,image,link) VALUES(?,?,?,?,?,?)", 
      (d["title"], d["desc"], d["price"], d["stars"], d["image"], m.text))
    await state.clear()
    await m.answer("✅ Group added successfully with <b>Unlimited Link</b>! It is now live on the store.", parse_mode="HTML")

@router.message(Command("list"))
async def lst(m: Message):
    if not adm(m.from_user.id): return
    rows = q("SELECT * FROM products")
    if not rows:
        return await m.answer("📂 No groups available in store.")
    
    list_text = "📋 <b>All Store Groups List:</b>\n\n"
    for r in rows:
        list_text += f"🔹 <b>ID:</b> <code>{r['id']}</code>\n" \
                     f"📌 <b>Name:</b> {r['title']}\n" \
                     f"💰 <b>Price:</b> ₹{r['price']} | ⭐ {r['stars']}\n" \
                     f"🔗 <b>Link:</b> {r['link']}\n" \
                     f"──────────────────────────\n"
    
    await m.answer(list_text, parse_mode="HTML")

@router.message(Command("del"))
async def dele(m: Message):
    if not adm(m.from_user.id): return
    try:
        parts = m.text.split()
        if len(parts) < 2: return await m.answer("⚠️ Please provide group ID. Example: `/del 1`")
        product_id = int(parts[1])
        q("DELETE FROM products WHERE id=?", (product_id,))
        q("DELETE FROM orders WHERE product_id=?", (product_id,))
        await m.answer(f"✅ Group #{product_id} deleted successfully.")
    except Exception as e:
        await m.answer(f"❌ Error: {e}")

@router.message(Command("clearall"))
async def clear_all(m: Message):
    if not adm(m.from_user.id): return
    q("DELETE FROM products")
    q("DELETE FROM orders")
    await m.answer("🗑 All products and order data cleared successfully!")

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
    dp = Dispatcher(); dp.include_router(router)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="alive"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080))).start()
    await dp.start_polling(bot)

asyncio.run(main())

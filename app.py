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
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,title TEXT,desc TEXT,price INTEGER,stars INTEGER,image TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY,product_id INTEGER,file_id TEXT,file_type TEXT,sold INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,qty INTEGER,amount INTEGER,method TEXT,status TEXT DEFAULT 'pending',shot TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT);
    """)
    c.commit(); c.close()

class Add(StatesGroup):
    title = State(); price = State(); stars = State(); desc = State(); image = State(); stock = State()

router = Router()
adm = lambda uid: uid in ADMIN_IDS

@router.message(Command("start"))
async def start(m: Message):
    q("INSERT OR IGNORE INTO users VALUES(?,?)", (m.from_user.id, m.from_user.first_name))
    
    welcome_text = (
        f"<b>Welcome, {m.from_user.first_name}! 👋</b>\n\n"
        "👑 <b>Welcome to our Exclusive Premium Group Store.</b>\n"
        "• Browse and select available premium groups.\n"
        "• Pay securely via UPI or Telegram Stars.\n"
        "• Get instant automated invite links upon successful verification!\n\n"
        "Please choose an option below 👇"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Browse Groups", callback_data="shop")
    kb.button(text="📦 My Orders", callback_data="orders")
    if adm(m.from_user.id): kb.button(text="⚙️ Admin Panel", callback_data="admin")
    kb.adjust(2)
    await m.answer(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    rows = q("SELECT * FROM products WHERE active=1")
    if not rows: return await c.message.edit_text("No groups available at the moment.")
    kb = InlineKeyboardBuilder()
    for r in rows:
        n = q("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (r["id"],), True)["c"]
        kb.button(text=f"{r['title']} — ₹{r['price']} ({n} slots)", callback_data=f"p:{r['id']}")
    kb.button(text="⬅️ Back to Menu", callback_data="home"); kb.adjust(1)
    await c.message.edit_text("<b>Select a group to view details:</b>", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "home")
async def home(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Browse Groups", callback_data="shop")
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
    n = q("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (r["id"],), True)["c"]
    kb = InlineKeyboardBuilder()
    if n:
        kb.button(text=f"💳 Pay UPI ₹{r['price']}", callback_data=f"qty:{r['id']}")
        kb.button(text=f"⭐ Pay {r['stars']} Stars", callback_data=f"star:{r['id']}")
    else: kb.button(text="❌ Sold Out (Slots Empty)", callback_data="shop")
    kb.button(text="⬅️ Back", callback_data="shop"); kb.adjust(1)
    
    caption = f"<b>{r['title']}</b>\n\n{r['desc'] or ''}\n\n💰 Price: ₹{r['price']}  |  ⭐ Stars: {r['stars']}\n📦 Available Slots: {n}"
    
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
    kb.button(text="❌ Cancel Order", callback_data=f"no:{oid}"); kb.adjust(1)
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
    items = q("SELECT * FROM stock WHERE product_id=? AND sold=0 LIMIT ?", (o["product_id"], o["qty"]))
    if not items:
        return await bot.send_message(chat_id, f"⚠️ Order #{oid} payment confirmed, but stock slots are empty. Admin will contact you shortly.")
    
    product = q("SELECT * FROM products WHERE id=?", (o["product_id"],), True)
    product_title = product["title"] if product else "PREMIUM GROUP"
    
    for it in items:
        try:
            await bot.send_message(chat_id, f"🔗 <b>Your Private Group Invite Link:</b>\n\n{it['file_id']}", parse_mode="HTML")
        except Exception as e: await bot.send_message(chat_id, f"Error: {e}")
        q("UPDATE stock SET sold=1 WHERE id=?", (it["id"],))
        
    q("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
    await bot.send_message(chat_id, f"✅ Order #{oid} delivered successfully. Welcome to the group!")

    # Broadcast notification to all store users
    try:
        alert_text = f"🎉 Customer #{oid} successfully purchased <b>{product_title}</b> ✅!\n\n🛍 Explore the store and choose your product below."
        kb_channels = InlineKeyboardBuilder()
        kb_channels.button(text="✨ Explore Store", callback_data="shop")
        kb_channels.button(text=f"✨ {product_title} · ₹{product['price']}", callback_data=f"p:{product['id']}")
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
    await c.message.answer(f"<b>Admin Control Panel</b>\nTotal Sales: {total}\nTotal Revenue: ₹{rev}\n\n/addproduct — Add new group\n/list — View all groups\n/del &lt;id&gt; — Delete group\n/clearall — Clear all database data\n/broadcast &lt;msg&gt; — Send broadcast message", parse_mode="HTML")

@router.message(Command("addproduct"))
async def addp(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    await state.set_state(Add.title); await m.answer("1/5 Enter Group Title/Name:")

@router.message(Add.title)
async def a1(m: Message, state: FSMContext):
    await state.update_data(title=m.text); await state.set_state(Add.price); await m.answer("2/5 Enter Price in INR (Number only, e.g., 199):")

@router.message(Add.price)
async def a2(m: Message, state: FSMContext):
    await state.update_data(price=int(m.text)); await state.set_state(Add.stars); await m.answer("3/5 Enter Price in Telegram Stars (Number only):")

@router.message(Add.stars)
async def a3(m: Message, state: FSMContext):
    await state.update_data(stars=int(m.text)); await state.set_state(Add.desc); await m.answer("4/5 Enter Group Description:")

@router.message(Add.desc)
async def a4(m: Message, state: FSMContext):
    await state.update_data(desc=m.text)
    await state.set_state(Add.image)
    await m.answer("5/5 <b>Send Demo Photo / Screenshot</b> for this group:", parse_mode="HTML")

@router.message(Add.image, F.photo)
async def a_image(m: Message, state: FSMContext):
    d = await state.get_data()
    file_id = m.photo[-1].file_id
    q("INSERT INTO products(title,desc,price,stars,image) VALUES(?,?,?,?,?)", 
      (d["title"], d["desc"], d["price"], d["stars"], file_id))
    await state.set_state(Add.stock)
    await m.answer("✅ Demo photo saved! Now send the <b>Invite Links</b> one by one as text messages (each message = 1 stock slot). Type /done when finished.", parse_mode="HTML")

@router.message(Add.stock)
async def a5(m: Message, state: FSMContext):
    pid = q("SELECT MAX(id) i FROM products", (), True)["i"]
    if m.text: 
        q("INSERT INTO stock(product_id,file_id,file_type) VALUES(?,?,'text')", (pid, m.text))
    else: 
        return await m.answer("Please send the invite link as text.")
    n = q("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (pid,), True)["c"]
    await m.answer(f"✅ Link added successfully. Available Links/Slots: {n}")

@router.message(Command("done"))
async def done(m: Message, state: FSMContext):
    await state.clear(); await m.answer("✅ Group is now live on the store!")

@router.message(Command("list"))
async def lst(m: Message):
    if not adm(m.from_user.id): return
    rows = q("SELECT p.*, (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.sold=0) st FROM products p")
    await m.answer("\n".join(f"#{r['id']} {r['title']} — ₹{r['price']} | Slots: {r['st']}" for r in rows) or "No groups available.")

@router.message(Command("del"))
async def dele(m: Message):
    if not adm(m.from_user.id): return
    try:
        parts = m.text.split()
        if len(parts) < 2: return await m.answer("⚠️ Please provide group ID. Example: `/del 1`")
        product_id = int(parts[1])
        q("DELETE FROM stock WHERE product_id=?", (product_id,))
        q("DELETE FROM products WHERE id=?", (product_id,))
        await m.answer(f"✅ Group #{product_id} deleted successfully.")
    except Exception as e:
        await m.answer(f"❌ Error: {e}")

@router.message(Command("clearall"))
async def clear_all(m: Message):
    if not adm(m.from_user.id): return
    q("DELETE FROM products")
    q("DELETE FROM stock")
    q("DELETE FROM orders")
    await m.answer("🗑 All products, stock, and order data cleared successfully!")

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

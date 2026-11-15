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
    
    # Bot enthu group/store aanu ennulla description / caption
    welcome_text = (
        f"<b>സ്വാഗതം {m.from_user.first_name}! 👋</b>\n\n"
        "🛍 <b>ഇത് ഡിജിറ്റൽ പ്രൊഡക്റ്റുകളും ഫയലുകളും എളുപ്പത്തിൽ വാങ്ങാനുള്ള സ്റ്റോർ ആണ്.</b>\n"
        "• വിശ്വസ്തതയോടെ പ്രൊഡക്റ്റുകൾ ബ്രൗസ് ചെയ്ത് വാങ്ങാം.\n"
        "• UPI അല്ലെങ്കിൽ Telegram Stars വഴി പേയ്മെന്റ് നടത്താം.\n"
        "• പെയ്മെന്റ് പൂർത്തിയായാൽ ഫയലുകൾ ഓട്ടോമാറ്റിക്കായി ഡെലിവറി ലഭിക്കും.\n\n"
        "താഴെ കാണുന്ന ഓപ്ഷനുകൾ ഉപയോഗിക്കുക 👇"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Shop", callback_data="shop")
    kb.button(text="📦 My Orders", callback_data="orders")
    if adm(m.from_user.id): kb.button(text="⚙️ Admin", callback_data="admin")
    kb.adjust(2)
    await m.answer(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    rows = q("SELECT * FROM products WHERE active=1")
    if not rows: return await c.message.edit_text("ഇപ്പോൾ product ഇല്ല.")
    kb = InlineKeyboardBuilder()
    for r in rows:
        n = q("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (r["id"],), True)["c"]
        kb.button(text=f"{r['title']} — ₹{r['price']} ({n})", callback_data=f"p:{r['id']}")
    kb.button(text="⬅️ Back", callback_data="home"); kb.adjust(1)
    await c.message.edit_text("തിരഞ്ഞെടുക്കുക:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "home")
async def home(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Shop", callback_data="shop")
    kb.button(text="📦 My Orders", callback_data="orders")
    if adm(c.from_user.id): kb.button(text="⚙️ Admin", callback_data="admin")
    kb.adjust(2)
    
    welcome_text = (
        "🛍 <b>ഡിജിറ്റൽ സ്റ്റോർ മെനു:</b>\n"
        "താഴെ നിന്ന് ആവശ്യമായത് തിരഞ്ഞെടുക്കുക 👇"
    )
    await c.message.edit_text(welcome_text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("p:"))
async def product(c: CallbackQuery):
    r = q("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),), True)
    if not r: return await c.answer("ഇല്ല", show_alert=True)
    n = q("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (r["id"],), True)["c"]
    kb = InlineKeyboardBuilder()
    if n:
        kb.button(text=f"💳 UPI ₹{r['price']}", callback_data=f"qty:{r['id']}")
        kb.button(text=f"⭐ {r['stars']} Stars", callback_data=f"star:{r['id']}")
    else: kb.button(text="Sold out", callback_data="shop")
    kb.button(text="⬅️ Back", callback_data="shop"); kb.adjust(1)
    
    caption = f"<b>{r['title']}</b>\n\n{r['desc'] or ''}\n\n💰 ₹{r['price']}  |  ⭐ {r['stars']}\n📦 Stock: {n}"
    
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
    kb.button(text="✅ Paid — screenshot അയക്കാം", callback_data=f"shot:{oid}")
    kb.button(text="❌ Cancel", callback_data=f"no:{oid}"); kb.adjust(1)
    await c.message.answer_photo(QR, caption=f"<b>Order #{oid}</b>\n\n₹{r['price']} ഈ UPI-ലേക്ക് അയക്കുക:\n<code>{UPI}</code>\n\nPay ചെയ്ത ശേഷം താഴെ ബട്ടൺ അമർത്തി screenshot അയക്കുക.", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("shot:"))
async def shot(c: CallbackQuery, state: FSMContext):
    await state.update_data(oid=int(c.data.split(":")[1]))
    await state.set_state("wait_shot")
    await c.message.answer("Screenshot അയക്കുക 👇")

@router.message(StateFilter("wait_shot"), F.photo)
async def got_shot(m: Message, state: FSMContext):
    oid = (await state.get_data())["oid"]
    q("UPDATE orders SET shot=? WHERE id=?", (m.photo[-1].file_id, oid))
    o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"ok:{oid}")
    kb.button(text="❌ Reject", callback_data=f"rno:{oid}")
    await m.answer("✅ കിട്ടി. Verify ചെയ്യുന്നു...")
    for a in ADMIN_IDS:
        try: await m.bot.send_photo(a, m.photo[-1].file_id, caption=f"Order #{oid}\nUser: {m.from_user.id}\n₹{o['amount']}", reply_markup=kb.as_markup())
        except: pass
    await state.clear()

@router.callback_query(F.data.startswith("star:"))
async def stars(c: CallbackQuery):
    r = q("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),), True)
    await c.bot.send_invoice(c.from_user.id, title=r["title"], description=(r["desc"] or "Product")[:250],
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
        return await bot.send_message(chat_id, f"⚠️ Order #{oid} paid, stock തീർന്നു. Admin ബന്ധപ്പെടും.")
    for it in items:
        try:
            if it["file_type"] == "doc": await bot.send_document(chat_id, it["file_id"])
            elif it["file_type"] == "video": await bot.send_video(chat_id, it["file_id"])
            elif it["file_type"] == "photo": await bot.send_photo(chat_id, it["file_id"])
            else: await bot.send_message(chat_id, it["file_id"])
        except Exception as e: await bot.send_message(chat_id, f"Error: {e}")
        q("UPDATE stock SET sold=1 WHERE id=?", (it["id"],))
    q("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
    await bot.send_message(chat_id, f"✅ Order #{oid} delivered. നന്ദി!")

@router.callback_query(F.data.startswith("ok:"))
async def okk(c: CallbackQuery):
    if not adm(c.from_user.id): return
    oid = int(c.data.split(":")[1]); o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    q("UPDATE orders SET status='paid' WHERE id=?", (oid,))
    await deliver(c.bot, oid, o["user_id"])
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n✅ APPROVED")

@router.callback_query(F.data.startswith("rno:"))
async def rno(c: CallbackQuery):
    if not adm(c.from_user.id): return
    oid = int(c.data.split(":")[1])
    o = q("SELECT * FROM orders WHERE id=?", (oid,), True)
    q("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
    try: await c.bot.send_message(o["user_id"], f"❌ Order #{oid} reject ചെയ്തു.")
    except: pass
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n❌ REJECTED")

@router.callback_query(F.data.startswith("no:"))
async def cancel(c: CallbackQuery):
    q("UPDATE orders SET status='cancelled' WHERE id=?", (int(c.data.split(":")[1]),))
    await c.message.edit_caption(caption="Order cancel ചെയ്തു.")

@router.callback_query(F.data == "orders")
async def myorders(c: CallbackQuery):
    rows = q("SELECT o.*, p.title FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? ORDER BY o.id DESC LIMIT 10", (c.from_user.id,))
    if not rows: return await c.answer("Order ഇല്ല", show_alert=True)
    t = "\n".join(f"#{r['id']} — {r['title']} — ₹{r['amount']} — {r['status']}" for r in rows)
    await c.message.answer(f"<b>നിങ്ങളുടെ orders:</b>\n\n{t}", parse_mode="HTML")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if not adm(c.from_user.id): return
    total = q("SELECT COUNT(*) c FROM orders WHERE status IN ('paid','delivered')", (), True)["c"]
    rev = q("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status IN ('paid','delivered')", (), True)["s"]
    await c.message.answer(f"<b>Admin Panel</b>\nSales: {total}\nRevenue: ₹{rev}\n\n/addproduct — പുതിയ product\n/list — products\n/del &lt;id&gt; — delete\n/clearall — എല്ലാ data-യും കളയാൻ\n/broadcast &lt;msg&gt; — അയക്കൽ", parse_mode="HTML")

@router.message(Command("addproduct"))
async def addp(m: Message, state: FSMContext):
    if not adm(m.from_user.id): return
    await state.set_state(Add.title); await m.answer("1/5 Product name:")

@router.message(Add.title)
async def a1(m: Message, state: FSMContext):
    await state.update_data(title=m.text); await state.set_state(Add.price); await m.answer("2/5 വില (₹ നമ്പർ മാത്രം):")

@router.message(Add.price)
async def a2(m: Message, state: FSMContext):
    await state.update_data(price=int(m.text)); await state.set_state(Add.stars); await m.answer("3/5 Stars വില (⭐ നമ്പർ):")

@router.message(Add.stars)
async def a3(m: Message, state: FSMContext):
    await state.update_data(stars=int(m.text)); await state.set_state(Add.desc); await m.answer("4/5 Description:")

@router.message(Add.desc)
async def a4(m: Message, state: FSMContext):
    await state.update_data(desc=m.text)
    await state.set_state(Add.image)
    await m.answer("5/5 <b>Demo Photo അയക്കുക</b> (പ്രൊഡക്റ്റിന്റെ ഡെമോ/സ്ക്രീൻഷോട്ട്):", parse_mode="HTML")

@router.message(Add.image, F.photo)
async def a_image(m: Message, state: FSMContext):
    d = await state.get_data()
    file_id = m.photo[-1].file_id
    q("INSERT INTO products(title,desc,price,stars,image) VALUES(?,?,?,?,?)", 
      (d["title"], d["desc"], d["price"], d["stars"], file_id))
    await state.set_state(Add.stock)
    await m.answer("✅ ഡെമോ ഫോട്ടോ സേവായി! ഇനി stock-നുള്ള ഫയലുകൾ ഓരോന്നായി forward ചെയ്യുക. തീർന്നാൽ /done എന്ന് ടൈപ്പ് ചെയ്യുക.")

@router.message(Add.stock)
async def a5(m: Message, state: FSMContext):
    pid = q("SELECT MAX(id) i FROM products", (), True)["i"]
    if m.document: q("INSERT INTO stock(product_id,file_id,file_type) VALUES(?,?,'doc')", (pid, m.document.file_id))
    elif m.video: q("INSERT INTO stock(product_id,file_id,file_type) VALUES(?,?,'video')", (pid, m.video.file_id))
    elif m.photo: q("INSERT INTO stock(product_id,file_id,file_type) VALUES(?,?,'photo')", (pid, m.photo.file_id))
    else: return await m.answer("ഫയൽ മാത്രം അയക്കുക")
    n = q("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (pid,), True)["c"]
    await m.answer(f"✅ ചേർത്തു. Stock: {n}")

@router.message(Command("done"))
async def done(m: Message, state: FSMContext):
    await state.clear(); await m.answer("✅ Product live ആയി.")

@router.message(Command("list"))
async def lst(m: Message):
    if not adm(m.from_user.id): return
    rows = q("SELECT p.*, (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.sold=0) st FROM products p")
    await m.answer("\n".join(f"#{r['id']} {r['title']} ₹{r['price']} stock:{r['st']}" for r in rows) or "ഒന്നുമില്ല")

@router.message(Command("del"))
async def dele(m: Message):
    if not adm(m.from_user.id): return
    try:
        parts = m.text.split()
        if len(parts) < 2: return await m.answer("⚠️ Please provide product ID. Eg: `/del 1`")
        product_id = int(parts[1])
        q("DELETE FROM stock WHERE product_id=?", (product_id,))
        q("DELETE FROM products WHERE id=?", (product_id,))
        await m.answer(f"✅ Product #{product_id} permanently deleted.")
    except Exception as e:
        await m.answer(f"❌ Error: {e}")

@router.message(Command("clearall"))
async def clear_all(m: Message):
    if not adm(m.from_user.id): return
    q("DELETE FROM products")
    q("DELETE FROM stock")
    q("DELETE FROM orders")
    await m.answer("🗑 എല്ലാ പ്രൊഡക്റ്റുകളും സ്റ്റോപ്പുകളും ഓർഡറുകളും വിജയകരമായി ക്ലിയർ ചെയ്തു!")

@router.message(Command("broadcast"))
async def bc(m: Message):
    if not adm(m.from_user.id): return
    txt = m.text.replace("/broadcast", "").strip(); n = 0
    for u in q("SELECT id FROM users"):
        try: await m.bot.send_message(u["id"], txt); n += 1
        except: pass
    await m.answer(f"അയച്ചു: {n}")

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

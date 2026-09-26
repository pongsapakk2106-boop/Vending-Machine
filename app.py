import base64
import hashlib
import hmac
import json
import time
import uuid

import requests
import streamlit as st

st.set_page_config(page_title="ตู้น้ำศักดิ์สิทธิ์ ", page_icon="🦒")

# ============================================
# ข้อมูลตั้งต้น (แก้ตรงนี้ที่เดียว ถ้าจะเพิ่ม/ลดเมนู)
# ============================================

# (ชื่อ, ราคา, หมวด) รูปอยู่ที่ images/<ชื่อ>.jpg
MENUS = [
    ("กาแฟดำเบิกเนตร", 35, "coffee"),
    ("ส้มสมหวัง", 30, "tea"),
    ("โกโก้แก้กรรม", 35, "milk"),
    ("นมสดสมองใส", 25, "milk"),
    ("ชาเขียวท็อปเซค", 40, "tea"),
    ("นมชมพูสละโสด", 25, "milk"),
]
TABS = {"ทั้งหมด": "", "☕ กาแฟ": "coffee", "🍵 ชา": "tea", "🥛 นม & โกโก้": "milk"}
SWEETS = ["ไม่หวาน", "หวานน้อยมาก", "หวานน้อย", "หวานปกติ", "หวานมาก", "หวานมากพิเศษ"]
PAYMENTS = ["เงินสด", "พร้อมเพย์", "บัตร", "LINE Pay"]
CASH_OPTIONS = [20, 50, 100, 500, 1000]

# ============================================
# ค่าคอนฟิก LINE Pay (แก้เป็นของร้านคุณเอง)
# ============================================
# ได้มาจาก LINE Pay Merchant Center หลังสมัครและผ่านการอนุมัติ
CHANNEL_ID = "2011751057"
CHANNEL_SECRET = "e81c720fcd5c03457f4dae3534920828"

# ตอนทดสอบใช้ sandbox ก่อน พอใช้งานจริงค่อยเปลี่ยนเป็น "https://api-pay.line.me"
LINE_PAY_API = "https://sandbox-api-pay.line.me"

# ต้องเป็น URL จริงที่ deploy แอปนี้ไว้ (ต้องเป็น https เท่านั้น LINE Pay ไม่รับ localhost)
# เช่น "https://your-app-name.streamlit.app"
APP_URL = "https://your-app-name.streamlit.app"

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Prompt:wght@400;600;700&display=swap');
:root { --ink:#0F3D3E; --shell:#1F7A5C; --sky:#f6e1aa; --sun:#FFC93C; }
.stApp { background: var(--sky); }
.stApp, .stApp :is(p, h1, h2, h3, label, button) { font-family: 'Prompt', sans-serif; color: var(--ink); }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; max-width: 760px; }

.hero { text-align: center; padding: 1.2rem; margin-bottom: 1.2rem; color: #fff; background: var(--shell);
        border: 3px solid var(--ink); border-radius: 22px; box-shadow: 6px 6px 0 var(--ink); }
.hero .name { font-size: 2.4rem; font-weight: 700; }
.hero b { color: var(--sun); }

button[data-baseweb="tab"] { border: 2px solid var(--ink); border-radius: 999px; background: #fff; height: auto; }
button[data-baseweb="tab"][aria-selected="true"] { background: var(--sun); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

[class*="st-key-card_"] { background: #fff; border: 3px solid var(--ink); border-radius: 20px;
                          padding: 12px; box-shadow: 5px 5px 0 var(--ink); }
[class*="st-key-card_"] img { aspect-ratio: 1; object-fit: cover; border-radius: 12px; border: 2px solid var(--ink); }
.price { background: var(--sun); border: 2px solid var(--ink); border-radius: 999px; padding: 0 .8rem; font-weight: 700; }

.stButton button { border: 2px solid var(--ink); border-radius: 12px; font-weight: 600; min-height: 3rem;
                   background: #fff; box-shadow: 3px 3px 0 var(--ink); }
.stButton button:hover { background: var(--sun); border-color: var(--ink); }
.stButton button:active { transform: translate(3px, 3px); box-shadow: none; }
.stButton button:disabled { opacity: .5; box-shadow: none; }
.st-key-pay button { background: var(--shell); }
.st-key-pay button p { color: #fff; }
[data-testid="stAlert"] { border: 2px solid var(--ink); border-radius: 14px; }
</style>
"""

HERO = """
<div class="hero">
  <div class="name">ตู้น้ำยีราฟศักดิ์สิทธิ์ 🦒</div>
  <b>WISH</b> · เปิด 24 ชั่วโมง ชงสดทุกแก้ว เลือกแล้วกดสั่งได้เลยครับ
</div>
"""


# ============================================
# ตัวช่วยจัดการ "ออเดอร์" ที่เก็บไว้ใน session_state
# ============================================

def get_order():
    """คืนค่าออเดอร์ปัจจุบัน หรือ None ถ้ายังไม่มี"""
    return st.session_state.get("order")


def start_order(name, price):
    """ลูกค้าเลือกเมนู -> สร้างออเดอร์ใหม่"""
    st.session_state.order = {"name": name, "price": price}


def confirm_payment(order, sweet, method):
    """ลูกค้ากดยืนยันจ่ายเงิน (หรือ LINE Pay confirm สำเร็จ) -> ปิดออเดอร์ว่าจ่ายแล้ว"""
    order.update(sweet=sweet, method=method)


def clear_order():
    """ล้างออเดอร์ทั้งหมด กลับไปเริ่มใหม่"""
    st.session_state.clear()


def order_is_paid(order):
    """เช็คว่าออเดอร์นี้จ่ายเงินเรียบร้อยแล้วหรือยัง"""
    return "method" in order


# ============================================
# LINE Pay: เซ็นลายเซ็นคำขอ และเรียก API
# (มาตรฐาน LINE Pay API v3: HMAC-SHA256 ของ secret + uri + body + nonce)
# ============================================

def _line_pay_signature(uri: str, body_str: str, nonce: str) -> str:
    message = (CHANNEL_SECRET + uri + body_str + nonce).encode()
    digest = hmac.new(CHANNEL_SECRET.encode(), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _line_pay_headers(uri: str, body_str: str) -> dict:
    nonce = str(uuid.uuid4())
    return {
        "Content-Type": "application/json",
        "X-LINE-ChannelId": CHANNEL_ID,
        "X-LINE-Authorization-Nonce": nonce,
        "X-LINE-Authorization": _line_pay_signature(uri, body_str, nonce),
    }


def line_pay_create_request(order_id: str, name: str, price: int) -> dict:
    """ยิง request ไป LINE Pay เพื่อขอ paymentUrl ให้ลูกค้าไปกดจ่ายเงิน"""
    uri = "/v3/payments/request"
    body = {
        "amount": price,
        "currency": "THB",
        "orderId": order_id,
        "packages": [{
            "id": "pkg-1",
            "amount": price,
            "products": [{"name": name, "quantity": 1, "price": price}],
        }],
        "redirectUrls": {
            "confirmUrl": f"{APP_URL}/?linepay_order={order_id}",
            "cancelUrl": f"{APP_URL}/?linepay_cancel={order_id}",
        },
    }
    body_str = json.dumps(body, separators=(",", ":"))
    res = requests.post(
        LINE_PAY_API + uri, data=body_str, headers=_line_pay_headers(uri, body_str), timeout=15
    )
    return res.json()


def line_pay_confirm(transaction_id: str, price: int) -> dict:
    """ยืนยันการจ่ายเงินหลังลูกค้ากดอนุมัติในหน้า LINE Pay แล้ว"""
    uri = f"/v3/payments/{transaction_id}/confirm"
    body = {"amount": price, "currency": "THB"}
    body_str = json.dumps(body, separators=(",", ":"))
    res = requests.post(
        LINE_PAY_API + uri, data=body_str, headers=_line_pay_headers(uri, body_str), timeout=15
    )
    return res.json()


def handle_linepay_callback():
    """เช็คทุกครั้งที่แอปโหลด ว่าลูกค้าเพิ่ง redirect กลับมาจาก LINE Pay หรือไม่"""
    params = st.query_params
    order = get_order()

    if "linepay_order" in params and order and order.get("order_id") == params["linepay_order"]:
        transaction_id = order.get("linepay_transaction_id")
        if transaction_id:
            result = line_pay_confirm(transaction_id, order["price"])
            st.query_params.clear()
            if result.get("returnCode") == "0000":
                confirm_payment(order, order.get("sweet", "หวานปกติ"), "LINE Pay")
            else:
                st.error(f"ยืนยันการชำระเงินไม่สำเร็จ: {result.get('returnMessage')}")
                clear_order()

    elif "linepay_cancel" in params:
        st.query_params.clear()
        clear_order()


# ============================================
# หน้า 1: เมนูเครื่องดื่ม
# ============================================

def render_menu_card(name, price, column, key):
    """แสดงเมนู 1 รายการเป็นการ์ด พร้อมปุ่มสั่ง"""
    with column, st.container(key=key):
        st.image(f"images/{name}.jpg", use_container_width=True)
        st.markdown(
            f"**{name}**<br><span class='price'>{price} บาท</span>",
            unsafe_allow_html=True,
        )
        if st.button("สั่ง", key=f"btn_{key}", use_container_width=True):
            start_order(name, price)
            st.rerun()


def render_menu_tab(category):
    """แสดงเมนูทั้งหมดในหมวดหมู่เดียว จัดเป็นตาราง 3 คอลัมน์"""
    items_in_category = [menu for menu in MENUS if not category or menu[2] == category]
    columns = st.columns(3)

    for index, (name, price, _) in enumerate(items_in_category):
        column = columns[index % 3]
        render_menu_card(name, price, column, key=f"card_{category}_{index}")


def show_menu():
    """แสดงเมนูแยกเป็นแท็บตามหมวดหมู่"""
    tab_list = st.tabs(list(TABS))
    for tab, category in zip(tab_list, TABS.values()):
        with tab:
            render_menu_tab(category)


# ============================================
# หน้า 2: สรุปคำสั่งซื้อ + เลือกวิธีจ่ายเงิน
# ============================================

def render_promptpay_payment(price):
    st.image("qrcode.jpg", caption=f"สแกนจ่าย {price} บาท", width=260)
    return True


def render_cash_payment(price):
    cash = st.radio("รับเงินมา (บาท)", CASH_OPTIONS, index=2, horizontal=True)
    can_pay = cash >= price

    if can_pay:
        st.info(f"เงินทอน: {cash - price} บาท")
    else:
        st.warning("จำนวนเงินไม่พอครับ")

    return can_pay


def render_card_payment():
    st.caption("💳 เสียบ/แตะบัตรเพื่อชำระเงิน (จำลองเท่านั้น)")
    return True


def render_linepay_payment(order):
    """
    แสดง UI สำหรับจ่ายผ่าน LINE Pay
    ต่างจากวิธีอื่นตรงที่ปุ่ม "ยืนยันการชำระเงิน" ปกติจะไม่ถูกใช้ -
    ระบบจะยืนยันให้อัตโนมัติหลังลูกค้าจ่ายเงินใน LINE Pay แล้ว redirect กลับมา
    """
    price = order["price"]

    if "linepay_transaction_id" not in order:
        if st.button("🟢 ไปหน้า LINE Pay เพื่อจ่ายเงิน", use_container_width=True):
            order["order_id"] = order.get("order_id", str(uuid.uuid4()))
            result = line_pay_create_request(order["order_id"], order["name"], price)

            if result.get("returnCode") == "0000":
                order["linepay_transaction_id"] = result["info"]["transactionId"]
                order["linepay_url"] = result["info"]["paymentUrl"]["web"]
                st.rerun()
            else:
                st.error(f"LINE Pay ผิดพลาด: {result.get('returnMessage')}")
        return False

    st.link_button("🔗 เปิดหน้าจ่ายเงิน LINE Pay", order["linepay_url"], use_container_width=True)
    st.caption("จ่ายเงินในหน้า LINE Pay แล้วระบบจะพากลับมาที่นี่อัตโนมัติ")
    return False


def render_payment_method(method, price, order):
    """แสดง UI ของแต่ละวิธีจ่ายเงิน คืนค่าว่าพร้อมจ่ายได้หรือยัง"""
    if method == "พร้อมเพย์":
        return render_promptpay_payment(price)
    if method == "เงินสด":
        return render_cash_payment(price)
    if method == "LINE Pay":
        return render_linepay_payment(order)
    return render_card_payment()


def show_checkout(order):
    """หน้าให้ลูกค้าเลือกความหวานและวิธีชำระเงิน"""
    price = order["price"]

    st.subheader("🧾 สรุปคำสั่งซื้อ")
    st.write(f"**{order['name']}** {price} บาท")

    sweet = st.select_slider("ระดับความหวาน", SWEETS, value=order.get("sweet", "หวานปกติ"))
    order["sweet"] = sweet  # เก็บไว้ทันที เผื่อต้อง redirect ไป LINE Pay แล้วกลับมา

    method = st.radio("วิธีชำระเงิน", PAYMENTS, horizontal=True)
    can_pay = render_payment_method(method, price, order)

    st.button(
        "✅ ยืนยันการชำระเงิน",
        key="pay",
        disabled=not can_pay,
        use_container_width=True,
        on_click=confirm_payment,
        args=(order, sweet, method),
    )
    st.button("❌ ยกเลิก", use_container_width=True, on_click=clear_order)


# ============================================
# หน้า 3: ชำระเงินสำเร็จ
# ============================================

def show_success(order):
    """แสดงแอนิเมชันชงเครื่องดื่ม แล้วบอกว่าสำเร็จ"""
    progress_bar = st.progress(0)
    for percent in range(0, 101, 5):
        time.sleep(0.15)
        progress_bar.progress(percent, text=f"☕ กำลังชง {order['name']} ... {percent}%")
    progress_bar.empty()

    st.success(
        f"🎉 **ชำระเงินสำเร็จ!** {order['price']} บาท ({order['method']})\n\n"
        f"☕ **{order['name']}** ({order['sweet']}) เรียบร้อยครับ! "
        f"รับได้ที่ช่องรับเครื่องดื่มเลย 🦒"
    )
    st.button("🔄 สั่งเครื่องดื่มใหม่", on_click=clear_order)


# ============================================
# ส่วนหลัก: ตัดสินใจว่าจะแสดงหน้าไหน
# ============================================

def main():
    st.markdown(STYLE + HERO, unsafe_allow_html=True)

    handle_linepay_callback()
    order = get_order()

    if not order:
        show_menu()
    elif not order_is_paid(order):
        show_checkout(order)
    else:
        show_success(order)


main()
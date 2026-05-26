import streamlit as st
import requests
import re
from PIL import Image
import io
import base64

st.set_page_config(
    page_title="eBay 出品ツール",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- カスタムCSS ----
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #E53238 0%, #c0392b 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { margin: 0; font-size: 1.6rem; }
    .main-header p  { margin: 0.25rem 0 0; opacity: 0.85; font-size: 0.9rem; }
    .rival-box {
        background: #fff8f8;
        border: 1.5px solid #f5c0c0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        color: #155724;
    }
    .spec-tag {
        display: inline-block;
        background: #f5f5f5;
        border: 1px solid #e0e0e0;
        border-radius: 99px;
        padding: 3px 10px;
        font-size: 0.8rem;
        margin: 2px;
        color: #555;
    }
    .stButton > button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ---- ヘッダー ----
st.markdown("""
<div class="main-header">
  <h1>🛒 eBay 出品ツール</h1>
  <p>Trading API (AddItem) · ライバルセラー参照機能付き</p>
</div>
""", unsafe_allow_html=True)

# ---- Session State 初期化 ----
defaults = {
    "rival_data": None,
    "specs": [],
    "images_b64": [],
    "auth_token": "",
    "app_id": "",
    "dev_id": "",
    "cert_id": "",
    "env": "sandbox",
    "title": "",
    "category_id": "",
    "description": "",
    "cond_id": "1000",
    "rival_item_id": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---- サイドバー: 認証設定 ----
with st.sidebar:
    st.markdown("### 🔐 認証設定")

    env = st.selectbox("環境", ["sandbox", "production"],
                       format_func=lambda x: "🟡 サンドボックス (テスト)" if x == "sandbox" else "🟢 本番 (Production)")
    st.session_state["env"] = env

    site = st.selectbox("対象サイト", ["EBAY-US (SiteID: 0)", "EBAY-JP (SiteID: 101)"])
    site_id = "0" if "US" in site else "101"
    site_name = "EBAY-US" if "US" in site else "EBAY-JP"

    st.markdown("---")
    auth_token = st.text_input("Auth Token *", type="password",
                               value=st.session_state["auth_token"],
                               placeholder="AgXXXXXXXXXXXXXX...")
    app_id = st.text_input("App ID (Client ID) *",
                           value=st.session_state["app_id"],
                           placeholder="YourApp-XXXX-XXXX-...")
    dev_id = st.text_input("Dev ID",
                           value=st.session_state["dev_id"],
                           placeholder="XXXXXXXX-XXXX-...")
    cert_id = st.text_input("Cert ID",  type="password",
                            value=st.session_state["cert_id"],
                            placeholder="XXX-XXXXXXXX-XXXX-...")

    st.session_state["auth_token"] = auth_token
    st.session_state["app_id"]     = app_id
    st.session_state["dev_id"]     = dev_id
    st.session_state["cert_id"]    = cert_id

    st.markdown("---")
    if st.button("📡 接続テスト", use_container_width=True):
        if not auth_token:
            st.error("Auth Token を入力してください")
        else:
            endpoint = ("https://api.sandbox.ebay.com/ws/api.dll"
                        if env == "sandbox" else "https://api.ebay.com/ws/api.dll")
            xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GeteBayOfficialTimeRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials><eBayAuthToken>{auth_token}</eBayAuthToken></RequesterCredentials>
</GeteBayOfficialTimeRequest>"""
            try:
                resp = requests.post(endpoint, data=xml_body.encode("utf-8"), headers={
                    "Content-Type": "text/xml",
                    "X-EBAY-API-CALL-NAME": "GeteBayOfficialTime",
                    "X-EBAY-API-SITEID": site_id,
                    "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
                    "X-EBAY-API-APP-NAME": app_id,
                    "X-EBAY-API-DEV-NAME": dev_id,
                    "X-EBAY-API-CERT-NAME": cert_id,
                }, timeout=10)
                if "Success" in resp.text:
                    st.success("✅ 接続成功！")
                elif "Failure" in resp.text or "Error" in resp.text:
                    # 正規表現でエラーメッセージを抽出（XMLパースを避ける）
                    m = re.search(r"<LongMessage>(.*?)</LongMessage>", resp.text)
                    err = m.group(1) if m else resp.text[:300]
                    st.error(f"接続失敗: {err}")
                else:
                    st.warning(f"レスポンス受信（要確認）: {resp.text[:200]}")
            except Exception as e:
                st.error(f"エラー: {e}")

    st.markdown("---")
    st.caption("💡 認証情報はこのセッション内のみ保存されます")

# ==================================================================
# メインエリア: タブ
# ==================================================================
tab_item, tab_price, tab_preview = st.tabs(["📦 商品情報", "💲 価格・配送", "👁 プレビュー・出品"])

# ==================================================================
# TAB 1: 商品情報
# ==================================================================
with tab_item:

    # ---- ライバルセラー参照 ----
    st.markdown('<div class="rival-box">', unsafe_allow_html=True)
    st.markdown("#### 🔍 ライバルセラーから情報をコピー")
    st.caption("ライバルセラーのItem IDを入力すると、カテゴリ・Item Specifics・タイトル・説明文を自動取得してフォームに入力します。")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        rival_id = st.text_input("ライバルセラーのItem ID", value=st.session_state["rival_item_id"],
                                 placeholder="例: 256789012345", label_visibility="collapsed")
        st.session_state["rival_item_id"] = rival_id
    with col_btn:
        fetch_clicked = st.button("🔎 取得", use_container_width=True)

    if fetch_clicked and rival_id:
        if not app_id:
            st.error("App ID を認証設定で入力してください")
        else:
            url = (f"https://open.api.ebay.com/shopping"
                   f"?callname=GetSingleItem&responseencoding=JSON"
                   f"&appid={app_id}&siteid=0&version=967"
                   f"&ItemID={rival_id}&IncludeSelector=ItemSpecifics,Description")
            with st.spinner("eBay Shopping APIから取得中..."):
                try:
                    resp = requests.get(url, timeout=10)
                    data = resp.json()
                    if data.get("Ack") == "Failure":
                        err = data.get("Errors", [{}])[0].get("LongMessage", "APIエラー")
                        st.error(f"取得失敗: {err}")
                    elif "Item" in data:
                        st.session_state["rival_data"] = data["Item"]
                        st.success("✅ アイテム情報を取得しました！下のチェックボックスで適用する項目を選んでください。")
                    else:
                        st.error("アイテムが見つかりませんでした")
                except Exception as e:
                    st.error(f"取得エラー: {e}")

    # 取得済みデータの表示と適用
    if st.session_state["rival_data"]:
        item = st.session_state["rival_data"]
        price_info = item.get("ConvertedCurrentPrice", {})
        price_val  = price_info.get("Value", "—")
        price_cur  = price_info.get("CurrencyID", "USD")
        cat_id     = item.get("PrimaryCategoryID", "—")
        cat_name   = item.get("PrimaryCategoryName", "").split(":")[-1].strip()
        cond_map   = {"1000":"新品","1500":"新品同様","2000":"良好","2500":"普通","3000":"やや傷あり","7000":"ジャンク"}
        cond_label = cond_map.get(item.get("ConditionID",""), "—")
        specs_raw  = item.get("ItemSpecifics", {}).get("NameValueList", [])
        if isinstance(specs_raw, dict):
            specs_raw = [specs_raw]
        specs_count = len(specs_raw)

        # アイテムカード表示
        c1, c2 = st.columns([1, 3])
        with c1:
            pics = item.get("PictureURL", [])
            if isinstance(pics, str):
                pics = [pics]
            if pics:
                st.image(pics[0], width=120)
            else:
                st.markdown("📷")
        with c2:
            st.markdown(f"**{item.get('Title','—')}**")
            st.markdown(
                f"`{price_cur} {price_val}` &nbsp; "
                f"`カテゴリ: {cat_id} {cat_name}` &nbsp; "
                f"`状態: {cond_label}` &nbsp; "
                f"`仕様: {specs_count}件`",
                unsafe_allow_html=True
            )
            if specs_raw:
                preview = " · ".join(
                    f"{s['Name']}: {s['Value'][0] if isinstance(s['Value'],list) else s['Value']}"
                    for s in specs_raw[:6]
                )
                st.caption(preview)

        st.markdown("**コピーする項目を選択:**")
        cc1, cc2, cc3 = st.columns(3)
        apply_title  = cc1.checkbox("タイトル", value=True, key="ck_title")
        apply_cat    = cc1.checkbox("カテゴリID", value=True, key="ck_cat")
        apply_desc   = cc2.checkbox("説明文", value=True, key="ck_desc")
        apply_specs  = cc2.checkbox("Item Specifics", value=True, key="ck_specs")
        apply_cond   = cc3.checkbox("商品状態", value=False, key="ck_cond")
        apply_price  = cc3.checkbox("価格", value=False, key="ck_price")

        if st.button("✅ フォームに適用する", type="primary"):
            applied = []
            if apply_title and item.get("Title"):
                st.session_state["title"] = item["Title"][:80]
                applied.append("タイトル")
            if apply_cat and item.get("PrimaryCategoryID"):
                st.session_state["category_id"] = item["PrimaryCategoryID"]
                applied.append("カテゴリID")
            if apply_desc and item.get("Description"):
                st.session_state["description"] = item["Description"]
                applied.append("説明文")
            if apply_specs and specs_raw:
                st.session_state["specs"] = [
                    {"n": s["Name"],
                     "v": s["Value"][0] if isinstance(s["Value"], list) else s["Value"]}
                    for s in specs_raw if s.get("Name") and s.get("Value")
                ]
                applied.append(f"仕様{len(st.session_state['specs'])}件")
            if apply_cond and item.get("ConditionID"):
                st.session_state["cond_id"] = item["ConditionID"]
                applied.append("状態")
            if apply_price and price_val != "—":
                st.session_state["rival_price"] = price_val
                applied.append("価格")
            st.success(f"✅ {' · '.join(applied)} をフォームに適用しました")
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ---- 画像アップロード ----
    st.markdown("#### 📷 商品画像")
    uploaded_files = st.file_uploader(
        "画像をアップロード (最大12枚 · JPEG/PNG · 推奨1600×1600px以上)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="img_uploader"
    )
    if uploaded_files:
        st.session_state["images_b64"] = []
        cols = st.columns(min(len(uploaded_files), 4))
        for i, f in enumerate(uploaded_files[:12]):
            img = Image.open(f)
            cols[i % 4].image(img, use_container_width=True, caption=f"画像 {i+1}")
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            st.session_state["images_b64"].append(base64.b64encode(buf.getvalue()).decode())

    st.markdown("---")

    # ---- 基本情報 ----
    st.markdown("#### 📋 基本情報")
    title = st.text_input("商品タイトル *", value=st.session_state["title"],
                          max_chars=80, placeholder="例: Apple iPhone 15 Pro 256GB Natural Titanium Unlocked")
    st.caption(f"{len(title)}/80文字")
    st.session_state["title"] = title

    col_cat, col_sku = st.columns(2)
    with col_cat:
        CATEGORIES = {
            "": "選択してください",
            "9355": "携帯電話 (9355)",
            "31388": "スマートフォン (31388)",
            "175673": "ゲーム機 (175673)",
            "139971": "カメラ (139971)",
            "11450": "衣類・ファッション (11450)",
            "888": "スポーツ (888)",
            "267": "本・雑誌 (267)",
            "11116": "おもちゃ (11116)",
            "58058": "家電 (58058)",
            "1": "その他 (1)",
        }
        # ライバルから取得したカテゴリIDが選択肢にない場合追加
        cat_val = st.session_state.get("category_id", "")
        if cat_val and cat_val not in CATEGORIES:
            CATEGORIES[cat_val] = f"カテゴリ {cat_val} (ライバルから取得)"
        cat_keys = list(CATEGORIES.keys())
        cat_idx = cat_keys.index(cat_val) if cat_val in cat_keys else 0
        selected_cat = st.selectbox("カテゴリID *", options=cat_keys,
                                    format_func=lambda x: CATEGORIES[x], index=cat_idx)
        st.session_state["category_id"] = selected_cat
    with col_sku:
        sku = st.text_input("SKU / カスタムID", placeholder="例: ITEM-001")

    # ---- 商品状態 ----
    st.markdown("#### ⭐ 商品状態")
    COND_OPTIONS = {
        "1000": "✨ 新品",
        "1500": "📦 新品同様",
        "2000": "👍 良好",
        "2500": "🙂 普通",
        "3000": "🔧 やや傷あり",
        "7000": "⚠️ ジャンク",
    }
    cond_keys = list(COND_OPTIONS.keys())
    cond_idx = cond_keys.index(st.session_state["cond_id"]) if st.session_state["cond_id"] in cond_keys else 0
    cond_cols = st.columns(len(COND_OPTIONS))
    for i, (k, label) in enumerate(COND_OPTIONS.items()):
        if cond_cols[i].button(label, key=f"cond_{k}",
                               type="primary" if st.session_state["cond_id"] == k else "secondary"):
            st.session_state["cond_id"] = k
            st.rerun()
    cond_note = st.text_input("状態説明", placeholder="例: 外箱なし、画面に小傷あり")

    # ---- 商品説明 ----
    st.markdown("#### 📝 商品説明")
    description = st.text_area("説明文 *", value=st.session_state["description"], height=180,
                               placeholder="商品の詳細、スペック、付属品、注意事項などを記載してください。HTMLタグも使用可能です。")
    st.session_state["description"] = description

    # ---- Item Specifics ----
    st.markdown("#### 🏷️ 商品仕様 (Item Specifics)")
    col_sn, col_sv, col_sadd = st.columns([2, 2, 1])
    with col_sn:
        spec_name = st.text_input("項目名", placeholder="例: ブランド", label_visibility="collapsed", key="sn")
    with col_sv:
        spec_val = st.text_input("値", placeholder="例: Apple", label_visibility="collapsed", key="sv")
    with col_sadd:
        if st.button("➕ 追加", use_container_width=True) and spec_name and spec_val:
            st.session_state["specs"].append({"n": spec_name, "v": spec_val})
            st.rerun()

    if st.session_state["specs"]:
        st.markdown("**登録済み仕様:**")
        for i, s in enumerate(st.session_state["specs"]):
            c1, c2 = st.columns([10, 1])
            c1.markdown(f'<span class="spec-tag">{s["n"]}: {s["v"]}</span>', unsafe_allow_html=True)
            if c2.button("✕", key=f"del_spec_{i}"):
                st.session_state["specs"].pop(i)
                st.rerun()


# ==================================================================
# TAB 2: 価格・配送
# ==================================================================
with tab_price:
    st.markdown("#### 💲 出品形式・価格")
    col_lt, col_dur = st.columns(2)
    with col_lt:
        listing_type = st.selectbox("出品形式", ["FixedPriceItem", "Chinese"],
                                    format_func=lambda x: "即決価格 (Buy It Now)" if x == "FixedPriceItem" else "オークション")
    with col_dur:
        duration = st.selectbox("出品期間", ["Days_7", "Days_10", "Days_30", "GTC"],
                                format_func=lambda x: {"Days_7":"7日間","Days_10":"10日間","Days_30":"30日間","GTC":"売り切れまで (GTC)"}[x])

    col_cur, col_price, col_qty = st.columns(3)
    with col_cur:
        currency = st.selectbox("通貨", ["USD","JPY","EUR","GBP","AUD"])
    with col_price:
        default_price = float(st.session_state.get("rival_price", 0.0)) if st.session_state.get("rival_price") else 0.01
        main_price = st.number_input(
            "即決価格 *" if listing_type == "FixedPriceItem" else "予約価格",
            min_value=0.01, step=0.01, value=default_price, format="%.2f")
    with col_qty:
        quantity = st.number_input("在庫数 *", min_value=1, value=1)

    start_price = 1.00
    if listing_type == "Chinese":
        start_price = st.number_input("開始価格 *", min_value=0.01, step=0.01, value=1.00, format="%.2f")

    st.markdown("---")
    st.markdown("#### 🚚 配送設定")
    col_ship, col_cost = st.columns(2)
    with col_ship:
        shipping_option = st.selectbox("配送オプション", [
            "USPSFirstClass", "USPSPriority", "FedExGround", "UPSGround",
            "EconomyShippingFromOutsideUS", "StandardShippingFromOutsideUS", "ExpeditedShippingFromOutsideUS"
        ], format_func=lambda x: {
            "USPSFirstClass": "USPS First Class",
            "USPSPriority": "USPS Priority",
            "FedExGround": "FedEx Ground",
            "UPSGround": "UPS Ground",
            "EconomyShippingFromOutsideUS": "海外発送 (エコノミー)",
            "StandardShippingFromOutsideUS": "海外発送 (スタンダード)",
            "ExpeditedShippingFromOutsideUS": "海外発送 (速達)",
        }[x])
    with col_cost:
        free_shipping = st.checkbox("送料無料")
        shipping_cost = 0.00 if free_shipping else st.number_input("送料", min_value=0.00, step=0.01, value=0.00, format="%.2f")

    col_country, col_zip = st.columns(2)
    with col_country:
        ship_from = st.selectbox("発送元の国", ["JP","US","GB","DE","AU"],
                                 format_func=lambda x: {"JP":"🇯🇵 日本","US":"🇺🇸 アメリカ","GB":"🇬🇧 イギリス","DE":"🇩🇪 ドイツ","AU":"🇦🇺 オーストラリア"}[x])
    with col_zip:
        postal_code = st.text_input("郵便番号", placeholder="例: 100-0001")

    st.markdown("---")
    st.markdown("#### 🔄 返品・支払設定")
    col_ret, col_pay = st.columns(2)
    with col_ret:
        return_policy = st.selectbox("返品ポリシー", ["ReturnsAccepted", "ReturnsNotAccepted"],
                                     format_func=lambda x: "返品受付 (30日)" if x == "ReturnsAccepted" else "返品不可")
    with col_pay:
        payment_method = st.selectbox("支払方法", ["PayPal", "CashOnPickup"],
                                      format_func=lambda x: "PayPal" if x == "PayPal" else "現地払い")
    paypal_email = st.text_input("PayPal メールアドレス", placeholder="your@email.com")


# ==================================================================
# TAB 3: プレビュー・出品
# ==================================================================
with tab_preview:
    st.markdown("#### 👁 出品プレビュー")

    cur_sym = {"USD":"$","JPY":"¥","EUR":"€","GBP":"£","AUD":"A$"}.get(currency if 'currency' in dir() else 'USD','$')
    price_disp = f"{cur_sym}{main_price:.2f}" if 'main_price' in dir() else "—"
    cond_disp = COND_OPTIONS.get(st.session_state["cond_id"], "—")

    with st.container(border=True):
        pc1, pc2 = st.columns([1, 3])
        with pc1:
            if st.session_state["images_b64"]:
                img_bytes = base64.b64decode(st.session_state["images_b64"][0])
                st.image(img_bytes, use_container_width=True)
            else:
                st.markdown("📷 画像なし")
        with pc2:
            st.markdown(f"### {st.session_state['title'] or '商品タイトルがここに表示されます'}")
            st.markdown(f"## :red[{price_disp}]")
            st.markdown(f"状態: **{cond_disp}** &nbsp;|&nbsp; 在庫: **{quantity if 'quantity' in dir() else 1}**", unsafe_allow_html=True)

    # ---- XML生成 ----
    def build_xml():
        img_xml = "\n".join(
            f"    <URL>data:image/jpeg;base64,{b64[:50]}...</URL>"
            for b64 in st.session_state["images_b64"]
        ) or "    <!-- 画像なし -->"
        spec_xml = "\n".join(
            f"    <NameValueList><Name>{s['n']}</Name><Value>{s['v']}</Value></NameValueList>"
            for s in st.session_state["specs"]
        ) or "    <!-- 仕様なし -->"
        sp_xml = (f"<StartPrice currencyID=\"{currency}\">{start_price:.2f}</StartPrice>"
                  if listing_type == "Chinese" else "")
        return f"""<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{auth_token or '[YOUR_AUTH_TOKEN]'}</eBayAuthToken>
  </RequesterCredentials>
  <Item>
    <Title>{st.session_state['title']}</Title>
    <Description><![CDATA[{st.session_state['description']}]]></Description>
    <PrimaryCategory>
      <CategoryID>{st.session_state['category_id'] or '1'}</CategoryID>
    </PrimaryCategory>
    <ConditionID>{st.session_state['cond_id']}</ConditionID>
    <ConditionDescription>{cond_note if 'cond_note' in dir() else ''}</ConditionDescription>
    {sp_xml}
    <StartPrice currencyID="{currency}">{main_price:.2f}</StartPrice>
    <BuyItNowPrice currencyID="{currency}">{main_price:.2f}</BuyItNowPrice>
    <Quantity>{quantity}</Quantity>
    <ListingType>{listing_type}</ListingType>
    <ListingDuration>{duration}</ListingDuration>
    <Country>{ship_from if 'ship_from' in dir() else 'JP'}</Country>
    <PostalCode>{postal_code if 'postal_code' in dir() else ''}</PostalCode>
    <Currency>{currency}</Currency>
    <Site>{site_name}</Site>
    <SKU>{sku if 'sku' in dir() else ''}</SKU>
    <PictureDetails>
{img_xml}
    </PictureDetails>
    <ShippingDetails>
      <ShippingType>Flat</ShippingType>
      <ShippingServiceOptions>
        <ShippingServicePriority>1</ShippingServicePriority>
        <ShippingService>{shipping_option if 'shipping_option' in dir() else 'USPSFirstClass'}</ShippingService>
        <ShippingServiceCost currencyID="{currency}">{shipping_cost if 'shipping_cost' in dir() else 0:.2f}</ShippingServiceCost>
        <FreeShipping>{'true' if free_shipping else 'false'}</FreeShipping>
      </ShippingServiceOptions>
    </ShippingDetails>
    <ReturnPolicy>
      <ReturnsAcceptedOption>{'ReturnsNotAccepted' if return_policy=='ReturnsNotAccepted' else 'ReturnsAccepted'}</ReturnsAcceptedOption>
      <ReturnsWithinOption>Days_30</ReturnsWithinOption>
      <RefundOption>MoneyBack</RefundOption>
      <ShippingCostPaidByOption>Buyer</ShippingCostPaidByOption>
    </ReturnPolicy>
    <PaymentMethods>{payment_method if 'payment_method' in dir() else 'PayPal'}</PaymentMethods>
    <PayPalEmailAddress>{paypal_email if 'paypal_email' in dir() else ''}</PayPalEmailAddress>
    <ItemSpecifics>
{spec_xml}
    </ItemSpecifics>
  </Item>
  <WarningLevel>High</WarningLevel>
</AddItemRequest>"""

    xml_str = build_xml()

    with st.expander("📄 生成XML (Trading API リクエスト)"):
        st.code(xml_str, language="xml")
        st.download_button("💾 XMLをダウンロード", data=xml_str,
                           file_name="ebay_request.xml", mime="text/xml")

    endpoint_url = ("https://api.sandbox.ebay.com/ws/api.dll"
                    if env == "sandbox" else "https://api.ebay.com/ws/api.dll")
    curl_cmd = f"""curl -X POST "{endpoint_url}" \\
  -H "Content-Type: text/xml" \\
  -H "X-EBAY-API-CALL-NAME: AddItem" \\
  -H "X-EBAY-API-SITEID: {site_id}" \\
  -H "X-EBAY-API-COMPATIBILITY-LEVEL: 967" \\
  -H "X-EBAY-API-APP-NAME: {app_id}" \\
  -H "X-EBAY-API-DEV-NAME: {dev_id}" \\
  -H "X-EBAY-API-CERT-NAME: {cert_id}" \\
  --data @ebay_request.xml"""

    with st.expander("💻 curlコマンド"):
        st.code(curl_cmd, language="bash")

    st.markdown("---")

    # ---- 出品ボタン ----
    col_sub, col_back = st.columns([2, 1])
    with col_sub:
        submit = st.button("🚀 出品する", type="primary", use_container_width=True)
    with col_back:
        st.info(f"環境: {'🟡 サンドボックス' if env == 'sandbox' else '🟢 本番'}")

    if submit:
        errors = []
        if not auth_token:    errors.append("Auth Token")
        if not st.session_state["title"]:  errors.append("商品タイトル")
        if not st.session_state["category_id"]: errors.append("カテゴリID")
        if not main_price:    errors.append("価格")
        if errors:
            st.error(f"必須項目が未入力です: {', '.join(errors)}")
        else:
            # 実際のXML（画像はbase64フルデータ）
            img_xml_full = "\n".join(
                f"    <URL>data:image/jpeg;base64,{b64}</URL>"
                for b64 in st.session_state["images_b64"]
            ) or "    <!-- 画像なし -->"
            spec_xml_full = "\n".join(
                f"    <NameValueList><Name>{s['n']}</Name><Value>{s['v']}</Value></NameValueList>"
                for s in st.session_state["specs"]
            )
            sp_xml2 = (f"<StartPrice currencyID=\"{currency}\">{start_price:.2f}</StartPrice>"
                       if listing_type == "Chinese" else "")
            xml_submit = f"""<?xml version="1.0" encoding="utf-8"?><AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents"><RequesterCredentials><eBayAuthToken>{auth_token}</eBayAuthToken></RequesterCredentials><Item><Title>{st.session_state['title']}</Title><Description><![CDATA[{st.session_state['description']}]]></Description><PrimaryCategory><CategoryID>{st.session_state['category_id']}</CategoryID></PrimaryCategory><ConditionID>{st.session_state['cond_id']}</ConditionID>{sp_xml2}<StartPrice currencyID="{currency}">{main_price:.2f}</StartPrice><BuyItNowPrice currencyID="{currency}">{main_price:.2f}</BuyItNowPrice><Quantity>{quantity}</Quantity><ListingType>{listing_type}</ListingType><ListingDuration>{duration}</ListingDuration><Country>{ship_from}</Country><PostalCode>{postal_code}</PostalCode><Currency>{currency}</Currency><Site>{site_name}</Site><SKU>{sku}</SKU><PictureDetails>{img_xml_full}</PictureDetails><ShippingDetails><ShippingType>Flat</ShippingType><ShippingServiceOptions><ShippingServicePriority>1</ShippingServicePriority><ShippingService>{shipping_option}</ShippingService><ShippingServiceCost currencyID="{currency}">{shipping_cost:.2f}</ShippingServiceCost><FreeShipping>{'true' if free_shipping else 'false'}</FreeShipping></ShippingServiceOptions></ShippingDetails><ReturnPolicy><ReturnsAcceptedOption>{'ReturnsNotAccepted' if return_policy=='ReturnsNotAccepted' else 'ReturnsAccepted'}</ReturnsAcceptedOption><ReturnsWithinOption>Days_30</ReturnsWithinOption><RefundOption>MoneyBack</RefundOption><ShippingCostPaidByOption>Buyer</ShippingCostPaidByOption></ReturnPolicy><PaymentMethods>{payment_method}</PaymentMethods><PayPalEmailAddress>{paypal_email}</PayPalEmailAddress><ItemSpecifics>{spec_xml_full}</ItemSpecifics></Item><WarningLevel>High</WarningLevel></AddItemRequest>"""

            with st.spinner("出品リクエストを送信中..."):
                try:
                    resp = requests.post(endpoint_url, data=xml_submit.encode("utf-8"), headers={
                        "Content-Type": "text/xml",
                        "X-EBAY-API-CALL-NAME": "AddItem",
                        "X-EBAY-API-SITEID": site_id,
                        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
                        "X-EBAY-API-APP-NAME": app_id,
                        "X-EBAY-API-DEV-NAME": dev_id,
                        "X-EBAY-API-CERT-NAME": cert_id,
                    }, timeout=30)

                    with st.expander("📨 APIレスポンス", expanded=True):
                        st.code(resp.text, language="xml")

                    if "Success" in resp.text:
                        m = re.search(r"<ItemID>(\d+)</ItemID>", resp.text)
                        item_id = m.group(1) if m else None
                        st.success(f"✅ 出品成功！ アイテムID: {item_id or '(レスポンス参照)'}")
                        if item_id:
                            base_url = "https://sandbox.ebay.com" if env == "sandbox" else "https://www.ebay.com"
                            st.markdown(f"[eBayで確認する → {base_url}/itm/{item_id}]({base_url}/itm/{item_id})")
                    else:
                        m = re.search(r"<LongMessage>(.*?)</LongMessage>", resp.text)
                        err = m.group(1) if m else "詳細はレスポンスをご確認ください"
                        st.error(f"出品失敗: {err}")
                except Exception as e:
                    st.error(f"送信エラー: {e}")

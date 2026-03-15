import streamlit as st
import pandas as pd
from tradingview_ta import TA_Handler, Interval
import yfinance as yf
import pandas_ta as ta
import time
import plotly.graph_objects as go
import plotly.express as px
import io
import requests
from bs4 import BeautifulSoup
import warnings

warnings.filterwarnings('ignore')

SEKTOR_VERILERI = {
    "Technology": {"ad": "Teknoloji / Bilişim", "pddd_ort": 5.2, "buyume_2026": "%35 (Yüksek)"},
    "Financial Services": {"ad": "Finans / Bankacılık", "pddd_ort": 1.5, "buyume_2026": "%15 (Durağan)"},
    "Industrials": {"ad": "Sanayi / Üretim", "pddd_ort": 3.0, "buyume_2026": "%20 (Ilımlı)"},
    "Consumer Cyclical": {"ad": "Dayanıklı Tüketim", "pddd_ort": 2.8, "buyume_2026": "%10 (Baskılanmış)"},
    "Basic Materials": {"ad": "Hammadde / Maden", "pddd_ort": 2.2, "buyume_2026": "%25 (Emtia Destekli)"},
    "Healthcare": {"ad": "Sağlık / İlaç", "pddd_ort": 4.0, "buyume_2026": "%30 (Güçlü)"},
    "Energy": {"ad": "Enerji", "pddd_ort": 2.5, "buyume_2026": "%40 (Çok Yüksek)"},
    "Real Estate": {"ad": "Gayrimenkul (GYO)", "pddd_ort": 1.2, "buyume_2026": "%5 (Riskli)"}
}

def akilli_sayi_cevirici(deger):
    if pd.isna(deger): return 0.0
    if isinstance(deger, (int, float)): return float(deger)
    try:
        return float(str(deger).replace('.', '').replace(',', '.'))
    except Exception:
        return 0.0

def bist_temel_veri_cek(ticker):
    url = f"https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx?hisse={ticker}"
    try:
        cevap = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(cevap.text, 'html.parser')
        fk, pddd, halka_aciklik = None, None, None
        for satir in soup.find_all('tr'):
            sutunlar = satir.find_all('td')
            if len(sutunlar) == 2:
                baslik = sutunlar[0].text.strip()
                try:
                    deger = float(sutunlar[1].text.strip().replace('.', '').replace(',', '.'))
                    if baslik == "F/K": fk = deger
                    elif baslik == "PD/DD": pddd = deger
                    elif baslik == "Halka Açıklık Oranı (%)": halka_aciklik = deger
                except ValueError: pass
        return fk, pddd, halka_aciklik
    except Exception: return None, None, None

def bist_haber_cek(ticker):
    url = f"https://news.google.com/rss/search?q={ticker}+hisse+borsa&hl=tr&gl=TR&ceid=TR:tr"
    try:
        cevap = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        return [item.title.text for item in BeautifulSoup(cevap.text, 'html.parser').find_all('item')][:5]
    except Exception: return []

def get_bist100_getiri():
    try:
        xu = yf.download("XU100.IS", period="2mo", progress=False)
        if isinstance(xu.columns, pd.MultiIndex): xu.columns = xu.columns.droplevel(1)
        if len(xu) < 22: return None
        return ((xu['Close'].iloc[-1] - xu['Close'].iloc[-21]) / xu['Close'].iloc[-21]) * 100
    except Exception: return None

def master_analiz(ticker, maliyet=0.0, kz=0.0, bist100_getiri=None):
    ticker_sembol = str(ticker).strip().upper()
    is_us_stock = ticker_sembol in ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "NVDA"]
    tv_exchange, tv_screener = ("NASDAQ", "america") if is_us_stock else ("BIST", "turkey")
    yf_ticker = ticker_sembol if is_us_stock else (ticker_sembol + ".IS" if not ticker_sembol.endswith(".IS") else ticker_sembol)

    olumlu_yonler, olumsuz_yonler = [], []
    puan, sektor_ing = 0, "Bilinmiyor"
    df_hist = pd.DataFrame()
    stop_loss, take_profit, anlik_fiyat, volatilite = None, None, None, None

    # --- 1. YFINANCE (Grafik, Hacim, Bollinger, BİST100 Kıyaslaması) ---
    for _ in range(2):
        try:
            hisse_yf = yf.Ticker(yf_ticker)
            df_hist = hisse_yf.history(period="1y")
            if not df_hist.empty and len(df_hist) > 50:
                if isinstance(df_hist.columns, pd.MultiIndex): df_hist.columns = df_hist.columns.droplevel(1)
                anlik_fiyat = float(df_hist['Close'].iloc[-1])
                
                df_hist.ta.atr(length=14, append=True)
                atr_col = [c for c in df_hist.columns if 'ATR' in c]
                if atr_col:
                    atr_degeri = df_hist[atr_col[0]].iloc[-1]
                    stop_loss, take_profit = anlik_fiyat - (1.5 * atr_degeri), anlik_fiyat + (2.0 * atr_degeri)
                
                volatilite = float(df_hist['Close'].pct_change().std() * 100)
                sektor_ing = hisse_yf.info.get('sector', 'Bilinmiyor')

                if 'Volume' in df_hist.columns:
                    son_hacim, ort_hacim = df_hist['Volume'].iloc[-1], df_hist['Volume'].tail(20).mean()
                    if son_hacim > (ort_hacim * 2) and ort_hacim > 0:
                        olumlu_yonler.append("🔥 Hacim Patlaması: Son işlem gününde hacim 20 günlük ortalamanın 2 katına ulaştı!")
                        puan += 1

                df_hist.ta.bbands(length=20, append=True)
                bbu_c, bbl_c, bbm_c = [c for c in df_hist.columns if 'BBU' in c], [c for c in df_hist.columns if 'BBL' in c], [c for c in df_hist.columns if 'BBM' in c]
                if bbu_c and bbl_c and bbm_c:
                    bant_genisligi = (df_hist[bbu_c[0]] - df_hist[bbl_c[0]]) / df_hist[bbm_c[0]]
                    if bant_genisligi.iloc[-1] <= bant_genisligi.tail(120).min() * 1.1:
                        olumlu_yonler.append("⚡ Bollinger Sıkışması: Hissede fiyat son 6 ayın en dar aralığına sıkıştı, kırılım gelebilir.")

                if not is_us_stock and bist100_getiri is not None and len(df_hist) > 22:
                    hisse_getiri = ((anlik_fiyat - df_hist['Close'].iloc[-21]) / df_hist['Close'].iloc[-21]) * 100
                    if hisse_getiri > bist100_getiri + 5:
                        olumlu_yonler.append("🏆 Göreceli Güç: Son 1 ayda BİST100 endeksinden daha fazla kazandırdı."); puan += 1
                    elif hisse_getiri < bist100_getiri - 5:
                        olumsuz_yonler.append("🐢 Göreceli Güç: Son 1 ayda BİST100 piyasa endeksinin gerisinde kaldı."); puan -= 1
            break
        except Exception: time.sleep(0.5)

    # --- 2. TEMEL ANALİZ, HABERLER VE EKSİK OLAN "TAHTA DERİNLİĞİ" KONTROLÜ ---
    try:
        if is_us_stock:
            info = yf.Ticker(yf_ticker).info
            fk_degeri = info.get('trailingPE')
            pddd_degeri = info.get('priceToBook')
            
            # US Hisseler İçin Tahta Derinliği
            shares_out = info.get('sharesOutstanding')
            float_shares = info.get('floatShares')
            if shares_out and float_shares:
                halka_aciklik = (float_shares / shares_out) * 100
            else:
                halka_aciklik = None
        else:
            # BİST Hisseler İçin Tahta Derinliği Eklendi (halka_aciklik artık çekiliyor)
            fk_degeri, pddd_degeri, halka_aciklik = bist_temel_veri_cek(ticker_sembol)
            
            haberler = bist_haber_cek(ticker_sembol)
            if haberler:
                skor = sum(1 for h in haberler if any(k in h.lower() for k in ['kar', 'büyüme', 'ihale', 'temettü', 'yatırım'])) - sum(1 for h in haberler if any(k in h.lower() for k in ['zarar', 'düşüş', 'ceza', 'dava']))
                if skor > 0: olumlu_yonler.append("📰 Haberler: Türkçe haber akışı olumlu yönde.")
                elif skor < 0: olumsuz_yonler.append("📰 Haberler: Türkçe haber akışı olumsuz (riskli) yönde.")

        # Temel Değerler (Kelepir)
        if fk_degeri and pddd_degeri:
            if fk_degeri < 15 and pddd_degeri < 2:
                olumlu_yonler.append(f"💎 Değer Hissesi: F/K ({fk_degeri:.1f}) ve PD/DD ({pddd_degeri:.1f}) çarpanlarına göre piyasada ucuz."); puan += 2
            elif fk_degeri > 25 or pddd_degeri > 5:
                olumsuz_yonler.append(f"🏢 Pahalı Çarpanlar: F/K ({fk_degeri:.1f}) veya PD/DD ({pddd_degeri:.1f}) oranları oldukça şişkin."); puan -= 1

        # Gözden Kaçan Tahta Derinliği (Fiili Dolaşım) Eklentisi!
        if halka_aciklik is not None:
            if halka_aciklik < 15:
                olumsuz_yonler.append(f"💧 Tahta Derinliği: Halka açıklık çok düşük (%{halka_aciklik:.1f}). Sığ tahta, fiyat çok hızlı manipüle edilebilir.")
            elif halka_aciklik > 80:
                olumsuz_yonler.append(f"🌊 Tahta Derinliği: Halka açıklık çok yüksek (%{halka_aciklik:.1f}). Hantal tahta, hissenin yükselmesi çok zor olabilir.")
            else:
                olumlu_yonler.append(f"⚖️ Tahta Derinliği: Halka açıklık oranı (%{halka_aciklik:.1f}) oldukça dengeli ve ideal.")

    except Exception: pass

    # Portföy Maliyet Uyarısı
    if maliyet > 0 and anlik_fiyat is not None:
        if stop_loss and stop_loss > maliyet:
            olumlu_yonler.append(f"🛡️ Akıllı Stop: Zarar Kes seviyesi ({stop_loss:.2f}), sizin maliyetinizin ({maliyet:.2f}) üzerinde! (Kârda Stop)")
        elif anlik_fiyat < maliyet:
            olumsuz_yonler.append(f"⚠️ Maliyet Uyarısı: Hisse şu an sizin alış maliyetinizin altında işlem görüyor.")

    # --- 3. TRADINGVIEW TEKNİK ANALİZ ---
    for _ in range(2):
        try:
            analiz = TA_Handler(symbol=ticker_sembol, screener=tv_screener, exchange=tv_exchange, interval=Interval.INTERVAL_1_DAY).get_analysis()
            durum = analiz.summary.get("RECOMMENDATION")
            al, sat = analiz.summary.get("BUY", 0), analiz.summary.get("SELL", 0)
            if durum == "STRONG_BUY": puan += 2
            elif durum == "BUY": puan += 1
            elif durum == "SELL": puan -= 1
            elif durum == "STRONG_SELL": puan -= 2
            
            if al > sat: olumlu_yonler.append(f"📊 Teknik: 26 teknik indikatörden {al} tanesi 'AL' sinyali veriyor.")
            if sat > 0: olumsuz_yonler.append(f"⚠️ Teknik: 26 teknik indikatörden {sat} tanesi 'SAT' sinyali veriyor.")
            break 
        except Exception: time.sleep(0.5)

    karar = "Ekleme Yap" if puan >= 2 else "Sat" if puan <= -2 else "Tut"
    if not olumlu_yonler: olumlu_yonler.append("Belirgin pozitif bir sinyal bulunamadı.")
    if not olumsuz_yonler: olumsuz_yonler.append("Belirgin negatif bir sinyal bulunamadı.")

    return {
        "Hisse": ticker_sembol, "Karar": karar, "Sektör": SEKTOR_VERILERI.get(sektor_ing, {}).get("ad", sektor_ing), 
        "Olumlu": olumlu_yonler, "Olumsuz": olumsuz_yonler, "Fiyat": anlik_fiyat, "Maliyet": maliyet, "KZ": kz,
        "Stop_Loss": stop_loss, "Take_Profit": take_profit, "Volatilite": volatilite, "Gecmis_Veri": df_hist
    }

# --- KULLANICI ARAYÜZÜ (UI) ---
st.set_page_config(layout="wide", page_title="Yapay Zeka Robo-Danışman") 
st.title("🤖 Yapay Zeka Robo-Danışman (Pro Sürüm)")
st.write("Maliyet analizi, teknik ve temel verilerle %100 Türkçe portföy yönetimi.")

uploaded_file = st.file_uploader("Excel veya CSV Formatında Portföy Dosyanızı Yükleyin", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            uploaded_file.seek(0)
            ilk_satir = uploaded_file.read().decode('utf-8').split('\n')[0]
            uploaded_file.seek(0)
            ayirici = ';' if ';' in ilk_satir else ','
            df_excel = pd.read_csv(uploaded_file, sep=ayirici)
        else:
            df_excel = pd.read_excel(uploaded_file)
            
        df_excel.columns = df_excel.columns.str.strip().str.replace('\ufeff', '')
    except Exception:
        st.error("Dosya okunamadı. Lütfen geçerli bir Excel veya CSV dosyası yüklediğinizden emin olun.")
        st.stop()
    
    hisse_col = next((c for c in df_excel.columns if 'hisse' in c.lower() or 'sembol' in c.lower()), None)
    maliyet_col = next((c for c in df_excel.columns if 'maliyet' in c.lower()), None)
    kz_col = next((c for c in df_excel.columns if 'k/z' in c.lower() or 'kz' in c.lower() or 'kar' in c.lower()), None)

    if not hisse_col:
        st.error("Yüklediğiniz dosyada 'Hisse' sütunu bulunamadı. Lütfen kontrol edip tekrar deneyin.")
    else:
        st.write("---")
        st.write("### ⚙️ Hisseleriniz İçin Derin Analiz Yapılıyor (Lütfen Bekleyin)...")
        bist100_getiri = get_bist100_getiri()
        
        results, fiyat_gecmisleri = [], {}
        progress_bar = st.progress(0)
        total_stocks = len(df_excel)
        
        for index, row in df_excel.iterrows():
            try:
                ticker = row[hisse_col]
                if pd.isna(ticker): continue
                
                maliyet_degeri = akilli_sayi_cevirici(row[maliyet_col]) if maliyet_col else 0.0
                kz_degeri = akilli_sayi_cevirici(row[kz_col]) if kz_col else 0.0
                
                analiz_sonucu = master_analiz(ticker, maliyet=maliyet_degeri, kz=kz_degeri, bist100_getiri=bist100_getiri)
                results.append(analiz_sonucu)
                
                if not analiz_sonucu["Gecmis_Veri"].empty:
                    fiyat_gecmisleri[analiz_sonucu["Hisse"]] = analiz_sonucu["Gecmis_Veri"]["Close"]
            except Exception: pass
                
            progress_bar.progress((index + 1) / total_stocks)
            
        st.success("Tüm Portföy Analizi Başarıyla Tamamlandı!")
        
        if not results:
            st.warning("Hiçbir hisse başarıyla analiz edilemedi. Lütfen hisse kodlarını kontrol edin.")
            st.stop()
            
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Karar Dağılımı", "⚖️ Risk ve Sepet Dağılımı", "🕸️ Hisse Korelasyonu", "📈 Grafikler ve Detaylı Analiz"])
        results_df = pd.DataFrame(results)
        
        with tab1:
            st.write("### Yapay Zeka Strateji Dağılımı")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.success("🟢 EKLEME YAP (AL)")
                hisseler_al = results_df[results_df["Karar"] == "Ekleme Yap"]
                if not hisseler_al.empty: st.dataframe(hisseler_al[["Hisse", "Sektör"]], hide_index=True)
            with col2:
                st.warning("🟡 TUT (BEKLE)")
                hisseler_tut = results_df[results_df["Karar"] == "Tut"]
                if not hisseler_tut.empty: st.dataframe(hisseler_tut[["Hisse", "Sektör"]], hide_index=True)
            with col3:
                st.error("🔴 SAT (ZARAR KES)")
                hisseler_sat = results_df[results_df["Karar"] == "Sat"]
                if not hisseler_sat.empty: st.dataframe(hisseler_sat[["Hisse", "Sektör"]], hide_index=True)

        with tab2:
            st.write("### 🧠 Riske Göre Akıllı Portföy Ağırlığı")
            gecerli_hisseler = [r for r in results if r["Volatilite"] is not None and r["Volatilite"] > 0]
            if gecerli_hisseler:
                ters_vol_toplami = sum(1 / r["Volatilite"] for r in gecerli_hisseler)
                agirliklar = [{"Hisse": r["Hisse"], "Ağırlık (%)": ((1 / r["Volatilite"]) / ters_vol_toplami) * 100} for r in gecerli_hisseler]
                st.plotly_chart(px.pie(pd.DataFrame(agirliklar), values='Ağırlık (%)', names='Hisse', title='Riski Düşük Hisselere Daha Fazla Bütçe Önerisi', hole=0.4), use_container_width=True)

        with tab3:
            st.write("### 🕸️ Hisse Yön Korelasyonu (Birlikte Hareket Etme Durumu)")
            if len(fiyat_gecmisleri) > 1:
                st.plotly_chart(px.imshow(pd.DataFrame(fiyat_gecmisleri).dropna().corr(), text_auto=".2f", aspect="auto", color_continuous_scale='RdBu_r'), use_container_width=True)

        with tab4:
            st.write("### 🔍 Portföyünüzdeki Hisselerin Detaylı Röntgeni")
            for item in results:
                ikon = "🟢" if item["Karar"] == "Ekleme Yap" else "🔴" if item["Karar"] == "Sat" else "🟡"
                with st.expander(f"{ikon} {item['Hisse']} - Yapay Zeka Kararı: {item['Karar']}"):
                    
                    if item['Maliyet'] > 0:
                        # EKSİK OLAN K/Z RENKLENDİRMESİ BURAYA EKLENDİ!
                        kz_renk = "green" if item['KZ'] >= 0 else "red"
                        isaret = "+" if item['KZ'] > 0 else ""
                        st.markdown(f"💰 **Sizin Maliyetiniz:** `{item['Maliyet']:.2f} TL` | 📉 **Net Kar/Zarar:** :{kz_renk}[**{isaret}{item['KZ']:.2f} TL**]")
                        
                    if item['Fiyat'] is not None:
                        st.markdown(f"**Anlık Fiyat:** `{item['Fiyat']:.2f} TL` | 🛡️ **Zarar Kes (Stop-Loss):** `{item['Stop_Loss']:.2f}` | 🎯 **Kar Al Hedefi:** `{item['Take_Profit']:.2f}`")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("#### ✅ Olumlu Sinyaller")
                        for y in item["Olumlu"]: st.success(f"- {y}")
                    with c2:
                        st.markdown("#### ❌ Olumsuz Sinyaller")
                        for y in item["Olumsuz"]: st.error(f"- {y}")
                    
                    if not item["Gecmis_Veri"].empty:
                        df_plot = item["Gecmis_Veri"].tail(90)
                        
                        fig = go.Figure(data=[go.Candlestick(
                            x=df_plot.index, 
                            open=df_plot['Open'], 
                            high=df_plot['High'], 
                            low=df_plot['Low'], 
                            close=df_plot['Close'], 
                            name="Fiyat Hareketi"
                        )])
                        
                        fig.update_layout(
                            xaxis_rangeslider_visible=False, 
                            height=400, 
                            margin=dict(l=0, r=0, t=30, b=0),
                            xaxis_title="Tarih",
                            yaxis_title="Fiyat (TL)"
                        )
                        
                        if item['Stop_Loss']:
                            fig.add_hline(y=item['Stop_Loss'], line_dash="dot", annotation_text="Zarar Kes Seviyesi", line_color="red")
                            fig.add_hline(y=item['Take_Profit'], line_dash="dot", annotation_text="Kar Al Seviyesi", line_color="green")
                        if item['Maliyet'] > 0:
                            fig.add_hline(y=item['Maliyet'], line_dash="solid", annotation_text="SİZİN MALİYETİNİZ", line_color="blue")
                            
                        st.plotly_chart(fig, use_container_width=True)

        st.write("---")
        df_rapor = pd.DataFrame([{"Hisse": r["Hisse"], "Yapay Zeka Kararı": r["Karar"], "Maliyetiniz": r["Maliyet"], "Kar/Zarar Durumu": r["KZ"], "Anlık Fiyat": round(r["Fiyat"], 2) if r["Fiyat"] else "Veri Yok", "Zarar Kes (Stop)": round(r["Stop_Loss"], 2) if r["Stop_Loss"] else "Veri Yok"} for r in results])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer: df_rapor.to_excel(writer, index=False, sheet_name='Detaylı Analiz Raporu')
        st.download_button(label="📁 Tüm Portföy Analizini Excel Olarak Bilgisayara İndir", data=output.getvalue(), file_name="Turkce_RoboDanisman_Raporu.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_cors import CORS
import requests
import os
import time
import threading
from dotenv import load_dotenv

load_dotenv()  # .env dosyasını yükler

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "salgintakip-gizli-2025")
CORS(app)

# =====================================================================
# CACHE — sık değişmeyen veriler için (TTL saniye cinsinden)
# =====================================================================
_cache = {}
_cache_lock = threading.Lock()

def cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if item and time.time() < item["expires"]:
            return item["data"]
    return None

def cache_set(key, data, ttl=300):  # varsayılan 5 dakika
    with _cache_lock:
        _cache[key] = {"data": data, "expires": time.time() + ttl}

def cached_route(key, ttl=300):
    """Decorator: sonucu cache'e alır, TTL dolana kadar Supabase'e gitme."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            full_key = key + "?" + request.query_string.decode()
            hit = cache_get(full_key)
            if hit is not None:
                return jsonify(hit)
            result = fn(*args, **kwargs)
            try:
                cache_set(full_key, result.get_json(), ttl)
            except Exception:
                pass
            return result
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

# =====================================================================
# SUPABASE REST API (PostgREST) — HTTPS, 443 portu, yurt ağında çalışır
# =====================================================================
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation"
}

def sb_get(table, params=None, select="*"):
    """Supabase REST GET isteği"""
    p = {"select": select}
    if params:
        p.update(params)
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=p)
    r.raise_for_status()
    return r.json()

def sb_rpc(func_name, body=None):
    """Supabase RPC (PostgreSQL fonksiyon çağrısı)"""
    r = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/{func_name}",
                      headers=HEADERS, json=body or {})
    r.raise_for_status()
    return r.json()

def sb_post(table, data):
    """Supabase REST POST (INSERT)"""
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}",
                      headers=HEADERS, json=data)
    r.raise_for_status()
    return r.json()

# =====================================================================
# ROUTES
# =====================================================================

@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect(url_for("login_sayfasi"))
    return render_template("index.html")

@app.route("/login")
def login_sayfasi():
    if session.get("user_id"):
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/api/ozet")
@cached_route("ozet", ttl=60)  # 1 dakika (sık güncellenen)
def api_ozet():
    try:
        d        = sb_rpc("get_ozet")
        toplam   = d.get("toplam_vaka", 0) or 0
        iyilesen = d.get("toplam_iyilesen", 0) or 0
        vefat    = d.get("toplam_vefat", 0) or 0
        aktif    = max(0, toplam - iyilesen - vefat)
        toplam_yatak = d.get("toplam_yatak", 0) or 0
        doluluk  = round(aktif / toplam_yatak * 100, 1) if toplam_yatak > 0 else 0

        return jsonify({
            "aktif_vaka":        aktif,
            "toplam_iyilesen":   iyilesen,
            "toplam_vefat":      vefat,
            "toplam_vaka":       toplam,
            "yatak_doluluk_pct": doluluk,
            "toplam_yatak":      toplam_yatak,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/gunluk_trend")
@cached_route("gunluk_trend", ttl=120)  # 2 dakika
def api_gunluk_trend():
    try:
        donem    = request.args.get("donem", "Son 30 gün")
        bolge    = request.args.get("bolge", "").strip()
        hastalik = request.args.get("hastalik", "").strip()

        gun = {"Son 7 gün": 7, "Son 30 gün": 30, "Son 90 gün": 90}.get(donem, 30)

        bolge_id    = None
        hastalik_id = None
        if bolge:
            b = sb_get("bolge", {"bolge_adi": f"eq.{bolge}"}, "bolge_id")
            if b: bolge_id = b[0]["bolge_id"]
        if hastalik:
            h = sb_get("hastalik", {"hastalik_adi": f"eq.{hastalik}"}, "hastalik_id")
            if h: hastalik_id = h[0]["hastalik_id"]

        rows = sb_rpc("get_gunluk_trend", {
            "p_gun":        gun,
            "p_bolge_id":   bolge_id,
            "p_hastalik_id": hastalik_id,
        })

        gunler, yeni_l, iyilesen_l, vefat_l = [], [], [], []
        for r in rows:
            gunler.append(r["tarih"][5:])  # MM-DD
            yeni_l.append(r["yeni"])
            iyilesen_l.append(r["iyilesen"])
            vefat_l.append(r["vefat"])

        return jsonify({"gunler": gunler, "yeni": yeni_l,
                        "iyilesen": iyilesen_l, "vefat": vefat_l})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hastalik_dagilim")
@cached_route("hastalik_dagilim", ttl=300)  # 5 dakika
def api_hastalik_dagilim():
    COLORS = ["#00d4ff", "#22d3a5", "#f97316", "#a78bfa", "#fbbf24", "#f43f5e"]
    try:
        rows = sb_rpc("get_hastalik_dagilim")
        return jsonify({
            "labels": [r["hastalik_adi"] for r in rows],
            "values": [r["toplam"]       for r in rows],
            "colors": COLORS[:len(rows)],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/kapasite")
@cached_route("kapasite", ttl=60)  # 1 dakika
def api_kapasite():
    try:
        rows = sb_rpc("get_kapasite")
        return jsonify([{
            "bolge":        r["bolge_adi"],
            "toplam_yatak": r["toplam_yatak"],
            "ybu_yatak":    r["ybu_yatak"],
            "aktif_vaka":   r["aktif_vaka"],
            "doluluk":      r["doluluk"],
            "risk":         r["risk"],
        } for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hastalik_detay")
@cached_route("hastalik_detay", ttl=600)  # 10 dakika (nadiren değişir)
def api_hastalik_detay():
    try:
        rows = sb_get("hastalik",
                      {"order": "risk_seviyesi.desc"},
                      "hastalik_adi,icd10_kodu,bulasma_sekli,ortalama_kulucka,risk_seviyesi,bulasicilik_r0,olumculuk_orani")
        return jsonify([{
            "hastalik_adi":    r["hastalik_adi"],
            "icd10_kodu":      r.get("icd10_kodu") or "-",
            "bulasma_sekli":   r.get("bulasma_sekli") or "-",
            "ortalama_kulucka": float(r["ortalama_kulucka"]) if r.get("ortalama_kulucka") else 0,
            "risk_seviyesi":   int(r["risk_seviyesi"]) if r.get("risk_seviyesi") else 0,
            "bulasicilik":     float(r["bulasicilik_r0"]) if r.get("bulasicilik_r0") else 0,
            "olumculuk":       float(r["olumculuk_orani"]) if r.get("olumculuk_orani") else 0,
        } for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hastane_detay")
@cached_route("hastane_detay", ttl=600)  # 10 dakika
def api_hastane_detay():
    try:
        hastaneler = sb_get("hastane",
                            select="hastane_adi,hastane_turu,yatak_kapasitesi,yogun_bakim_kapasitesi,solunum_cihazi,aktif_personel_sayisi,bolge_id")
        bolgeler   = {b["bolge_id"]: b["bolge_adi"]
                      for b in sb_get("bolge", select="bolge_id,bolge_adi")}
        return jsonify([{
            "hastane_adi": h["hastane_adi"],
            "bolge":       bolgeler.get(h["bolge_id"], "-"),
            "tur":         h.get("hastane_turu") or "-",
            "yatak":       int(h.get("yatak_kapasitesi") or 0),
            "ybu":         int(h.get("yogun_bakim_kapasitesi") or 0),
            "solunum":     int(h.get("solunum_cihazi") or 0),
            "personel":    int(h.get("aktif_personel_sayisi") or 0),
        } for h in hastaneler])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tedbirler")
@cached_route("tedbirler", ttl=300)  # 5 dakika
def api_tedbirler():
    try:
        bolge_filter = request.args.get("bolge", "").strip()
        bt_rows = sb_get("bolge_tedbir",
                         select="bolge_id,tedbir_id,baslangic_tarihi,bitis_tarihi")
        bolgeler  = {b["bolge_id"]: b["bolge_adi"]
                     for b in sb_get("bolge", select="bolge_id,bolge_adi")}
        tedbirler = {t["tedbir_id"]: t
                     for t in sb_get("tedbir", select="tedbir_id,tedbir_adi,etki_seviyesi")}
        result = []
        for bt in bt_rows:
            bolge_adi = bolgeler.get(bt["bolge_id"], "-")
            if bolge_filter and bolge_adi != bolge_filter:
                continue
            t = tedbirler.get(bt["tedbir_id"], {})
            bitis = bt.get("bitis_tarihi")
            result.append({
                "bolge":        bolge_adi,
                "tedbir_adi":   t.get("tedbir_adi", "-"),
                "etki_seviyesi": t.get("etki_seviyesi", "-"),
                "baslangic":    (bt.get("baslangic_tarihi") or "-")[:10],
                "bitis":        bitis[:10] if bitis else "Devam ediyor",
                "durum":        "Aktif" if not bitis else "Tamamlandı",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/personel")
@cached_route("personel", ttl=300)  # 5 dakika
def api_personel():
    try:
        bolge_filter = request.args.get("bolge", "").strip()
        unvan_filter = request.args.get("unvan", "").strip()

        params = {"select": "ad_soyad,unvan,departman,vardiya,ise_baslama_tarihi,aktif_mi,hastane_id"}
        if unvan_filter:
            params["unvan"] = f"eq.{unvan_filter}"
        personeller = sb_get("personel", params)

        hastaneler = {h["hastane_id"]: h
                      for h in sb_get("hastane", select="hastane_id,hastane_adi,bolge_id")}
        bolgeler   = {b["bolge_id"]: b["bolge_adi"]
                      for b in sb_get("bolge", select="bolge_id,bolge_adi")}

        result = []
        for p in personeller:
            h = hastaneler.get(p.get("hastane_id"), {})
            bolge_adi = bolgeler.get(h.get("bolge_id"), "-")
            if bolge_filter and bolge_adi != bolge_filter:
                continue
            result.append({
                "ad_soyad":  p["ad_soyad"],
                "unvan":     p.get("unvan", "-"),
                "departman": p.get("departman", "-"),
                "vardiya":   p.get("vardiya", "-"),
                "hastane":   h.get("hastane_adi", "-"),
                "bolge":     bolge_adi,
                "tarih":     (p.get("ise_baslama_tarihi") or "-")[:10],
                "aktif":     bool(p.get("aktif_mi", True)),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/vaka_log")
@cached_route("vaka_log", ttl=30)  # 30 saniye (log sık güncellenir)
def api_vaka_log():
    try:
        rows = sb_get("vaka_log",
                      {"order": "log_id.desc", "limit": "100"},
                      "log_id,bildirim_id,islem_tipi,islem_tarihi,eski_vaka_sayisi,yeni_vaka_sayisi")
        return jsonify([{
            "log_id":       r["log_id"],
            "bildirim_id":  r["bildirim_id"],
            "islem_tipi":   r.get("islem_tipi", "-"),
            "islem_tarihi": (r.get("islem_tarihi") or "-")[:19],
            "eski_vaka":    r.get("eski_vaka_sayisi"),
            "yeni_vaka":    r.get("yeni_vaka_sayisi"),
        } for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/vaka_bildir", methods=["POST"])
def api_vaka_bildir():
    try:
        data     = request.get_json()
        tarih    = data.get("tarih")
        bolge    = data.get("bolge")
        hastalik = data.get("hastalik")
        yas      = data.get("yas")
        cinsiyet = data.get("cinsiyet", "E")
        kronik   = data.get("kronik", "Yok") == "Var"
        yeni     = int(data.get("yeni_vaka", 1))
        iyilesen = int(data.get("iyilesen_sayisi", 0))
        vefat    = int(data.get("vefat_sayisi", 0))

        if not tarih or not bolge or not hastalik:
            return jsonify({"error": "Tarih, bölge ve hastalık zorunludur"}), 400

        bolgeler   = sb_get("bolge",    {"bolge_adi":    f"eq.{bolge}"},    "bolge_id")
        hastalikar = sb_get("hastalik", {"hastalik_adi": f"eq.{hastalik}"}, "hastalik_id")

        if not bolgeler:   return jsonify({"error": f"Bölge bulunamadı: {bolge}"}), 400
        if not hastalikar: return jsonify({"error": f"Hastalık bulunamadı: {hastalik}"}), 400

        bolge_id    = bolgeler[0]["bolge_id"]
        hastalik_id = hastalikar[0]["hastalik_id"]

        # Demografik grup bul — bulunamazsa ilk grubu kullan
        gruplar = sb_get("demografik_grup",
                         {"yas_araligi": f"eq.{yas}", "cinsiyet": f"eq.{cinsiyet}"},
                         "grup_id")
        if not gruplar:
            gruplar = sb_get("demografik_grup", select="grup_id")
        grup_id = gruplar[0]["grup_id"] if gruplar else 1

        # Bölgedeki ilk hastaneyi bul
        hastaneler = sb_get("hastane", {"bolge_id": f"eq.{bolge_id}"}, "hastane_id")
        if not hastaneler:
            return jsonify({"error": "Bu bölgede hastane bulunamadı"}), 400
        hastane_id = hastaneler[0]["hastane_id"]

        sb_post("vaka_bildirimi", {
            "bildirim_tarihi":  tarih,
            "bolge_id":         bolge_id,
            "hastalik_id":      hastalik_id,
            "grup_id":          grup_id,
            "hastane_id":       hastane_id,
            "yeni_vaka_sayisi": yeni,
            "iyilesen_sayisi":  iyilesen,
            "vefat_sayisi":     vefat,
        })
        return jsonify({"success": True,
                        "mesaj": f"✅ Vaka kaydedildi: {tarih}, {bolge}, {hastalik}, {yeni} yeni vaka"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/iller")
def api_iller():
    try:
        bolge = request.args.get("bolge", "").strip()
        if bolge:
            bolgeler = sb_get("bolge", {"bolge_adi": f"eq.{bolge}"}, "bolge_id")
            if not bolgeler:
                return jsonify([])
            bolge_id = bolgeler[0]["bolge_id"]
            rows = sb_get("il", {"bolge_id": f"eq.{bolge_id}"}, "il_id,il_adi")
        else:
            rows = sb_get("il", select="il_id,il_adi,bolge_id")
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/hastane_ekle", methods=["POST"])
def api_hastane_ekle():
    try:
        d = request.get_json()
        il_adi = d.get("il")
        iller = sb_get("il", {"il_adi": f"eq.{il_adi}"}, "il_id,bolge_id")
        if not iller:
            return jsonify({"success": False, "message": f"'{il_adi}' ili bulunamadı"}), 400
        il_id    = iller[0]["il_id"]
        bolge_id = iller[0]["bolge_id"]
        sb_post("hastane", {
            "hastane_adi":             d.get("hastane_adi"),
            "hastane_turu":            d.get("tur"),
            "bolge_id":                bolge_id,
            "il_id":                   il_id,
            "yatak_kapasitesi":        int(d.get("yatak_kapasitesi", 0)),
            "yogun_bakim_kapasitesi":  int(d.get("yogun_bakim_kapasitesi", 0)),
            "solunum_cihazi":          int(d.get("solunum_cihazi", 0)),
            "aktif_personel_sayisi":   int(d.get("aktif_personel_sayisi", 0)),
        })
        return jsonify({"success": True, "mesaj": f"✅ {d.get('hastane_adi')} eklendi."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/personel_ekle", methods=["POST"])
def api_personel_ekle():
    try:
        d = request.get_json()
        hastane_adi = d.get("hastane", "").strip()
        if not hastane_adi:
            return jsonify({"success": False, "message": "Hastane seçilmedi"}), 400

        hastaneler = sb_get("hastane", {"hastane_adi": f"eq.{hastane_adi}"}, "hastane_id")
        if not hastaneler:
            return jsonify({"success": False, "message": f"'{hastane_adi}' hastanesi bulunamadı"}), 400

        ad_soyad = d.get("ad_soyad", "").strip()
        if not ad_soyad:
            return jsonify({"success": False, "message": "Ad soyad boş olamaz"}), 400

        sb_post("personel", {
            "ad_soyad":           ad_soyad,
            "unvan":              d.get("unvan", "Doktor"),
            "departman":          d.get("departman", "").strip(),
            "vardiya":            d.get("vardiya", "Gündüz"),
            "hastane_id":         hastaneler[0]["hastane_id"],
            "ise_baslama_tarihi": d.get("ise_baslama_tarihi"),
            "aktif_mi":           True,
        })
        return jsonify({"success": True, "mesaj": f"✅ {ad_soyad} personel olarak eklendi."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/hastane_guncelle", methods=["POST"])
def api_hastane_guncelle():
    try:
        d = request.get_json()
        hastane_adi = d.get("hastane_adi")
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/hastane?hastane_adi=eq.{hastane_adi}",
            headers=HEADERS,
            json={
                "yatak_kapasitesi":        int(d.get("yatak_kapasitesi", 0)),
                "yogun_bakim_kapasitesi":  int(d.get("yogun_bakim_kapasitesi", 0)),
                "solunum_cihazi":          int(d.get("solunum_cihazi", 0)),
                "aktif_personel_sayisi":   int(d.get("aktif_personel_sayisi", 0)),
            }
        )
        r.raise_for_status()
        # Cache'i temizle
        cache_set("kapasite?", None, ttl=0)
        return jsonify({"success": True, "mesaj": f"✅ {hastane_adi} güncellendi."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/hastaneler")
def api_admin_hastaneler():
    try:
        rows = sb_get("hastane", select="hastane_adi,bolge_id,yatak_kapasitesi,yogun_bakim_kapasitesi,solunum_cihazi,aktif_personel_sayisi")
        bolgeler = {b["bolge_id"]: b["bolge_adi"] for b in sb_get("bolge", select="bolge_id,bolge_adi")}
        return jsonify([{**r, "bolge_adi": bolgeler.get(r["bolge_id"], "-")} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data     = request.get_json()
        email    = data.get("email", "").strip()
        password = data.get("password", "")
        role     = data.get("role", "vatandas")

        if not email or not password:
            return jsonify({"success": False, "message": "E-posta ve şifre boş bırakılamaz."}), 400

        # Supabase Auth — email+password ile giriş
        r = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": password}
        )

        if r.status_code != 200:
            return jsonify({"success": False, "message": "E-posta veya şifre hatalı."}), 401

        auth_data    = r.json()
        access_token = auth_data.get("access_token")
        user_id      = auth_data.get("user", {}).get("id")

        # Kullanıcının profilinden rolü al (yoksa seçilen rolü kaydet)
        profil = requests.get(
            f"{SUPABASE_URL}/rest/v1/kullanici_profil?id=eq.{user_id}&select=rol,ad_soyad",
            headers={**HEADERS, "Authorization": f"Bearer {access_token}"}
        ).json()

        if profil:
            db_rol = profil[0].get("rol", role)
        else:
            # İlk girişte profil oluştur
            requests.post(
                f"{SUPABASE_URL}/rest/v1/kullanici_profil",
                headers={**HEADERS, "Authorization": f"Bearer {access_token}"},
                json={"id": user_id, "rol": role}
            )
            db_rol = role

        # Rol bazlı yönlendirme
        redirect_map = {
            "admin":    "/",
            "doktor":   "/",
            "vatandas": "/",
        }

        session["user_id"] = user_id
        session["access_token"] = access_token
        session["rol"] = db_rol
        session["email"] = auth_data.get("user", {}).get("email", email)
        session.permanent = True
        return jsonify({
            "success":      True,
            "access_token": access_token,
            "rol":          db_rol,
            "redirect":     redirect_map.get(db_rol, "/"),
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout():
    token = session.get("access_token") or request.headers.get("Authorization","").replace("Bearer ","")
    try:
        if token:
            requests.post(f"{SUPABASE_URL}/auth/v1/logout",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"},
                timeout=3)
    except Exception:
        pass
    session.clear()
    return jsonify({"success": True})


@app.route("/api/me")
def api_me():
    """Session kontrolu — anlik, Supabase'e gitme."""
    if "user_id" not in session:
        return jsonify({"authenticated": False, "reason": "no_session"}), 401
    return jsonify({
        "authenticated": True,
        "email":    session.get("email", ""),
        "rol":      session.get("rol", "vatandas"),
        "ad_soyad": session.get("ad_soyad", ""),
    })


if __name__ == "__main__":
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        print("🔌 Supabase REST API baglantisi test ediliyor...")
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/bolge?select=bolge_adi&limit=1",
                             headers=HEADERS, timeout=5)
            if r.status_code == 200:
                print(f"✅ Baglanti basarili! Bolgeler: {r.json()}")
            else:
                print(f"❌ HTTP {r.status_code}: {r.text}")
        except Exception as e:
            print(f"⚠️  Baglanti testi basarisiz (uygulama calisir): {e}")
    app.run(debug=True, use_reloader=True)
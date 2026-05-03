-- ============================================================
-- SalgınTakip KDS — Supabase / PostgreSQL Schema + Seed Data
-- Supabase SQL Editor'a yapıştırıp çalıştırın
-- ============================================================

-- ============================================================
-- 1. TABLOLAR
-- ============================================================

CREATE TABLE IF NOT EXISTS bolge (
    bolge_id   SERIAL PRIMARY KEY,
    bolge_adi  VARCHAR(100) NOT NULL UNIQUE,
    nufus      BIGINT       NOT NULL CHECK (nufus > 0)
);

CREATE TABLE IF NOT EXISTS hastane (
    hastane_id            SERIAL PRIMARY KEY,
    bolge_id              INT          NOT NULL REFERENCES bolge(bolge_id),
    hastane_adi           VARCHAR(150) NOT NULL,
    hastane_turu          VARCHAR(50),
    yatak_kapasitesi      INT          NOT NULL CHECK (yatak_kapasitesi > 0),
    yogun_bakim_kapasitesi INT          NOT NULL DEFAULT 0,
    solunum_cihazi        INT          NOT NULL DEFAULT 0,
    aktif_personel_sayisi INT
);

CREATE TABLE IF NOT EXISTS hastalik (
    hastalik_id      SERIAL PRIMARY KEY,
    hastalik_adi     VARCHAR(150) NOT NULL UNIQUE,
    icd10_kodu       VARCHAR(10)  UNIQUE,
    bulasma_sekli    VARCHAR(100),
    ortalama_kulucka DECIMAL(5,1),
    risk_seviyesi    SMALLINT     CHECK (risk_seviyesi BETWEEN 1 AND 5),
    bulasicilik_r0   DECIMAL(4,2),
    olumculuk_orani  DECIMAL(5,4)
);

CREATE TABLE IF NOT EXISTS demografik_grup (
    grup_id                  SERIAL PRIMARY KEY,
    yas_araligi              VARCHAR(30) NOT NULL,
    cinsiyet                 CHAR(1)     CHECK (cinsiyet IN ('E','K','B')) DEFAULT 'B',
    kronik_hastalik_durumu   BOOLEAN     NOT NULL DEFAULT FALSE,
    asi_durumu               VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS vaka_bildirimi (
    vaka_id           BIGSERIAL PRIMARY KEY,
    bildirim_tarihi   DATE        NOT NULL,
    bolge_id          INT         NOT NULL REFERENCES bolge(bolge_id),
    hastalik_id       INT         NOT NULL REFERENCES hastalik(hastalik_id),
    grup_id           INT         NOT NULL REFERENCES demografik_grup(grup_id),
    hastane_id        INT         NOT NULL REFERENCES hastane(hastane_id),
    yeni_vaka_sayisi  INT         NOT NULL DEFAULT 0 CHECK (yeni_vaka_sayisi >= 0),
    iyilesen_sayisi   INT         NOT NULL DEFAULT 0 CHECK (iyilesen_sayisi >= 0),
    vefat_sayisi      INT         NOT NULL DEFAULT 0 CHECK (vefat_sayisi >= 0)
);

CREATE TABLE IF NOT EXISTS tedbir (
    tedbir_id     SERIAL PRIMARY KEY,
    tedbir_adi    VARCHAR(200) NOT NULL,
    etki_seviyesi VARCHAR(20)  CHECK (etki_seviyesi IN ('Düşük','Orta','Yüksek'))
);

CREATE TABLE IF NOT EXISTS bolge_tedbir (
    id              SERIAL PRIMARY KEY,
    bolge_id        INT  NOT NULL REFERENCES bolge(bolge_id),
    tedbir_id       INT  NOT NULL REFERENCES tedbir(tedbir_id),
    baslangic_tarihi DATE,
    bitis_tarihi     DATE
);

CREATE TABLE IF NOT EXISTS personel (
    personel_id       SERIAL PRIMARY KEY,
    hastane_id        INT         NOT NULL REFERENCES hastane(hastane_id),
    ad_soyad          VARCHAR(150) NOT NULL,
    unvan             VARCHAR(50),
    departman         VARCHAR(100),
    vardiya           VARCHAR(30),
    ise_baslama_tarihi DATE,
    aktif_mi          BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS vaka_log (
    log_id         BIGSERIAL PRIMARY KEY,
    bildirim_id    BIGINT      NOT NULL,
    islem_tipi     VARCHAR(10) NOT NULL,
    islem_tarihi   TIMESTAMP   NOT NULL DEFAULT NOW(),
    eski_vaka_sayisi INT,
    yeni_vaka_sayisi INT
);

-- ============================================================
-- 2. VIEW — vw_bolge_kapasite_ozeti
-- ============================================================

CREATE OR REPLACE VIEW vw_bolge_kapasite_ozeti AS
SELECT
    b.bolge_adi,
    COALESCE(SUM(h.yatak_kapasitesi), 0)               AS toplam_yatak,
    COALESCE(SUM(h.yogun_bakim_kapasitesi), 0)          AS toplam_yb_yatak,
    COALESCE(SUM(vb.yeni_vaka_sayisi), 0)               AS toplam_yeni_vaka,
    ROUND(
        CAST(COALESCE(SUM(vb.yeni_vaka_sayisi), 0) AS NUMERIC)
        / NULLIF(SUM(h.yatak_kapasitesi), 0) * 100
    , 2) AS doluluk_orani_pct
FROM bolge b
LEFT JOIN hastane h         ON h.bolge_id  = b.bolge_id
LEFT JOIN vaka_bildirimi vb ON vb.bolge_id = b.bolge_id
GROUP BY b.bolge_adi;

-- ============================================================
-- 3. TRIGGER — vaka_log otomatik kayıt
-- ============================================================

CREATE OR REPLACE FUNCTION fn_vaka_log_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.yeni_vaka_sayisi < 0 OR NEW.vefat_sayisi < 0 OR NEW.iyilesen_sayisi < 0 THEN
        RAISE EXCEPTION 'Negatif değer girilemez.';
    END IF;
    IF NEW.vefat_sayisi > NEW.yeni_vaka_sayisi THEN
        RAISE EXCEPTION 'Vefat sayısı yeni vaka sayısını aşamaz.';
    END IF;

    INSERT INTO vaka_log (bildirim_id, islem_tipi, islem_tarihi, eski_vaka_sayisi, yeni_vaka_sayisi)
    VALUES (
        NEW.vaka_id,
        TG_OP,
        NOW(),
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.yeni_vaka_sayisi ELSE NULL END,
        NEW.yeni_vaka_sayisi
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_vaka_kontrol ON vaka_bildirimi;
CREATE TRIGGER trg_vaka_kontrol
    AFTER INSERT OR UPDATE ON vaka_bildirimi
    FOR EACH ROW EXECUTE FUNCTION fn_vaka_log_trigger();

-- ============================================================
-- 4. SEED DATA — Bölgeler
-- ============================================================

INSERT INTO bolge (bolge_adi, nufus) VALUES
  ('Marmara',               15840900),
  ('Ege',                    4479525),
  ('İç Anadolu',             5782285),
  ('Karadeniz',              7689000),
  ('Akdeniz',               10500000),
  ('Doğu Anadolu',           6500000),
  ('Güneydoğu Anadolu',      8900000)
ON CONFLICT (bolge_adi) DO NOTHING;

-- ============================================================
-- 5. SEED DATA — Hastaneler
-- ============================================================

INSERT INTO hastane (bolge_id, hastane_adi, hastane_turu, yatak_kapasitesi, yogun_bakim_kapasitesi, solunum_cihazi, aktif_personel_sayisi)
SELECT b.bolge_id, h.hastane_adi, h.hastane_turu, h.yatak, h.ybu, h.solunum, h.personel
FROM (VALUES
  ('Marmara',            'İstanbul Eğitim Araştırma Hastanesi', 'Eğitim', 1250, 180, 210, 2450),
  ('Marmara',            'Kartal Eğitim Araştırma Hastanesi',   'Eğitim', 980,  130, 160, 1900),
  ('Marmara',            'Marmara Üniversite Hastanesi',        'Üniversite', 800, 110, 120, 1600),
  ('Marmara',            'Pendik Devlet Hastanesi',             'Devlet', 620,  70,  80,  1200),
  ('Ege',                'Ege Üniversite Hastanesi',            'Üniversite', 980, 114, 128, 1870),
  ('Ege',                'İzmir Tepecik EAH',                   'Eğitim', 870, 100, 115, 1700),
  ('İç Anadolu',         'Ankara Şehir Hastanesi',              'Şehir',  2100, 240, 310, 4200),
  ('İç Anadolu',         'Hacettepe Üniversite Hastanesi',      'Üniversite', 1200, 170, 200, 2800),
  ('Karadeniz',          'Ondokuz Mayıs Üniversite Hastanesi',  'Üniversite', 750,  90, 100, 1400),
  ('Karadeniz',          'Trabzon Numune Hastanesi',            'Devlet', 600,  70,  85, 1100),
  ('Akdeniz',            'Antalya Eğitim Araştırma Hastanesi',  'Eğitim', 900, 120, 140, 1800),
  ('Akdeniz',            'Çukurova Üniversite Hastanesi',       'Üniversite', 850, 110, 130, 1650),
  ('Doğu Anadolu',       'Atatürk Üniversite Hastanesi',        'Üniversite', 700,  80,  95, 1300),
  ('Güneydoğu Anadolu',  'Dicle Üniversite Hastanesi',          'Üniversite', 750,  85, 100, 1400),
  ('Güneydoğu Anadolu',  'Diyarbakır Eğitim Araştırma Hastanesi','Eğitim', 680, 78,  90, 1250)
) AS h(bolge_adi, hastane_adi, hastane_turu, yatak, ybu, solunum, personel)
JOIN bolge b ON b.bolge_adi = h.bolge_adi;

-- ============================================================
-- 6. SEED DATA — Hastalıklar
-- ============================================================

INSERT INTO hastalik (hastalik_adi, icd10_kodu, bulasma_sekli, ortalama_kulucka, risk_seviyesi, bulasicilik_r0, olumculuk_orani)
VALUES
  ('COVID-19',                'U07.1', 'Damlacık/Aerosol', 5.0,  5, 2.50, 0.0210),
  ('Grip',                    'J11',   'Damlacık',         2.0,  3, 1.30, 0.0010),
  ('Zatürre',                 'J18',   'Damlacık/Temas',   3.0,  3, 1.10, 0.0050),
  ('Menenjit',                'G03',   'Damlacık',         4.0,  4, 1.50, 0.0150),
  ('Mpox',                    'B04',   'Temas/Damlacık',   12.0, 4, 1.80, 0.0340),
  ('RSV',                     'B97.4', 'Damlacık/Temas',   5.0,  3, 1.60, 0.0020)
ON CONFLICT (hastalik_adi) DO NOTHING;

-- ============================================================
-- 7. SEED DATA — Demografik Gruplar (tüm kombinasyonlar)
-- ============================================================

INSERT INTO demografik_grup (yas_araligi, cinsiyet, kronik_hastalik_durumu, asi_durumu)
SELECT y.yas, c.cins, k.kronik, a.asi
FROM
  (VALUES ('0-14'), ('15-29'), ('30-44'), ('45-64'), ('65+')) AS y(yas),
  (VALUES ('E'), ('K')) AS c(cins),
  (VALUES (FALSE), (TRUE)) AS k(kronik),
  (VALUES ('Tam Aşılı'), ('Kısmi'), ('Aşısız')) AS a(asi);

-- ============================================================
-- 8. SEED DATA — Vaka Bildirimleri (son 90 gün, gerçekçi veri)
-- ============================================================

DO $$
DECLARE
    gun         INT;
    bolge_rec   RECORD;
    hastalik_rec RECORD;
    grup_rec    RECORD;
    hastane_rec RECORD;
    base_vaka   INT;
    yeni        INT;
    iyilesen    INT;
    vefat       INT;
    tarih       DATE;
BEGIN
    FOR gun IN 0..89 LOOP
        tarih := CURRENT_DATE - gun;

        FOR bolge_rec IN SELECT bolge_id, bolge_adi FROM bolge LOOP
            -- Her bölge için ana hastaneyi al
            SELECT hastane_id INTO hastane_rec
            FROM hastane WHERE bolge_id = bolge_rec.bolge_id
            ORDER BY yatak_kapasitesi DESC LIMIT 1;

            FOR hastalik_rec IN SELECT hastalik_id, hastalik_adi FROM hastalik LOOP
                FOR grup_rec IN
                    SELECT grup_id FROM demografik_grup
                    WHERE cinsiyet IN ('E','K')
                    ORDER BY random() LIMIT 4
                LOOP
                    -- Bölge bazlı taban vaka
                    base_vaka := CASE bolge_rec.bolge_adi
                        WHEN 'Marmara'             THEN 120
                        WHEN 'Ege'                 THEN 50
                        WHEN 'İç Anadolu'          THEN 45
                        WHEN 'Karadeniz'           THEN 25
                        WHEN 'Akdeniz'             THEN 55
                        WHEN 'Doğu Anadolu'        THEN 18
                        WHEN 'Güneydoğu Anadolu'   THEN 30
                        ELSE 20
                    END;

                    -- Hastalık çarpanı
                    base_vaka := base_vaka * CASE hastalik_rec.hastalik_adi
                        WHEN 'COVID-19' THEN 5
                        WHEN 'Grip'     THEN 3
                        WHEN 'Zatürre'  THEN 2
                        WHEN 'Menenjit' THEN 1
                        ELSE 2
                    END / 5;

                    yeni     := GREATEST(1, base_vaka + (random() * 20 - 10)::INT);
                    iyilesen := GREATEST(0, (yeni * 0.7 + random() * 5)::INT);
                    vefat    := GREATEST(0, (yeni * 0.02 + random() * 1)::INT);

                    -- Trigger kontrolü: vefat <= yeni
                    vefat := LEAST(vefat, yeni);

                    INSERT INTO vaka_bildirimi
                        (bildirim_tarihi, bolge_id, hastalik_id, grup_id, hastane_id,
                         yeni_vaka_sayisi, iyilesen_sayisi, vefat_sayisi)
                    VALUES
                        (tarih, bolge_rec.bolge_id, hastalik_rec.hastalik_id,
                         grup_rec.grup_id, hastane_rec.hastane_id,
                         yeni, iyilesen, vefat);
                END LOOP;
            END LOOP;
        END LOOP;
    END LOOP;
END;
$$;

-- ============================================================
-- 9. SEED DATA — Tedbirler
-- ============================================================

INSERT INTO tedbir (tedbir_adi, etki_seviyesi) VALUES
  ('Sokağa Çıkma Kısıtlaması',          'Yüksek'),
  ('Maske Zorunluluğu',                  'Orta'),
  ('Okul Kapanmaları',                   'Yüksek'),
  ('Turistik Tesis Kapasite Kısıtı',    'Orta'),
  ('Yoğun Bakım Kapasite Artırımı',     'Yüksek'),
  ('Sosyal Mesafe Kuralları',            'Orta'),
  ('Kalabalık Etkinlik Yasağı',          'Yüksek'),
  ('Toplu Taşıma Kapasite Kısıtı',      'Düşük')
ON CONFLICT DO NOTHING;

INSERT INTO bolge_tedbir (bolge_id, tedbir_id, baslangic_tarihi, bitis_tarihi)
SELECT b.bolge_id, t.tedbir_id, (CURRENT_DATE - 60), NULL
FROM bolge b, tedbir t
WHERE b.bolge_adi = 'Marmara' AND t.tedbir_adi = 'Sokağa Çıkma Kısıtlaması';

INSERT INTO bolge_tedbir (bolge_id, tedbir_id, baslangic_tarihi, bitis_tarihi)
SELECT b.bolge_id, t.tedbir_id, (CURRENT_DATE - 45), NULL
FROM bolge b, tedbir t
WHERE b.bolge_adi IN ('Ege','Akdeniz') AND t.tedbir_adi = 'Maske Zorunluluğu';

INSERT INTO bolge_tedbir (bolge_id, tedbir_id, baslangic_tarihi, bitis_tarihi)
SELECT b.bolge_id, t.tedbir_id, (CURRENT_DATE - 30), (CURRENT_DATE + 30)
FROM bolge b, tedbir t
WHERE b.bolge_adi = 'İç Anadolu' AND t.tedbir_adi = 'Okul Kapanmaları';

INSERT INTO bolge_tedbir (bolge_id, tedbir_id, baslangic_tarihi, bitis_tarihi)
SELECT b.bolge_id, t.tedbir_id, (CURRENT_DATE - 20), NULL
FROM bolge b, tedbir t
WHERE b.bolge_adi = 'Güneydoğu Anadolu' AND t.tedbir_adi = 'Yoğun Bakım Kapasite Artırımı';

-- ============================================================
-- 10. SEED DATA — Personel
-- ============================================================

INSERT INTO personel (hastane_id, ad_soyad, unvan, departman, vardiya, ise_baslama_tarihi, aktif_mi)
SELECT h.hastane_id, p.ad, p.unvan, p.dept, p.vardiya, p.tarih::DATE, TRUE
FROM (VALUES
  ('İstanbul Eğitim Araştırma Hastanesi', 'Dr. Ayşe Kaya',    'Doktor',     'Enfeksiyon',    'Gündüz', '2019-08-15'),
  ('İstanbul Eğitim Araştırma Hastanesi', 'Hemş. Fatma Demir','Hemsire',    'YBÜ',           'Gece',   '2021-01-03'),
  ('İstanbul Eğitim Araştırma Hastanesi', 'Tek. Ali Çelik',   'Teknisyen',  'Laboratuvar',   'Gündüz', '2022-06-20'),
  ('Ege Üniversite Hastanesi',            'Dr. Mehmet Yılmaz','Doktor',     'Dahiliye',      'Gündüz', '2018-03-10'),
  ('Ege Üniversite Hastanesi',            'Hemş. Zeynep Arslan','Hemsire',  'Acil',          'Gece',   '2020-09-15'),
  ('Ankara Şehir Hastanesi',              'Dr. Can Öztürk',   'Doktor',     'Göğüs Hastalıkları','Gündüz','2017-05-22'),
  ('Ankara Şehir Hastanesi',              'Hemş. Selin Kurt', 'Hemsire',    'YBÜ',           'Gündüz', '2019-11-01'),
  ('Ankara Şehir Hastanesi',              'Tek. Burak Şahin', 'Teknisyen',  'Radyoloji',     'Gece',   '2021-07-14'),
  ('Antalya Eğitim Araştırma Hastanesi',  'Dr. Elif Güneş',   'Doktor',     'Enfeksiyon',    'Gündüz', '2020-02-28'),
  ('Dicle Üniversite Hastanesi',          'Dr. Serhat Kılıç', 'Doktor',     'Mikrobiyoloji', 'Gündüz', '2016-09-01')
) AS p(hastane_adi, ad, unvan, dept, vardiya, tarih)
JOIN hastane h ON h.hastane_adi = p.hastane_adi;

-- ============================================================
-- TAMAMLANDI
-- Kontrol sorguları:
-- SELECT COUNT(*) FROM vaka_bildirimi;  -- ~25.000+ satır beklenir
-- SELECT * FROM vw_bolge_kapasite_ozeti;
-- SELECT * FROM vaka_log LIMIT 10;
-- ============================================================

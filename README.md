# 🦠 SalgınTakip KDS - Karar Destek Sistemi

**Salgın Hastalık Yayılımı ve Sağlık Altyapısı Kapasite Analizi**  
*Muş Alparslan Üniversitesi – VTYS Proje Bahar 2024-25*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Flask](https://img.shields.io/badge/Flask-2.3+-black)](https://flask.palletsprojects.com/)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ecf8e)](https://supabase.com/)

> Gerçek zamanlı vaka takibi, hastane kapasite yönetimi, demografik risk analizi ve tahmine dayalı karar destek arayüzü.

![Dashboard Önizleme](https://via.placeholder.com/800x400?text=Dashboard+Ekran+G%C3%B6r%C3%BCnt%C3%BCsü)  
*(<img width="1621" height="908" alt="image" src="https://github.com/user-attachments/assets/d29dbb2c-ad77-4102-a644-0576c6347fe4" />
)*

---

## 📌 İçindekiler
- [Özellikler](#-özellikler)
- [Teknoloji Mimarisi](#-teknoloji-mimarisi)
- [Kurulum & Çalıştırma](#-kurulum--çalıştırma)
- [Ortam Değişkenleri (.env)](#-ortam-değişkenleri-env)
- [Veritabanı Şeması](#-veritabanı-şeması)
- [API Dokümantasyonu](#-api-dokümantasyonu)
- [Rol Bazlı Erişim](#-rol-bazlı-erişim)
- [Katkıda Bulunma](#-katkıda-bulunma)
- [Lisans](#-lisans)

---

## 🚀 Özellikler

- **Dashboard** – Anlık vaka sayıları, kümülatif grafikler, 7 günlük vaka tahmini (simüle ARIMA), hastalık dağılımı ve bölge haritası (Leaflet + doluluk renklendirmesi)
- **Hastane Kapasitesi** – Bölge bazlı yatak/YBÜ doluluk oranları, solunum cihazı ve personel takibi
- **Demografik Analiz** – Yaş aralığı, cinsiyet, kronik hastalık ve aşı durumuna göre risk segmentasyonu (CTE ile KÖO hesaplama)
- **Bölge Raporu** – `sp_BolgeVakaRaporu` ile parametrik vaka trendi, iki bölgeyi karşılaştırma
- **Hastalık Detayı** – ICD-10 kodları, R₀ bulaşıcılık katsayısı, kuluçka süresi, risk skoru
- **Tedbir & Personel Yönetimi** – Aktif tedbirler, sağlık çalışanları takibi (1-N ilişki)
- **Vaka Log & Denetim** – Trigger (`trg_Vaka_Kontrol`) ile otomatik loglama, INSERT/UPDATE izleme
- **Vaka Bildir (Doktor)** – Yeni vaka ekleme formu (tarih, bölge, hastalık, demografik bilgiler)
- **Yönetici Paneli** – Vaka bildirimi, personel ekleme, hastane kapasite güncelleme
- **Raporlama** – Excel (XLSX) ve PDF dışa aktarım (html2canvas + jsPDF)
- **Tema Desteği** – Koyu / açık tema (localStorage + CSS değişkenleri)


## ⚙️ Kurulum & Çalıştırma

### Gereksinimler
- Python 3.10+
- pip
- Supabase hesabı 

### Adımlar

1. **Depoyu klonlayın**
   ```bash
   git clone https://github.com/kullaniciadiniz/salgintakip-kds.git
   cd salgintakip-kds
   ```bash
   git clone https://github.com/kullaniciadiniz/salgintakip-kds.git
   cd salgintakip-kds

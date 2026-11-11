# NEO-TRAFFIC — Simulator Lampu Lalu Lintas Cyberpunk

Proyek Python (pygame) yang dijalankan di browser lewat **pygbag** (WebAssembly)
dan di-hosting di **Cloudflare Pages**.

## Struktur folder

```
neo-traffic/
├── main.py      <- seluruh kode (wajib bernama main.py untuk pygbag)
├── README.md
└── font.ttf     <- OPSIONAL, font .ttf bergaya cyberpunk (lihat bagian Font)
```

## 1. Jalankan di komputer (desktop)

```
pip install pygame
cd neo-traffic
python main.py
```

## 2. Tes versi web di komputer

Jalankan dari folder **di luar** `neo-traffic`:

```
pip install pygbag
pygbag neo-traffic
```

Lalu buka http://localhost:8000 di browser. Saat pertama kali, loading agak lama
karena runtime diunduh dulu. Klik layar jika diminta untuk memulai.

## 3. Build untuk di-upload

```
pygbag --build neo-traffic
```

Hasilnya ada di `neo-traffic/build/web/` (berisi `index.html` dan file `.apk`).
**Folder `build/web` inilah yang di-upload ke Cloudflare.**
Setiap kali kode diubah, jalankan build lagi lalu upload ulang.

## 4. Deploy ke Cloudflare Pages

### Cara A — lewat command line (wrangler)

Butuh Node.js. Lalu:

```
npm install -g wrangler
wrangler login
wrangler pages project create neo-traffic --production-branch main
wrangler pages deploy neo-traffic/build/web --project-name=neo-traffic
```

Setelah selesai, situs langsung aktif di `https://neo-traffic.pages.dev`
(nama bisa berbeda, lihat output perintah).

### Cara B — lewat dashboard

Di dashboard Cloudflare: **Workers & Pages** -> buat project Pages -> pilih
upload langsung (Direct Upload) -> upload isi folder `build/web`.
Tampilan menu Cloudflare bisa berubah, jadi kalau beda, cari opsi "upload assets".

## 5. Pasang domain sendiri

1. Dashboard Cloudflare -> **Workers & Pages** -> pilih project -> tab **Custom domains**.
2. Klik **Set up a domain**, masukkan domain kamu (mis. `traffic.domainkamu.com`
   atau domain utamanya), lalu **Continue**.
3. Karena domain sudah memakai nameserver Cloudflare, DNS-nya diatur otomatis
   dan sertifikat HTTPS dibuat otomatis. Tunggu beberapa menit sampai aktif.

Untuk subdomain, kalau perlu manual: tambah record **CNAME** dengan nama subdomain,
target `NAMA-PROJECT.pages.dev`, proxy menyala.

## Kontrol

| Tombol | Fungsi |
|---|---|
| `A` / `M` / `E` | Mode Auto / Manual / Alert (semua merah berkedip) |
| `N` | Fase berikutnya |
| `Spasi` | Pause |
| `R` | Hujan on/off |
| `+` / `-` | Kepadatan lalu lintas |
| `L` | Mode LITE (kurangi efek jika lag) |

Semua juga bisa diklik/disentuh lewat tombol di panel kanan layar.

## Font (opsional)

Di browser tidak ada font sistem, jadi dipakai font bawaan pygame. Untuk tampilan
lebih cyberpunk, unduh font .ttf gratis (mis. "Share Tech Mono" atau "Orbitron" dari
Google Fonts), ubah namanya jadi `font.ttf`, taruh di folder `neo-traffic`
(sejajar dengan `main.py`), lalu build ulang.

## Kalau ada masalah

- **Layar hitam / loading lama saat pertama:** normal, runtime pygbag diunduh dari
  internet. Pastikan koneksi aktif, lalu tunggu atau refresh.
- **Terasa lag:** tekan `L`. Di browser, mode LITE juga menyala otomatis kalau FPS
  rendah lebih dari 3 detik.
- **Setelah update, tampilan masih versi lama:** hard refresh (`Ctrl+Shift+R`).
- **Di HP Safari tidak jalan:** coba build dengan `pygbag --ume_block 0 --build neo-traffic`.

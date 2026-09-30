# repolens

CLI untuk membuat dokumentasi teknis dari sebuah repository. Jalankan satu perintah, lalu dapatkan dokumen **PDF**, **Word**, dan **Markdown** berisi struktur folder, tech stack beserta versinya, daftar endpoint, skema database, konfigurasi, dan temuan keamanan. Setiap rilis bisa diekspor sebagai arsip dokumentasi, lengkap dengan perubahan dibanding rilis sebelumnya.

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Butuh Python 3.10+ dan `git`. Untuk AI (opsional): kredensial Anthropic.

## Pemakaian

Jalankan `repolens` tanpa argumen untuk **menu interaktif**: pilih aksi, sumber (folder lokal atau URL git), cara membaca folder, rilis pembanding, format, AI, dan bahasa. Sebelum dijalankan, menu menampilkan perintah yang setara sehingga bisa disalin ke script atau CI.

```bash
# Pindai folder lokal (mengikuti .gitignore), export PDF + Word + Markdown
repolens scan ../mobile_pos

# Pindai folder lokal apa adanya, tanpa git: semua file di disk (termasuk yang di-.gitignore), tanpa info commit/tag
repolens scan ../mobile_pos --no-git

# Dokumen dalam bahasa Indonesia (default: bahasa Inggris, atau REPOLENS_LANG)
repolens scan ../mobile_pos --lang id

# Lihat ringkasan dan temuan tanpa menulis file dan tanpa memanggil AI
repolens scan ../mobile_pos --dry-run

# Pindai tag rilis tertentu. Working tree Anda tidak disentuh (repo di-clone ke folder sementara).
repolens scan ../mobile_pos --ref v3.2.0

# Dokumen rilis + perubahan dibanding rilis sebelumnya
repolens scan ../mobile_pos --ref v3.2.0 --compare-ref v3.1.3

# Langsung dari URL git
repolens scan git@github.com:KA-Logistik/mobile_pos.git --ref v3.2.0

# Hanya format tertentu, tanpa AI
repolens scan ../backend-api --format pdf,docx --no-ai

# Untuk CI: exit code 1 jika ada bagian yang kemungkinan terlewat
repolens scan . --ref "$TAG" --compare-ref "$PREV_TAG" --no-ai --strict

# Render ulang dari hasil scan tanpa memindai lagi
repolens export docs-output/mobile_one-v3.2.0/scan.json --format docx

# Bandingkan dua hasil scan
repolens diff docs-output/app-v1.0.0/scan.json docs-output/app-v1.1.0/scan.json

# Hasil untuk script: JSON di stdout (scan, doctor, diff)
repolens doctor ../mobile_pos --json | jq '.coverage[] | select(.level == "warn")'
```

### Bahasa

Terminal dan dokumen (PDF, Word, Markdown, termasuk narasi AI) memakai bahasa Inggris secara default. Pilih bahasa Indonesia dengan `--lang id`, atau set `REPOLENS_LANG=id` agar berlaku untuk semua perintah. `repolens export` memakai bahasa yang sama dengan saat scan, kecuali `--lang` diberikan. Temuan dan catatan yang dihasilkan saat scan tetap dalam bahasa scan tersebut, jadi scan ulang untuk terjemahan penuh. `scan.json` lama (versi 0.1, berbahasa Indonesia) tetap bisa di-export dan dibandingkan.

### Folder lokal: dengan atau tanpa git

| Cara | Perintah | File yang dibaca | Info rilis |
| :--- | :--- | :--- | :--- |
| Working tree (default) | `repolens scan <folder>` | File di disk yang tidak di-.gitignore | Commit, branch, tag, remote |
| Folder biasa | `repolens scan <folder> --no-git` | Semua file di disk, kecuali folder dependency/build (`node_modules`, `vendor`, `build`, ...) dan `ignore` di `.repolens.yml` | Tidak ada |
| Rilis tertentu | `repolens scan <folder> --ref v1.2.0` | Isi commit tersebut (di-clone ke folder sementara) | Lengkap |

Folder yang bukan repository git otomatis dipindai sebagai folder biasa. `--no-git` tidak bisa digabung dengan `--ref`, `--compare-ref`, atau URL git.

Hasil ada di `docs-output/<proyek>-<rilis>/`:

```text
docs-output/mobile_one-v3.2.0/
├── mobile_one-v3.2.0.pdf
├── mobile_one-v3.2.0.docx
├── mobile_one-v3.2.0.md
└── scan.json          # data mentah hasil scan, dipakai untuk export ulang dan perbandingan
```

Jika folder tujuan sudah berisi dokumen **proyek lain** dengan nama dan rilis yang sama (misalnya dua aplikasi hasil fork dengan `name` dan `version` sama di `pubspec.yaml`), scan dihentikan agar dokumen itu tidak tertimpa. Bedakan lewat `name` di `.repolens.yml`, pakai `--out` lain, atau tambahkan `--force`. Scan ulang proyek yang sama tetap menimpa hasil sebelumnya.

### Exit code

| Kode | Arti |
| :--- | :--- |
| 0 | Berhasil |
| 1 | Gagal (input salah, git gagal, file tidak ditemukan), atau ada temuan "perlu dicek" saat memakai `--strict` |
| 2 | Argumen tidak valid, atau error tak terduga. Jalankan ulang dengan `--debug` (atau `REPOLENS_DEBUG=1`) untuk melihat traceback |
| 130 | Dibatalkan (Ctrl+C) |

Git tidak pernah meminta username/password secara interaktif, sehingga tidak menggantung di CI. Siapkan akses lewat SSH key atau credential helper. Token di URL tidak pernah ditampilkan di pesan error maupun dokumen.

## Proyek dengan struktur berbeda

Setiap proyek punya variasi sendiri: `vendor/` tidak di-commit, route di file tambahan, tabel tanpa migration, dan sebagainya. Ada tiga alat untuk menanganinya.

### 1. `repolens doctor`: cek sebelum membuat dokumen

```bash
repolens doctor ../web-portal
```

Perintah ini menampilkan apa yang terdeteksi beserta sumbernya, lalu apa yang **kemungkinan terlewat** dan cara melengkapinya. Contoh:

```text
Coverage
  ⚠ [Tech stack] CodeIgniter 4 version unknown (spark + app/Config/Routes.php (exact version unknown: no vendor/ folder)).
    → Set `frameworks: [{name: CodeIgniter 4, version: ...}]` in `.repolens.yml`, or run `composer install` before scanning.
  ⚠ [Endpoint] 2 of 12 controllers do not appear in any route: Legacy, Report.
    → They may be reached through auto-routing or dynamically built routes. Add their endpoints under `endpoints` in `.repolens.yml`, ...
```

Temuan yang sama juga tampil di terminal setelah `scan`, dan di bagian **Scan Coverage** (*Cakupan Pemindaian* dengan `--lang id`) pada dokumen. Tambahkan `--strict` agar exit code bernilai 1 jika ada temuan (berguna untuk CI).

### 2. `.repolens.yml`: isi yang tidak bisa dideteksi

```bash
repolens init ../web-portal     # buat template berdasarkan hasil deteksi
```

File ini disimpan di root proyek dan ikut di-commit, sehingga berlaku untuk setiap rilis.

```yaml
name: Web Portal KAI Logistik
version: 2.1.0                       # jika manifest tidak menyimpan versi
frameworks:
  - {name: CodeIgniter 4, version: 4.1.3}
routes:                              # file route di luar lokasi standar
  - app/Config/RoutesAdmin.php
schema:                              # SQL dump tanpa data, ekstensi bebas, boleh di-.gitignore
  - database/schema.sql
ignore:                              # dikecualikan dari pemindaian
  - public/assets/vendor
endpoints:                           # endpoint dinamis yang tidak terdeteksi
  - {method: GET, path: /legacy/export, handler: Legacy::export, note: auto-routing}
notes:                               # tampil di dokumen
  - Auto-routing aktif di production.
tree_depth: 4
```

Key yang tidak dikenal atau pola file yang tidak cocok dengan apa pun akan dilaporkan oleh `doctor`.

### 3. Test regresi: perbaikan tidak saling merusak

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                 # fixture sintetis, cepat, tanpa jaringan
.venv/bin/pytest -m corpus       # repository nyata yang dipatok ke commit (tests/corpus.yml)
```

Saat menemukan proyek yang hasilnya salah:

1. Buat fixture kecil di `tests/fixtures/<nama>/` yang meniru polanya, lalu tambahkan test di `tests/test_fixtures.py`.
2. Jika repository-nya bisa diakses, tambahkan juga ke `tests/corpus.yml` dengan commit yang diuji dan hasil yang sudah dicek manual.
3. Perbaiki extractor sampai semua test lolos, bukan hanya test yang baru.

## Isi dokumen

| Bagian | Sumber |
| :--- | :--- |
| Ringkasan, arsitektur, modul | AI (opsional), berdasarkan fakta hasil scan |
| Perubahan dibanding rilis sebelumnya | `--compare-ref` atau `--compare` |
| Informasi rilis | git: commit, tag, branch, remote (kredensial di URL dibuang) |
| Tech stack & versi | Manifest + lock file (versi yang benar-benar terpasang) |
| Struktur folder | File tree, mengikuti `.gitignore` |
| Endpoint & route | Definisi route server, panggilan API klien, route UI |
| Database | SQL, migration, entity/model ORM, konfigurasi koneksi |
| Konfigurasi | **Nama** key env dan config (nilainya tidak pernah dibaca) |
| Cakupan pemindaian | Hal yang kemungkinan terlewat, beserta cara melengkapinya |
| Platform & infrastruktur | Android/iOS, Dockerfile, docker-compose, CI/CD |
| Dependency | Semua package per manifest: deklarasi vs terpasang |
| Keamanan | Pola token/password/private key, file env yang ikut di-commit. Tingkat *tinggi*, *sedang*, *rendah* (file test dan API key config Firebase klien) |

## Stack yang didukung

| Stack | Endpoint | Database | Versi |
| :--- | :--- | :--- | :--- |
| Spring Boot (Java/Kotlin) | `@*Mapping` + prefix `@RequestMapping` class | JPA `@Entity`, SQL | Maven, Gradle |
| Laravel | `routes/*.php` termasuk `prefix`/`group`, `resource`, `apiResource` | Migration | `composer.lock` |
| CodeIgniter 4 | `app/Config/Routes.php` termasuk `group`, `resource` | Migration, Model (`$table`, query builder) | composer, `system/CodeIgniter.php` |
| CodeIgniter 3 | `application/config/routes.php` | SQL, Model (query builder) | `system/core/CodeIgniter.php` |
| Next.js | App Router `route.ts`, Pages API, halaman | Prisma, Drizzle, TypeORM | npm/yarn/pnpm lock |
| React | React Router, panggilan `axios`/`fetch` | - | npm/yarn/pnpm lock |
| Express / NestJS | `app.get(...)`, `@Controller` + `@Get` | Prisma, TypeORM, Sequelize (engine) | npm lock |
| Flutter / Dart | Panggilan API di datasource (Dio, http, wrapper `.call`) | Hive | `pubspec.lock`, `.fvmrc` |
| Python (FastAPI, Flask, Django) | Decorator route, `urls.py` | Django models | requirements, pyproject |
| Go (Gin, Echo, Fiber) | `r.GET(...)` | - | `go.mod` |

Untuk stack lain, bagian umum (struktur folder, bahasa, dependency, env, keamanan, git, CI/Docker) tetap terisi.

## AI

Tanpa `--no-ai`, CLI meminta Claude menulis ringkasan, penjelasan arsitektur, keterangan folder, daftar modul, langkah setup, dan observasi. Kredensial dibaca dari `ANTHROPIC_API_KEY` atau profil `ant auth login`. Jika kredensial tidak ada, bagian AI dilewati dan dokumen tetap dibuat.

Yang dikirim ke AI **hanya fakta hasil scan**: nama, versi, path, nama kolom, nama env key, dan potongan README. Isi source code, nilai env, dan cuplikan rahasia tidak pernah dikirim. Gunakan `--no-ai` jika tidak ada data yang boleh keluar sama sekali.

Model default: `claude-opus-5`, dengan server-side fallback (`fallbacks: "default"`) jika permintaan ditolak oleh classifier.

## Keterbatasan

- Analisis statis: kode tidak dijalankan. Route yang dibentuk saat runtime (auto-routing, route dari database, prefix yang dirakit dinamis) bisa tidak terdeteksi. Dokumen mencatat hal ini jika terdeteksi.
- Pemindaian keamanan hanya memeriksa file saat ini, bukan riwayat git.
- Font PDF memakai Arial Unicode/Menlo (macOS) atau DejaVu (Linux). Tanpa font tersebut, karakter khusus diganti versi ASCII-nya.

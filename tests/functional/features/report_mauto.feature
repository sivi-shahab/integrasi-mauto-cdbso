@epic:Report_Mauto_CDSBO
Feature: POST /v1/report_mauto
  Mengambil data report M-Auto CDSBO berdasarkan nik dan apply_date (ddmmyyyy),
  dengan filter opsional cc_reff, branch_code, account_number serta paging limit/offset.

  Konvensi:
    - Rule      = Test Scenario (TS-xx)
    - Scenario  = Test Case (TC-xx)
    - Tag @severity:<level> dipetakan ke severity Allure
    - Tag @needs-confirmation = expected result mengikuti perilaku service saat ini,
      perlu konfirmasi bisnis apakah memang itu yang diharapkan.

  Background:
    Given service report_mauto tersedia
    And API key yang digunakan "valid"

  # ---------------------------------------------------------------------------
  Rule: TS-01 Pengambilan data dengan nik dan apply_date valid

    @TC-01 @severity:blocker
    Scenario Outline: TC-01 Data ditemukan untuk nik <nik> pada apply_date <apply_date>
      When request dikirim dengan nik "<nik>" dan apply_date "<apply_date>"
      Then HTTP status adalah 200
      And responseCode adalah "00"
      And data tidak kosong
      And semua baris memiliki nik "<nik>"
      And semua baris memiliki apply_date pada tanggal "<apply_date>"
      And baris terurut berdasarkan apply_date secara ascending
      And waktu respons di bawah 2000 ms

      Examples:
        | nik              | apply_date |
        | 3201133107990002 | 12112025   |
        | 3204375008970013 | 24092026   |
        | 3201133107990002 | 09032026   |
        | 3201133107990002 | 31102025   |
        | 3201133107990002 | 27022026   |
        | 3201133107990002 | 29092025   |
        | 3201133107990002 | 30012026   |
        | 3201133107990002 | 02102025   |
        | 3201133107990002 | 13022026   |

    @TC-02 @severity:critical
    Scenario: TC-02 Response memuat field utama
      When request dikirim dengan nik "3201133107990002" dan apply_date "12112025"
      Then responseCode adalah "00"
      And setiap baris memuat field "application_id, nik, apply_date, status, cc_reff, branch_code, account_number"

    @TC-03 @severity:normal
    Scenario: TC-03 Spasi di awal/akhir nik diabaikan
      When request dikirim dengan nik " 3201133107990002 " dan apply_date "12112025"
      Then HTTP status adalah 200
      And responseCode adalah "00"
      And data tidak kosong
      And semua baris memiliki nik "3201133107990002"

  # ---------------------------------------------------------------------------
  Rule: TS-02 Filter opsional cc_reff, branch_code, account_number

    @TC-04 @severity:critical
    Scenario Outline: TC-04 Filter <field> mempersempit hasil
      Given data acuan untuk nik "3201133107990002" dan apply_date "29092025"
      When request dikirim dengan filter <field> dari baris acuan
      Then HTTP status adalah 200
      And responseCode adalah "00"
      And data tidak kosong
      And semua baris memiliki <field> sama dengan baris acuan
      And jumlah baris tidak lebih dari data acuan

      Examples:
        | field          |
        | cc_reff        |
        | branch_code    |
        | account_number |

    @TC-05 @severity:normal
    Scenario: TC-05 Filter yang tidak cocok menghasilkan data kosong
      When request dikirim dengan body {"nik": "3201133107990002", "apply_date": "29092025", "cc_reff": "TIDAK-ADA-999"}
      Then HTTP status adalah 200
      And responseCode adalah "00"
      And data kosong

    @TC-06 @severity:minor
    Scenario: TC-06 Placeholder Swagger "string" pada filter diabaikan
      Given data acuan untuk nik "3201133107990002" dan apply_date "29092025"
      When request dikirim dengan body {"nik": "3201133107990002", "apply_date": "29092025", "cc_reff": "string", "branch_code": "string", "account_number": "string"}
      Then responseCode adalah "00"
      And jumlah baris sama dengan data acuan

  # ---------------------------------------------------------------------------
  Rule: TS-03 Paging limit dan offset

    @TC-07 @severity:normal
    Scenario: TC-07 limit=1 mengembalikan tepat 1 baris
      When request dikirim dengan body {"nik": "3201133107990002", "apply_date": "29092025", "limit": 1, "offset": 0}
      Then responseCode adalah "00"
      And jumlah baris adalah 1

    @TC-08 @severity:critical
    Scenario: TC-08 Paging per halaman tidak duplikat dan tidak ada yang hilang
      Given data acuan untuk nik "3201133107990002" dan apply_date "29092025"
      When seluruh halaman diambil dengan limit 5
      Then gabungan semua halaman sama persis dengan data acuan

    @TC-09 @severity:normal
    Scenario: TC-09 offset melebihi total data menghasilkan data kosong
      When request dikirim dengan body {"nik": "3201133107990002", "apply_date": "29092025", "limit": 100, "offset": 9999}
      Then HTTP status adalah 200
      And responseCode adalah "00"
      And data kosong

    @TC-10 @severity:minor
    Scenario: TC-10 limit=0 memakai default limit (100)
      Given data acuan untuk nik "3201133107990002" dan apply_date "29092025"
      When request dikirim dengan body {"nik": "3201133107990002", "apply_date": "29092025", "limit": 0}
      Then responseCode adalah "00"
      And jumlah baris sama dengan data acuan

    @TC-11 @severity:minor
    Scenario: TC-11 limit di atas batas maksimum tetap diterima
      When request dikirim dengan body {"nik": "3201133107990002", "apply_date": "29092025", "limit": 5000}
      Then HTTP status adalah 200
      And responseCode adalah "00"

    @TC-12 @severity:normal
    Scenario Outline: TC-12 Nilai paging negatif ditolak (<case>)
      When request dikirim dengan body <body>
      Then HTTP status adalah 200
      And responseCode adalah "40"
      And responseDescription mengandung "Limit and offset must be greater than or equal to 0"
      And data kosong

      Examples:
        | case           | body                                                                     |
        | limit negatif  | {"nik": "3201133107990002", "apply_date": "29092025", "limit": -1}       |
        | offset negatif | {"nik": "3201133107990002", "apply_date": "29092025", "offset": -1}      |

  # ---------------------------------------------------------------------------
  Rule: TS-04 Validasi input request

    @TC-13 @severity:critical
    Scenario Outline: TC-13 Request tidak valid ditolak (<case>)
      When request dikirim dengan body <body>
      Then HTTP status adalah <http>
      And responseCode adalah "40"
      And responseDescription mengandung "<message>"
      And data kosong

      Examples:
        | case                         | body                                                      | http | message                                         |
        | tanpa nik dan cc_reff        | {"apply_date": "12112025"}                                | 400  | At least one of nik or cc_reff must be provided |
        | tanpa apply_date             | {"nik": "3201133107990002"}                               | 400  | apply_date: Field required                      |
        | limit bukan angka            | {"nik": "3201133107990002", "apply_date": "12112025", "limit": "abc"} | 400  | limit                                |
        | apply_date format yyyy-mm-dd | {"nik": "3201133107990002", "apply_date": "2025-11-12"}   | 200  | apply_date is required with format ddmmyyyy     |
        | apply_date tidak valid       | {"nik": "3201133107990002", "apply_date": "32132025"}     | 200  | apply_date is required with format ddmmyyyy     |
        | apply_date kosong            | {"nik": "3201133107990002", "apply_date": ""}             | 200  | apply_date is required with format ddmmyyyy     |
        | apply_date placeholder       | {"nik": "3201133107990002", "apply_date": "string"}       | 200  | apply_date is required with format ddmmyyyy     |
        | nik placeholder              | {"nik": "string", "apply_date": "12112025"}               | 200  | nik is required                                 |

    @TC-14 @severity:normal @needs-confirmation
    Scenario: TC-14 Request hanya dengan cc_reff (tanpa nik) ditolak
      # Schema menerima "nik ATAU cc_reff", tetapi service mewajibkan nik.
      When request dikirim dengan body {"cc_reff": "ABC123", "apply_date": "12112025"}
      Then HTTP status adalah 200
      And responseCode adalah "40"
      And responseDescription mengandung "nik is required"

  # ---------------------------------------------------------------------------
  Rule: TS-05 Data tidak ditemukan

    @TC-15 @severity:normal @needs-confirmation
    Scenario Outline: TC-15 Tidak ada data (<case>) mengembalikan sukses dengan data kosong
      # Belum ada responseCode 44 (NOT_FOUND) untuk endpoint ini.
      When request dikirim dengan nik "<nik>" dan apply_date "<apply_date>"
      Then HTTP status adalah 200
      And responseCode adalah "00"
      And data kosong

      Examples:
        | case                     | nik              | apply_date |
        | nik tidak terdaftar      | 0000000000000000 | 12112025   |
        | tanggal tanpa pengajuan  | 3201133107990002 | 01011990   |

  # ---------------------------------------------------------------------------
  Rule: TS-06 Autentikasi API key

    @TC-16 @severity:blocker
    Scenario Outline: TC-16 Request dengan API key <key> ditolak
      Given API key yang digunakan "<key>"
      When request dikirim dengan nik "3201133107990002" dan apply_date "12112025"
      Then HTTP status adalah 401
      And responseCode adalah "41"
      And responseDescription mengandung "Invalid API Key"
      And data kosong

      Examples:
        | key     |
        | salah   |
        | kosong  |
        | tanpa   |

  # ---------------------------------------------------------------------------
  # TS-08 merekam isu di tests/k6/README.md §9 SEBELUM diperbaiki.
  # Tag @known_issue = isu belum diperbaiki: test diharapkan GAGAL (bukti "before")
  # dan tidak menggagalkan pipeline. Setelah fix, hapus tag @known_issue agar
  # test menjadi gate (bukti "after"). Lihat docs/implementation-fixing-plan.md.
  Rule: TS-08 Isu performa dan operasional (README k6 §9)

    @TC-22 @severity:critical @known_issue @issue_9_1
    Scenario: TC-22 Connection pool database dikonfigurasi eksplisit (§9.1)
      When konfigurasi pool database service dibaca
      Then pool_pre_ping aktif
      And pool_timeout tidak lebih dari 10 detik

    @TC-23 @severity:normal @known_issue @issue_9_2
    Scenario: TC-23 Ukuran pool dapat diatur lewat environment variable (§9.2)
      When konfigurasi pool database service dibaca dengan env "DB_POOL_SIZE=3,DB_MAX_OVERFLOW=2"
      Then pool_size adalah 3
      And max_overflow adalah 2

    @TC-24 @severity:critical @known_issue @issue_9_3
    Scenario: TC-24 Log aplikasi level INFO tidak memuat NIK (§9.3)
      When request dikirim sambil memantau log service dengan nik "3201133107990002" dan apply_date "29092025"
      Then responseCode adalah "00"
      And log service level INFO tidak memuat nik "3201133107990002"

    @TC-25 @severity:normal @known_issue @issue_9_3
    Scenario: TC-25 File log dirotasi harian (§9.3)
      When konfigurasi logging service dibaca
      Then file log memakai rotasi harian

    # §9.4 keputusan 2026-11-03: kontrak response TETAP (kolom gambar tetap dikirim).
    # Perbaikan difokuskan pada efisiensi serialisasi, bukan isi response.
    @TC-26 @severity:critical @issue_9_4
    Scenario: TC-26 Kontrak response tetap memuat kolom gambar (§9.4)
      When request dikirim dengan nik "3201133107990002" dan apply_date "29092025"
      Then responseCode adalah "00"
      And data tidak kosong
      And setiap baris memuat field "selfie, request_base64_ktp, profile_pic"
      And apply_date dalam format ISO 8601 "YYYY-MM-DDTHH:MM:SS"

    @TC-27 @severity:critical @issue_9_4
    Scenario: TC-27 Rendering response besar efisien (§9.4)
      When response 12 baris dengan kolom gambar seukuran UAT dirender lewat endpoint
      Then waktu render median di bawah 35 ms

# AI Expense Audit System

Hệ thống hỗ trợ nhân viên kế toán đọc và kiểm tra bộ chứng từ **trước khi thanh toán**:
upload chứng từ, dùng AI trích xuất thông tin, đối chiếu tính nhất quán giữa các chứng từ,
gắn cờ rủi ro và lưu lại toàn bộ lịch sử kiểm toán.

> **Disclaimer:** đây là cờ cảnh báo dựa trên quy tắc, **không phải kết luận gian lận**.
> Mọi trường hợp rủi ro cao đều cần người có thẩm quyền rà soát trước khi thanh toán.

![Stack](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.142-009688) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791) ![React](https://img.shields.io/badge/React-18-61dafb) ![Tailwind](https://img.shields.io/badge/Tailwind-4-38bdf8)

---

## 1. Bài toán và hướng tiếp cận

Một bộ hồ sơ thanh toán gồm 3 chứng từ: **Purchase Order** (PO), **Invoice**,
**Payment Request** (PR). Rủi ro thực tế không nằm ở việc đọc từng file, mà ở chỗ
**các con số phải khớp nhau**: tổng PO với tổng Invoice, số tiền đề nghị với
giá trị hóa đơn, tài khoản nhận tiền với tài khoản của nhà cung cấp.

Nguyên tắc thiết kế của dự án:

1. **LLM chỉ lo trích xuất, không lo phán xét.** Mọi kết luận rủi ro đến từ
   code tất định trong `validation.py`. Nếu không làm vậy, kết quả sẽ thay đổi
   mỗi lần gọi API và không kiểm toán được.
2. **Không suy diễn dữ liệu vắng mặt.** Thiếu trường phải ra `None`, không phải `0`.
3. **Có bằng chứng kèm theo.** Mỗi giá trị quan trọng gắn `field_evidence`
   (số trang + trích dẫn nguyên văn) để người dùng tự kiểm chứng.
4. **Lịch sử bất biến.** Mỗi lần kiểm tra được lưu thành một `audit_run` riêng,
   không ghi đè kết quả cũ.

---

## 2. Tính năng

| Nhóm | Mô tả |
|---|---|
| Quản lý hồ sơ | Tạo job, upload nhiều chứng từ, xem lại lịch sử các phiên đã xử lý |
| Đọc tài liệu | PDF nhiều trang, TXT, MD; tự nhận dạng loại chứng từ bằng LLM |
| Trích xuất | Pydantic schema cho từng loại chứng từ + bằng chứng theo trang |
| Kiểm tra chéo | 15 rule đối chiếu số tiền, số lượng, bên liên quan, ngân hàng, phê duyệt |
| Lịch sử kiểm tra | Mỗi lần chạy lưu 1 `audit_run`; mở lại lần cũ không tốn phí LLM |
| Giao diện | React + Tailwind: dashboard lịch sử, trang chi tiết job, xem PDF cạnh kết quả |

---

## 3. Kiến trúc

```
expense-audit/
├── app/
│   ├── main.py                  # Khởi tạo FastAPI, gắn router
│   ├── routers/
│   │   ├── jobs.py              # CRUD job + số liệu tổng hợp cho dashboard
│   │   ├── documents.py         # Upload, xem/xoá file, lấy text & extraction
│   │   ├── issues.py            # Xem & cập nhật trạng thái issue
│   │   └── extractation.py      # Luồng kiểm tra chính (compare) + lịch sử run
│   ├── services/
│   │   ├── document_reader.py   # Đọc text từ PDF, fallback OCR
│   │   ├── extractor.py         # Gọi LLM: phân loại + trích xuất theo schema
│   │   ├── schemas.py           # Pydantic model cho 3 loại chứng từ
│   │   └── validation.py        # 15 rule kiểm tra tất định (không dùng LLM)
│   └── database/
│       ├── models.py            # SQLAlchemy ORM
│       ├── crud.py              # Truy vấn dữ liệu
│       └── connection.py        # Engine, Session, Base
├── frontend/                    # React 18 + Vite + Tailwind 4
├── trasas_assignment.sql        # Schema PostgreSQL
├── requirements.txt
└── .env.example
```

**Luồng kiểm tra một job:**

```
Upload file
   → document_reader đọc text (PDF embedded → OCR nếu cần)
   → extractor.detect_document_type()  phân loại chứng từ
   → extractor.extract_structured_data()  LLM trả JSON → Pydantic validate
   → validation.validate_documents()  15 rule tất định
   → lưu audit_run + validation_issues → trả kết quả về UI
```

---

## 4. Cài đặt và chạy

### Yêu cầu
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Gemini API key (miễn phí là đủ)

### Bước 1 — Database

```bash
createdb expense_audit
psql -d expense_audit -f trasas_assignment.sql
```

File SQL tạo đủ 6 bảng: `processing_jobs`, `documents`, `document_extractions`,
`audit_runs`, `validation_issues`, `validation_issue_documents`.

### Bước 2 — Backend

```bash
python -m venv .venv
# Windows:  .venv\Scripts\Activate.ps1
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

Tạo file cấu hình:

```bash
cp .env.example .env        # Windows: Copy-Item .env.example .env
```

Sửa `.env`:

```ini
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/expense_audit
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
```

Chạy API:

```bash
uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

### Bước 3 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Giao diện: http://127.0.0.1:5173

Vite đã cấu hình proxy `/api` sang `127.0.0.1:8000`, nên **không cần cấu hình CORS**.

> Lưu ý: `DATABASE_URL` dùng scheme `postgresql+psycopg` (driver psycopg 3).
> Nếu dùng `postgresql+psycopg2` thì cần cài `psycopg2-binary` thay vì `psycopg`.

---

## 5. Hướng dẫn sử dụng

1. Mở trang chủ → bấm **Tạo Job mới**.
2. Ở trang chi tiết, upload các file PDF chứng từ (nhiều file một lục).
3. Bấm **Kiểm tra Expense Audit** để chạy trích xuất + kiểm tra chéo.
4. Xem kết quả ở khung giữa; bấm từng finding để xem bằng chứng.
5. Bấm vào một chứng từ trong sidebar để xem PDF cạnh kết quả kiểm tra.
6. Bấm **Kiểm tra** lần nữa để tạo lịch sử; mở lần cũ ở sidebar dưới để xem lại.

### Về chế độ xem lịch sử
Khi mở một lần kiểm tra cũ, hệ thống **chỉ cho phép xem**:
nút upload, xoá chứng từ và nút kiểm tra bị ẩn đi. Ràng buộc này được enforce ở
**backend** chứ không chỉ ở giao diện — các API ghi sẽ trả về `409 Conflict`
nếu request có kèm `run_id` của một lần đang xem lại.

---

## 6. API chính

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/health` | Kiểm tra dịch vụ |
| `POST` | `/api/jobs` | Tạo hồ sơ mới |
| `GET` | `/api/jobs` | Danh sách job kèm số liệu tổng hợp (dashboard) |
| `GET` | `/api/jobs/{job_id}` | Chi tiết job |
| `DELETE` | `/api/jobs/{job_id}` | Xoá job (cascade toàn bộ dữ liệu) |
| `POST` | `/api/documents/upload` | Upload chứng từ (`multipart`) |
| `GET` | `/api/documents/by-job/{job_id}` | Danh sách chứng từ của job |
| `DELETE` | `/api/documents/{document_id}` | Xoá chứng từ + file vật lý |
| `GET` | `/api/documents/{document_id}/file` | Trả file (hiển thị inline) |
| `GET` | `/api/documents/{document_id}/text` | Text đã đọc + nguồn từng trang |
| `POST` | `/api/AI/jobs/{job_id}/compare` | **Chạy kiểm tra toàn bộ bộ chứng từ** |
| `GET` | `/api/AI/jobs/{job_id}/report` | Báo cáo (mặc định lần mới nhất) |
| `GET` | `/api/AI/jobs/{job_id}/report?run_id=` | Báo cáo của một lần cũ |
| `GET` | `/api/AI/jobs/{job_id}/runs` | Danh sách các lần đã kiểm tra |
| `GET` | `/api/AI/jobs/{job_id}/runs/{run_id}` | Chi tiết một lần kiểm tra |
| `GET` | `/api/issues/by-job/{job_id}` | Danh sách issue đã lưu |
| `PATCH` | `/api/issues/{issue_id}/status` | Đánh dấu đã xem / đã xử lý |

### Ví dụ: kiểm tra một job

```bash
curl -X POST http://127.0.0.1:8000/api/AI/jobs/<job_id>/compare
```

```json
{
  "status": "COMPLETED",
  "documents_used": ["invoice", "payment_request", "purchase_order"],
  "validation": {
    "risk_level": "HIGH",
    "summary": { "FAIL": 2, "REVIEW": 1, "PASS": 12 },
    "findings": [
      {
        "rule_id": "BANK-001",
        "severity": "HIGH",
        "status": "FAIL",
        "message": "Số tài khoản thụ hưởng trên Payment Request khác với PO/Invoice...",
        "documents": ["purchase_order", "invoice", "payment_request"],
        "evidence": {
          "source_accounts": { "purchase_order": "888800001042" },
          "payment_request_account": "888800009917"
        }
      }
    ]
  },
  "persisted_issue_ids": ["..."]
}
```

---

## 7. Các rule kiểm tra

Toàn bộ rule nằm trong `app/services/validation.py`, **không dùng LLM**, nên cho kết quả
giống nhau mỗi lần chạy. Mỗi finding có `rule_id`, `severity`, `status`, `evidence`.

| Rule | Kiểm tra | Mức |
|---|---|---|
| `DOC-001` | Thiếu chứng từ nào trong bộ (PO / Invoice / PR) | MEDIUM |
| `FIELD-001` | Thiếu trường bắt buộc của từng loại chứng từ | MEDIUM |
| `REF-PO-001` | Số PO giữa Purchase Order và Payment Request | HIGH |
| `REF-INV-001` | Số hóa đơn giữa Invoice và Payment Request | HIGH |
| `REF-PO-002` | Số hóa đơn có nhất quán với dải số PO trong bộ không | MEDIUM |
| `PARTY-BUYER-001` | Bên mua ở PO và Invoice có khớp không | HIGH |
| `PARTY-SELLER-001` | Bên bán ở PO và Invoice có khớp không | HIGH |
| `AMOUNT-PO-INV-001` | Tổng tiền PO có bằng tổng tiền hóa đơn không | HIGH |
| `AMOUNT-INV-PR-001` | Giá trị hóa đơn ở PR có khớp tổng Invoice không | HIGH |
| `AMOUNT-PR-001` | Số tiền đề nghị = giá trị hóa đơn − đã thanh toán | HIGH |
| `MATH-LINE-001` | Tổng tiền từng dòng có cộng đúng không | MEDIUM |
| `ITEM-001` | Danh mục hàng PO có khớp Invoice không | HIGH |
| `ITEM-QTY-001` | Số lượng từng mã hàng có khớp không | MEDIUM |
| `BANK-001` | Số tài khoản thụ hưởng có khớp tài khoản nhà cung cấp không | HIGH |
| `BANK-NAME-001` | Tên chủ tài khoản có khớp tên nhà cung cấp không | HIGH |
| `APPROVAL-001` | Có bước phê duyệt chưa hoàn tất không | MEDIUM |

**Mức rủi ro tổng thể** = `HIGH` nếu có bất kỳ finding nào `HIGH` ở trạng thái
`FAIL`/`REVIEW`; nếu không thì `MEDIUM` khi có `FAIL`/`REVIEW`, còn lại là `LOW`.

### Ví dụ rủi ro thực tế mà hệ thống bắt được
Trong bộ chứng từ mẫu, Payment Request chuyển tiền cho tài khoản
`888800009917` mang tên **cá nhân** (`NGUYỄN VĂN PHÚ`), trong khi PO và Invoice
đều ghi tài khoản công ty `888800001042`. Hai rule `BANK-001` và `BANK-NAME-001`
cùng bắt được đây — đây là mẫu gian lận chuyển khoản khá phổ biến.

---

## 8. Schema database

| Bảng | Mô tả |
|---|---|
| `processing_jobs` | Mỗi bộ hồ sơ. Có cache `risk_level`, `validation_summary` của lần chạy mới nhất để dashboard không phải join |
| `documents` | File đã upload kèm loại, số trang, `text_preview`, `page_sources` |
| `document_extractions` | Kết quả trích xuất + evidence của từng chứng từ |
| `audit_runs` | **Lịch sử các lần kiểm tra.** Mỗi lần bấm nút tạo 1 dòng, có `run_number` tăng dần |
| `validation_issues` | Issue phát hiện được, gắn với `audit_run_id` để biết thuộc lần nào |
| `validation_issue_documents` | Quan hệ nhiều-nhiều issue ↔ chứng từ |

### Vì sao cần bảng `audit_runs`
Nếu chỉ lưu kết quả mới nhất trên `processing_jobs`, thì mỗi lần kiểm tra sẽ
**ghi đè** lần trước và người dùng không xem lại được kết quả cũ — cũng tốn tiền
gọi LLM lần nữa. `audit_runs` giữ lại từng lần, kèm `document_snapshot` (tên +
loại chứng từ tại thời điểm chạy) để lịch sử vẫn đọc được ngay cả khi file gốc
đã bị xoá.

---

## 9. Quyết định thiết kế

**Tách LLM khỏi logic kiểm tra.** LLM chỉ trả về JSON có cấu trúc; việc so số
tiền, so tài khoản... do code tất định thực hiện. Nhờ vậy kết quả kiểm toán có
thể tái lập và giải thích được.

**Cache kết quả trích xuất.** `extractor` tách riêng phần đọc file và phần gọi
LLM, nên khi bấm kiểm tra lần 2 hệ thống chỉ chạy lại rule, không gọi lại LLM.

**Ưu tiên tiết kiệm.** Mỗi chứng từ cần 2 lần gọi LLM (phân loại + trích xuất).
Với 3 chứng từ là 6 lần cho lần chạy đầu; các lần sau gần như miễn phí nhờ cache.

**Đọc file trước, phân loại sau.** `document_reader` chỉ lo lấy text, còn phân loại
do LLM quyết định — vì định dạng chứng từ rất đa dạng, quy tắc cứng dễ sai.

**Ràng buộc ở tầng API.** Chế độ chỉ đọc khi xem lịch sử được kiểm soát bằng
`run_id` và trả `409`, thay vì chỉ ẩn nút trên giao diện.

---

## 10. Hạn chế đã biết

- Chưa hỗ trợ ảnh (JPG/PNG) dù đề bài cho phép; `document_reader` mới nhận PDF/TXT/MD.
- OCR cần cài thêm Tesseract ở mức hệ điều hành, không chỉ cài `pytesseract`.
- Quy tắc so khớp tên bên liên quan dùng chuẩn hóa chuỗi đơn giản, chưa xử lý
  được trường hợp khác nhau về chữ hoa/thương mại (`CÔNG TY TNHH` vs `CÔNG TY TNHH`).
- Khi hồ sơ có **dưới 2 loại chứng từ khác nhau**, hệ thống từ chối so sánh và báo
  rõ loại còn thiếu, vì so sánh 1 chứng từ không có ý nghĩa đối chiếu chéo.
- Chưa có phân quyền người dùng và xác thực.
- Tiền tệ dùng `float`; với dữ liệu thực nên chuyển sang `Decimal`.

---

## 11. Công nghệ sử dụng

**Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x, Pydantic v2, PyMuPDF,
OpenAI SDK (trỏ sang endpoint tương thích của Gemini), psycopg 3

**Frontend:** React 18, React Router 6, Vite 5, Tailwind CSS 4

---

## 12. Demo

[![Demo Video](https://img.youtube.com/vi/oxPfaEdITt4/hqdefault.jpg)](https://www.youtube.com/watch?v=oxPfaEdITt4)

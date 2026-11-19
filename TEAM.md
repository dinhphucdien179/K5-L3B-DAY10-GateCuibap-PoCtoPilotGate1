# Team

## Thông tin nhóm

- Tên nhóm (`TenNhom`, không dấu, không khoảng trắng): `GateCuibap`
- Lớp: `L3B`
- Repo của bàn: `K5-L3B-DAY10-GateCuibap-PoCtoPilotGate1`
- Thẻ sự cố đã bốc (S1–S8): `S6` (Tài xế bị trừ thưởng vì kiện của hãng khác)
- Khai về thứ tự làm việc:
  - Thẻ S6 được kéo về lúc 17:02 (commit `ac88a47`), **trước** khi ký tiêu chí (21:26, `aa39fcd`) và trước khi chốt vòng 1 (21:38, `9e4a02e9`).
  - Lần đánh giá đầu tiên vẫn chạy sau commit ký.
  - Bản chốt vòng 1 đúng bằng `lab10/guards.py` lúc 16:43 (commit `616de99`, blob `e5b6e28`), viết trước khi có thẻ.
  - Chi tiết: Phiếu B (đầu phiếu, B7.2) và Phiếu C mục C1.

## Thành viên

Họ tên đầy đủ và MSSV của **mọi** thành viên; bàn 3 người thì để trống dòng 4. Vai: Kỹ sư cổng · Sản phẩm và kinh doanh · Vận hành và pháp lý (README mục 3, phút 0–15).

| STT | Họ và tên | MSSV | Vai | Trưởng nhóm |
| --: | --------- | ---- | --- | :---------: |
|   1 | Đinh Phúc Diên | 2A202603876 | Kỹ sư cổng | ✔ |
|   2 | Lê Nguyễn Anh Khôi | 2A202603755 | Sản phẩm và kinh doanh | |
|   3 | Lê Nguyễn Anh Nhân | 2A202603838 | Vận hành và pháp lý | |
|   4 |           |      |     |             |

Ghi `members` trong `submission/submission.json` theo dạng `"HoVaTen-MSSV"`, khớp bảng trên.

## Cá nhân

Mỗi thành viên tự viết một mục bên dưới (chép mẫu, đổi tiêu đề thành họ tên không dấu và MSSV, ví dụ `## NguyenVanAn-20241234`).

## DinhPhucDien-2A202603876

### Phần việc phụ trách

- Vai: Kỹ sư cổng, trưởng nhóm, giữ máy chạy chính (thư mục `runs/` nằm trên máy này).
- Câu của đề: 1.3, 2.1, 2.2, 2.6–2.8, 3.1 (trace), 3.5 (code), 3.6.
- Mục phiếu: Phiếu A mục A2 (cột Offline); Phiếu B mục B0–B2, B7.1–B7.3; Phiếu C mục C0, C2, C6–C8.
- File: `lab10/guards.py`, `lab10/monitors.py`.

### Đóng góp cụ thể

- Vòng 1:
  - Viết cổng `pre_guard` và `write_gate`, gồm W1, W2, W4–W12: quyền lợi tính lại từ DB, chặn ghi lặp và đơn đã hoàn, kiểm phê duyệt, trần trong `ops_limits`, ghi lỗi đúng kiện, thông báo cho hãng chỉ gồm các trường chính sách cho phép.
  - Viết 16 chỉ số theo dõi.
  - Kết quả: bộ nền từ 0.9909 lên 1.0; hoàn sai và lỗi oan về 0.
- Vòng 2 (thẻ S6):
  - Vá W7b: ticket không nêu kiện mà có từ 2 kiện đủ điều kiện ghi lỗi, khác hãng hoặc khác tài xế, thì chuyển người trước `issue_refund`.
  - Ghi log can thiệp cho W7, W7b, W11; thêm 3 monitor `ambiguous_fault_target_rate`, `fault_target_fixed_rate`, `strike_cap_hold_rate`.
  - Kết quả trên gói S6: pass 0.8333 (prepared) lên 1.0 (after), lỗi oan 10 về 0, ROI 0.05 lên 0.46.
- Chạy toàn bộ lệnh đo: ký, eval, gate, checkpoint, grade, check_submission.

### Bằng chứng

- Commit:
  - `616de99`: cổng vòng 1 và monitor.
  - `aa39fcd`: ký tiêu chí.
  - `fcbc3d3`: chốt vòng 1 và quyết định v1.
  - Commit vòng 2: `guards.py`, `monitors.py`.
- Mã lần chạy:
  - Bộ nền: `R-base-before-20261119-212650-a033a4`, `R-base-after-20261119-212722-855177`, `R-base-prepared-20261119-213851-855177`.
  - Gói S6: `R-S6-grade-20261119-214103-855177` (prepared), `R-S6-after-20261119-214237-f25bc7` (W7b), `R-S6-grade-20261119-214350-48706e` (bản cuối, PASS-VISIBLE).
- Dòng trong phiếu: Phiếu B mục B0, B7.1; Phiếu C mục C0, C7, C8.
- Dùng AI:
  - Dùng Claude (Claude Code) để đọc codebase.
  - Soạn nháp các phiếu A/B/C từ report và trace thật.
  - Viết phần code vòng 2 (W7b, log, 3 monitor).
  - Mọi ngưỡng, con số config và quyết định v1/v2 do bàn duyệt.

### Exit ticket

- **Học được:**
  - Cổng tốt phải **hẹp**: ca hợp lệ ẩn là điều kiện cứng.
  - Khi đầu vào không đủ để biết ai chịu lỗi, hệ thống **không được đoán**, mà phải dừng trước lệnh ghi tiền.
- **Còn chưa chắc:** test ẩn có ca hai kiện cùng hãng nhưng khác tài xế, hoặc khách nêu sai kiện không, và cổng W7b có xử lý đúng các ca đó không.

## LeNguyenAnhKhoi-2A202603755

### Phần việc phụ trách

- Vai: Sản phẩm và kinh doanh.
- Câu của đề: 1.1, 1.6, 2.3, 2.9, 3.2, quyết định v1 và v2.
- Mục phiếu: Phiếu A mục A1 (câu 1.1), A4, A5; Phiếu B mục B3, B7.4, B8; Phiếu C mục C5 (câu 3.2), C12.
- File: `config/acceptance_criteria.json`, `config/operating_gates.json` (mục `business`).

### Đóng góp cụ thể

(Khôi tự viết.)

### Bằng chứng

(Khôi tự viết: mã commit, mã lần chạy, dòng trong phiếu.)

### Exit ticket

(Khôi tự viết.)

## LeNguyenAnhNhan-2A202603838

### Phần việc phụ trách

- Vai: Vận hành và pháp lý.
- Câu của đề: 1.2, 1.4, 2.4, 2.10, 3.3, 3.7.
- Mục phiếu: Phiếu A mục A1 (câu 1.2), A2 (cột Telemetry); Phiếu B mục B4, B5, B7.5, B7.6; Phiếu C mục C3.2, C4, C9–C11.
- File: `config/operating_gates.json` (mục `operations`, `legal`), `submission/submission.json`.

### Đóng góp cụ thể

(Nhân tự viết.)

### Bằng chứng

(Nhân tự viết: mã commit, mã lần chạy, dòng trong phiếu.)

### Exit ticket

(Nhân tự viết.)

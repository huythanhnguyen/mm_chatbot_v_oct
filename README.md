## MM Search Bot — Kiến trúc và Hướng dẫn tổng quan

README này mô tả cấu trúc dự án, vai trò của các thành phần chính (backend agent, công cụ, dữ liệu, frontend), và gợi ý cách bắt đầu làm việc với mã nguồn.

### Mục tiêu dự án
- **Tìm kiếm/tham vấn sản phẩm thông minh**: Tận dụng công cụ tìm kiếm, bộ nhớ ngữ cảnh, và API CnG để trả lời truy vấn mua sắm.
- **Giao diện trò chuyện**: Frontend hiển thị hội thoại, đề xuất sản phẩm, giỏ hàng, đăng nhập, và chi tiết sản phẩm.
- **Ghi nhật ký & phân tích**: Theo dõi tương tác và hoạt động của agent để tối ưu chất lượng trả lời.

---

## Cấu trúc thư mục

```
d:\mm_search_bot\
  AGENT_LOGGING_GUIDE.md
  CLEANUP_SUMMARY.md
  README-INSTALL.md
  requirements.txt
  test_agent_integration.py
  api-worker-windows (1)\
    api-worker-windows.exe
  app\
    agent.py
    agent_analytics.py
    log_api.py
    optimized_memory_agent.py
    memory_config.py
    runner_config.py
    data\
      mm_data_index.py
      MM_general_data\ (JSON chính sách, thông tin cửa hàng, v.v.)
    eval\
      default.json
    shared_libraries\
      constants.py
      safety.py
    tools\
      compare.py
      explore.py
      search.py
      context_optimized_tools.py
      memory_tools.py
      cng\
        product_tools.py
        api_client\ (client CnG: auth, cart, product, config,...)
  docs\ (tài liệu kỹ thuật & nhật ký)
  frontend\ (ứng dụng web Vite + React + TypeScript)
```

---

## Kiến trúc tổng thể

- **Agent Backend (Python, thư mục `app/`)**
  - Điều phối phiên hội thoại, gọi công cụ tìm kiếm/sản phẩm, dùng bộ nhớ để cung cấp trả lời theo ngữ cảnh, và ghi nhật ký tương tác.
  - Tách rõ phần lõi agent (`agent.py`, `optimized_memory_agent.py`) với lớp công cụ (`tools/`) và thư viện chia sẻ (`shared_libraries/`).

- **Công cụ (Tools, `app/tools/`)**
  - `search.py`, `explore.py`, `compare.py`: Tìm kiếm, duyệt, và so sánh sản phẩm.
  - `context_optimized_tools.py`: Gọi công cụ có tối ưu theo ngữ cảnh hội thoại.
  - `memory_tools.py`: Truy cập/ghi nhớ thông tin ngắn hạn/dài hạn.
  - `cng/`: Tích hợp API CnG (xem mục CnG bên dưới).

- **Tích hợp CnG (`app/tools/cng/`)**
  - `api_client/`: Client Python kiểu module hóa, gồm `auth.py`, `product.py`, `cart.py`, `config.py`, `client_factory.py`, `response.py`, v.v.
  - `product_tools.py`: Lớp adapter công cụ để agent gọi sang client CnG.

- **Bộ nhớ & dữ liệu (`app/data/`, `app/memory_config.py`)**
  - `mm_data_index.py`: Lập chỉ mục dữ liệu nội bộ (chính sách, cửa hàng, hướng dẫn mua hàng) để trả lời nhanh.
  - `MM_general_data/*.json`: Nguồn dữ liệu tĩnh: chính sách, thông tin cửa hàng, hướng dẫn, v.v.
  - `memory_config.py`: Cấu hình tầng nhớ (cache, giới hạn, chiến lược ưu tiên, v.v.).

- **An toàn & hằng số (`app/shared_libraries/`)**
  - `safety.py`: Quy tắc an toàn/trung lập nội dung agent.
  - `constants.py`: Hằng số dùng chung giữa các module.

- **Ghi nhật ký & phân tích**
  - `log_api.py`: Gateway ghi sự kiện/nhật ký từ agent.
  - `agent_analytics.py`: Tổng hợp/đo lường hành vi để cải thiện chất lượng câu trả lời.
  - `docs/agent_logs_YYYY-MM-DD.json`: Mẫu nhật ký ngày.

- **Frontend (`frontend/`)**
  - Vite + React + TypeScript.
  - Thành phần chính: `ChatMessagesView.tsx`, `InputForm.tsx`, `SessionManager.tsx`, `ProductGrid.tsx`, `ProductDetailModal.tsx`, `CartPanel.tsx`, `LoginPanel.tsx`, `ThinkingProcess.tsx`, `TypingIndicator.tsx`, v.v.
  - Dịch vụ: `services/authService.ts`, `services/cartService.ts`.
  - Kiểu dữ liệu: `types/` (auth, cart, chat, product).

---

## Luồng hoạt động của Agent (tóm tắt)

1. Frontend gửi truy vấn của người dùng tới backend.
2. `app/agent.py` nhận yêu cầu, chuẩn hóa ngữ cảnh, áp dụng quy tắc an toàn (`shared_libraries/safety.py`).
3. Agent gọi công cụ phù hợp:
   - Tìm sản phẩm: `tools/search.py` → `tools/cng/product_tools.py` → `tools/cng/api_client/*`.
   - So sánh/duyệt: `tools/compare.py`, `tools/explore.py`.
   - Khai thác dữ liệu tĩnh: `data/mm_data_index.py` + `MM_general_data/*.json`.
4. Agent tổng hợp kết quả, cập nhật/bổ sung bộ nhớ (`memory_tools.py`), và trả về câu trả lời có cấu trúc cho frontend.
5. `log_api.py`/`agent_analytics.py` ghi sự kiện và số liệu phục vụ giám sát.

---

## Các tệp/Module quan trọng

- `app/agent.py`: Điểm vào chính của agent, điều phối gọi công cụ và xử lý phiên.
- `app/optimized_memory_agent.py`: Biến thể agent ưu tiên hiệu năng/bộ nhớ ngữ cảnh.
- `app/tools/search.py`, `app/tools/explore.py`, `app/tools/compare.py`: Bộ công cụ tìm kiếm/khám phá/so sánh.
- `app/tools/context_optimized_tools.py`: Tối ưu chọn công cụ dựa trên ngữ cảnh hội thoại.
- `app/tools/memory_tools.py`: Đọc/ghi bộ nhớ tác vụ và tri thức.
- `app/tools/cng/api_client/*`: Client API CnG (xác thực, sản phẩm, giỏ hàng, cấu hình, phản hồi chuẩn hóa).
- `app/data/mm_data_index.py`: Lập chỉ mục dữ liệu tĩnh và truy vấn nhanh.
- `app/shared_libraries/safety.py`: Quy tắc an toàn nội dung.
- `app/log_api.py`, `app/agent_analytics.py`: Ghi nhật ký và phân tích hoạt động.

---

## Frontend (tóm tắt)

- Khởi tạo tại `frontend/` với Vite.
- UI chính: màn hình chào (`WelcomeScreen.tsx`), khung hội thoại (`ChatMessagesView.tsx`), nhập liệu (`InputForm.tsx`), quản lý phiên (`SessionManager.tsx`), hiển thị sản phẩm (`ProductGrid.tsx`, `ProductCard.tsx`, `ProductDetailModal.tsx`), giỏ hàng (`CartPanel.tsx`), đăng nhập (`LoginPanel.tsx`).
- Thư viện UI: các thành phần trong `components/ui/` (button, card, modal, input, textarea, badge).

---

## Thiết lập & chạy

- Xem chi tiết cài đặt tại `README-INSTALL.md`.
- Gợi ý nhanh cho backend:
  1) Cài Python (>=3.10) và các gói: `pip install -r requirements.txt`.
  2) Thiết lập biến môi trường/API keys cho CnG (xem `app/tools/cng/api_client/config.py`).
  3) Khởi động tiến trình backend agent theo cách triển khai của bạn (ví dụ qua một runner hoặc tích hợp với API worker nếu có).

- Gợi ý nhanh cho frontend:
  1) `cd frontend`
  2) Cài đặt: `npm install` (hoặc `pnpm install`)
  3) Chạy dev: `npm run dev`

Lưu ý: Repo có thể đi kèm `api-worker-windows.exe` (thư mục `api-worker-windows (1)/`) cho môi trường Windows. Tùy vào triển khai của bạn, có thể dùng làm tiến trình trung gian giao tiếp với backend agent.

---

## Kiểm thử

- `test_agent_integration.py`: Bài kiểm thử tích hợp agent ở mức cơ bản.
- `tests/`: Các kiểm thử bổ sung (nếu có); một số tệp kiểm thử lịch sử có thể đã được dọn dẹp.

---

## Ghi nhật ký & phân tích

- Xem `AGENT_LOGGING_GUIDE.md` để cấu hình và chuẩn ghi log.
- Nhật ký ví dụ nằm trong `docs/agent_logs_YYYY-MM-DD.json`.
- `agent_interactions.log` ở root là tệp log tổng hợp (nếu bật).

---

## Bảo trì & mở rộng

- Thêm công cụ mới: tạo module dưới `app/tools/` và tích hợp vào `agent.py` hoặc `context_optimized_tools.py` để điều phối.
- Tích hợp API mới: xây dựng client trong một thư mục con (tương tự `tools/cng/api_client/`) và tạo lớp adapter công cụ.
- Mở rộng bộ nhớ: cập nhật `memory_config.py` và các hàm trong `memory_tools.py` để lưu/đọc tri thức mong muốn.
- Chuẩn hóa dữ liệu tĩnh: cập nhật `app/data/mm_data_index.py` và các JSON trong `MM_general_data/`.

---

## Tài liệu liên quan

- `docs/[Tech] MMVN & CDP 365 API Smart Search.md`: Ghi chú kỹ thuật về Smart Search.
- `docs/CnG API Doc.md`: Tài liệu về tích hợp API CnG.
- `docs/Antsomi_Filter_Analysis.md`: Phân tích bộ lọc Antsomi (liên quan tìm kiếm/sắp xếp).
- `Memory_Agent_Usage_Guide.md`, `Memory_Integration_Guide.md`: Hướng dẫn về agent bộ nhớ và tích hợp bộ nhớ.

---

## FAQ ngắn

- Agent gọi API CnG ở đâu? → Trong `app/tools/cng/api_client/` qua `product_tools.py`.
- Dữ liệu tĩnh nằm ở đâu? → `app/data/MM_general_data/` và được lập chỉ mục bởi `mm_data_index.py`.
- Quy tắc an toàn ở đâu? → `app/shared_libraries/safety.py`.
- Frontend giao tiếp với backend thế nào? → Tuỳ cấu hình triển khai; frontend gọi endpoint/dịch vụ đã cấu hình để chuyển truy vấn đến agent (tham khảo các service trong `frontend/src/services/`).

---

Nếu bạn cần phần hướng dẫn chạy cụ thể cho môi trường của mình, hãy mở một issue hoặc cung cấp thêm chi tiết (endpoint backend, biến môi trường, cơ chế auth) để README có thể được bổ sung chính xác hơn.

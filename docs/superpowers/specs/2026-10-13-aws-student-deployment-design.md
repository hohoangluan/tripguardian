# Thiết kế thử nghiệm AWS và Ansible cho TripGuardian

Tài liệu làm việc tạm theo `RULE.md` §0.1. Mục tiêu trước mắt là tự triển khai thử trên AWS; chưa thay đổi cách production hiện tại và chưa tự động hóa bằng Ansible.

## 1. Mục tiêu

- Học luồng triển khai một ứng dụng thật lên AWS với chi phí phù hợp sinh viên.
- Giữ Cloudflare làm lớp public, HTTPS và tunnel; AWS chỉ thay máy đang chạy origin.
- Chạy được User Web và API của TripGuardian trên một EC2 trong thời gian thử nghiệm.
- Kiểm chứng bằng test offline và smoke test sẵn có trước khi cho người ngoài dùng.
- Sau khi triển khai tay ổn định, dùng Ansible để tái tạo cùng máy và cùng quy trình.

Thử nghiệm thành công khi một EC2 mới có thể chạy TripGuardian, domain Cloudflare truy cập được, dữ liệu không nằm trong git, backup tải được khỏi EC2 và toàn bộ tài nguyên thử nghiệm có thể dừng hoặc xóa có chủ ý.

## 2. Hiện trạng liên quan

Production hiện chạy trên một máy bằng `./run.sh prod`:

- build User Web vào staging rồi chép sang `web/dist`;
- backup và migrate PostgreSQL;
- chạy harness ở `127.0.0.1:8769`, public server ở `127.0.0.1:28899` và notification worker;
- chạy PostgreSQL, SearXNG và OSRM cục bộ;
- `cloudflared` nối hostname public tới public server;
- smoke test kiểm tra test login bị tắt, guest đăng nhập được và tạo được hành trình.

Cloudflare không host ứng dụng. Nó nhận traffic public rồi chuyển qua tunnel tới origin. Vì vậy thử nghiệm AWS chỉ cần thay máy origin hiện tại bằng EC2; không cần đổi domain hoặc mở cổng `28899` ra Internet.

## 3. Các phương án

### A. Một EC2, mọi dịch vụ trên cùng máy — chọn cho lần thử đầu

Web, harness, worker, PostgreSQL, SearXNG, OSRM và `cloudflared` cùng chạy trên một EC2.

- Ưu: gần hiện trạng, ít dịch vụ AWS, dễ hiểu, dễ xóa, phù hợp học EC2 và Ansible.
- Nhược: một điểm lỗi; RAM có thể thiếu; database và ứng dụng tranh tài nguyên.

### B. EC2 + RDS + S3

Ứng dụng chạy trên EC2, PostgreSQL chuyển sang RDS, backup và artifact nằm ở S3.

- Ưu: học managed database, tách dữ liệu khỏi máy ứng dụng, phục hồi rõ hơn.
- Nhược: tăng chi phí và cấu hình mạng; chưa cần để chứng minh ứng dụng chạy được trên AWS.

### C. Container platform hoặc Kubernetes

Chạy ứng dụng bằng ECS/EKS, registry và nhiều dịch vụ managed.

- Ưu: gần kiến trúc cloud quy mô lớn.
- Nhược: chi phí và độ phức tạp vượt mục tiêu học hiện tại; khó phân biệt lỗi ứng dụng với lỗi platform.

Thứ tự chọn: **A → thêm S3 → Ansible → cân nhắc RDS**. Không dùng EKS, NAT Gateway, Application Load Balancer hoặc GPU instance trong thử nghiệm đầu.

## 4. Kiến trúc thử nghiệm

```text
Người dùng
    │ HTTPS
    ▼
Cloudflare DNS / bảo vệ / Tunnel
    │ kết nối outbound do cloudflared tạo
    ▼
EC2 Ubuntu
    ├── web/server.mjs          127.0.0.1:28899
    ├── harness                127.0.0.1:8769
    ├── notification worker
    ├── PostgreSQL container   127.0.0.1:5433
    ├── SearXNG container      127.0.0.1:8888
    └── OSRM container         127.0.0.1:5000
             │
             └── S3: backup PostgreSQL và gói dữ liệu
```

Security Group không mở các cổng ứng dụng trên ra Internet. Quản trị máy ưu tiên AWS Systems Manager Session Manager; nếu dùng SSH thì chỉ mở `22` cho IP quản trị trong thời gian cần thiết. EC2 cần outbound HTTPS để cài dependency, gọi API ngoài và nối Cloudflare Tunnel.

## 5. Phạm vi tài nguyên

### Bắt buộc cho lần thử đầu

- Một EC2 Linux x86-64.
- EBS đủ chứa source, môi trường Python/Node, snapshot, OSRM và log thử nghiệm.
- Một IAM role quyền tối thiểu cho EC2 đọc/ghi đúng S3 bucket thử nghiệm.
- Một S3 bucket private cho backup và artifact; bật Versioning và Lifecycle phù hợp.
- Cloudflare Tunnel token lưu ngoài git.

Không chốt instance type trước khi đo. Có thể bắt đầu bằng loại nhỏ thuộc Free Tier/credit đang hiện trong tài khoản; nếu build hoặc runtime hết RAM thì tăng một bậc và ghi lại số đo. Không chọn GPU instance. Các bước crawl, ASR, photo ranking, build index cần GPU tiếp tục chạy trên máy hiện tại; EC2 chỉ nhận output đã tạo.

### Chưa dùng

- RDS trong lần chạy đầu.
- EKS/ECS và container registry.
- Load balancer, Auto Scaling và nhiều Availability Zone.
- NAT Gateway hoặc private subnet cần NAT.
- AWS-hosted LLM/GPU.

## 6. Bảo vệ chi phí và tài khoản

1. Ưu tiên AWS Free Plan hoặc lab do trường cấp. Kiểm tra ngày hết credit trước khi tạo tài nguyên.
2. Bật MFA cho root; công việc thường ngày dùng IAM/Identity Center, không dùng root.
3. Nếu dùng Paid Plan, tạo AWS Budget và cảnh báo chi phí ngay trước khi deploy.
4. Gắn tag tối thiểu: `Project=tripguardian`, `Environment=learning`, `Owner=student`.
5. Chỉ chọn một Region cho toàn bộ thử nghiệm.
6. Dừng EC2 khi không dùng. Nhớ rằng EBS, snapshot, public IPv4, RDS hoặc tài nguyên khác vẫn có thể tính phí khi EC2 dừng.
7. Cuối mỗi buổi kiểm tra Resource Explorer/Billing và danh sách EC2, EBS, Elastic IP, RDS, S3.
8. Không tạo NAT Gateway, EKS hoặc GPU instance để “thử nhanh”.

## 7. Quy trình thử thủ công

### Bước 0 — Có baseline cục bộ

- Chạy test offline liên quan theo `README.md`.
- Chạy `./run.sh prod` và xác nhận smoke test pass trên máy hiện tại.
- Ghi dung lượng `data/`, `osrm-data/`, `web/dist`, RAM lúc idle và RAM lúc tạo một hành trình.
- Xác định runtime có thật sự cần `HARNESS_GPU` hay có thể dùng index đã build sẵn trên CPU.

Baseline này quyết định dung lượng EBS và instance type; không đoán bằng cảm giác.

### Bước 1 — Tạo EC2 tối thiểu

- Tạo EC2 Ubuntu trong public subnet đơn giản, không đặt database public.
- Gắn IAM role quyền tối thiểu tới đúng bucket.
- Kết nối bằng Session Manager hoặc SSH giới hạn IP.
- Cài Git, Python, Node, Docker, Chrome/Playwright dependency và `cloudflared` theo `README.md`.

### Bước 2 — Deploy tay một lần

- Clone đúng branch/commit cần thử.
- Cài Python bằng `pip install -e ".[dev]"` và web bằng `npm ci`.
- Chuyển gói dữ liệu qua S3 hoặc kênh riêng; không commit `data/`, snapshot chứa dữ liệu thật hoặc fixture crawl.
- Tạo `.env` trực tiếp trên EC2 với quyền đọc giới hạn; không đưa secret vào image, git hoặc log.
- Khởi tạo PostgreSQL bằng `./run.sh db`.
- Chuẩn bị OSRM từ artifact đã xử lý nếu việc dựng index trên EC2 quá nặng.
- Chạy test nhanh rồi `./run.sh prod`.
- Kiểm tra `logs/run/`, smoke test và URL local trước khi nối domain.

### Bước 3 — Nối Cloudflare

- Đặt tunnel token ngoài repository.
- Cho hostname thử nghiệm trỏ tới `http://127.0.0.1:28899`.
- Xác nhận chỉ landing, `/app`, asset và các API public được truy cập.
- Xác nhận `/admin`, analytics private, cổng database, harness, OSRM và SearXNG không truy cập trực tiếp từ Internet.

### Bước 4 — Backup ra khỏi EC2

- Chạy `./run.sh db-backup`.
- Upload file backup sang S3 bằng IAM role của EC2.
- Tải một backup về máy khác, kiểm tra gzip và thực hiện ít nhất một lần restore vào database thử nghiệm.
- Chỉ coi backup là hợp lệ sau khi restore kiểm chứng được.

### Bước 5 — Kết thúc thử nghiệm

- Lưu số đo RAM, CPU, dung lượng, thời gian build, thời gian smoke và chi phí thực tế.
- Stop EC2 nếu còn cần giữ; terminate nếu đã xong.
- Xóa volume, snapshot, Elastic IP hoặc tài nguyên tạm không còn dùng.
- Giữ backup cần thiết theo chính sách dữ liệu của dự án; xóa dữ liệu thật khỏi tài khoản lab sắp hết hạn.

## 8. Cổng chất lượng trước khi public

Mỗi lần deploy thử phải qua:

1. `python -m pytest -q` không gọi mạng.
2. Web type-check và production build thành công.
3. Database backup thành công trước migration.
4. Migration thành công.
5. Các service trả lời trên localhost.
6. Smoke test trong `run.sh` pass.
7. Kiểm tra tay một hành trình từ đăng nhập tới Planning.
8. Không có secret, `.env`, dữ liệu crawl hoặc token trong git và log.

Live test có LLM, weather, lodging hoặc OSRM chạy riêng; lỗi nguồn ngoài không được sửa test offline để che đi.

## 9. Vai trò của Ansible sau lần thử tay

Chỉ viết Ansible sau khi các bước tay trên đã chạy được một lần và ghi đủ dependency. Ansible sẽ tái tạo, không phát minh quy trình triển khai.

Một cấu trúc dự kiến:

```text
deploy/ansible/
    ansible.cfg
    inventories/
        learning.aws_ec2.yml
    group_vars/
        learning.yml
    playbooks/
        provision.yml
        deploy.yml
        backup.yml
        cleanup.yml
    roles/
        base/
        docker/
        tripguardian/
        cloudflared/
```

Ranh giới trách nhiệm:

- `provision.yml`: package hệ điều hành, user dịch vụ, thư mục, Docker và `systemd`.
- `deploy.yml`: lấy release, cài dependency, nhận artifact, migrate, restart, smoke; thất bại thì giữ release đang chạy.
- `backup.yml`: tạo backup, upload S3, kiểm tra object tồn tại.
- `cleanup.yml`: dừng service của thử nghiệm; không tự xóa dữ liệu production.

Secret lấy từ AWS Systems Manager Parameter Store, Secrets Manager hoặc Ansible Vault; không đặt plaintext trong inventory. EC2 inventory dùng plugin `amazon.aws.aws_ec2` và lọc theo tag `Project`/`Environment`.

## 10. Lỗi và phục hồi

| Lỗi | Xử lý dự kiến |
|---|---|
| Build web hỏng | Không chép staging sang `web/dist`; giữ site cũ |
| Migration hỏng | Dừng deploy, giữ log và backup; không tự chạy migration ngược |
| Service không lên | Đọc log, giữ release cũ và restart release cũ |
| Smoke test hỏng | Không quảng bá deploy là thành công; rollback ứng dụng |
| EC2 hết RAM | Dừng build/service nặng, đo lại và tăng instance hoặc tách workload |
| Tunnel mất kết nối | Origin vẫn kiểm tra được qua localhost; restart `cloudflared` bằng service manager |
| Mất EC2 | Tạo máy mới từ playbook, lấy artifact/data và restore PostgreSQL từ S3 |
| Credit sắp hết | Backup, tải dữ liệu cần giữ, rồi stop/terminate trước hạn |

## 11. Tiêu chí quyết định sau thử nghiệm

Sau lần thử đầu, chỉ chuyển sang Ansible khi trả lời được:

- Instance nhỏ nhất chạy ổn là loại nào, dựa trên số đo RAM/CPU?
- Dữ liệu nào phải nằm trên EBS, dữ liệu nào có thể lấy từ S3?
- OSRM và corpus index được dựng ở đâu, phát hành dưới dạng artifact nào?
- Runtime có cần GPU không?
- Một deploy mất bao lâu và phần nào gây downtime?
- Backup restore mất bao lâu và có đủ dữ liệu không?
- Chi phí một ngày bật máy và một tháng chạy liên tục là bao nhiêu theo Region đã chọn?

Nếu mục tiêu chỉ là demo và học DevOps, tiếp tục một EC2. Chỉ chuyển PostgreSQL sang RDS khi cần học managed database hoặc cần tách vòng đời database khỏi EC2. Chỉ thiết kế nhiều máy khi có nhu cầu uptime hoặc tải đo được.

## 12. Nguồn tham khảo

- [AWS Free Tier](https://aws.amazon.com/free/)
- [AWS Educate](https://aws.amazon.com/education/awseducate/)
- [Cloudflare Tunnel trên AWS](https://developers.cloudflare.com/tunnel/guides/aws/)
- [Ansible Amazon AWS Guide](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/docsite/guide_aws.html)
- Thiết lập và lệnh hiện tại: `README.md`, `run.sh`, `.env.example`.

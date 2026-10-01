// §3.6: the metric catalogue is fixed; numbers appear once events are recorded.
const GROUPS = [
  { name: 'Chất lượng', note: 'Quan trọng nhất. Chỉ số thành công của sản phẩm (Project_Context §18).', metrics: ['Kế hoạch được chấp nhận', 'Số lần sửa trước khi có kế hoạch hợp lệ', 'Độ tự tin sau khi lập kế hoạch', 'Còn phải tìm thêm chỗ khác'] },
  { name: 'Phễu sản phẩm', note: 'Landing đến chấp nhận kế hoạch.', metrics: ['Landing', 'CTA', 'Bắt đầu', 'Xong bối cảnh', 'Xem shortlist', 'Chọn địa điểm', 'Kiểm tra khả thi', 'Tạo lịch', 'Chấp nhận kế hoạch'] },
  { name: 'Quyết định', note: 'Ứng viên đến lựa chọn cuối.', metrics: ['Ứng viên nhập', 'Shortlist', 'Được chọn', 'Bỏ / khóa / so sánh / thay', 'Số xung đột'] },
  { name: 'Pilot', note: 'Theo đợt thử nghiệm.', metrics: ['Người tham gia', 'Hoàn thành', 'Thời gian lập kế hoạch trung vị', 'Số lần sửa trung bình', 'Phản hồi'] },
  { name: 'Acquisition', note: 'Ít quan trọng hơn chất lượng.', metrics: ['Lượt vào landing', 'Click CTA, CTR', 'Nguồn traffic', 'UTM source / medium / campaign / content', 'Chuyến bắt đầu theo nguồn'] },
]

export function Analytics() {
  return (
    <div className="a-page">
      <header className="a-head">
        <div>
          <h1>Analytics</h1>
          <p>Chưa có sự kiện nào được ghi, nên mọi ô đều trống. Ngưỡng chỉ đặt sau khi có baseline thật.</p>
        </div>
      </header>
      <div className="a-grid2">
        {GROUPS.map((g) => (
          <section className="a-card" key={g.name}>
            <h2>{g.name}</h2>
            <p className="a-muted">{g.note}</p>
            <table className="a-table a-table--compact">
              <tbody>
                {g.metrics.map((m) => (
                  <tr key={m}>
                    <td>{m}</td>
                    <td className="num a-muted">chưa có</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    </div>
  )
}

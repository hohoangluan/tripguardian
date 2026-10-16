import type { IconName } from '../ui/icons'

// Ways into a trip on the home page: a theme's prompt becomes the first turn of Tìm hiểu. Photos are real places of
// the corpus (Đồi Đa Phú, Tiệm Cà Phê Cũ 1991, Rừng thông, Hồ Xuân Hương, HongKong Cổ Trấn); they illustrate the
// theme and prove nothing about hours, weather or constraints.
export interface Theme {
  id: string
  title: string
  short: string
  tab: string // the word on the blog's side tab
  subtitle: string
  category: string
  icon: IconName
  photo: string
  alt: string
  prompt: string
  description: string
}

export const THEMES: Theme[] = [
  { id: 'cloud', tab: 'Săn mây', title: 'Săn mây, đón một ngày mới', short: 'Săn mây buổi sớm', subtitle: 'Theo giờ · Cho những buổi dậy sớm', category: 'Sáng sớm · Thiên nhiên', icon: 'cloud', photo: '/img/home/cloud.jpg', alt: 'Bình minh giữa rừng thông và mây tại Đồi Đa Phú, Đà Lạt', prompt: 'Mình muốn săn mây buổi sáng rồi ngồi cà phê ở Đà Lạt.', description: 'Bắt đầu bằng một buổi sáng giữa núi đồi. Mình sẽ hỏi thời gian đi và cách di chuyển trước khi gợi ý địa điểm cụ thể.' },
  { id: 'cafe', tab: 'Cà phê', title: 'Cà phê và một góc bình yên', short: 'Một góc cà phê', subtitle: 'Theo gu · Chậm lại một chút', category: 'Cà phê · Thư thả', icon: 'coffee', photo: '/img/home/cafe.jpg', alt: 'Mặt tiền Tiệm Cà Phê Cũ 1991, Đà Lạt', prompt: 'Mình muốn một chuyến Đà Lạt thư thả, có cà phê và góc ngồi yên tĩnh.', description: 'Một cách mở đầu cho chuyến đi thích ngồi lâu và chuyện trò. Địa điểm và thông tin thực tế được xem ở bước Lựa chọn.' },
  { id: 'pine', tab: 'Rừng thông', title: 'Đi một vòng giữa rừng thông', short: 'Giữa rừng thông', subtitle: 'Theo gu · Gần với thiên nhiên', category: 'Thiên nhiên · Đi dạo', icon: 'tree', photo: '/img/home/pine.jpg', alt: 'Rừng thông ở Đà Lạt', prompt: 'Mình thích thiên nhiên và muốn đi dạo giữa rừng thông ở Đà Lạt.', description: 'Thêm một chút thiên nhiên vào chuyến đi. Mình sẽ hỏi khả năng đi bộ của nhóm và mức di chuyển bạn thấy thoải mái.' },
  { id: 'lake', tab: 'Bên hồ', title: 'Chiều muộn, hẹn nhau bên hồ', short: 'Một chiều bên hồ', subtitle: 'Theo giờ · Ngắm chiều xuống', category: 'Chiều muộn · Thư giãn', icon: 'sun', photo: '/img/home/lake.jpg', alt: 'Hồ Xuân Hương, Đà Lạt', prompt: 'Mình muốn dành một buổi chiều muộn thư giãn bên hồ ở Đà Lạt.', description: 'Dành một khoảng trống cho buổi chiều. Thời điểm và nơi đến được kiểm tra khi đã có thông tin chuyến đi.' },
  { id: 'rain', tab: 'Ngày mưa', title: 'Một ngày mưa vẫn thật vui', short: 'Nếu trời đổ mưa', subtitle: 'Theo thời tiết · Gợi ý trong nhà', category: 'Trong nhà · Ngày mưa', icon: 'home', photo: '/img/home/indoor.jpg', alt: 'Không gian HongKong Cổ Trấn, Đà Lạt', prompt: 'Mình muốn chuẩn bị các chỗ trong nhà cho chuyến Đà Lạt nếu trời mưa.', description: 'Chuẩn bị một lựa chọn trong nhà để chuyến đi linh hoạt hơn. Nơi nào trú mưa được cần có bằng chứng trước khi vào lịch.' },
]

export const themeOf = (id: string) => THEMES.find((t) => t.id === id)

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase()
export const matches = (t: Theme, q: string) => fold(`${t.title} ${t.subtitle} ${t.category}`).includes(fold(q.trim()))

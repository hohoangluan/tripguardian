// Theme cards of Khám phá. Each is a way in: picking one sends {kind: 'theme', value: id} and the server writes the
// theme's fixed tastes (config/trip.yaml `themes`, same ids); no sentence is read. Photos are real places of that theme.
export const THEMES = [
  { id: 'area', area: 'Theo khu', title: 'Săn mây và cà phê Trại Mát', photo: '0x3171132a3f334c1f:0x2d831c6a07e1a1f9' },
  { id: 'rain', area: 'Theo thời tiết', title: 'Chỗ trong nhà khi mưa', photo: '0x3171136e35839279:0x33eb38c0b831e212' }, // Mọt Cafe & Books
  { id: 'hour', area: 'Theo giờ trong ngày', title: 'Chiều muộn bên hồ', photo: '0x31711321284ed77f:0x7752634a02e162e9' },
]
// What the user picked on Khám phá arrives as the first message text: the theme it names, if any.
export const themeOf = (text: string | null | undefined) => THEMES.find((t) => t.title === text) ?? null

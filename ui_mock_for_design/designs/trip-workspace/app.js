const app = document.querySelector('.app');
const scroll = document.querySelector('#discovery-scroll');
const originalDiscovery = scroll.innerHTML;
const originalChat = document.querySelector('#chat-log').innerHTML;
const places = [
  { id: 'coffee', rating: 4.9, reviews: 1100, hours: "06:30–19:00", name: 'Tiệm cà phê Thênh Thang', category: 'CÀ PHÊ', area: 'Trại Mát', image: 'coffee-place', group: 'coffee', reason: 'Cà phê — đúng loại nơi bạn muốn ghé', caveat: 'Độ yên tĩnh và giá đồ uống: chưa xác nhận.', duration: 'Thời gian ở lại: chưa chọn', map: 'Tiệm cà phê Thênh Thang Đà Lạt' },
  { id: 'lake', rating: 4.7, reviews: 2812, hours: "00:00–24:00", name: 'Hồ Xuân Hương', category: 'THIÊN NHIÊN', area: 'Trung tâm', image: 'lake-place', group: 'nature', reason: 'Không gian hồ — theo gu thiên nhiên của bạn', caveat: 'Tuyến đi bộ phù hợp và độ đông: cần kiểm tra thêm.', duration: 'Thời gian ở lại: chưa chọn', map: 'Hồ Xuân Hương Đà Lạt' },
  { id: 'cloud', rating: 4.3, reviews: 1176, hours: "04:30–18:00", name: 'Thiên Đường Săn Mây Cầu Đất', category: 'THIÊN NHIÊN', area: 'Cầu Đất', image: 'cloud-place', group: 'nature', reason: 'Một hướng khác cho sở thích thiên nhiên', caveat: 'Xa trung tâm hơn. Thời tiết và đường vào: chưa xác nhận.', duration: 'Chưa kiểm tra khả thi', map: 'Thiên Đường Săn Mây Cầu Đất' }
];
const state = { view: 'understand', pace: null, date: '', budget: '', filter: 'all', selected: new Set(), saved: new Set(), lodging: false, day: 0, variant: 'Ít di chuyển', notes: [], links: [], fixed: false };
const dialog = document.querySelector('#dialog');
let toastTimer;
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function hydrateIcons(root = document) { root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); }); }
function toast(message) { const el = document.querySelector('#toast'); el.textContent = message; el.classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('visible'), 3200); }
function showDialog(content) { document.querySelector('#dialog-content').innerHTML = content; hydrateIcons(dialog); const heading = dialog.querySelector('h2'); if (heading) { heading.id = 'dialog-title'; dialog.setAttribute('aria-labelledby', 'dialog-title'); } if (!dialog.open) dialog.showModal(); document.querySelector('#edit-trip')?.setAttribute('aria-expanded', 'true'); }
function dateLabel() { return state.date ? new Date(state.date + 'T12:00:00').toLocaleDateString('vi-VN') : 'Chưa rõ'; }
function chatMessage(text, who = 'user') { const div = document.createElement('div'); div.className = who === 'user' ? 'user-message' : 'bot-message'; if (who === 'bot') div.innerHTML = '<div class="bot-byline"><span class="bot-mark">' + icon('sparkle') + '</span><b>TripGuardian</b></div>'; const p = document.createElement('p'); p.textContent = text; div.appendChild(p); const log = document.querySelector('#chat-log'); log.appendChild(div); log.scrollTo({ top: log.scrollHeight, behavior: 'smooth' }); }
function renderBrief() {
  const dateButton = document.querySelector('#pick-date');
  if (dateButton) dateButton.innerHTML = 'Ngày đi: ' + escapeHtml(dateLabel()) + icon(state.date ? 'edit' : 'plus');
  const chip = document.querySelector('#pace-chip');
  if (chip) { chip.hidden = !state.pace; chip.textContent = state.pace || ''; }
  const note = document.querySelector('#match-note');
  if (note) note.innerHTML = state.pace ? `Đã thêm nhịp đi <b>${escapeHtml(state.pace.toLowerCase())}</b>. Vẫn giữ các nơi để bạn cân nhắc; chưa kiểm tra khả thi.` : 'Đang xem theo <b>cà phê</b> và <b>thiên nhiên</b>. Còn cần biết ngày đi để kiểm tra thêm.';
}
function placeCard(p) {
  const isSelection = state.view === 'selection';
  return `<article class="place-card"><div class="place-photo"><img src="assets/places/${p.image}.jpg" alt="${escapeHtml(p.name)} — ảnh Google Maps" loading="lazy"><span class="photo-source">Ảnh: Google Maps</span><button class="place-save ${state.saved.has(p.id) ? 'saved' : ''}" data-save="${p.id}" aria-label="Lưu ${escapeHtml(p.name)}" aria-pressed="${state.saved.has(p.id)}">${icon('heart')}</button></div><div class="place-meta"><div class="place-category">${p.category}<span>·</span>${p.area}</div><h3>${p.name}</h3><div class="place-rating"><span aria-label="Đánh giá">★</span><b>${p.rating.toFixed(1).replace('.',',')}</b><span>(${p.reviews.toLocaleString('vi-VN')} đánh giá)</span></div><p class="place-hours">${icon('calendar')}<span>${p.hours} · theo catalog</span></p><div class="match-reason">${icon('check')}<span>${p.reason}</span></div><p class="place-caveat">${p.caveat}</p><div class="place-card-footer"><span>${p.duration}</span><button data-detail="${p.id}">Xem chi tiết ${icon('arrow')}</button></div>${isSelection ? `<label class="selection-check"><input type="checkbox" data-select="${p.id}" ${state.selected.has(p.id) ? 'checked' : ''}>Chọn cho chuyến này</label>` : ''}</div></article>`;
}
function renderPlaces() { const grid = document.querySelector('#place-grid'); if (!grid) return; grid.innerHTML = places.filter(p => state.filter === 'all' || p.group === state.filter).map(placeCard).join(''); }
function setPace(pace) {
  state.pace = pace;
  document.querySelectorAll('[data-pace]').forEach(button => { const selected = button.dataset.pace === pace; button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
  chatMessage('Mình muốn đi ' + pace.toLowerCase() + '.');
  chatMessage(pace === 'Thong thả' ? 'Mình ghi lại nhịp thong thả. Bạn có thể ngồi cà phê lâu hơn; các nơi xa như Cầu Đất vẫn cần cân nhắc khi chọn.' : 'Mình đã cập nhật nhịp đi. Các nơi bên cạnh vẫn là bản xem trước; bạn chọn khi thấy đủ thông tin.', 'bot');
  renderBrief(); if (state.view === 'review') renderReview();
}
function footer(label, copy, button) { document.querySelector('#footer-label').textContent = label; document.querySelector('#footer-copy').textContent = copy; document.querySelector('#next').innerHTML = button + icon('arrow'); document.querySelector('#next').disabled = false; }
function row(label, value, kind = 'confirmed', edit = 'edit-trip') { return `<button class="checklist-row" data-action="${edit}"><span class="check-status ${kind === 'unknown' ? 'unknown' : ''}">${icon(kind === 'unknown' ? 'plus' : 'check')}</span><span><small>${label}</small><b>${escapeHtml(value)}</b></span><span class="row-edit">${icon('edit')}</span></button>`; }
function renderReview() {
  scroll.innerHTML = `<div class="review-intro"><span class="eyebrow">TRƯỚC KHI CHỌN ĐỊA ĐIỂM</span><h2>Chuyến này, mình hiểu như vậy.</h2><p>Bạn kiểm tra một lần. Điều gì chưa đúng, cứ sửa ngay tại đây.</p></div><div class="review-checklist"><div class="checklist-header"><span class="checklist-meter">${icon('check')}</span><div><h2>Đã đủ để xem nơi phù hợp</h2><p>Thông tin chưa rõ vẫn được giữ lại.</p></div></div><div class="checklist-items">${row('ĐI ĐÂU · TỪ LỜI BẠN', 'Đà Lạt · 3 ngày 2 đêm')}${row('ĐI CÙNG AI · TỪ LỜI BẠN', 'Người yêu · 2 người')}${row('DI CHUYỂN · TỪ LỜI BẠN', 'Xe máy')}${row('NGÀY ĐI', dateLabel(), state.date ? 'confirmed' : 'unknown', 'pick-date')}${row('NHỊP ĐI', state.pace || 'Chưa rõ', state.pace ? 'confirmed' : 'unknown', 'edit-pace')}${row('NGÂN SÁCH', state.budget || 'Chưa rõ', state.budget ? 'confirmed' : 'unknown', 'edit-budget')}</div></div><div class="review-block"><div class="review-block-heading">${icon('heart')}<h3>Những điều bạn thích</h3><span>Sở thích, có thể đổi</span></div><div class="brief-preferences"><span class="soft-chip">Cà phê <small>từ lời bạn</small></span><span class="soft-chip">Thiên nhiên <small>từ lời bạn</small></span>${state.pace ? `<span class="soft-chip">${escapeHtml(state.pace)} <small>từ câu trả lời</small></span>` : ''}</div></div><div class="review-block"><div class="review-block-heading">${icon('lock')}<h3>Điều cần giữ đúng</h3></div><p>${state.fixed ? 'Không chọn nơi có đường dốc. Những nơi chưa xác nhận đường vào sẽ chưa được chọn.' : 'Bạn chưa nêu yêu cầu bắt buộc. Thêm nếu chuyến này có điều không thể thay đổi.'}</p><button class="text-button" data-action="hard-rule">${state.fixed ? 'Sửa yêu cầu' : 'Thêm yêu cầu bắt buộc'} ${icon('plus')}</button></div><div class="review-block muted-block"><div class="review-block-heading">${icon('info')}<h3>Vẫn còn chưa rõ</h3></div><p>${state.date ? '' : 'Ngày đi · '}${state.budget ? '' : 'Ngân sách · '}Chỗ ở · Điểm xuất phát</p><p class="small">Bạn có thể bổ sung sau. Chỗ ở sẽ cần được chọn trước khi xem lịch trình.</p></div>${state.notes.length ? `<div class="review-block"><h3>Ghi chú của bạn</h3>${state.notes.map(n => `<p>${escapeHtml(n)}</p>`).join('')}</div>` : ''}<button class="text-button" data-action="back-chat">${icon('arrowLeft')}Tiếp tục trò chuyện, xem địa điểm</button>`;
  footer('BẠN LÀ NGƯỜI CHỐT', 'Chọn địa điểm sau khi xác nhận nhu cầu', 'Xác nhận & chọn nơi');
  scroll.scrollTop = 0;
}
function setView(view) {
  state.view = view;
  app.dataset.stage = view === 'planning' ? 'planning' : 'understand';
  document.querySelectorAll('.stage').forEach(button => button.classList.toggle('active', button.dataset.view === (view === 'review' ? 'understand' : view)));
  document.querySelector('.planning-panel').hidden = view !== 'planning';
  if (view === 'planning') { renderPlanning(); document.querySelector('#app-footer-note').textContent = 'Lịch minh họa · Chưa gọi kiểm tra khả thi'; return; }
  document.querySelector('#app-footer-note').textContent = view === 'selection' ? 'Bạn chọn địa điểm và chỗ ở trước khi xếp lịch' : 'Chưa nơi nào được tự động thêm vào lịch trình';
  if (view === 'review') { renderReview(); return; }
  scroll.innerHTML = originalDiscovery;
  renderBrief(); renderPlaces(); hydrateIcons(scroll);
  document.querySelectorAll('[data-filter]').forEach(button => { const active = button.dataset.filter === state.filter; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
  if (view === 'selection') {
    document.querySelector('.discovery-heading h2').textContent = 'Giữ lại những nơi bạn thích.';
    document.querySelector('.discovery-heading p').textContent = 'Màn nối minh họa · Chọn nơi và chỗ ở trước khi xếp lịch.';
    document.querySelector('.preview-badge').innerHTML = icon('check') + 'Bạn quyết định';
    const bar = document.createElement('div'); bar.className = 'selection-bar'; bar.innerHTML = `<span>Chỗ ở làm điểm đầu và cuối mỗi ngày.</span><label class="selection-check"><input id="lodging-check" type="checkbox" ${state.lodging ? 'checked' : ''}>Đã chọn chỗ ở minh họa</label>`; document.querySelector('#place-grid').before(bar);
    updateSelection();
  } else footer('KHI BẠN MUỐN ĐI TIẾP', 'Bạn sẽ chọn nơi ở bước tiếp theo', 'Tiếp tục đến chọn nơi');
  scroll.scrollTop = 0;
}
function updateSelection() { footer('BƯỚC CHỌN NƠI · MINH HỌA', state.selected.size + ' nơi đã chọn · ' + (state.lodging ? 'Đã có chỗ ở' : 'Cần chọn chỗ ở'), 'Xem lịch trình'); document.querySelector('#next').disabled = state.selected.size === 0 || !state.lodging || state.fixed; }
function renderPlanning() {
  const schedules = [
    [{ time:'09:00', title:'Bắt đầu từ chỗ ở đã chọn', desc:'Điểm neo minh họa. Chưa có địa chỉ thực tế.', home:true }, { time:'10:00', title:'Hồ Xuân Hương', desc:'Ghé hồ, dành thời gian nghỉ chân.', place:'lake', travel:'Chặng tiếp theo: chưa tính thời gian' }, { time:'12:00', title:'Ăn trưa & nghỉ', desc:'Chừa khoảng nghỉ; chưa chọn địa điểm ăn.' }],
    [{ time:'08:30', title:'Bắt đầu từ chỗ ở đã chọn', desc:'Giữ một buổi sáng thoải mái.', home:true }, { time:'09:30', title:'Tiệm cà phê Thênh Thang', desc:'Ngồi cà phê. Khoảng ở lại minh họa: 60–90 phút.', place:'coffee', travel:'Thời gian di chuyển: chưa được kiểm tra' }, { time:'12:00', title:'Ăn trưa & thời gian tự do', desc:'Khoảng nghỉ dành riêng cho hai bạn.' }],
    [{ time:'09:00', title:'Một buổi sáng chưa xếp kín', desc:'Bạn có thể quay lại chọn thêm nơi.' }, { time:'11:00', title:'Chuẩn bị rời Đà Lạt', desc:'Giờ trả phòng và giờ rời thành phố: chưa rõ.' }]
  ];
  const selectedNames = [...state.selected].map(id => places.find(p => p.id === id)?.name).filter(Boolean);
  const stops = schedules[state.day].filter(stop => !stop.place || state.selected.size === 0 || state.selected.has(stop.place));
  if (state.selected.has('cloud') && state.day === 2) stops.splice(0,0,{time:'Chưa xếp',title:'Thiên Đường Săn Mây Cầu Đất',desc:'Chưa đủ thông tin về giờ đi và đường vào để xếp.',place:'cloud'});
  document.querySelector('.planning-panel').innerHTML = `<aside class="plan-sidebar"><div><span class="eyebrow">CHUYẾN ĐI CỦA HAI BẠN</span><h2>Ba ngày<br>ở Đà Lạt.</h2><p>${dateLabel()} · Xe máy</p></div><div class="day-buttons">${['Một khoảng thảnh thơi','Cà phê & chậm lại','Trước khi trở về'].map((title,i)=>`<button class="day-button ${state.day === i ? 'active' : ''}" data-day="${i}" aria-pressed="${state.day === i}"><span class="day-number">${i+1}</span><span><b>Ngày ${i+1}</b><small>${title}</small></span></button>`).join('')}</div><button class="text-button" data-action="back-selection">${icon('plus')}Thêm hoặc đổi địa điểm</button><div class="plan-home"><span class="eyebrow">ĐIỂM ĐẦU & CUỐI MỖI NGÀY</span><b>Chỗ ở bạn đã chọn</b><button data-action="back-selection">Đổi chỗ ở ${icon('arrow')}</button><p>Địa chỉ đang là dữ liệu minh họa.</p></div></aside><div class="plan-main"><div class="plan-scroll"><div class="plan-heading"><div><span class="eyebrow">NGÀY ${state.day+1} · BẢN XEM TRƯỚC</span><h2>${['Một khoảng thảnh thơi.','Cà phê, rồi chậm lại.','Mang theo một chút Đà Lạt.'][state.day]}</h2><p>Bố cục lịch trình đề xuất · Giờ và thời gian đều minh họa</p></div><span class="preview-badge">${icon('info')}Chưa kiểm tra</span></div><div class="plan-tabs" aria-label="Phương án lịch trình">${['Ít di chuyển','Theo gu','Nhiều trải nghiệm'].map(v=>`<button data-variant="${v}" class="${state.variant===v?'active':''}" aria-pressed="${state.variant===v}">${v}</button>`).join('')}</div><div class="plan-assumption">${state.variant === 'Ít di chuyển' ? 'Ưu tiên gom nơi gần nhau. Chưa có địa chỉ chỗ ở để tính đường.' : state.variant === 'Theo gu' ? 'Ưu tiên dành thời gian cho cà phê và thiên nhiên.' : 'Cân nhắc thêm trải nghiệm; chỉ bổ sung sau khi bạn chọn và kiểm tra khả thi.'}${selectedNames.length ? '<br>Nơi bạn chọn: ' + selectedNames.map(escapeHtml).join(' · ') : ''}</div><div class="timeline">${stops.map((s,i)=>`<article class="timeline-stop"><time>${s.time}</time><div class="timeline-line"><span>${s.home?icon('home'):i+1}</span></div><div class="stop-content"><div class="stop-card"><h3>${s.title}</h3><p>${s.desc}</p>${s.place?'<p class="place-warning">Giờ mở cửa và đường đi chưa xác nhận.</p><button data-detail="'+s.place+'">Chi tiết địa điểm '+icon('arrow')+'</button>':''}</div>${s.travel?'<p class="travel-note">'+icon('route')+s.travel+'</p>':''}</div></article>`).join('')}<article class="timeline-stop"><time>Cuối ngày</time><div class="timeline-line"><span>${icon('home')}</span></div><div class="stop-content"><div class="stop-card"><h3>Trở lại chỗ ở</h3><p>Giờ về sẽ phụ thuộc lộ trình sau khi kiểm tra.</p></div></div></article></div><div class="plan-warning"><b>Một khoảng trống cũng là một lựa chọn.</b><p>Có thể giữ thời gian tự do, hoặc quay lại chọn thêm nơi. Mỗi thay đổi sẽ cần được kiểm tra trước khi chốt.</p><button data-action="back-selection">Xem nơi đã chọn ${icon('arrow')}</button></div></div><footer class="discovery-footer"><div><span class="small-label">LỊCH MINH HỌA</span><b>Chưa đủ dữ liệu để chốt lịch thực tế</b></div><button class="primary-button" disabled>Chốt lịch trình ${icon('lock')}</button></footer></div>`;
  hydrateIcons(document.querySelector('.planning-panel'));
}
function editDate() { showDialog('<span class="eyebrow">BỔ SUNG CHUYẾN ĐI</span><h2>Bạn định đi khi nào?</h2><p>Chưa chắc ngày cũng được. Mình sẽ giữ phần này là chưa rõ.</p><form id="date-form"><label>Ngày bắt đầu<input id="date-value" type="date" value="'+escapeHtml(state.date)+'"></label><button class="primary-button" type="submit">Lưu ngày đi '+icon('check')+'</button></form><button class="text-button" data-action="unknown-date">Mình chưa chắc</button>'); }
function editTrip() {
  const field = (label, value, action = 'summary-chat') => `<div class="summary-field ${value ? '' : 'is-unknown'}"><span>${label}</span><b>${escapeHtml(value || 'Chưa rõ')}</b><button type="button" class="text-button" data-action="${action}">${value ? 'Sửa' : 'Bổ sung'} ${icon('edit')}</button></div>`;
  showDialog(`<div class="summary-heading"><span class="eyebrow">TỪ NHỮNG ĐIỀU BẠN ĐÃ KỂ</span><h2>Tóm tắt chuyến đi</h2><p>Kiểm tra những gì mình đã hiểu. Bạn có thể bổ sung hoặc sửa bất cứ lúc nào.</p></div>
    <section class="summary-section"><h3>Chuyến đi của bạn</h3><div class="summary-grid">
    ${field('Điểm đến', 'Đà Lạt')}${field('Thời lượng', '3 ngày · 2 đêm')}${field('Đi cùng ai', 'Người yêu')}${field('Số người', '2 người')}${field('Phương tiện', 'Xe máy')}${field('Ngày bắt đầu', state.date ? dateLabel() : '', 'pick-date')}${field('Điểm xuất phát', '')}${field('Chỗ ở', '')}
    </div></section>
    <section class="summary-section"><h3>Gu và nhịp đi</h3><div class="summary-grid">${field('Sở thích', 'Cà phê · Thiên nhiên')}${field('Nhịp đi', state.pace, 'edit-pace')}${field('Ngân sách & phạm vi', state.budget, 'edit-budget')}${field('Thời gian di chuyển mỗi chặng', '')}</div></section>
    <section class="summary-section"><h3>Điều cần giữ đúng</h3><div class="summary-grid">${field('Yêu cầu bắt buộc', state.fixed ? 'Không chọn nơi có đường dốc' : '', 'hard-rule')}${field('Nơi bạn đã gửi', state.links.length ? state.links.length + ' link · chưa xác minh' : '')}</div></section>
    ${state.notes.length ? `<section class="summary-section"><h3>Ghi chú từ cuộc trò chuyện</h3><ul class="summary-notes">${state.notes.map(n=>`<li>${escapeHtml(n)}</li>`).join('')}</ul></section>` : ''}
    <p class="summary-footnote">Chưa rõ nghĩa là bạn chưa cung cấp thông tin. Sở thích có thể đổi; các nơi chưa được tự động chọn.</p><button class="primary-button summary-return" type="button" data-action="summary-chat">Tiếp tục trò chuyện ${icon('arrow')}</button>`);
}

function detail(id) { const p = places.find(p=>p.id===id); if (!p) return; showDialog(`<span class="eyebrow">${p.category} · ${p.area}</span><h2>${p.name}</h2><img src="assets/places/${p.image}.jpg" alt="${p.name} — ảnh Google Maps"><p>Ảnh: Google Maps · Tên địa điểm lấy từ catalog TripGuardian.</p><div class="modal-rows"><div><b>Vì sao đang hiện ở đây</b><span>${p.reason}. Đây là ví dụ trình bày trong mock, chưa chạy xếp hạng.</span></div><div><b>Điều cần cân nhắc</b><span>${p.caveat} Giá vé và giờ mở cửa: chưa có thông tin được xác nhận trong mock.</span></div></div><iframe title="Bản đồ Google Maps của ${p.name}" loading="lazy" src="https://maps.google.com/maps?q=${encodeURIComponent(p.map)}&output=embed"></iframe><a class="text-button" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.map)}" target="_blank" rel="noopener">Mở Google Maps ${icon('external')}</a>`); }
function action(name) {
  if (name === 'summary-chat') { dialog.close(); document.querySelector('#chat-input').focus(); return; }
  if (name === 'pick-date') return editDate();
  if (name === 'edit-trip') return editTrip();
  if (name === 'edit-pace') return showDialog('<span class="eyebrow">NHỊP ĐI CỦA CHUYẾN NÀY</span><h2>Bạn muốn đi thế nào?</h2><div class="pace-options">'+['Thong thả','Cân bằng','Đi nhiều'].map(p=>`<button data-set-pace="${p}">${icon('coffee')}<b>${p}</b></button>`).join('')+'</div>');
  if (name === 'edit-budget') return showDialog('<h2>Ngân sách cho chuyến này</h2><p>Ghi cả phạm vi, ví dụ “5 triệu cho cả hai, cả chuyến”. Chưa biết thì để trống.</p><form id="budget-form"><label>Ngân sách<input id="budget-value" value="'+escapeHtml(state.budget)+'" placeholder="Số tiền và phạm vi"></label><button type="submit" class="primary-button">Lưu ngân sách</button></form>');
  if (name === 'back-chat') { if (dialog.open) dialog.close(); return setView('understand'); }
  if (name === 'back-selection') return setView('selection');
  if (name === 'unknown-date') { state.date=''; dialog.close(); renderBrief(); if(state.view==='review')renderReview(); return; }
  if (name === 'hard-rule') return showDialog('<h2>Điều không thể thay đổi</h2><p>Ví dụ minh họa: không chọn nơi có đường dốc. Khi chưa có bằng chứng về đường vào, nơi đó sẽ chưa được chọn.</p><label class="selection-check"><input type="checkbox" id="hard-check" '+(state.fixed?'checked':'')+'>Không chọn nơi có đường dốc</label><button class="primary-button" id="save-hard">Lưu yêu cầu</button>');
}
document.addEventListener('click', event => {
  const button = event.target.closest('button,a'); if (!button) return;
  if (button.dataset.action) return action(button.dataset.action);
  if (button.dataset.view) return setView(button.dataset.view);
  if (button.dataset.pace) return setPace(button.dataset.pace);
  if (button.dataset.setPace) { dialog.close(); return setPace(button.dataset.setPace); }
  if (button.dataset.filter) { state.filter=button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b=>{const active=b.dataset.filter===state.filter;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});return renderPlaces(); }
  if (button.dataset.detail) return detail(button.dataset.detail);
  if (button.dataset.save) { const id=button.dataset.save; if(state.saved.has(id))state.saved.delete(id);else state.saved.add(id);renderPlaces();toast(state.saved.has(id)?'Đã lưu để cân nhắc. Chưa thêm vào lịch trình.':'Đã bỏ khỏi nơi đã lưu.');return; }
  if (button.dataset.day) { state.day=Number(button.dataset.day);return renderPlanning(); }
  if (button.dataset.variant) { state.variant=button.dataset.variant;return renderPlanning(); }
  if (button.dataset.compose) { const input=document.querySelector('#chat-input');input.value=button.dataset.compose;input.focus();return; }
  if (button.id === 'dialog-close') return dialog.close();
  if (button.id === 'pick-date') return editDate();
  if (button.id === 'edit-trip') return editTrip();
  if (button.id === 'save-hard') {state.fixed=document.querySelector('#hard-check').checked;dialog.close();if(state.view==='review')renderReview();if(state.view==='selection')updateSelection();return;}
  if (button.id === 'skip') {chatMessage('Mình chưa chắc nhịp đi.');chatMessage('Không sao, mình để nhịp đi là chưa rõ. Bạn có thể tiếp tục xem nơi bên cạnh hoặc xem lại bản nhu cầu.','bot');return;}
  if (button.id === 'next') { if(state.view==='understand')return setView('review'); if(state.view==='review')return setView('selection'); if(state.view==='selection' && state.lodging && state.selected.size && !state.fixed)return setView('planning'); }
  if (button.id === 'reset') {state.pace=null;state.date='';state.budget='';state.filter='all';state.notes=[];state.links=[];state.fixed=false;state.selected.clear();state.saved.clear();state.lodging=false;state.day=0;document.querySelector('#chat-log').innerHTML=originalChat;hydrateIcons();setView('understand');return;}
  if (button.id === 'attachment' || button.id === 'saved-links') return showDialog('<h2>Mang theo một nơi bạn thích</h2><p>Dán link Maps hoặc TikTok đã lưu. Trong mock, link được giữ như một ghi chú chưa xác minh.</p><form id="link-form"><label>Link địa điểm<input id="link-value" type="url" required placeholder="https://…"></label><button class="primary-button" type="submit">Giữ trong bản nháp</button></form>');
  if (button.id === 'design-notes') return showDialog('<span class="eyebrow">CONCEPT · CHỜ BẠN DUYỆT</span><h2>Chat để hiểu. Địa điểm để thấy.</h2><p>Màu và chất liệu theo mock homepage của bạn. Học Layla ở bố cục trò chuyện bên trái, nội dung trực quan bên phải.</p><div class="modal-rows"><div><b>01 · Chat + địa điểm — đề xuất</b><span>Bản hiểu gọn ở trên; các thẻ địa điểm là nội dung chính trong lúc trò chuyện. Dễ thấy và đối chiếu nhiều nơi.</span></div><div><b>02 · Ảnh lớn + địa điểm</b><span>Thêm ảnh không khí để tạo cảm xúc. Địa điểm nằm thấp hơn, cần cuộn nhiều hơn.</span></div><div><b>03 · Chat tập trung</b><span>Chat rộng hơn, địa điểm thành một cột. Hợp cuộc trò chuyện dài; so sánh ít nơi cùng lúc hơn.</span></div></div><p style="margin-top:16px">Bản hiểu đầy đủ chỉ mở khi bạn muốn đi tiếp. Bước chọn nơi vẫn riêng. Planning dùng thao tác và timeline, không mở chat.</p><p>Địa điểm và ảnh có thật trong catalog; lý do phù hợp, giờ và lịch trình là ví dụ trình bày. Không gọi backend hay thay đổi app hiện tại.</p>');
});
document.addEventListener('change', event => {
  const el=event.target;
  if(el.id==='layout'){app.dataset.layout=el.value;return;}
  if(el.dataset.select){if(state.fixed){el.checked=false;toast('Chưa xác nhận đường vào. Cần kiểm tra yêu cầu bắt buộc trước khi chọn.');return;}if(el.checked)state.selected.add(el.dataset.select);else state.selected.delete(el.dataset.select);updateSelection();}
  if(el.id==='lodging-check'){state.lodging=el.checked;updateSelection();}
});
document.addEventListener('submit',event=>{
  event.preventDefault();
  if(event.target.id==='date-form'){state.date=document.querySelector('#date-value').value;dialog.close();renderBrief();if(state.view==='review')renderReview();toast(state.date?'Đã cập nhật ngày đi trong bản nháp.':'Ngày đi vẫn chưa rõ.');return;}
  if(event.target.id==='budget-form'){state.budget=document.querySelector('#budget-value').value.trim();dialog.close();renderBrief();if(state.view==='review')renderReview();toast('Đã cập nhật ngân sách.');return;}
  if(event.target.id==='link-form'){const url=document.querySelector('#link-value').value;state.links.push(url);state.notes.push('Link đã lưu, chưa xác minh: '+url);dialog.close();chatMessage('Mình có nơi đã lưu: '+url);chatMessage('Mình giữ link này trong bản nháp, đánh dấu chưa xác minh.','bot');return;}
  if(event.target.id==='composer'){const input=document.querySelector('#chat-input');const text=input.value.trim();if(!text)return;input.value='';chatMessage(text);const normalized=text.toLocaleLowerCase('vi');state.notes.push(text);if(/thong thả|chậm|ít nơi/.test(normalized))state.pace='Thong thả';else if(/cân bằng/.test(normalized))state.pace='Cân bằng';else if(/đi nhiều/.test(normalized))state.pace='Đi nhiều';if(/triệu|ngân sách/.test(normalized))state.budget=text;if(/cà phê/.test(normalized))state.filter='coffee';else if(/thiên nhiên|hồ|săn mây/.test(normalized))state.filter='nature';chatMessage('Mình đã giữ thêm ghi chú của bạn trong bản nháp. Bạn có thể kiểm tra lại trước khi chọn nơi.','bot');if(state.view==='review')renderReview();else if(state.view!=='planning'){renderBrief();renderPlaces();document.querySelectorAll('[data-filter]').forEach(b=>{const active=b.dataset.filter===state.filter;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});} }
});
document.querySelector('#chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();document.querySelector('#composer').requestSubmit();}});
dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
hydrateIcons();renderPlaces();
requestAnimationFrame(() => { const log = document.querySelector('#chat-log'); log.scrollTop = log.scrollHeight; });

dialog.addEventListener('close', () => document.querySelector('#edit-trip')?.setAttribute('aria-expanded', 'false'));

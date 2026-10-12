/* Interactive design prototype. All place data is explicitly illustrative. */
const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="assets/icons.svg#${name}"/></svg>`;
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const places = [
  {id:'coffee',name:'Cà phê giữa rừng thông',category:'coffee',label:'Cà phê & thư giãn',image:'terrace',duration:75,price:'60–100k',reason:'Một khoảng nghỉ yên tĩnh, đúng gu cà phê của bạn.',risk:'Chưa xác nhận giờ mở cửa.',tag:'Dành cho một buổi thong thả',stepFree:true,evidence:'Ví dụ cách trình bày tín hiệu: không gian yên tĩnh, nhiều cây xanh. Bản mẫu không có review hay nguồn xác minh thật.',opening:null},
  {id:'lake',name:'Dạo bên hồ',category:'nature',label:'Thiên nhiên',image:'lake',duration:90,price:null,reason:'Đi dạo nhẹ nhàng, có thời gian ở bên nhau.',risk:'Chưa có thông tin về chi phí.',tag:'Hợp nhịp đi chậm',stepFree:true,evidence:'Ví dụ cách trình bày sự phù hợp: trải nghiệm ngoài trời, thời lượng linh hoạt. Đây không phải xác nhận điều kiện tại một địa điểm thật.',opening:'06:00–18:00 · mẫu'},
  {id:'cloud',name:'Đón mây đầu ngày',category:'nature',label:'Thiên nhiên',image:'cloud',duration:90,price:null,reason:'Dành cho buổi sáng bạn muốn thử săn mây.',risk:'Đường dốc; cần xuất phát từ sáng sớm.',tag:'Một trải nghiệm khác biệt',stepFree:false,evidence:'Ví dụ đánh đổi cần hiện trước khi chọn: dậy sớm, đường vào dốc. Không cam kết thời tiết hay khả năng nhìn thấy mây.',opening:null},
  {id:'terrace',name:'Cà phê nhìn ra thung lũng',category:'coffee',label:'Cà phê & thư giãn',image:'coffee',duration:75,price:'80–120k',reason:'Ngồi lâu ngắm cảnh, hợp một buổi không vội.',risk:'Chưa xác nhận lối đi không bậc.',tag:'Cho người thích ngắm cảnh',stepFree:null,evidence:'Ví dụ về dữ liệu còn thiếu: chưa biết có bậc thang hay không. Không có bằng chứng không đồng nghĩa với phù hợp.',opening:'07:00–17:00 · mẫu'},
  {id:'pine',name:'Một vòng rừng thông',category:'nature',label:'Thiên nhiên',image:'pine',duration:60,price:null,reason:'Đổi không khí với một khoảng xanh ngoài trời.',risk:'Đường có thể trơn khi mưa.',tag:'Chậm lại giữa thiên nhiên',stepFree:null,evidence:'Ví dụ cảnh báo theo bối cảnh: trải nghiệm ngoài trời có thể bị ảnh hưởng bởi mưa. Cần dữ liệu đường đi trước khi kiểm tra giới hạn vận động.',opening:null},
  {id:'dusk',name:'Bữa tối bên hồ',category:'food',label:'Ăn uống',image:'dusk',duration:90,price:'150–250k',reason:'Khép lại một ngày bằng bữa tối cùng nhau.',risk:'Chưa xác nhận tình trạng đặt chỗ.',tag:'Kết ngày thật nhẹ nhàng',stepFree:true,evidence:'Ví dụ thông tin cần kiểm tra trước chuyến đi: khả năng đặt chỗ và giờ phục vụ. Không có thông tin còn bàn trong bản mẫu.',opening:'17:00–21:00 · mẫu'}
];
const defaultTrip = {date:'2026-10-17',days:3,people:2,vehicle:'Xe máy',pace:'Thảnh thơi',note:'Thích cà phê, thiên nhiên và có thời gian nghỉ.',stepFree:false};
let trip = {...defaultTrip};
let selected = ['coffee','lake'];
let comparing = [];
let filter = 'all';
let query = '';
let activeDay = 0;
let undoState = null;
let lastModalTrigger = null;
let storageAvailable = true;
const storageKey = 'tripguardian-design-oct2026-v1';
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
  if (saved && saved.trip && Array.isArray(saved.selected)) {
    const t = saved.trip;
    if (/^\d{4}-\d{2}-\d{2}$/.test(t.date) && Number.isFinite(Date.parse(t.date)) && Number.isInteger(t.days) && t.days >= 1 && t.days <= 7 && Number.isInteger(t.people) && t.people >= 1 && t.people <= 12 && ['Xe máy','Ô tô','Taxi'].includes(t.vehicle) && ['Thảnh thơi','Vừa phải'].includes(t.pace)) {
      trip = {...defaultTrip,...t,note:String(t.note || '').slice(0,500),stepFree:t.stepFree === true};
      selected = [...new Set(saved.selected)].filter((id) => places.some((p) => p.id === id && (!trip.stepFree || p.stepFree === true)));
    }
  }
} catch { storageAvailable = false; }
const main = document.querySelector('#main');
const modal = document.querySelector('#modal');
const selectedPlaces = () => selected.map((id) => places.find((p) => p.id === id));
const duration = (minutes) => minutes >= 60 ? `${Math.floor(minutes/60)} giờ${minutes%60 ? ` ${minutes%60}′` : ''}` : `${minutes} phút`;
const canSelect = (place) => !trip.stepFree || place.stepFree === true;
const dateAt = (day = 0) => {const date = new Date(`${trip.date}T12:00:00`);date.setDate(date.getDate()+day);return date;};
const shortDate = (day = 0) => dateAt(day).toLocaleDateString('vi-VN',{day:'numeric',month:'numeric'});
const tripDates = () => `${shortDate()} – ${shortDate(trip.days-1)}`;
const view = () => ['understand','discover','plan'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'discover';
const totalDuration = () => selectedPlaces().reduce((total,p) => total+p.duration,0);
const save = () => {try {localStorage.setItem(storageKey,JSON.stringify({trip,selected}));} catch {storageAvailable=false;}};
const button = (label,action,id='',style='') => `<button class="button ${style}" data-action="${action}" ${id ? `data-id="${id}"` : ''}>${label}</button>`;
const addButton = (p,style='small') => canSelect(p) ? button(selected.includes(p.id) ? `${icon('check')}Đã chọn` : `${icon('plus')}Thêm vào chuyến`,'toggle-place',p.id,`${style} ${selected.includes(p.id)?'selected':''}`) : '<button class="button small secondary" disabled>Chưa đủ điều kiện</button>';

function notify(message,undo = false) {
  document.querySelector('#feedback').innerHTML = `<span>${escapeHTML(message)}</span>${undo ? '<button class="text-btn" data-action="undo">Hoàn tác</button>' : ''}<button class="icon-button" data-action="dismiss-feedback" aria-label="Đóng thông báo">${icon('x')}</button>`;
  document.querySelector('#feedback').classList.add('visible');
}
function rerenderWithFocus() {
  const current = document.activeElement;
  const action = current?.dataset?.action;
  const id = current?.dataset?.id;
  const compare = current?.dataset?.compare;
  render();
  const target = action ? main.querySelector(`[data-action="${action}"]${id?`[data-id="${id}"]`:''}`) : compare ? main.querySelector(`[data-compare="${compare}"]`) : null;
  target?.focus({preventScroll:true});
}
function togglePlace(id) {
  const p = places.find((p) => p.id === id);
  if (!p || !canSelect(p)) return;
  undoState = {selected:[...selected],trip:{...trip}};
  const removing = selected.includes(id);
  selected = removing ? selected.filter((value) => value !== id) : [...selected,id];
  save();rerenderWithFocus();
  if(modal.open && modal.dataset.kind === 'detail') showDetails(id,false);
  if(modal.open && modal.dataset.kind === 'compare') {showCompare(false);modal.querySelector(`[data-action="toggle-place"][data-id="${id}"]`)?.focus({preventScroll:true});}
  if(modal.open && modal.dataset.kind === 'selection') showSelection(false);
  notify(`${removing?'Đã bỏ':'Đã thêm'} ${p.name.toLowerCase()}.`,true);
}
function card(p) {
  return `<article class="place-card ${selected.includes(p.id)?'is-selected':''}">
    <div class="card-photo"><button class="photo-button" data-action="detail" data-id="${p.id}" aria-label="Xem chi tiết ${p.name}"><img src="assets/${p.image}.webp" alt="Ảnh không khí minh họa cho ${p.name.toLowerCase()}, không phải địa điểm thật" loading="${places.indexOf(p)>1?'lazy':'eager'}" width="640" height="360"></button><span class="photo-tag">${selected.includes(p.id)?icon('check'):''}${selected.includes(p.id)?'Trong chuyến của bạn':p.tag}</span><span class="image-credit">Ảnh minh họa</span></div>
    <div class="card-body"><p class="card-category">${p.label}</p><button class="place-title" data-action="detail" data-id="${p.id}">${p.name}</button><span class="sample-tag">mẫu</span><div class="card-meta"><span>${icon('clock')}Khoảng ${duration(p.duration)}</span><span>${icon('wallet')}${p.price?`≈ ${p.price}/người`:'Chưa có giá'}</span></div><p class="reason">${icon('check')}<span>${p.reason}</span></p><p class="caution">${icon('info')}<span>${p.risk}</span></p></div>
    <div class="card-footer"><label class="compare-check"><input type="checkbox" data-compare="${p.id}" ${comparing.includes(p.id)?'checked':''} aria-label="So sánh ${p.name}">So sánh</label>${addButton(p)}</div></article>`;
}
function filteredPlaces() {
  const normalize = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase();
  return places.filter((p) => canSelect(p) && (filter === 'all' || filter === p.category) && normalize(p.name+' '+p.label).includes(normalize(query)));
}
function cardResults() {
  const result = filteredPlaces();
  return result.length ? result.map(card).join('') : `<div class="empty"><h3>Chưa có nơi phù hợp với tìm kiếm này</h3><p>Thử tên ngắn hơn hoặc xem lại các nhóm địa điểm.</p>${button('Xóa tìm kiếm & bộ lọc','clear-filters','','secondary')}</div>`;
}
function compareTray() {
  return comparing.length ? `<div class="compare-tray"><div><p>Đang chọn ${comparing.length}/2 nơi để so sánh</p><small>${comparing.length<2?'Chọn thêm một nơi trên thẻ.':'Xem điểm hợp và điều cần cân nhắc cạnh nhau.'}</small></div><button class="button" data-action="compare" ${comparing.length<2?'disabled':''}>So sánh ${icon('arrow')}</button><button class="icon-button" data-action="clear-compare" aria-label="Bỏ chọn so sánh" style="color:white">${icon('x')}</button></div>` : '';
}
function tripPanel(mobile = false) {
  const list = selectedPlaces();
  const missing = list.filter((p) => !p.opening).length;
  return `<section class="trip-panel ${mobile?'mobile-panel':''}" aria-label="Chuyến đi đang chọn"><div class="trip-cover"><img src="assets/lake.webp" alt="Phong cảnh hồ minh họa" width="600" height="230"><div class="cover-caption"><small>MỘT CHUYẾN ĐI CỦA RIÊNG BẠN</small><b>Đà Lạt, mình đi nhé.</b></div><span class="image-credit">Ảnh minh họa</span></div><div class="trip-inner"><div class="panel-heading"><h2>Chuyến của bạn</h2><button class="text-btn" data-action="edit-trip">Chỉnh sửa</button></div><p class="trip-caption">${trip.days} ngày · ${trip.people} người · ${trip.vehicle.toLowerCase()}</p><div class="interest-tags"><span>${escapeHTML(trip.pace)}</span><span>Cà phê</span><span>Thiên nhiên</span></div><div class="selection-heading"><b>Địa điểm đã chọn</b><span>${list.length} nơi</span></div><ul class="selected-list">${list.map((p) => `<li class="selected-item"><img src="assets/${p.image}.webp" alt="" width="43" height="47"><div><b>${p.name}</b><small>Khoảng ${duration(p.duration)}</small></div><button class="icon-button" data-action="toggle-place" data-id="${p.id}" aria-label="Bỏ ${p.name} khỏi chuyến">${icon('x')}</button></li>`).join('')}</ul>${!list.length?'<p class="sidebar-empty">Thêm một nơi bạn muốn đi. Bạn có thể đổi ý bất cứ lúc nào.</p>':''}<div class="selection-totals"><span>Tổng tham quan dự kiến</span><strong>${duration(totalDuration())}</strong></div><div class="selection-note"><b>${missing?`${missing} nơi cần kiểm tra giờ mở cửa`:'Chưa kiểm tra tuyến đường'}</b><p>${missing?'Bạn vẫn có thể lưu nháp. Cần kiểm tra trước khi chốt chuyến.':'Chưa thể kết luận các nơi này đi được cùng nhau.'}</p>${missing?'<button class="text-btn" data-action="review-issues">Xem nơi cần kiểm tra →</button>':''}</div><button class="button wide" data-action="go-plan" ${!list.length?'disabled':''}>Xem lịch nháp ${icon('arrow')}</button><p class="panel-footnote">Bạn vẫn có thể thêm, bỏ và đổi nơi sau bước này.<br>Thời lượng chưa gồm đi lại, ăn và nghỉ.</p></div></section>`;
}
function discover() {
  return `<div class="page"><div class="breadcrumb">${icon('pin')}<span>Đà Lạt</span><span>/</span><b>Chọn những nơi bạn thật sự muốn đi</b></div><div class="layout"><section class="content"><div class="heading"><p class="eyebrow">ÍT TÌM KIẾM HƠN · NHIỀU TRẢI NGHIỆM HƠN</p><h1>Một chút Đà Lạt, <em>thật đúng gu bạn.</em></h1><p>Chọn nơi bạn thích, hiểu rõ đánh đổi, rồi ghép thành chuyến đi.</p></div><div class="context-line"><span>${icon('cal')}${tripDates()}</span><span class="divider"></span><span>${icon('users')}${trip.people} người</span><span class="divider"></span><span>${icon('moto')}${trip.vehicle}</span><button class="text-btn" data-action="edit-trip">Sửa chuyến đi</button></div><div class="browse-tools"><div class="tabs" aria-label="Lọc loại địa điểm">${[['all','Tất cả'],['nature','Thiên nhiên'],['coffee','Cà phê'],['food','Ăn uống']].map(([id,label])=>`<button class="filter" data-action="filter" data-id="${id}" aria-pressed="${filter===id}">${label}</button>`).join('')}</div><label class="search">${icon('search')}<input id="place-search" type="search" placeholder="Tìm trong gợi ý" aria-label="Tìm trong địa điểm mẫu" value="${escapeHTML(query)}"></label></div>${trip.stepFree?'<p class="hard-filter-note">Yêu cầu lối đi không bậc: chỉ hiện 3 nơi có bằng chứng minh họa đáp ứng. 3 nơi còn lại bị loại vì không đáp ứng hoặc chưa có bằng chứng.</p>':''}<div class="results-meta"><span id="result-count"><strong>${filteredPlaces().length} gợi ý mẫu</strong> · Để bạn thử chọn & so sánh</span><button class="text-btn" data-action="ranking">Vì sao có những gợi ý này?</button></div><div class="cards" id="cards">${cardResults()}</div><div id="compare-slot">${compareTray()}</div><p class="subtle-note">${icon('info')}<span>Thông tin chưa rõ được ghi thẳng trên thẻ. Mở một nơi để xem đầy đủ điều đã biết và cần kiểm tra.</span></p></section><aside class="sidebar-wrap">${tripPanel()}<button class="assistant-card" data-action="help">${icon('spark')}<span><b>Chưa biết nên chọn nơi nào?</b><small>Thử so sánh hai nơi trước khi quyết định.</small></span></button></aside></div></div>`;
}
function tripFields() {
  return `<div class="form-grid"><label class="field">Ngày bắt đầu<input name="date" type="date" required value="${trip.date}"><small>Ngày cụ thể giúp kiểm tra giờ mở cửa.</small></label><label class="field">Số ngày<select name="days">${[1,2,3,4,5,6,7].map((n)=>`<option value="${n}" ${trip.days===n?'selected':''}>${n} ngày</option>`).join('')}</select></label><label class="field">Số người<input name="people" type="number" min="1" max="12" required value="${trip.people}"></label><label class="field">Di chuyển tại Đà Lạt<select name="vehicle">${['Xe máy','Ô tô','Taxi'].map((v)=>`<option ${trip.vehicle===v?'selected':''}>${v}</option>`).join('')}</select></label><label class="field full">Nhịp đi bạn muốn<select name="pace">${['Thảnh thơi','Vừa phải'].map((v)=>`<option ${trip.pace===v?'selected':''}>${v}</option>`).join('')}</select><small>Có thể đổi cho từng chuyến, không phải sở thích cố định.</small></label><label class="field full">Bạn muốn điều gì cho chuyến này?<textarea name="note" maxlength="500" rows="3">${escapeHTML(trip.note)}</textarea><small>Bản mẫu lưu ghi chú để thử giao diện, chưa tự phân tích bằng AI.</small></label></div><label class="check-field"><input type="checkbox" name="stepFree" ${trip.stepFree?'checked':''}><span>Cần lối đi không bậc<small>Chỉ giữ nơi có bằng chứng đáp ứng; nơi chưa rõ sẽ không được thêm vào chuyến.</small></span></label>`;
}
function understand() {
  return `<div class="page"><div class="breadcrumb">${icon('pin')}Đà Lạt<span>/</span><b>Bắt đầu từ điều bạn muốn</b></div><div class="understand-layout"><section><div class="heading"><p class="eyebrow">CHUYẾN NÀY, ĐI THEO CÁCH CỦA BẠN</p><h1>Vài điều nhỏ,<br>cho một chuyến đi <em>vừa ý.</em></h1><p>Xem lại thông tin chuyến đi. Bạn có thể quay lại sửa bất cứ lúc nào mà vẫn giữ những nơi đã chọn.</p></div><form class="intro-box" id="understand-form"><h2>Bạn định đi thế nào?</h2><p>Thông tin mẫu đã được điền sẵn để bạn thử toàn bộ luồng.</p>${tripFields()}<div class="form-actions"><small>Không cần đăng nhập để thử bản thiết kế.</small><button class="button" type="submit">Xem gợi ý địa điểm ${icon('arrow')}</button></div></form></section><aside class="understand-side"><div class="postcard"><img src="assets/pine.webp" alt="Rừng thông minh họa không khí Đà Lạt"><span class="image-credit">Ảnh minh họa</span></div><div class="summary-paper"><p class="eyebrow">BẠN LUÔN LÀ NGƯỜI QUYẾT ĐỊNH</p><h3>Đi ít hơn cũng được.<br>Miễn là đúng nơi bạn thích.</h3><div class="summary-row"><span>Thông tin đang nhập</span><b id="draft-trip-summary">${trip.days} ngày · ${trip.people} người</b></div><div class="summary-row"><span>Địa điểm đã chọn</span><b>${selected.length} nơi</b></div><div class="summary-row"><span>Nhịp đi</span><b id="draft-pace">${trip.pace}</b></div></div><div class="guidance"><h3>Điều bắt buộc và điều bạn thích là khác nhau.</h3><p>Giới hạn vận động phải được đáp ứng. Sở thích giúp ưu tiên gợi ý và luôn có thể chỉnh lại.</p></div></aside></div></div>`;
}
function dayPlaces(day) {return selectedPlaces().filter((_,index) => index%trip.days === day);}
function plan() {
  activeDay = Math.min(activeDay,trip.days-1);
  const daily = dayPlaces(activeDay);
  return `<div class="page"><div class="breadcrumb"><a href="#discover">${icon('arrow')} Trở lại chọn địa điểm</a><span>/</span><b>Lịch nháp của bạn</b></div><div class="layout"><section class="content"><div class="plan-title-row"><div class="heading"><p class="eyebrow">CÓ KẾ HOẠCH · VẪN CÓ KHOẢNG THỞ</p><h1>${trip.days} ngày Đà Lạt,<br><em>theo nhịp của bạn.</em></h1><p>${tripDates()} · ${trip.people} người · ${trip.vehicle.toLowerCase()}</p></div>${button('Sửa chuyến đi','edit-trip','','secondary')}</div><div class="plan-notice">${icon('info')}<div><b>Lịch minh họa, chưa đủ thông tin để chốt</b>Các nơi được chia ngày để thử giao diện. Giờ mở cửa và đường đi cần được kiểm tra trước khi dùng cho chuyến thật.</div></div><div class="day-tabs" role="tablist" aria-label="Ngày trong chuyến">${Array.from({length:trip.days},(_,i)=>`<button class="day-tab" id="day-${i}" role="tab" aria-controls="day-content" aria-selected="${activeDay===i}" tabindex="${activeDay===i?0:-1}" data-action="day" data-id="${i}"><b>Ngày ${i+1}</b><small>${shortDate(i)} · ${dayPlaces(i).length} nơi</small></button>`).join('')}</div><div id="day-content" role="tabpanel" aria-labelledby="day-${activeDay}" tabindex="0"><div class="day-summary"><div><h2>${daily.length?'Một ngày không cần vội':'Một ngày còn để ngỏ'}</h2><p>${daily.length} nơi · ${duration(daily.reduce((n,p)=>n+p.duration,0))} tham quan dự kiến, chưa gồm đi lại</p></div><a class="text-btn" href="#discover">Thêm địa điểm</a></div><ol class="timeline">${daily.map((p,i)=>`<li class="stop"><div class="stop-time"><b>Điểm ${i+1}</b>Chưa xếp giờ</div><div class="stop-content"><div class="stop-card"><img src="assets/${p.image}.webp" alt="Ảnh minh họa"><div class="stop-desc"><h3>${p.name}</h3><p>Khoảng ${duration(p.duration)} · ${p.price?`≈ ${p.price}/người`:'Chưa có giá'}</p><div class="caution">${icon('info')}${p.risk}</div><button class="text-btn" data-action="detail" data-id="${p.id}">Xem thông tin & điều cần kiểm tra</button></div><button class="icon-button" data-action="toggle-place" data-id="${p.id}" aria-label="Bỏ ${p.name} khỏi lịch">${icon('x')}</button></div>${i<daily.length-1?`<p class="leg">${icon('route')}Đoạn đường tiếp theo: chưa có thời gian di chuyển.</p>`:'<div class="leg"></div>'}</div></li>`).join('')}</ol><div class="rest-block"><h3>${daily.length?'Chừa chỗ cho những điều ngẫu hứng.':'Chưa chọn nơi nào cho ngày này.'}</h3><p>${daily.length?'Bạn không cần lấp đầy cả ngày. Ăn, nghỉ và di chuyển cũng cần thời gian.':'Có thể dành ngày nghỉ hoặc quay lại chọn thêm địa điểm.'}</p></div></div></section><aside class="sidebar-wrap"><section class="trip-panel plan-side"><p class="eyebrow">BỨC TRANH CẢ CHUYẾN</p><h2>Chuyến đi đang thành hình.</h2><div class="summary-row" style="margin-top:20px"><span>Đã chọn</span><b>${selected.length} địa điểm</b></div><div class="summary-row"><span>Tham quan dự kiến</span><b>${duration(totalDuration())}</b></div><div class="summary-row"><span>Di chuyển</span><b>Chưa ước tính</b></div><div class="summary-row"><span>Tổng chi phí</span><b>Chưa đủ dữ liệu</b></div><div class="selection-note"><b>Trước khi chốt chuyến</b><p>Kiểm tra giờ mở cửa, đường đi và những giới hạn bắt buộc. Hiện chưa thể kết luận lịch khả thi.</p><button class="text-btn" data-action="review-issues">Xem thông tin từng nơi →</button></div><button class="button wide" data-action="export" ${!selected.length?'disabled':''}>${icon('cal')}Tải bản nháp</button><button class="text-btn" data-action="go-discover">Quay lại chọn địa điểm</button><p class="panel-footnote">Tải tệp văn bản để xem lại.<br>Không tạo đặt chỗ hay sự kiện lịch.</p></section><div class="guidance"><h3>Bạn có thể đổi ý.</h3><p>Bỏ một nơi không làm mất những nơi còn lại. Luôn có Hoàn tác sau mỗi thay đổi.</p></div></aside></div></div>`;
}
function render() {
  const route = view();
  document.querySelectorAll('[data-step]').forEach((el)=>{if(el.dataset.step===route)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
  document.querySelector('#header-date').textContent=tripDates();
  main.innerHTML=route==='understand'?understand():route==='plan'?plan():discover();
  document.querySelector('#mobile-dock').innerHTML = route==='understand'?'':`<button class="text-btn" data-action="selection">${selected.length} nơi đã chọn<small>${duration(totalDuration())} tham quan dự kiến</small></button><button class="button" data-action="${route==='plan'?'export':'go-plan'}" ${!selected.length?'disabled':''}>${route==='plan'?'Tải bản nháp':'Xem lịch nháp'} ${icon('arrow')}</button>`;
}
function openModal(title,body,kind='info',drawer=false,actions='',resetFocus=true) {
  const alreadyOpen=modal.open;
  if(!alreadyOpen)lastModalTrigger=document.activeElement;
  modal.classList.toggle('drawer',drawer);modal.dataset.kind=kind;
  document.querySelector('#dialog-content').innerHTML=`<div class="dialog-head"><h2 id="dialog-title">${title}</h2><button class="icon-button" data-action="close-modal" aria-label="Đóng cửa sổ">${icon('x')}</button></div>${body}${actions?`<div class="dialog-actions">${actions}</div>`:''}`;
  if(!alreadyOpen){modal.showModal();document.body.style.overflow='hidden';}
  if(resetFocus)modal.querySelector('[data-action="close-modal"]').focus();
}
function closeModal(){modal.close();}
modal.addEventListener('close',()=>{document.body.style.overflow='';if(lastModalTrigger?.isConnected)lastModalTrigger.focus({preventScroll:true});else main.focus({preventScroll:true});});
modal.addEventListener('click',(event)=>{if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();}});
function showDetails(id,resetFocus=true) {
  const p=places.find((p)=>p.id===id);if(!p)return;
  openModal('Một nơi đáng cân nhắc',`<div class="detail-photo"><img src="assets/${p.image}.webp" alt="Ảnh không khí minh họa"><span class="image-credit">Ảnh minh họa · không phải địa điểm thật</span></div><div class="dialog-body"><p class="eyebrow">${p.label} · ĐỊA ĐIỂM MẪU</p><h3 class="detail-title">${p.name}</h3><p class="detail-intro">Đặt điều bạn muốn trải nghiệm cạnh những điều cần biết trước khi đi.</p><div class="detail-block positive"><h3>Vì sao có thể hợp chuyến này</h3><p>${p.reason}</p></div><div class="detail-block warning"><h3>Điều cần cân nhắc</h3><p>${p.risk}</p></div><div class="detail-block"><h3>Thông tin để bạn quyết định</h3><div class="evidence-row"><span>Thời lượng ước tính</span><b>Khoảng ${duration(p.duration)}</b></div><div class="evidence-row"><span>Chi phí ước tính</span><b>${p.price?`≈ ${p.price}/người`:'Chưa có thông tin'}</b></div><div class="evidence-row"><span>Giờ mở cửa</span><b>${p.opening||'Chưa xác nhận'}</b></div><div class="evidence-row"><span>Lối đi không bậc</span><b>${p.stepFree===null?'Chưa có bằng chứng':p.stepFree?'Có · dữ liệu mẫu':'Không · dữ liệu mẫu'}</b></div></div><details class="detail-block"><summary>Nguồn thông tin & mức chắc chắn</summary><p style="margin-top:14px">${p.evidence}</p><p style="margin-top:10px">Khi kết nối dữ liệu thật, khu vực này cần hiện nguồn gốc, ngày kiểm chứng và đường dẫn bằng chứng. Hiện không có dữ liệu thật để đối chiếu.</p></details></div>`,'detail',true,addButton(p,'wide'),resetFocus);
  if(!resetFocus)modal.querySelector('[data-action="toggle-place"]')?.focus({preventScroll:true});
}
function showCompare(resetFocus=true) {
  if(comparing.length!==2)return;
  const list=comparing.map((id)=>places.find((p)=>p.id===id));
  const row=(label,content,cls='')=>`<tr><th scope="row">${label}</th>${list.map((p)=>`<td class="${cls}">${content(p)}</td>`).join('')}</tr>`;
  openModal('Chọn nơi nào hợp bạn hơn?',`<div class="dialog-body"><p class="detail-intro">Hai địa điểm mẫu, cùng một bộ tiêu chí. Bạn chọn điều mình coi trọng hơn.</p><table class="compare-table"><caption class="source" style="text-align:left;margin-bottom:12px">So sánh dữ liệu minh họa; mọi mức giá và thời lượng đều là ước tính mẫu.</caption><thead><tr><th scope="col">Tiêu chí</th>${list.map((p)=>`<th scope="col"><img src="assets/${p.image}.webp" alt="" style="width:100%;height:100px;object-fit:cover;border-radius:8px;margin-bottom:12px"><strong>${p.name}</strong></th>`).join('')}</tr></thead><tbody>${row('Hợp vì',p=>p.reason,'match')}${row('Cân nhắc',p=>p.risk,'risk')}${row('Thời lượng',p=>'Khoảng '+duration(p.duration))}${row('Chi phí/người',p=>p.price?'≈ '+p.price:'Chưa có thông tin')}${row('Giờ mở cửa',p=>p.opening||'Chưa xác nhận')}${row('Lối không bậc',p=>p.stepFree===null?'Chưa có bằng chứng':p.stepFree?'Có · mẫu':'Không · mẫu')}${row('Quyết định',p=>addButton(p,'small'))}</tbody></table></div>`,'compare',false,'',resetFocus);
}
function showSelection(resetFocus=true){openModal('Những nơi bạn đã chọn',`<div class="dialog-body">${tripPanel(true)}</div>`,'selection',true,'',resetFocus);}
function editTrip(){openModal('Chỉnh chuyến đi của bạn',`<form id="edit-trip-form"><div class="dialog-body">${tripFields()}<p class="form-note">Khi đổi yêu cầu bắt buộc, nơi không đáp ứng sẽ được bỏ khỏi lựa chọn. Bạn luôn có thể hoàn tác thay đổi.</p></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-modal">Để sau</button><button class="button" type="submit">Lưu thay đổi ${icon('check')}</button></div></form>`,'trip');}
function reviewIssues(){openModal('Những điều cần kiểm tra',`<div class="dialog-body"><p class="detail-intro">${selected.length?'Xem đúng thông tin còn thiếu của từng nơi trước khi quyết định.':'Chưa chọn địa điểm nào. Quay lại danh sách để bắt đầu.'}</p>${selectedPlaces().map((p)=>`<div class="detail-block warning"><h3>${p.name}</h3><p>${p.risk}</p><button class="text-btn" data-action="detail" data-id="${p.id}">Xem thông tin & nguồn →</button></div>`).join('')}<div class="detail-block"><h3>Toàn chuyến</h3><p>Chưa kiểm tra tuyến đường, tổng chi phí và giờ mở cửa theo ngày đi. Không có đánh dấu “khả thi” trước khi có đủ dữ liệu.</p></div></div>`,'issues',true);}
function exportDraft(){
  if(!selected.length)return;
  const content=[`TRIPGUARDIAN — BẢN NHÁP MINH HỌA`,`Đây là bản thiết kế, không dùng làm lịch trình thật.`,`Địa điểm và ảnh là mẫu. Chưa kiểm tra đường đi, giờ mở cửa hay tổng chi phí.`,`Đà Lạt · ${tripDates()} · ${trip.people} người · ${trip.vehicle}`,`Nhịp đi: ${trip.pace}`,`Ghi chú của bạn: ${trip.note}`,'',...Array.from({length:trip.days},(_,i)=>[`NGÀY ${i+1} · ${shortDate(i)}`,...dayPlaces(i).map(p=>`- ${p.name} (mẫu): khoảng ${duration(p.duration)}. ${p.risk}`),'Chưa xếp giờ; thời gian di chuyển chưa có.','']).flat()].join('\n');
  const url=URL.createObjectURL(new Blob([content],{type:'text/plain;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='tripguardian-design-draft.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  notify('Đã tải bản nháp minh họa dạng văn bản.');
}
document.addEventListener('click',(event)=>{
  const target=event.target.closest('[data-action]');if(!target)return;
  const {action,id}=target.dataset;
  if(action==='toggle-place')togglePlace(id);
  if(action==='detail')showDetails(id);
  if(action==='close-modal')closeModal();
  if(action==='edit-trip')editTrip();
  if(action==='selection')showSelection();
  if(action==='review-issues')reviewIssues();
  if(action==='filter'){filter=id;rerenderWithFocus();}
  if(action==='clear-filters'){filter='all';query='';render();document.querySelector('#place-search')?.focus();}
  if(action==='clear-compare'){comparing=[];render();}
  if(action==='compare')showCompare();
  if(action==='go-plan'||action==='go-discover'){if(modal.open)closeModal();location.hash=action==='go-plan'?'plan':'discover';}
  if(action==='day'){activeDay=Number(id);render();document.querySelector(`#day-${id}`)?.focus({preventScroll:true});}
  if(action==='dismiss-feedback')document.querySelector('#feedback').classList.remove('visible');
  if(action==='undo'&&undoState){selected=undoState.selected;trip=undoState.trip;undoState=null;save();if(modal.open)closeModal();render();notify('Đã khôi phục lựa chọn trước đó.');}
  if(action==='export')exportDraft();
  if(action==='ranking')openModal('Gợi ý dễ hiểu, quyết định thuộc về bạn',`<div class="dialog-body"><div class="detail-block positive"><h3>1. Đáp ứng điều bắt buộc</h3><p>Giới hạn vận động được kiểm tra trước. Thiếu bằng chứng thì chưa cho chọn, không tự coi là phù hợp.</p></div><div class="detail-block"><h3>2. Ưu tiên điều bạn muốn trong chuyến này</h3><p>Cà phê, thiên nhiên và nhịp đi thảnh thơi là bối cảnh minh họa. Sở thích không được dùng để nới điều bắt buộc.</p></div><div class="detail-block"><h3>3. Nói rõ điều phải đánh đổi</h3><p>Dậy sớm, đường dốc hay giờ mở cửa chưa rõ đều xuất hiện trước khi bạn thêm nơi đó.</p></div><p class="form-note">Bản thiết kế dùng 6 địa điểm mẫu theo thứ tự cố định để thử UI; chưa có thuật toán xếp hạng hay kết nối Place Intelligence.</p></div>`);
  if(action==='help')openModal('Bắt đầu bằng hai nơi bạn phân vân',`<div class="dialog-body"><div class="detail-block positive"><h3>So sánh trước, thêm sau</h3><p>Chọn ô “So sánh” trên hai thẻ. Xem lý do phù hợp, thời lượng, chi phí và điều cần cân nhắc ngay cạnh nhau.</p></div><div class="detail-block"><h3>Giữ lịch có khoảng thở</h3><p>Thời gian trên thẻ chỉ là tham quan. Đừng quên dành thêm thời gian đi lại, ăn và nghỉ. Bản nháp chưa chứng minh lịch khả thi.</p></div></div>`);
});
document.addEventListener('change',(event)=>{
  const id=event.target.dataset.compare;if(!id)return;
  if(event.target.checked){if(comparing.length===2){event.target.checked=false;notify('So sánh tối đa 2 nơi. Bỏ chọn một nơi để đổi.');return;}comparing.push(id);}else comparing=comparing.filter((value)=>value!==id);
  document.querySelector('#compare-slot').innerHTML=compareTray();
});
document.addEventListener('input',(event)=>{
  const tripForm=event.target.closest('#understand-form');
  if(tripForm){document.querySelector('#draft-trip-summary').textContent=`${tripForm.elements.days.value} ngày · ${tripForm.elements.people.value || '…'} người`;document.querySelector('#draft-pace').textContent=tripForm.elements.pace.value;}
  if(event.target.id!=='place-search')return;
  query=event.target.value;document.querySelector('#cards').innerHTML=cardResults();document.querySelector('#result-count').innerHTML=`<strong>${filteredPlaces().length} gợi ý mẫu</strong> · Để bạn thử chọn & so sánh`;
});
document.addEventListener('submit',(event)=>{
  if(!['understand-form','edit-trip-form'].includes(event.target.id))return;
  event.preventDefault();const values=new FormData(event.target);undoState={selected:[...selected],trip:{...trip}};
  trip={date:values.get('date'),days:Number(values.get('days')),people:Number(values.get('people')),vehicle:values.get('vehicle'),pace:values.get('pace'),note:values.get('note'),stepFree:values.has('stepFree')};
  const count=selected.length;selected=selected.filter((id)=>canSelect(places.find((p)=>p.id===id)));comparing=comparing.filter((id)=>canSelect(places.find((p)=>p.id===id)));activeDay=0;save();
  if(modal.open)closeModal();
  if(event.target.id==='understand-form')location.hash='discover';
  render();notify(`Đã cập nhật chuyến đi.${count>selected.length?` Đã bỏ ${count-selected.length} nơi chưa đáp ứng yêu cầu bắt buộc.`:''}${!storageAvailable?' Trình duyệt không lưu được, thay đổi chỉ giữ trong phiên.':''}`,true);
});
document.addEventListener('keydown',(event)=>{
  if(event.target.getAttribute('role')!=='tab')return;
  if(['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){
    event.preventDefault();activeDay=event.key==='Home'?0:event.key==='End'?trip.days-1:(activeDay+(event.key==='ArrowRight'?1:-1)+trip.days)%trip.days;render();document.querySelector(`#day-${activeDay}`).focus({preventScroll:true});
  }
});
window.addEventListener('hashchange',()=>{if(modal.open)closeModal();document.querySelector('#feedback').classList.remove('visible');render();window.scrollTo({top:0,behavior:'instant'});main.focus({preventScroll:true});});
render();

"""Compose the TripGuardian brand story video (1920x1080, 24 fps) with ffmpeg + PIL.

Shots: k1 saved clips, k2 crossroads, 3D miniature, real app demo, k3 sunrise, end card.
AI shots use a slow push (zero credits). Drop a generated clip at clips/<key>.mp4
(e.g. clips/k2-crossroads-2.mp4) and it replaces the still automatically.

Steps: python gen_keys.py (optional, new keyframes via 9router) ->
node render-mini.cjs (miniature frames) -> python build_video.py.
Web copy: scale to 1280x720, crf 25, into public/media/story.mp4.
"""
import pathlib, subprocess, sys, urllib.request
from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = pathlib.Path(__file__).parent
W, H, FPS = 1920, 1080, 24
PINE, LAKE, PAPER, DAQUY = (30, 58, 52), (47, 93, 107), (244, 240, 230), (242, 179, 27)
TMP = D / 'tmp'
TMP.mkdir(exist_ok=True)
DEMO = str(D.parents[1] / 'public' / 'media' / 'demo.mp4')
FONTS = {
    'Phudu.ttf': 'https://github.com/google/fonts/raw/main/ofl/phudu/Phudu%5Bwght%5D.ttf',
    'Geologica.ttf': 'https://github.com/google/fonts/raw/main/ofl/geologica/Geologica%5BCRSV%2CSHRP%2Cslnt%2Cwght%5D.ttf',
}


def font(name, size, weight):
    path = D / 'fonts' / name
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(FONTS[name], path)
    f = ImageFont.truetype(str(path), size)
    f.set_variation_by_axes([weight] if name.startswith('Phudu') else [weight, 0, 0, 0])
    return f


def run(args):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)


def text_layer(path, lines, *, x=140, y=None, size=104, sub=None, card=True, eyebrow=None, align='left'):
    """A full-frame RGBA overlay: uppercase Phudu lines on a soft paper card."""
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    big = font('Phudu.ttf', size, 820)
    small = font('Geologica.ttf', 44, 460)
    eb = font('Geologica.ttf', 30, 640)
    lines = [l.upper() for l in lines]
    lh = int(size * 0.98)
    widths = [d.textbbox((0, 0), l, font=big)[2] for l in lines]
    block_w = max(widths + ([d.multiline_textbbox((0, 0), sub, font=small)[2]] if sub else []))
    block_h = lh * len(lines) + (30 + d.multiline_textbbox((0, 0), sub, font=small)[3] if sub else 0) + (54 if eyebrow else 0)
    if y is None:
        y = (H - block_h) // 2
    if align == 'center':
        x = (W - block_w) // 2
    if card:
        pad = 56
        box = [x - pad, y - pad + 6, x + block_w + pad, y + block_h + pad + 14]
        shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([box[0], box[1] + 24, box[2], box[3] + 24], 34, fill=(19, 35, 31, 70))
        im = Image.alpha_composite(im, shadow.filter(ImageFilter.GaussianBlur(30)))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle(box, 34, fill=(*PAPER, 236))
    cy = y
    if eyebrow:
        d.text((x, cy), eyebrow.upper(), font=eb, fill=LAKE)
        cy += 54
    for i, l in enumerate(lines):
        lx = x + (block_w - widths[i]) // 2 if align == 'center' else x
        d.text((lx, cy), l, font=big, fill=PINE if i == 0 or len(lines) < 2 else LAKE)
        cy += lh
    if sub:
        sx = x + (block_w - d.textbbox((0, 0), sub, font=small)[2]) // 2 if align == 'center' else x
        d.multiline_text((sx, cy + 22), sub, font=small, fill=(61, 79, 74), spacing=10)
    im.save(path)
    return path


def overlay_chain(base, layers):
    """layers: [(png, start, end)] -> filter graph fading each in/out with a small rise."""
    parts, last = [], base
    for i, (_, st, en) in enumerate(layers):
        k = i + 1
        parts.append(f'[{k}:v]format=rgba,fade=in:st={st}:d=0.5:alpha=1,fade=out:st={en - 0.45}:d=0.45:alpha=1[t{k}]')
        parts.append(f"[{last}][t{k}]overlay=x=0:y='if(lt(t,{st}),26,max(0,26-(t-{st})*60))':enable='between(t,{st},{en})'[o{k}]")
        last = f'o{k}'
    return parts, last


def shot(name, src_args, base_filter, dur, layers):
    out = TMP / f'{name}.mp4'
    inputs = [*src_args]
    for png, _, _ in layers:
        inputs += ['-loop', '1', '-t', str(dur), '-i', str(png)]
    chain, last = overlay_chain('b', layers)
    graph = ';'.join([f'[0:v]{base_filter},fps={FPS},format=yuv420p,setsar=1[b]', *chain])
    run([*inputs, '-filter_complex', graph, '-map', f'[{last}]', '-t', str(dur), '-r', str(FPS),
         '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p', str(out)])
    return out


def still_or_clip(key, dur, zoom_from, zoom_to, drift=(0.5, 0.5)):
    clip = D / 'clips' / f'{key}.mp4'
    if clip.exists():
        return ['-i', str(clip)], f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},trim=0:{dur},setpts=PTS-STARTPTS'
    # Slow push on a 4K upscale (no zoompan jitter at this size).
    n = int(dur * FPS)
    z = f'{zoom_from}+({zoom_to}-{zoom_from})*on/{n}'
    fx, fy = drift
    src = str(D / 'keys' / f'{key}.jpg')
    return (['-loop', '1', '-t', str(dur), '-i', src],
            f"scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
            f"zoompan=z='{z}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={n}:s={W}x{H}:fps={FPS}")


def phone_assets():
    """Paper background with a phone shadow, and a bezel with a transparent screen."""
    sw, sh = 470, 1016
    px, py = 1250, (H - sh) // 2 + 4
    bg = Image.new('RGBA', (W, H), (*PAPER, 255))
    sh_im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh_im).rounded_rectangle([px - 14, py + 40, px + sw + 14, py + sh + 60], 60, fill=(19, 35, 31, 110))
    bg = Image.alpha_composite(bg, sh_im.filter(ImageFilter.GaussianBlur(40)))
    bg.convert('RGB').save(TMP / 'phone-bg.png')
    bez = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(bez).rounded_rectangle([px - 12, py - 12, px + sw + 12, py + sh + 12], 52, fill=(22, 34, 31, 255))
    hole = Image.new('L', (W, H), 0)
    ImageDraw.Draw(hole).rounded_rectangle([px, py, px + sw, py + sh], 40, fill=255)
    a = bez.getchannel('A')
    a.paste(0, mask=hole)
    bez.putalpha(a)
    bez.save(TMP / 'phone-bezel.png')
    return px, py, sw, sh


def main():
    shots = []
    # 1. Too many saved places.
    src, f = still_or_clip('k1-saved-2', 6, 1.0, 1.12, (0.5, 0.45))
    shots.append(shot('s1', src, f, 6, [(text_layer(TMP / 't1.png', ['Lưu cả chục clip.'], sub='Đi 3 ngày. Chưa biết chỗ nào hợp mình.'), 0.5, 6)]))
    # 2. Which one fits?
    src, f = still_or_clip('k2-crossroads-2', 6.5, 1.12, 1.0, (0.5, 0.6))
    shots.append(shot('s2', src, f, 6.5, [
        (text_layer(TMP / 't2a.png', ['Chỗ nào cũng đẹp.'], y=150, align='center'), 0.4, 3.4),
        (text_layer(TMP / 't2b.png', ['Chỗ nào hợp mình?'], y=150, align='center'), 3.3, 6.5),
    ]))
    # 3. The miniature: three settle, the thread draws.
    mini = ['-framerate', str(FPS), '-start_number', '60', '-i', str(D / 'mini' / '%04d.png')]
    shots.append(shot('s3', mini, f'scale={W}:{H}', 7, [
        (text_layer(TMP / 't3a.png', ['Chọn trước.'], card=False, eyebrow='TripGuardian', size=120), 0.4, 2.7),
        (text_layer(TMP / 't3b.png', ['Chọn trước.', 'Xếp lịch sau.'], card=False, eyebrow='TripGuardian', size=120,
                    sub='Mỗi nơi có lý do hợp,\ncái giá đánh đổi và clip thật\ncủa người đi trước.'), 2.6, 7),
    ]))
    # 4. The real app, 21-41 s of the demo at 2x.
    px, py, sw, sh = phone_assets()
    out = TMP / 's4.mp4'
    t4 = text_layer(TMP / 't4.png', ['Chỗ nào chưa chắc,', 'bạn thấy ngay.'], card=False, size=104,
                    sub='Màn hình thật của TripGuardian.', eyebrow='Kiểm tra trước khi đi')
    run(['-loop', '1', '-t', '10', '-i', str(TMP / 'phone-bg.png'),
         '-ss', '21', '-t', '20', '-i', DEMO,
         '-loop', '1', '-t', '10', '-i', str(TMP / 'phone-bezel.png'),
         '-loop', '1', '-t', '10', '-i', str(t4),
         '-filter_complex',
         f'[1:v]setpts=(PTS-STARTPTS)/2,scale={sw}:{sh},fps={FPS}[app];'
         f'[0:v][app]overlay={px}:{py}[a];[a][2:v]overlay=0:0[b];'
         f"[3:v]format=rgba,fade=in:st=0.5:d=0.5:alpha=1[t];[b][t]overlay=x=-40:y='if(lt(t,0.5),26,max(0,26-(t-0.5)*60))'[o]",
         '-map', '[o]', '-t', '10', '-r', str(FPS), '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p', str(out)])
    shots.append(out)
    # 5. The trip that went right.
    src, f = still_or_clip('k3-sunrise-2', 6.5, 1.0, 1.1, (0.35, 0.5))
    shots.append(shot('s5', src, f, 6.5, [(text_layer(TMP / 't5.png', ['Chọn đúng nơi.', 'Đi đúng gu.'], x=1040, y=170), 0.6, 6.5)]))
    # 6. End card.
    card = Image.new('RGB', (W, H), PAPER)
    d = ImageDraw.Draw(card)
    wm, head, sub, btn = font('Phudu.ttf', 54, 820), font('Phudu.ttf', 132, 820), font('Geologica.ttf', 36, 420), font('Phudu.ttf', 40, 800)
    def centered(y, s, f, fill):
        d.text(((W - d.textbbox((0, 0), s, font=f)[2]) // 2, y), s, font=f, fill=fill)
    centered(250, 'TRIPGUARDIAN', wm, PINE)
    centered(360, 'ĐÀ LẠT ĐANG CHỜ.', head, PINE)
    centered(490, 'CHỌN ĐÚNG NƠI THÔI.', head, LAKE)
    label = 'BẮT ĐẦU LÊN KẾ HOẠCH'
    bw = d.textbbox((0, 0), label, font=btn)[2] + 96
    bx = (W - bw) // 2
    d.rounded_rectangle([bx, 700, bx + bw, 790], 22, fill=PINE)
    centered(722, label, btn, (255, 255, 255))
    centered(830, 'Chuyến Đà Lạt 2–4 ngày · Không cần tài khoản', sub, (61, 79, 74))
    card.save(TMP / 'end.png')
    shots.append(shot('s6', ['-loop', '1', '-t', '4', '-i', str(TMP / 'end.png')], f'scale={W}:{H}', 4, []))

    # Crossfade everything together.
    durs = [6, 6.5, 7, 10, 6.5, 4]
    xf = 0.6
    args, graph, last, off = [], [], '0:v', 0.0
    for s in shots:
        args += ['-i', str(s)]
    for i in range(1, len(shots)):
        off += durs[i - 1] - xf
        graph.append(f'[{last}][{i}:v]xfade=transition=fade:duration={xf}:offset={off:.2f}[x{i}]')
        last = f'x{i}'
    graph.append(f'[{last}]fade=in:st=0:d=0.6,fade=out:st={off + durs[-1] - 0.8:.2f}:d=0.8[v]')
    final = D / 'TripGuardian-Story.mp4'
    run([*args, '-filter_complex', ';'.join(graph), '-map', '[v]', '-r', str(FPS), '-c:v', 'libx264', '-crf', '20',
         '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', str(final)])
    print('done', final)


if __name__ == '__main__':
    main()

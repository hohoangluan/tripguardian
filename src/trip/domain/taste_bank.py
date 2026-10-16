"""The fixed wording of every option the agent may offer on its own question (ask_user).

The agent chooses WHICH readings to offer (the writes) and writes the question that leads to them; the label and the
description of each option come from here, never from the model. A write with no entry here is not offered: a model
that is free to word an option invents ones that mean nothing ("Ngày 1") or promise what no field can hold.
"""

# soft feature=value -> (label, description)
SOFT = {
    "scenic_view=present": ("Có view đẹp", "Mình ưu tiên nơi nhìn ra đồi, núi, rừng thông hay hồ."),
    "cloud_hunting=present": ("Săn mây", "Mình ưu tiên nơi hay có biển mây; có thấy hay không còn tùy thời tiết."),
    "sunset_view=present": ("Ngắm hoàng hôn, bình minh", "Mình ưu tiên nơi ngắm được lúc trời lên hoặc xuống nắng."),
    "photo_spot=present": ("Chụp ảnh đẹp", "Mình ưu tiên nơi nhiều góc chụp."),
    "nature=present": ("Thiên nhiên", "Mình ưu tiên rừng, thác, suối và không khí trong lành."),
    "flower_garden=present": ("Vườn hoa, đồi hoa", "Mình ưu tiên nơi có vườn hoa hoặc mùa hoa."),
    "heritage_architecture=present": ("Kiến trúc, di tích", "Mình ưu tiên nơi có kiến trúc cổ, di tích, văn hóa."),
    "cozy_decor=present": ("Không gian ấm cúng", "Mình ưu tiên nơi decor có gu, ngồi dễ chịu."),
    "laptop_friendly=present": ("Ngồi làm việc được", "Mình ưu tiên nơi có bàn, ổ cắm và wifi dùng được."),
    "long_stay_chill=present": ("Ngồi lâu, thư giãn", "Mình ưu tiên nơi ngồi lâu được, không bị giục."),
    "live_music=present": ("Nhạc sống", "Mình ưu tiên nơi có người biểu diễn trực tiếp."),
    "adventure_activity=present": ("Trò mạo hiểm", "Mình ưu tiên nơi có zipline, máng trượt, canyoning."),
    "hiking=present": ("Đi bộ đường dài, leo núi", "Mình ưu tiên nơi có đường trekking."),
    "animals=present": ("Có thú để xem, chơi cùng", "Mình ưu tiên nơi có mèo, cừu, ngựa."),
    "local_specialty_food=present": ("Món đặc sản", "Mình ưu tiên nơi bán món địa phương."),
    "pick_your_own=present": ("Tự hái dâu, rau, trái cây", "Mình ưu tiên vườn cho khách tự hái."),
    "hands_on_workshop=present": ("Workshop tự tay làm", "Mình ưu tiên nơi có làm bánh, socola, pha cà phê."),
    "camping=present": ("Cắm trại, glamping", "Mình ưu tiên nơi ngủ lều hoặc glamping."),
    "tasting_available=present": ("Được nếm thử", "Mình ưu tiên nơi cho nếm trà, cà phê, rượu vang, mứt."),
    "kids_play_area=present": ("Có khu chơi cho trẻ", "Mình ưu tiên nơi có sân chơi hoặc đồ chơi cho trẻ."),
    "outdoor_seating=present": ("Ngồi ngoài trời", "Mình ưu tiên nơi có bàn ngoài sân, ban công, sân vườn."),
    "spacious=present": ("Không gian rộng, thoáng", "Mình ưu tiên nơi rộng và thoáng."),
    "setting=indoor": ("Trong nhà", "Mình ưu tiên nơi ngồi hoặc tham quan trong nhà."),
    "setting=outdoor": ("Ngoài trời", "Mình ưu tiên nơi ngoài trời, sân vườn, không gian mở."),
    "weather_exposed=sheltered": ("Có mái che", "Mình ưu tiên nơi mưa vẫn đi được."),
    "noise=quiet": ("Yên tĩnh", "Mình ưu tiên nơi ít ồn."),
    "crowd=low": ("Vắng, ít người", "Mình ưu tiên nơi ít khách, hoặc giờ vắng."),
    "drink_quality=good": ("Đồ uống ngon", "Mình ưu tiên nơi được khen đồ uống."),
    "food_quality=good": ("Đồ ăn ngon", "Mình ưu tiên nơi được khen đồ ăn."),
    "cultural_show=present": ("Biểu diễn, giao lưu văn hóa", "Mình ưu tiên nơi có cồng chiêng, văn hóa bản địa."),
}

# the other fields an agent option may write: value -> (label, description)
PACE = {"slow": ("Thong thả, ít nơi", "Mỗi ngày ít nơi, có thời gian nghỉ."),
        "normal": ("Vừa phải", "Số nơi mỗi ngày vừa sức."),
        "packed": ("Đi được nhiều", "Mỗi ngày ghé nhiều nơi.")}
CROWD = {"avoid": ("Tránh chỗ đông", "Mình tránh hoặc xếp vào giờ vắng hơn."),
         "ok_if_worth": ("Chấp nhận nếu đáng", "Đông vẫn đi nếu nơi đó đáng."),
         "fine": ("Không ngại đông", "Mình không tránh nơi đông.")}
NOVELTY = {"familiar": ("Theo gu quen", "Mình giữ những kiểu bạn đã thích."),
           "new": ("Thử cái mới", "Mình bớt những nơi bạn đã đi."),
           "mix": ("Trộn cả hai", "Có chỗ quen, có chỗ mới.")}
GROUPS = {"nature": ("Thiên nhiên", "Mình ưu tiên các nơi thiên nhiên."),
          "sights": ("Điểm tham quan", "Mình ưu tiên các điểm tham quan."),
          "chill": ("Chill, cà phê", "Mình ưu tiên quán cà phê và chỗ thư giãn."),
          "meal": ("Ăn uống", "Mình ưu tiên các quán ăn.")}


def fixed(writes) -> tuple[str, str] | None:
    """The app's label and description for one option, or None when its writes have no fixed wording (not offered).
    Exactly one write: a label for two writes at once would say less than the option does."""
    from .questions import PURPOSE

    if len(writes) != 1:
        return None
    w = writes[0]
    field, value = w["field"], str(w["value"])
    if field == "soft":
        key, _, weight = value.rpartition(":")
        return SOFT.get(key if weight in {"love", "avoid", "off"} else value)
    if field == "purpose":
        return (PURPOSE[value][0], "Mình chọn nơi hợp với mục đích này.") if value in PURPOSE else None
    table = {"pace": PACE, "crowd_tolerance": CROWD, "novelty": NOVELTY, "liked_groups": GROUPS}.get(field)
    return table.get(value) if table else None

"""TikTok in independent phases, each reading only the previous phase's files:

search.py   query -> data/tiktok/search/<city>/<query>.jsonl
listing.py  search files -> one deduplicated list data/tiktok/list/<city>.json
filter.py   list captions -> data/tiktok/filter/<video_id>.json (about travel in the city: yes / no / unsure)
crawl.py    kept videos -> data/tiktok/videos/<video_id>/{info,video}.json + video.mp4

Then per place of data/gmaps/list/<city>.json, three more phases:

place_search.py  place name -> top videos data/tiktok/place_search/<city>/<fid_dir>.json
place_filter.py  captions -> data/tiktok/place_filter/<fid_dir>.json (about this place: yes / no / unsure)
place_crawl.py   "yes" videos -> data/tiktok/videos/<video_id>/ (same files as crawl.py)
asr.py           every saved video's speech (VAD + ASR) -> video.json transcript
asr_check.py     transcript + frames -> kept / fixed / dropped per segment (Extractor, code-guarded) -> video.json
asr_alt.py       segments asr_check could not trust -> second ASR model (alt_text), then asr_check again
place_verify.py  caption + transcript + 4 frames -> is the video about its matched place -> video.json places
"""

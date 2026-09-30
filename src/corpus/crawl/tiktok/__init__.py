"""TikTok in four independent phases, each reading only the previous phase's files:

search.py   query -> data/tiktok/search/<city>/<query>.jsonl
listing.py  search files -> one deduplicated list data/tiktok/list/<city>.json
filter.py   list captions -> data/tiktok/filter/<video_id>.json (about travel in the city: yes / no / unsure)
crawl.py    kept videos -> data/tiktok/videos/<video_id>/{info,video}.json + video.mp4
"""

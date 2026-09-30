"""Google Maps in six independent phases, each reading only earlier phases' files:

search.py   category x map tile -> data/gmaps/search/<city>/<category>.jsonl
filter.py   searched places' name + category -> data/gmaps/filter/<fid_dir>.json (for visitors: yes / no / unsure)
counts.py   kept places whose cards hid the review count -> data/gmaps/counts/<city>.json (signed-in place page)
listing.py  search files + kept places -> one deduplicated, in-area, ranked list data/gmaps/list/<city>.json
crawl.py    list -> data/gmaps/places/<fid_dir>/{reviews,place}.json
qc.py       places -> data/gmaps/qc/ (rule checks + Gemma, Judge role)
"""

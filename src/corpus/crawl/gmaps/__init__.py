"""Google Maps in eight independent phases, each reading only earlier phases' files:

search.py   category x map tile -> data/gmaps/search/<city>/<category>.jsonl
filter.py   searched places' name + category -> data/gmaps/filter/<fid_dir>.json (for visitors: yes / no / unsure)
counts.py   kept places whose cards hid the review count -> data/gmaps/counts/<city>.json (signed-in place page)
listing.py  search files + kept places -> one deduplicated, in-area, ranked list data/gmaps/list/<city>.json
crawl.py    list -> data/gmaps/places/<fid_dir>/{reviews,place}.json
relevant.py places with more reviews than crawl kept -> data/gmaps/places/<fid_dir>/reviews_relevant.json
extremes.py places with >= 30 reviews -> data/gmaps/places/<fid_dir>/reviews_extremes.json (lowest + highest rated)
keywords.py places by category group -> data/gmaps/places/<fid_dir>/reviews_keywords.json (Maps review search)
visit.py    places with popular times -> data/gmaps/places/<fid_dir>/visit.json ("people typically spend ... here")
qc.py       places -> data/gmaps/qc/ (rule checks + Gemma, Judge role)
"""

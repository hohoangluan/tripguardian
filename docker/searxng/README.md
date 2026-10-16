# SearXNG cho `web_search` của Trip agent

Chạy một lần (container tự khởi động lại; cache trong repo):

```sh
docker run -d --name tripguardian-searxng --restart unless-stopped \
  -p 127.0.0.1:8888:8080 -e SEARXNG_SECRET="$(openssl rand -hex 32)" \
  -v "$PWD/docker/searxng:/etc/searxng" -v "$PWD/.cache/searxng:/var/cache/searxng" \
  searxng/searxng:latest
```

Kiểm tra: `curl 'http://127.0.0.1:8888/search?q=retro&format=json'`. Địa chỉ nằm ở `config/trip.yaml` (`web_base_url`); để trống thì agent không có tool web.
